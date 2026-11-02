"""P2/P3 research regressions. These are invented fixtures, NOT forward results."""
from datetime import datetime,timedelta,timezone
from pathlib import Path

from alpha_hunter.successor_forward_science_gate_v01 import (
    assess_forward,CONTRACT_ID,MIN_CANDIDATES,MIN_SYMBOL_CLUSTERS,
    MIN_UTC_DAY_CLUSTERS,SEALED_R9_START,SEALED_R9_END,
)

APPROVAL="synthetic-only-unsigned-review-not-valid-approval"
FINGERPRINT="synthetic-successor-v0"
START="2026-11-04T00:00:00Z"


def fixture(index, delta=1):
    # 60 distinct symbols spread over 20 UTC days, 240 synthetic candidate pairs.
    day=datetime(2026,11,5,tzinfo=timezone.utc)+timedelta(days=index%20)
    stamp=day+timedelta(hours=index%20)
    return dict(
        cohort="PREREGISTERED_SUCCESSOR_FORWARD_PAPER_SHADOW",
        event_id=f"fake-only-{index}",
        symbol=f"SYNTHETIC{index%60}USDT",
        symbol_group_id=f"SYNTHETIC{index%60}USDT",
        entry_at_utc=stamp.isoformat(),completed_at_utc=(stamp+timedelta(minutes=50)).isoformat(),
        entry_utc_day=stamp.strftime("%Y-%m-%d"),
        baseline_execution_version="FROZEN_BASELINE",
        successor_fingerprint=FINGERPRINT,
        quote_source_custody="INDEPENDENTLY_ATTESTED",
        depth_and_exit_liquidity="INDEPENDENTLY_VERIFIED",
        structural_stop_geometry="VERIFIED_NO_WIDENING",
        fee_binding="VENUE_EVIDENCE_BOUND",
        funding_binding="VENUE_EVIDENCE_BOUND",
        protection_evidence="BOTH_LEGS_AND_RESIDUAL_CONFIRMED",
        first_touch_ordering="INDEPENDENTLY_RECONSTRUCTED",
        max_monitor_gap_minutes="25",
        baseline_net_usdt_after_all_costs="0",
        successor_net_usdt_after_all_costs=str(delta),
        independent_quote_attestation_id=f"fake-quote-{index}",
        provider_receipt_id=f"fake-provider-{index}",
    )


def evaluate(rows,**overrides):
    options=dict(preregistered_activation_utc=START,
                 independent_risk_review_reference=APPROVAL,
                 frozen_successor_fingerprint=FINGERPRINT)
    options.update(overrides)
    return assess_forward(rows,**options)


def assert_inert(r):
    assert r["scientific_promotion_permitted"] is False
    assert r["production_promotion_permitted"] is False
    assert r["trade_permission"] is False
    assert r["admission_permission"] is False
    assert r["live_order_authority"] is False
    assert r["profitability_claim_permitted"] is False
    assert r["historical_reclassifications"]==0
    assert r["r9_start"]==SEALED_R9_START
    assert r["r9_cutoff"]==SEALED_R9_END
    assert r["monitoring_cap_minutes"]==35
    assert r["contract"]==CONTRACT_ID


def test_no_external_prereg_signoff_rejects_all():
    rows=[fixture(i) for i in range(240)]
    out=evaluate(rows,independent_risk_review_reference=None)
    assert out["status"]=="BLOCKED_NOT_PREREGISTERED"
    assert out["accepted_forward_events"]==0
    assert_inert(out)


def test_no_actual_forward_events_still_blocked():
    out=evaluate([])
    assert out["status"]=="BLOCKED_NO_FORWARD_EVIDENCE"
    assert_inert(out)


def test_r9_window_cannot_count_as_successor_forward():
    out=evaluate([fixture(i) for i in range(240)],
                 preregistered_activation_utc="2026-10-17T00:00:00Z")
    assert out["status"]=="BLOCKED_NOT_PREREGISTERED"
    assert out["reason"]=="FORWARD_SUCCESSOR_CANNOT_OVERLAP_SEALED_R9"
    assert_inert(out)


