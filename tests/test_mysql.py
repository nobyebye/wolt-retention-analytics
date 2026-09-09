"""Hand-calculated business cases against an actual disposable MySQL schema."""

import csv
import os
from datetime import date
from pathlib import Path
import pytest
from wolt_analytics.cli import run
from wolt_analytics.db import connect, rows

pytestmark = pytest.mark.integration


@pytest.fixture
def fixture_data(tmp_path):
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_TESTS=1 and MYSQL_DATABASE=wolt_test")
    if not os.getenv("MYSQL_DATABASE", "").endswith("_test"):
        pytest.fail("Integration tests only run in a database ending _test")
    first = [
        ("01.05.20", "u1", "f1", "v", "Restaurant"),
        ("02.05.20", "u2", "f2", "v", "Restaurant"),
        ("01.05.20", "u3", "f3", "v", "Retail store"),
        ("20.06.20", "u4", "f4", "v", "Restaurant"),
    ]
    purchases = [
        ("01.05.20", "u1", "f1", "v", "Restaurant"),
        ("10.05.20", "u1", "p1", "v", "Retail store"),
        ("01.06.20", "u1", "p2", "v", "Restaurant"),
        ("02.06.20", "u3", "p3", "v", "Restaurant"),
        ("01.06.20", "unknown", "p4", "v", "Restaurant"),
    ]
    for name, column, data in [
        ("first_purchases.csv", "first_purchase_date", first),
        ("purchases.csv", "purchase_date", purchases),
    ]:
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([column, "user_id", "purchase_id", "venue_id", "product_line"])
            w.writerows(data)
    return tmp_path


def execute_fixture(
    directory, end=date(2020, 6, 30), start=date(2020, 5, 1), sql_dir=None
):
    return run(
        directory,
        directory / "out",
        start,
        end,
        sql_dir or Path(__file__).resolve().parents[1] / "sql",
    )


def test_retention_and_repurchase_business_cases(fixture_data):
    summary = execute_fixture(fixture_data)
    assert summary["quarantined_events"] == 1
    with connect() as db:
        restaurant = rows(
            db,
            "SELECT * FROM mart_retention WHERE cohort_month='2020-05-01' AND acquisition_line='Restaurant' AND month_number=1",
        )[0]
        assert float(restaurant["platform_retention"]) == 0.5
        retail = rows(
            db,
            "SELECT * FROM mart_retention WHERE cohort_month='2020-05-01' AND acquisition_line='Retail store' AND month_number=1",
        )[0]
        assert float(retail["platform_retention"]) == 1
        assert float(retail["same_line_retention"]) == 0
        repeat = rows(
            db, "SELECT * FROM mart_repurchase WHERE acquisition_line='Restaurant'"
        )[0]
        assert repeat["eligible_users"] == 2  # June 20 acquisition is censored.
        assert repeat["repeat_users_30d"] == 1
        assert repeat["cross_line_users_30d"] == 1


def test_partial_calendar_month_is_null(fixture_data):
    execute_fixture(fixture_data, end=date(2020, 6, 25))
    with connect() as db:
        records = rows(
            db, "SELECT * FROM mart_retention WHERE activity_month='2020-06-01'"
        )
        assert records and all(r["platform_retention"] is None for r in records)


def test_full_month_with_no_returns_is_zero(fixture_data):
    execute_fixture(fixture_data, end=date(2020, 7, 31))
    with connect() as db:
        records = rows(
            db, "SELECT * FROM mart_retention WHERE activity_month='2020-07-01'"
        )
        assert records and all(r["platform_retention"] == 0 for r in records)


def test_rerun_does_not_duplicate_and_failure_preserves_snapshot(fixture_data):
    first = execute_fixture(fixture_data)
    second = execute_fixture(fixture_data)
    assert first["clean_events"] == second["clean_events"]
    with connect() as db:
        baseline = rows(db, "SELECT * FROM fact_purchase ORDER BY purchase_id")
    broken = fixture_data / "broken_sql"
    broken.mkdir()
    source = Path(__file__).resolve().parents[1] / "sql"
    (broken / "01_schema.sql").write_text(
        (source / "01_schema.sql").read_text(), encoding="utf-8"
    )
    (broken / "02_marts.sql").write_text(
        "SELECT * FROM deliberately_missing_table;", encoding="utf-8"
    )
    with pytest.raises(Exception):
        execute_fixture(fixture_data, sql_dir=broken)
    with connect() as db:
        assert rows(db, "SELECT * FROM fact_purchase ORDER BY purchase_id") == baseline
        assert (
            rows(db, "SELECT COUNT(*) n FROM pipeline_runs WHERE status='failed'")[0][
                "n"
            ]
            >= 1
        )
