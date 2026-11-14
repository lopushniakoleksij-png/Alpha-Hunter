"""Fail-closed offline QA for dated Bitget futures event/scan reconstruction.

Historical evidence inspection only. NO network, database, orders, deployments,
or backfill authorisation. Official announcement timestamps are *scheduled*
events; they do not prove an uninterrupted historical trading interval.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).parent
INTERVALS = HERE / "HISTORICAL_MISSING_CONTRACT_INTERVALS_V1.csv"
ELIGIBILITY = HERE / "HISTORICAL_ELIGIBILITY_20261108.csv"
TARGET = datetime(2026, 11, 8, tzinfo=timezone.utc)

def date_utc(value):
    if not value:
        return None
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.utcoffset() is None or d.utcoffset().total_seconds() != 0:
        raise ValueError("timestamp must be UTC")
    return d

def official(url):
    p = urlparse(url)
    return p.scheme == "https" and p.hostname == "www.bitget.com" and p.path.startswith("/support/articles/")

def validate_row(row, eligibility):
    s = row["symbol"]
    if not s or not s.endswith("USDT") or row["product_type"] != "USDT-FUTURES":
        raise ValueError("not USDT-futures")
    if row["current_catalogue_asof_20261114"] != "ABSENT":
        raise ValueError("currently listed contract incorrectly classified absent")
    if not official(row["official_delisting_source"]):
        raise ValueError("missing official futures delisting source")
    start = date_utc(row["new_positions_block_scheduled_utc"])
    ended = date_utc(row["futures_termination_scheduled_utc"])
    if not start or not ended or not start < ended < TARGET:
        raise ValueError("invalid new-position block or delisting event order")
    if row["listing_announcement_date_as_published"] and not official(row["official_listing_source"]):
        raise ValueError("listing date missing official source")
    if row["official_listing_source"] and not row["listing_announcement_date_as_published"]:
        raise ValueError("listing source without dated announcement")
    launched = date_utc(row["listing_effective_at_utc_if_exact"])
    if launched and (launched >= start or not row["official_listing_source"]):
        raise ValueError("listing timestamp unsupported or after delisting restrictions")
    first = date_utc(row["scanner_snapshot_first_seen_utc"])
    last = date_utc(row["scanner_snapshot_last_seen_utc"])
    snaps = int(row["scanner_snapshots"])
    signals = int(row["scanner_signals"])
    close_only = int(row["signals_during_close_only_window"])
    post = int(row["signals_after_scheduled_termination"])
    post_snap = int(row["snapshots_after_scheduled_termination"])
    permitted = int(row["post_termination_signals_with_trade_permission_true"])
    if min(snaps,signals,close_only,post,post_snap,permitted) < 0 or signals < close_only+post:
        raise ValueError("invalid scanner counts")
    if (snaps == 0 and (first or last)) or (snaps > 0 and (not first or not last or first > last)):
        raise ValueError("scanner observation date range malformed")
    if post > 0 and not row["post_termination_signal_states"]:
        raise ValueError("post-termination signal states missing")
    expected_flag = ("POST_TERMINATION_SIGNAL" if post else
                     "POST_TERMINATION_SNAPSHOT" if post_snap else
                     "CLOSE_ONLY_SIGNAL" if close_only else "NONE")
    if row["review_flag"] != expected_flag:
        raise ValueError("review flag must reflect observed evidence")
    if permitted:
        raise ValueError("post-termination trading permission regression requires immediate investigation")
    if row["relisting_evidence"] != "UNKNOWN" or row["continuous_eligibility_certified"] != "NO":
        raise ValueError("unverified relisting or full trading eligibility assertion")
    if row["nov08_status"] != "EXCLUDED_PROVISIONAL":
        raise ValueError("unexpected target-window classification")
    r = eligibility.get(s)
    if not r or r["window_eligibility"] != "EXCLUDED" or r["backfill_allowed"] != "NO":
        raise ValueError("interval not linked to sealed eligibility register")
    if r["dated_official_source_url"] != row["official_delisting_source"] or date_utc(r["documented_effective_utc"]) != ended:
        raise ValueError("official event conflicts with eligibility register")

def validate_intervals(interval_path=INTERVALS, eligibility_path=ELIGIBILITY):
    with eligibility_path.open(newline="", encoding="utf-8") as f:
        full = {r["symbol"]:r for r in csv.DictReader(f)}
    with interval_path.open(newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        rows=list(reader)
    if len(rows)<15 or len({r["symbol"] for r in rows})!=len(rows):
        raise ValueError("incomplete/duplicate historical candidate ledger")
    for row in rows:
        validate_row(row,full)
    return {
        "contracts":len(rows),
        "with_scanner_evidence":sum(int(r["scanner_snapshots"])>0 for r in rows),
        "close_only_signals":sum(int(r["signals_during_close_only_window"]) for r in rows),
        "post_termination_signals":sum(int(r["signals_after_scheduled_termination"]) for r in rows),
        "post_termination_snapshots":sum(int(r["snapshots_after_scheduled_termination"]) for r in rows),
        "post_termination_permission_true":sum(int(r["post_termination_signals_with_trade_permission_true"]) for r in rows)
    }

if __name__=="__main__":
    print("HISTORICAL EVENT INTERVAL QA:",validate_intervals())
    print("RELlSTING/CONTINUOUS ELIGIBILITY CERTIFICATION: NOT ESTABLISHED")
    print("NOVEMBER 8 WIDER HISTORICAL BACKFILL: NO-GO")