def test_230_threshold_cannot_be_faked_with_32_historical_outcomes():
    rows=[fixture(i) for i in range(32)]
    for row in rows:
        row["cohort"]="LEGACY_PAPER"
        row["entry_at_utc"]="2026-10-02T00:00:00Z"
    out=evaluate(rows)
    assert out["accepted_forward_events"]==0
    assert out["status"]=="BLOCKED_INSUFFICIENT_INDEPENDENT_FORWARD_EVIDENCE"
    assert out["rejection_reasons"]["LEGACY_OR_WRONG_COHORT"]==32
    assert_inert(out)


def test_perfect_fake_data_can_never_grant_actual_scientific_authority():
    rows=[fixture(i) for i in range(240)]
    out=evaluate(rows)
    assert out["accepted_forward_events"]==240
    assert out["symbol_clusters"]==60
    assert out["utc_day_clusters"]==20
    assert out["symbol_equal_95_lcb"]>0
    assert out["day_equal_95_lcb"]>0
    assert out["status"]=="NUMERIC_RESEARCH_GATE_ONLY_INDEPENDENT_APPROVAL_REQUIRED"
    assert_inert(out)


def test_zero_net_after_costs_fails_positive_lower_bound():
    rows=[fixture(i,0) for i in range(240)]
    out=evaluate(rows)
    assert out["status"]=="REJECTED_NONPOSITIVE_INDEPENDENCE_ADJUSTED_LCB"
    assert_inert(out)


def test_insufficient_symbol_or_day_independence_rejected():
    rows=[fixture(i) for i in range(240)]
    for row in rows:
        row["symbol"]=row["symbol_group_id"]="SAMEUSDT"
        row["entry_utc_day"]="2026-11-05"
    out=evaluate(rows)
    assert out["symbol_clusters"]==0 or out["symbol_clusters"]<MIN_SYMBOL_CLUSTERS
    assert out["status"]=="BLOCKED_INSUFFICIENT_INDEPENDENT_FORWARD_EVIDENCE"
    assert_inert(out)


def test_unverified_depth_stop_fee_funding_quoted_source_or_guard_excluded():
    fields=["quote_source_custody","depth_and_exit_liquidity",
            "structural_stop_geometry","fee_binding","funding_binding",
            "protection_evidence","first_touch_ordering",
            "independent_quote_attestation_id","provider_receipt_id"]
    for f in fields:
        rows=[fixture(i) for i in range(240)]
        rows[0][f]=None
        out=evaluate(rows)
        assert out["accepted_forward_events"]==239,(f,out)
        assert out["rejected_events"]==1
        assert_inert(out)


def test_36_minute_monitoring_gap_is_excluded():
    rows=[fixture(i) for i in range(240)]
    rows[0]["max_monitor_gap_minutes"]="36"
    out=evaluate(rows)
    assert out["accepted_forward_events"]==239
    assert out["rejection_reasons"]["MONITORING_INTEGRITY_FAIL"]==1
    assert_inert(out)


def test_mismatched_fingerprint_and_duplicate_event_do_not_count():
    rows=[fixture(i) for i in range(240)]
    rows[1]["successor_fingerprint"]="drifted"
    rows[2]["event_id"]=rows[0]["event_id"]
    out=evaluate(rows)
    assert out["accepted_forward_events"]==238
    assert out["rejected_events"]==2
    assert_inert(out)


def test_research_has_no_database_network_order_or_approval_capability():
    s=Path("alpha_hunter/successor_forward_science_gate_v01.py").read_text()
    for forbidden in ("import requests","urllib","psycopg","supabase",
                      "place_order(","cancel_order(","execute_sql","apply_migration"):
        assert forbidden not in s
    assert "profitability_claim_permitted=False" in s
    assert "NUMERIC_RESEARCH_GATE_ONLY_INDEPENDENT_APPROVAL_REQUIRED" in s
