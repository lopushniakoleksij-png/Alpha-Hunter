"""R11 isolated short-duration prospective capture pilot. Never trades or reads production.

Three future scheduled observations; real public Bitget HTTPS bytes; local
SQLite diagnostic probe receipts; offline replay; external Sigstore GitHub
artifact attestation is performed and verified by the CI workflow, NOT here.

The probe is a SYNTHETIC paper monitor, not an opened Alpha Hunter position.
A well-formed short pilot does NOT establish sustained 35m monitoring,
separately governed human custody, provider signatures or release authority.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta

SOURCE = Path(__file__).with_name("p03_r11_live_public_source_local_pg_v01.py")
spec = importlib.util.spec_from_file_location("r11_public_source", SOURCE)
witness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(witness)

COHORT = "R11-ISOLATED-3SCAN-TRANSPORT-PILOT"
PROBE = "r11-synthetic-probe-no-execution"
MAX_GAP_SECONDS = 35 * 60
# Short PR pilot only: 3 real observations ~75s apart, never a perpetual daemon.
INTERVAL_SECONDS = 75
START_LEAD_SECONDS = 90


class EvidenceNoGo(ValueError):
    pass


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(x):
    return hashlib.sha256(x).hexdigest()


def parse_time(value):
    if not isinstance(value, str):
        raise EvidenceNoGo("UTC_TIMESTAMP_MISSING")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise EvidenceNoGo("UTC_TIMESTAMP_INVALID") from e
    if d.utcoffset() is None:
        raise EvidenceNoGo("UTC_OFFSET_REQUIRED")
    return d.astimezone(timezone.utc)


def utc(d):
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def make_schedule(now, run_id):
    if now.utcoffset() is None or not str(run_id).isdecimal():
        raise EvidenceNoGo("SCHEDULE_ORIGIN_INVALID")
    now = now.astimezone(timezone.utc)
    start = now + timedelta(seconds=START_LEAD_SECONDS)
    return {
        "schema": "ah-r11-prospective-isolated-pilot-schedule-v01",
        "cohort_id": COHORT, "genesis_utc": utc(now),
        "research_only": True, "schedule_period_seconds": INTERVAL_SECONDS,
        "required_runs": [
            {"run_id": f"r11-{run_id}-scan-{i+1}",
             "scheduled_at_utc": utc(start + timedelta(seconds=i*INTERVAL_SECONDS)),
             "expected_symbols": ["BTCUSDT"],
             "expected_synthetic_receipt_ids": [PROBE]}
            for i in range(3)
        ],
        "diagnostic_position": {
            "id": PROBE,
            "entry_at_utc": utc(start-timedelta(seconds=30)),
            "identity": "synthetic monitoring probe only",
            "not_an_exchange_or_paper_order": True,
        },
        "source": "https://api.bitget.com", "source_transport": "verified_https",
        "independent_issuer_kind": "GitHub OIDC Sigstore for workflow provenance only",
        "independent_human_controller_approved": False,
        "provider_signed_market_data": False,
        "active_alpha_hunter_positions_created": 0,
        "legacy_history_reclassified": False, "legacy_evidence_status": "EVIDENCE_NO_GO",
        "production_release_authorized": False, "trade_permission": False,
        "paper_only": True,
    }


def validate_schedule(schedule):
    if not isinstance(schedule, dict) or schedule.get("cohort_id") != COHORT:
        raise EvidenceNoGo("SCHEDULE_COHORT_INVALID")
    if (schedule.get("legacy_evidence_status") != "EVIDENCE_NO_GO"
            or schedule.get("legacy_history_reclassified") is not False
            or schedule.get("trade_permission") is not False
            or schedule.get("production_release_authorized") is not False
            or schedule.get("independent_human_controller_approved") is not False):
        raise EvidenceNoGo("AUTHORITY_OR_LEGACY_INVALID")
    runs = schedule.get("required_runs")
    position = schedule.get("diagnostic_position")
    if (not isinstance(runs, list) or len(runs) != 3
            or not isinstance(position, dict) or position.get("id") != PROBE
            or position.get("not_an_exchange_or_paper_order") is not True):
        raise EvidenceNoGo("RUN_OR_POSITION_INVENTORY_INVALID")
    t0 = parse_time(schedule["genesis_utc"])
    entry_time = parse_time(position["entry_at_utc"])
    if t0 >= entry_time or (entry_time-t0).total_seconds() > MAX_GAP_SECONDS:
        raise EvidenceNoGo("PROBE_ENTRY_ORIGIN_INVALID")
    prev = None
    for i, run in enumerate(runs):
        if (run.get("run_id", "").rsplit("-scan-", 1)[-1] != str(i+1)
                or run.get("expected_symbols") != ["BTCUSDT"]
                or run.get("expected_synthetic_receipt_ids") != [PROBE]):
            raise EvidenceNoGo("SCHEDULE_EXPECTED_RUN_MISMATCH")
        scheduled = parse_time(run["scheduled_at_utc"])
        if scheduled <= entry_time:
            raise EvidenceNoGo("PROBE_ENTRY_NOT_PROSPECTIVE")
        if prev is not None and not (0 < (scheduled-prev).total_seconds() <= MAX_GAP_SECONDS):
            raise EvidenceNoGo("SCHEDULE_GAP_OVER_35M")
        prev = scheduled
    return True


def build_event(schedule, index, capture, observed_at, previous_hash):
    plan = schedule["required_runs"][index]
    rid = plan["run_id"]
    ticker, book = capture["ticker"], capture["orderbook"]
    if (not isinstance(ticker.get("raw"), bytes)
            or not isinstance(book.get("raw"), bytes)):
        raise EvidenceNoGo("ORIGINAL_QUOTE_BYTES_MISSING")
    if abs(ticker["parsed"]["source_timestamp_ms"] -
           book["parsed"]["source_timestamp_ms"]) > 90_000:
        raise EvidenceNoGo("PUBLIC_SOURCES_NOT_COMPARABLE")
    timestamp = utc(observed_at)
    return {
        "cohort_id": COHORT, "run_id": rid, "scheduled_at_utc": plan["scheduled_at_utc"],
        "observed_at_utc": timestamp, "previous_event_sha256": previous_hash,
        "source_transport": "verified_https",
        "provider_signed": False, "signed_by_independent_human": False,
        "public_market_raw_sha256": {
            "ticker": sha(ticker["raw"]), "orderbook": sha(book["raw"])},
        "persisted_children": [{
            "run_id": rid, "symbol": "BTCUSDT",
            "payload": {"symbol": "BTCUSDT",
                        "public_quote_source": "Bitget public v3, no execution",
                        "ticker_sha256": sha(ticker["raw"]),
                        "orderbook_sha256": sha(book["raw"])} }],
        "position_receipts": [{
            "entry_order_id": PROBE, "source_run_id": rid,
            "observed_at_utc": timestamp, "outcome": "NO_TRIGGER",
            "blockers": [], "synthetic_probe_only": True,
            "no_actual_alpha_hunter_position": True, "paper_only": True,
            "exchange_authority": False, "trade_permission": False, "order_path": "NONE",
        }],
    }


def validate_events(schedule, events, raw_by_run):
    """Strict total schedule census plus real-source payload digest checks."""
    validate_schedule(schedule)
    required = schedule["required_runs"]
    if not isinstance(events, list) or len(events) != len(required):
        raise EvidenceNoGo("REQUIRED_RUNS_MISSING")
    previous_hash = "GENESIS"
    previous_receipt_at = parse_time(schedule["diagnostic_position"]["entry_at_utc"])
    expected_ids = set()
    for run, event in zip(required, events):
        rid = run["run_id"]
        expected_ids.add(rid)
        if (event.get("run_id") != rid or event.get("cohort_id") != COHORT
                or event.get("previous_event_sha256") != previous_hash):
            raise EvidenceNoGo("RUN_ID_OR_EVENT_HASH_CHAIN_INVALID")
        if event.get("scheduled_at_utc") != run["scheduled_at_utc"]:
            raise EvidenceNoGo("SCHEDULE_OBSERVATION_IDENTITY_MISMATCH")
        now = parse_time(event["observed_at_utc"])
        scheduled = parse_time(run["scheduled_at_utc"])
        if not 0 <= (now-scheduled).total_seconds() <= MAX_GAP_SECONDS:
            raise EvidenceNoGo("LATE_OR_EARLY_SCAN_OUTSIDE_35M")
        if not 0 < (now-previous_receipt_at).total_seconds() <= MAX_GAP_SECONDS:
            raise EvidenceNoGo("PROSPECTIVE_PAPER_PROBE_GAP_OVER_35M")
        previous_receipt_at = now
        receipts = event.get("position_receipts")
        if (not isinstance(receipts, list) or len(receipts) != 1
                or receipts[0].get("entry_order_id") != PROBE
                or receipts[0].get("source_run_id") != rid
                or receipts[0].get("observed_at_utc") != event["observed_at_utc"]
                or receipts[0].get("synthetic_probe_only") is not True
                or receipts[0].get("no_actual_alpha_hunter_position") is not True
                or receipts[0].get("paper_only") is not True
                or receipts[0].get("trade_permission") is not False
                or receipts[0].get("exchange_authority") is not False
                or receipts[0].get("order_path") != "NONE"):
            raise EvidenceNoGo("DIAGNOSTIC_POSITION_RECEIPT_MISSING")
        child = event.get("persisted_children")
        if (not isinstance(child, list) or len(child) != 1
                or child[0].get("run_id") != rid or child[0].get("symbol") != "BTCUSDT"
                or child[0].get("payload", {}).get("symbol") != "BTCUSDT"):
            raise EvidenceNoGo("CHILD_EVIDENCE_MISSING_OR_DIFFERENT")
        raw = raw_by_run.get(rid)
        if not isinstance(raw, dict) or set(raw) != {"ticker", "orderbook"}:
            raise EvidenceNoGo("RAW_SOURCE_CAPTURE_MISSING")
        for kind in ("ticker", "orderbook"):
            if sha(raw[kind]) != event["public_market_raw_sha256"].get(kind):
                raise EvidenceNoGo("RAW_SOURCE_SHA256_MISMATCH")
            if sha(raw[kind]) != child[0]["payload"].get(kind+"_sha256"):
                raise EvidenceNoGo("CHILD_HASH_SOURCE_MISMATCH")
        previous_hash = sha(canonical(event))
    if set(raw_by_run) != expected_ids:
        raise EvidenceNoGo("EXTRA_OR_MISSING_CAPTURE")
    return {
        "status": "R11_SHORT_PILOT_REAL_PUBLIC_SOURCE_3_OF_3_CONTRACT_PASS_ONLY",
        "scheduled_runs": 3, "observed_runs": 3, "synthetic_diagnostic_receipts": 3,
        "duration_seconds": (parse_time(events[-1]["observed_at_utc"]) -
                             parse_time(events[0]["observed_at_utc"])).total_seconds(),
        "last_event_sha256": previous_hash,
        "continuous_long_term_monitoring_proven": False,
        "independent_human_custody_approved": False,
        "exchange_quote_cryptographically_signed": False,
        "real_paper_positions_observed": 0,
        "prospective_dual_human_signer_gate": "NO_GO",
        "legacy_evidence_status": "EVIDENCE_NO_GO",
        "paper_only": True, "trade_permission": False,
        "production_release_authorized": False,
    }


def _sqlite_connect(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS public_captures (run_id TEXT PRIMARY KEY, event_json TEXT NOT NULL, event_sha256 TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS diagnostic_receipts (run_id TEXT PRIMARY KEY, probe_id TEXT NOT NULL, observed_at_utc TEXT NOT NULL)")
    db.commit()
    return db


def collect(schedule_path, output):
    # Do not trust a mere Boolean from a caller as human independence. The
    # workflow must first verify the externally issued Sigstore attestation.
    # This env gate is scope defense, not cryptographic verification itself.
    if os.getenv("AH_SCHEDULE_SIGSTORE_VERIFIED") != "1":
        raise EvidenceNoGo("SCHEDULE_EXTERNAL_PROVENANCE_NOT_VERIFIED")
    if any(os.getenv(x) for x in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                                  "BITGET_API_KEY", "BITGET_SECRET_KEY",
                                  "BITGET_API_PASSPHRASE", "RENDER_API_KEY")):
        raise EvidenceNoGo("PRODUCTION_SECRET_PRESENT")
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    validate_schedule(schedule)
    output.mkdir(parents=True, exist_ok=True)
    db = _sqlite_connect(output/"isolated_receipts.sqlite3")
    previous_hash = "GENESIS"
    events = []
    raws = {}
    for idx, plan in enumerate(schedule["required_runs"]):
        expected = parse_time(plan["scheduled_at_utc"])
        delay = (expected - datetime.now(timezone.utc)).total_seconds()
        if delay < -20:
            raise EvidenceNoGo("MISSED_SCHEDULED_START")
        if delay > 0:
            time.sleep(delay)
        ticker = witness._read_public("ticker")
        book = witness._read_public("orderbook")
        observed = datetime.now(timezone.utc)
        capture = {"ticker":ticker,"orderbook":book}
        event = build_event(schedule,idx,capture,observed,previous_hash)
        raw_folder = output/plan["run_id"]
        raw_folder.mkdir(parents=True,exist_ok=True)
        (raw_folder/"ticker.json").write_bytes(ticker["raw"])
        (raw_folder/"orderbook.json").write_bytes(book["raw"])
        (raw_folder/"event.json").write_bytes(canonical(event)+b"\n")
        with db:
            db.execute("INSERT INTO public_captures VALUES (?,?,?)",
                       (plan["run_id"], canonical(event).decode(), sha(canonical(event))))
            db.execute("INSERT INTO diagnostic_receipts VALUES (?,?,?)",
                       (plan["run_id"], PROBE, event["observed_at_utc"]))
        events.append(event)
        raws[plan["run_id"]]={"ticker":ticker["raw"],"orderbook":book["raw"]}
        previous_hash=sha(canonical(event))
        print("R11 REAL EVENT",idx+1,plan["run_id"],
              event["observed_at_utc"],previous_hash,flush=True)
    result = validate_events(schedule,events,raws)
    db_events=db.execute("SELECT run_id,event_sha256 FROM public_captures ORDER BY rowid").fetchall()
    db_receipts=db.execute("SELECT run_id,probe_id,observed_at_utc FROM diagnostic_receipts ORDER BY rowid").fetchall()
    db.close()
    if len(db_events)!=3 or len(db_receipts)!=3:
        raise EvidenceNoGo("LOCAL_PERSISTED_RECEIPTS_MISSING")
    for event, persisted, receipt in zip(events,db_events,db_receipts):
        if persisted!=(event["run_id"],sha(canonical(event))) or receipt != (
                event["run_id"],PROBE,event["observed_at_utc"]):
            raise EvidenceNoGo("LOCAL_PERSISTENCE_READBACK_INVALID")
    result["isolated_sqlite_readback_verified"]=True
    result["signed_schedule_independently_verified_in_ci"]=True
    (output/"results.json").write_bytes(canonical(result)+b"\n")
    (output/"schedule_copy.json").write_bytes(canonical(schedule)+b"\n")
    print("R11 SHORT PILOT THREE ACTUAL OBSERVATIONS AND SQLITE RECEIPTS PASS",flush=True)
    return result


def replay(schedule_path, data_dir):
    schedule=json.loads(schedule_path.read_text())
    raw={}
    events=[]
    for run in schedule["required_runs"]:
        directory=data_dir/run["run_id"]
        events.append(json.loads((directory/"event.json").read_text()))
        raw[run["run_id"]]={"ticker":(directory/"ticker.json").read_bytes(),
                           "orderbook":(directory/"orderbook.json").read_bytes()}
    return validate_events(schedule,events,raw)


def main(argv):
    if len(argv)<2:
        raise EvidenceNoGo("USAGE: module schedule|collect|replay ...")
    if argv[1]=="schedule" and len(argv)==3:
        schedule=make_schedule(datetime.now(timezone.utc),os.environ.get("GITHUB_RUN_ID",""))
        Path(argv[2]).parent.mkdir(parents=True,exist_ok=True)
        Path(argv[2]).write_bytes(canonical(schedule)+b"\n")
        print("R11 forward schedule generated; not independent human signed")
    elif argv[1]=="collect" and len(argv)==4:
        collect(Path(argv[2]),Path(argv[3]))
    elif argv[1]=="replay" and len(argv)==4:
        print(json.dumps(replay(Path(argv[2]),Path(argv[3])),indent=2))
    else:
        raise EvidenceNoGo("INVALID_COMMAND")


if __name__=="__main__":
    try:
        main(sys.argv)
    except (EvidenceNoGo,witness.WitnessRejected,OSError,ValueError,KeyError,TypeError,
            sqlite3.Error) as exc:
        print("R11_EVIDENCE_NO_GO:",type(exc).__name__,str(exc),file=sys.stderr)
        raise SystemExit(1)
