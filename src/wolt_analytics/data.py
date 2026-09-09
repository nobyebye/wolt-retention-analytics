"""Source contract, deterministic parsing, reconciliation and provenance."""

import csv
import hashlib
import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

SOURCE = "https://raw.githubusercontent.com/woltapp/analytics-summer-intern-2022/main/"
LINES = {"Restaurant", "Retail store"}


@dataclass(frozen=True)
class Purchase:
    purchase_id: str
    user_id: str
    venue_id: str
    product_line: str
    purchase_date: date


def download(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source": SOURCE,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    for name in ("first_purchases.csv", "purchases.csv"):
        with urllib.request.urlopen(SOURCE + name, timeout=60) as response:
            payload = response.read()
        temporary = directory / (name + ".tmp")
        temporary.write_bytes(payload)
        read_source(temporary, first=name.startswith("first_"))
        temporary.replace(directory / name)
        manifest["files"][name] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def read_source(path: Path, first=False):
    date_column = "first_purchase_date" if first else "purchase_date"
    result, raw = [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = {date_column, "user_id", "purchase_id", "venue_id", "product_line"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError(
                f"Unexpected CSV columns in {path.name}: {reader.fieldnames}"
            )
        for number, row in enumerate(reader, 2):
            if any(not isinstance(v, str) or not v.strip() for v in row.values()):
                raise ValueError(f"Missing field at {path.name}:{number}")
            if any(len(row[k]) > 64 for k in ("purchase_id", "user_id", "venue_id")):
                raise ValueError(f"Oversize identifier at {path.name}:{number}")
            if row["product_line"] not in LINES:
                raise ValueError(f"Unknown product line at {path.name}:{number}")
            parsed = datetime.strptime(row[date_column], "%d.%m.%y").date()
            result.append(
                Purchase(
                    row["purchase_id"],
                    row["user_id"],
                    row["venue_id"],
                    row["product_line"],
                    parsed,
                )
            )
            raw.append((number, json.dumps(row, ensure_ascii=False)))
    if not result:
        raise ValueError(f"Empty source: {path.name}")
    return result, raw


def reconcile(first, purchases, as_of):
    """First-purchase records anchor cohorts; unknown users never enter denominators."""
    anchors, events, quarantine = {}, {}, []
    exact_duplicates = 0
    for row in first:
        if row.user_id in anchors and anchors[row.user_id] != row:
            raise ValueError(f"Conflicting first purchase for user {row.user_id}")
        if row.purchase_date > as_of:
            raise ValueError("First purchase falls after the declared as-of date")
        anchors[row.user_id] = row
        if row.purchase_id in events and events[row.purchase_id] != row:
            raise ValueError("Conflicting purchase ID in first-purchase source")
        if row.purchase_id in events:
            exact_duplicates += 1
        events[row.purchase_id] = row
    unknown_ids = set()
    seen_purchases = {}
    for row in purchases:
        if row.purchase_date > as_of:
            raise ValueError("Purchase falls after the declared as-of date")
        if row.purchase_id in seen_purchases:
            if seen_purchases[row.purchase_id] != row:
                raise ValueError("Conflicting purchase ID in purchase source")
            exact_duplicates += 1
            continue
        seen_purchases[row.purchase_id] = row
        if row.purchase_id in events:
            if events[row.purchase_id] != row:
                raise ValueError("Conflicting purchase ID across sources")
            exact_duplicates += 1
            continue
        if row.user_id not in anchors:
            unknown_ids.add(row.user_id)
            quarantine.append((row, "unknown_first_purchase_user"))
        elif row.purchase_date < anchors[row.user_id].purchase_date:
            quarantine.append((row, "purchase_before_first_purchase"))
        else:
            events[row.purchase_id] = row
    stats = {
        "first_source_rows": len(first),
        "purchase_source_rows": len(purchases),
        "cohort_users": len(anchors),
        "clean_events": len(events),
        "quarantined_events": len(quarantine),
        "unknown_users": len(unknown_ids),
        "exact_duplicates": exact_duplicates,
        "overlapping_source_purchase_ids": len(
            {p.purchase_id for p in first} & {p.purchase_id for p in purchases}
        ),
    }
    return anchors, list(events.values()), quarantine, stats
