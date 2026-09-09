import argparse
import csv
import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import Path
from .data import download, read_source, reconcile
from .db import connect, execute_file, rows

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger(__name__)


def checks(db):
    queries = {
        "no_orphan_events": "SELECT COUNT(*) n FROM fact_purchase p LEFT JOIN dim_customer c USING(user_id) WHERE c.user_id IS NULL",
        "no_pre_acquisition_events": "SELECT COUNT(*) n FROM fact_purchase p JOIN dim_customer c USING(user_id) WHERE p.purchase_date<c.first_purchase_date",
        "rates_in_range": "SELECT COUNT(*) n FROM mart_retention WHERE platform_retention NOT BETWEEN 0 AND 1 OR same_line_retention NOT BETWEEN 0 AND 1",
        "censored_cells_are_null": "SELECT COUNT(*) n FROM mart_retention WHERE eligible=0 AND (platform_retention IS NOT NULL OR same_line_retention IS NOT NULL)",
        "full_month_zero_equals_one": "SELECT COUNT(*) n FROM mart_retention WHERE eligible=1 AND month_number=0 AND (platform_retention<>1 OR same_line_retention<>1)",
        "same_line_subset": "SELECT COUNT(*) n FROM mart_retention WHERE same_line_active_users>platform_active_users",
        "repurchase_in_range": "SELECT COUNT(*) n FROM mart_repurchase WHERE repeat_users_30d>eligible_users OR cross_line_users_30d>repeat_users_30d",
    }
    result = {name: int(rows(db, query)[0]["n"]) for name, query in queries.items()}
    if any(result.values()):
        raise ValueError(f"Quality checks failed: {result}")
    return result


def export(db, out, summary):
    out.mkdir(parents=True, exist_ok=True)
    for table in ("mart_retention", "mart_repurchase", "mart_monthly"):
        data = rows(db, f"SELECT * FROM {table} ORDER BY 1,2")
        path = out / (table + ".csv")
        if data:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(data[0]))
                writer.writeheader()
                writer.writerows(data)
    (out / "run_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )


def run(data_dir, output_dir, observation_start, as_of, sql_dir=ROOT / "sql"):
    if observation_start > as_of:
        raise ValueError("observation_start must not be after as_of")
    first, raw_first = read_source(data_dir / "first_purchases.csv", first=True)
    purchases, raw_purchases = read_source(data_dir / "purchases.csv")
    if min(p.purchase_date for p in purchases) < observation_start:
        raise ValueError("Purchases precede declared observation_start")
    anchors, events, rejected, stats = reconcile(first, purchases, as_of)
    hashes = {
        name: hashlib.sha256((data_dir / name).read_bytes()).hexdigest()
        for name in ("first_purchases.csv", "purchases.csv")
    }
    run_id = str(uuid.uuid4())
    db = connect()
    locked = False
    committed = False
    try:
        locked = (
            rows(db, "SELECT GET_LOCK(CONCAT(DATABASE(), ':pipeline'),0) acquired")[0][
                "acquired"
            ]
            == 1
        )
        if not locked:
            raise RuntimeError("Another pipeline is running")
        execute_file(db, sql_dir / "01_schema.sql")
        with db.cursor() as c:
            c.execute(
                "INSERT INTO pipeline_runs(run_id,status,source_hashes,observation_start,as_of_date) VALUES(%s,'running',%s,%s,%s)",
                (run_id, json.dumps(hashes), observation_start, as_of),
            )
        db.commit()
        # DELETE (not TRUNCATE) keeps the snapshot replacement transactional.
        with db.cursor() as c:
            for table in (
                "mart_retention",
                "mart_repurchase",
                "mart_monthly",
                "fact_purchase",
                "dim_customer",
                "raw_records",
                "quarantine_purchase",
                "analysis_config",
            ):
                c.execute(f"DELETE FROM {table}")
            c.execute(
                "INSERT INTO analysis_config VALUES(1,%s,%s,%s)",
                (observation_start, as_of, run_id),
            )
            for source, values in (
                ("first_purchases", raw_first),
                ("purchases", raw_purchases),
            ):
                c.executemany(
                    "INSERT INTO raw_records VALUES(%s,%s,%s,%s)",
                    [(source, n, payload, run_id) for n, payload in values],
                )
            c.executemany(
                "INSERT INTO dim_customer VALUES(%s,%s,%s,%s,%s)",
                [
                    (
                        p.user_id,
                        p.purchase_id,
                        p.purchase_date,
                        p.product_line,
                        p.purchase_date.replace(day=1),
                    )
                    for p in anchors.values()
                ],
            )
            c.executemany(
                "INSERT INTO fact_purchase VALUES(%s,%s,%s,%s,%s)",
                [
                    (
                        p.purchase_id,
                        p.user_id,
                        p.venue_id,
                        p.product_line,
                        p.purchase_date,
                    )
                    for p in events
                ],
            )
            if rejected:
                c.executemany(
                    "INSERT INTO quarantine_purchase VALUES(%s,%s,%s,%s,%s)",
                    [
                        (
                            p.purchase_id,
                            p.user_id,
                            p.purchase_date,
                            reason,
                            json.dumps(asdict(p), default=str),
                        )
                        for p, reason in rejected
                    ],
                )
        execute_file(db, sql_dir / "02_marts.sql")
        summary = {
            "run_id": run_id,
            "source_hashes": hashes,
            "observation_start": str(observation_start),
            "as_of": str(as_of),
            **stats,
            "quality_checks": checks(db),
            "repurchase": rows(
                db, "SELECT * FROM mart_repurchase ORDER BY acquisition_line"
            ),
            "database_version": rows(db, "SELECT VERSION() version")[0]["version"],
        }
        with db.cursor() as c:
            c.execute(
                "UPDATE pipeline_runs SET status='success',completed_at=CURRENT_TIMESTAMP(6),summary=%s WHERE run_id=%s",
                (json.dumps(summary, default=str), run_id),
            )
        db.commit()
        committed = True
        export(db, output_dir, summary)
        LOG.info(
            "Published snapshot: users=%s clean_events=%s quarantine=%s",
            len(anchors),
            len(events),
            len(rejected),
        )
        return summary
    except Exception as exc:
        db.rollback()
        if committed:
            LOG.error(
                "MySQL snapshot committed, but export failed; rerun to regenerate exports"
            )
            raise
        try:
            with db.cursor() as c:
                c.execute(
                    "UPDATE pipeline_runs SET status='failed',completed_at=CURRENT_TIMESTAMP(6),summary=%s WHERE run_id=%s",
                    (json.dumps({"error_type": type(exc).__name__}), run_id),
                )
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        if locked:
            rows(db, "SELECT RELEASE_LOCK(CONCAT(DATABASE(), ':pipeline'))")
        db.close()


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(
        description="Reproducible MySQL retention analytics"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    r.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    r.add_argument("--sql-dir", type=Path, default=Path("sql"))
    r.add_argument("--observation-start", type=date.fromisoformat, required=True)
    r.add_argument("--as-of", type=date.fromisoformat, required=True)
    r.add_argument("--download", action="store_true")
    sub.add_parser("check")
    args = parser.parse_args()
    if args.command == "run":
        if args.download:
            download(args.data_dir)
        result = run(
            args.data_dir,
            args.output_dir,
            args.observation_start,
            args.as_of,
            args.sql_dir,
        )
    else:
        with connect() as db:
            result = checks(db)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
