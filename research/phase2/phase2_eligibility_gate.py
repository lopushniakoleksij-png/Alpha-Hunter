"""Offline, fail-closed validation of Phase 2 historical instrument registry.

Validates *evidence classification*, not exchange history itself.
No network, DB access, orders, or repository changes.
"""
import csv
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REGISTER = Path(__file__).with_name("HISTORICAL_ELIGIBILITY_20261108.csv")
WINDOW_START = datetime(2026, 11, 8, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 11, 9, tzinfo=timezone.utc)

def official(url: str) -> bool:
    p = urlparse(url or "")
    return p.scheme == "https" and p.hostname == "www.bitget.com" and p.path.startswith("/support/articles/")

def _date(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.utcoffset() is None or dt.utcoffset().total_seconds() != 0:
        raise ValueError("date must be UTC")
    return dt

def validate_row(row: dict) -> None:
    symbol = row["symbol"]
    if not symbol or not symbol.endswith("USDT"):
        raise ValueError("invalid symbol")
    if row["product_type"] != "USDT-FUTURES":
        raise ValueError("wrong product")
    if _date(row["target_window_start_utc"]) != WINDOW_START or _date(row["target_window_end_utc"]) != WINDOW_END:
        raise ValueError("wrong target window")
    status = row["window_eligibility"]
    if status not in {"VERIFIED", "UNKNOWN", "EXCLUDED"}:
        raise ValueError("invalid status")
    if row["listing_event_evidence"] not in {"VERIFIED", "UNKNOWN"}:
        raise ValueError("invalid listing evidence status")
    if row["backfill_allowed"] != "NO":
        raise ValueError("broad backfill remains NO-GO")
    listing_source = row.get("listing_event_source_url", "")
    listing_day = row.get("listing_event_date_as_published", "")
    if row["listing_event_evidence"] == "VERIFIED":
        if not official(listing_source) or not listing_day:
            raise ValueError("verified listing event must have separate official dated listing source")
        try:
            announced = date.fromisoformat(listing_day)
        except ValueError as exc:
            raise ValueError("invalid listing announcement date") from exc
        if announced > WINDOW_START.date():
            raise ValueError("future listing announcement cannot support this period")
    elif listing_source or listing_day:
        raise ValueError("listing evidence supplied but not verified")
    if status == "VERIFIED":
        # Intentionally no auto-certification path; future process needs independent
        # historical availability, suspension/delisting audit, and human approval.
        raise ValueError("window VERIFIED requires independent certification and explicit gate revision")
    if status == "EXCLUDED":
        if row["current_catalogue"] != "NO":
            raise ValueError("exclusion conflicts with current listing; investigate")
        if row["documented_event_type"] != "DELISTED_FUTURES" or not official(row["dated_official_source_url"]):
            raise ValueError("exclusion needs official dated futures delisting evidence")
        try:
            effective = _date(row["documented_effective_utc"])
        except (TypeError, ValueError) as e:
            raise ValueError("invalid exclusion effective date") from e
        if effective > WINDOW_START:
            raise ValueError("exclusion is not effective before window")
    if row["current_catalogue"] not in {"YES", "NO"}:
        raise ValueError("invalid catalogue presence")
    if row["catalogue_request_time_ms"] and int(row["catalogue_request_time_ms"]) < 0:
        raise ValueError("invalid snapshot timestamp")

def validate_registry(path: Path = REGISTER) -> Counter:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"symbol", "product_type", "target_window_start_utc",
                    "target_window_end_utc", "current_catalogue",
                    "window_eligibility", "listing_event_evidence",
                    "documented_event_type", "documented_effective_utc",
                    "dated_official_source_url", "backfill_allowed",
                    "catalogue_request_time_ms", "listing_event_source_url",
                    "listing_event_date_as_published"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("missing required schema columns")
        rows = list(reader)
    seen = set()
    counts = Counter()
    for row in rows:
        validate_row(row)
        if row["symbol"] in seen:
            raise ValueError("duplicate symbol")
        seen.add(row["symbol"])
        counts[row["window_eligibility"]] += 1
    if not rows:
        raise ValueError("empty register")
    return counts

if __name__ == "__main__":
    result = validate_registry()
    print("ELIGIBILITY REGISTER STRUCTURAL AUDIT: PASS")
    print("Window statuses:", dict(sorted(result.items())))
    print("ALL HISTORICAL BACKFILL AUTHORISATION: NO-GO")
