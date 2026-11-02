"""P2 rolling quote/position custody: 72h SYNTHETIC time replay only.

No live Supabase, Bitget, Render, clock sleeps, paid services, or credentials.
Success here is a LOCAL consistency regression, never continuous live proof.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ops" / "reviews"))
from successor_p2_source_quote_provenance_contract_v01 import (
    seal, source_manifest,
)
from successor_p2_offline_rolling_chain_v01 import audit_local_rolling_chain

spec = importlib.util.spec_from_file_location(
    "p2_existing_synthetic_contract_fixture",
    ROOT / "tests" / "test_successor_p2_source_quote_provenance_contract_v01.py",
)
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)


def cycle(index, prior=None, *, elapsed_seconds=None, positions=2):
    when = existing.NOW + timedelta(
        seconds=(elapsed_seconds if elapsed_seconds is not None else index * 300)
    )
    case = existing.fixture(n_managed=positions, gap=300)
    source = copy.deepcopy(case["source"]["payload"])
    source["run_id"] = f"synthetic-p2-rolling-{index}"
    source["asof_utc"] = (when - timedelta(seconds=1)).isoformat()
    source["captured_at_utc"] = when.isoformat()
    source["db_read"]["snapshot_token"] = f"synthetic-local-snapshot-{index}"
    for t in source["tables"].values():
        t["snapshot_token"] = f"synthetic-local-snapshot-{index}"
    case["source"] = seal("SOURCE_REPEATABLE_READ", source, existing.K_SOURCE)
    _, manifest, _ = source_manifest(case["source"], existing.K_SOURCE, when)
    if prior is not None:
        case["previous"] = prior
    case["now_utc"] = when.isoformat()
    for i, q in enumerate(case["quotes"]):
        quote = copy.deepcopy(q["payload"])
        raw = json.loads(base64.b64decode(quote["raw_response_b64"]))
        raw["data"][0]["ts"] = str(int((when - timedelta(seconds=2)).timestamp() * 1000))
        raw_bytes = json.dumps(raw, separators=(",", ":")).encode()
        quote["raw_response_b64"] = base64.b64encode(raw_bytes).decode()
        quote["raw_response_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        quote["run_id"] = source["run_id"]
        quote["request_id"] = f"synthetic-rolling-request-{index}-{i}-nonce"
        quote["transport_captured_at_utc"] = when.isoformat()
        case["quotes"][i] = seal("PUBLIC_BITGET_QUOTE_BYTES", quote, existing.K_QUOTE)
    case["current"] = []
    for i in range(positions):
        old = case["previous"][i]
        now = {
            "run_id": source["run_id"],
            "entry_order_id": f"synthetic-entry-{i}",
            "symbol": f"SYNTH{i}USDT",
            "direction": "LONG",
            "observed_at_utc": when.isoformat(),
            "source_manifest_sha256": manifest["manifest_sha256"],
            "source_receipt_digest": case["source"]["digest_sha256"],
            "quote_receipt_digest": case["quotes"][i]["digest_sha256"],
            "previous_receipt_digest": old["digest_sha256"],
            "stop_id": f"synthetic-stop-{i}",
            "target_id": f"synthetic-target-{i}",
            "top_book": ["1", "1.01", "10", "20"],
            "trade_permission": False,
            "exchange_authority": False,
        }
        case["current"].append(seal("PAPER_POSITION_OBSERVATION", now, existing.K_MONITOR))
    return case


def replay(times):
    out = []
    prior = None
    for index, seconds in enumerate(times):
        c = cycle(index, prior, elapsed_seconds=seconds)
        out.append(c)
        prior = c["current"]
    return out


def audit(cycles):
    return audit_local_rolling_chain(
        cycles, source_key=existing.K_SOURCE,
        quote_key=existing.K_QUOTE, custody_key=existing.K_MONITOR,
    )


def test_72_hour_synthetic_replay_cannot_claim_real_continuous_monitoring():
    # 865 simulated captures = exactly 72h at an ideal 5-minute interval.
    # Elapsed fixture timestamps are NOT 72 elapsed real-world hours.
    result = audit(replay(range(0, 72 * 3600 + 1, 300)))
    assert result["status"] == "LOCAL_ROLLING_CHAIN_STRUCTURALLY_CONSISTENT_NOT_LIVE_PROOF", result
    assert result["cycles_checked"] == 865
    assert result["max_local_observation_gap_seconds"] == 300
    assert result["frozen_monitor_limit_seconds"] == 2100
    for key in (
        "bootstrap_prior_history_authenticated",
        "source_authenticated_by_independent_live_connection",
        "venue_quote_signed_by_bitget",
        "operational_independent_custody_proven",
        "continuous_prospective_35m_proven",
        "actual_alert_delivery_verified",
        "scientific_pass_permitted",
        "trade_permission",
        "exchange_authority",
        "production_promotion_permitted",
    ):
        assert result[key] is False


def test_exact_35_minute_interval_is_allowed_only_as_local_structure():
    r = audit(replay([0, 2100]))
    assert r["status"] == "LOCAL_ROLLING_CHAIN_STRUCTURALLY_CONSISTENT_NOT_LIVE_PROOF", r
    assert r["max_local_observation_gap_seconds"] == 2100


def test_35_minutes_one_second_is_rejected():
    r = audit(replay([0, 2101]))
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP", r
    assert any("FROZEN_35_MINUTE_MONITOR_GAP_BREACH" in x for x in r["blockers"])
    assert r["continuous_prospective_35m_proven"] is False


def test_missing_one_position_in_a_cycle_is_not_a_complete_journal():
    rows = replay([0, 300, 600])
    rows[1]["current"].pop()
    r = audit(rows)
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP"
    assert any("PER_CYCLE_ORDER_COVERAGE_MISMATCH" in x for x in r["blockers"])


def test_forged_relink_to_two_cycles_ago_is_caught_even_if_locally_signed():
    rows = replay([0, 300, 600])
    rows[2]["previous"] = rows[0]["current"]
    altered = []
    for i, e in enumerate(rows[2]["current"]):
        p = copy.deepcopy(e["payload"])
        p["previous_receipt_digest"] = rows[0]["current"][i]["digest_sha256"]
        altered.append(seal("PAPER_POSITION_OBSERVATION", p, existing.K_MONITOR))
    rows[2]["current"] = altered
    r = audit(rows)
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP", r
    assert any("PREVIOUS_SEAL_NOT_FROM_PRIOR_CYCLE" in x for x in r["blockers"])


def test_single_cycle_does_not_claim_continuity():
    r = audit(replay([0]))
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP"
    assert "INSUFFICIENT_MULTICYCLE_EVIDENCE" in r["blockers"]
    assert r["continuous_prospective_35m_proven"] is False


def test_empty_evidence_fails_closed():
    r = audit([])
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP"
    assert r["scientific_pass_permitted"] is False


def test_unattested_position_disappearance_fails_closed():
    one = cycle(0)
    next_one = cycle(1, one["current"][:1], positions=1)
    r = audit([one, next_one])
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP"
    assert any("POSITION_MEMBERSHIP_CHANGE_UNPROVEN" in x for x in r["blockers"])


def test_repeated_source_run_identity_is_not_sequential_proof():
    one = cycle(0)
    two = cycle(0, one["current"], elapsed_seconds=300)
    r = audit([one, two])
    assert r["status"] == "FAIL_CLOSED_UNKNOWN_OR_GAP"
    assert any("REPLAY_OR_NONMONOTONIC_SOURCE_RUN" in x for x in r["blockers"])


def test_contract_has_no_network_runtime_or_order_path():
    src = (ROOT / "ops/reviews/successor_p2_offline_rolling_chain_v01.py").read_text()
    assert "def audit_local_rolling_chain(" in src
    assert "def scan(" not in src
    assert "requests." not in src and "urlopen(" not in src
    assert "place_order(" not in src and "cancel_order(" not in src
    assert "FROZEN_MAX_GAP_SECONDS" in src
