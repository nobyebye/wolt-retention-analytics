"""Compare identical result sets with and without the composite user/date index."""

import json
import statistics
import time
from pathlib import Path
from wolt_analytics.db import connect, rows

with connect() as db:
    user = rows(
        db,
        "SELECT user_id,COUNT(*) n FROM fact_purchase GROUP BY user_id ORDER BY n DESC,user_id LIMIT 1",
    )[0]["user_id"]
    predicates = " WHERE user_id=%s AND purchase_date>='2020-05-01' AND purchase_date<'2020-11-01'"
    query = "SELECT COUNT(*) n FROM fact_purchase"
    variants = {
        "without_secondary_indexes": query
        + " IGNORE INDEX(idx_user_date_line,idx_date_line)"
        + predicates,
        "with_user_date_index": query + " FORCE INDEX(idx_user_date_line)" + predicates,
    }
    result = {
        "database_version": rows(db, "SELECT VERSION() v")[0]["v"],
        "fact_rows": rows(db, "SELECT COUNT(*) n FROM fact_purchase")[0]["n"],
        "method": "1 warm-up, 7 timed runs per variant; client wall time; same user/date predicate; local warm-cache microbenchmark, not production SLA",
        "variants": {},
    }
    counts = []
    for name, sql in variants.items():
        counts.append(rows(db, sql, (user,))[0]["n"])
        durations = []
        for _ in range(7):
            start = time.perf_counter()
            rows(db, sql, (user,))
            durations.append((time.perf_counter() - start) * 1000)
        plan = rows(db, "EXPLAIN ANALYZE " + sql, (user,))
        result["variants"][name] = {
            "median_ms": round(statistics.median(durations), 3),
            "runs_ms": [round(x, 3) for x in durations],
            "plan": plan,
        }
    assert len(set(counts)) == 1, "Benchmark queries returned different results"
    result["identical_result_count"] = counts[0]
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/benchmark.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
