"""Pure no-network / no-database successor P0 deadman red-team tests."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/"ops/reviews/successor_p0_deadman_readiness_v01.py"
spec = spec_from_file_location("research_deadman_gate", SOURCE)
gate = module_from_spec(spec)
spec.loader.exec_module(gate)

NOW = "2026-10-23T12:00:00+00:00"


def fixture():
    ledger = {
        "all_cohort_residual_count": 3,
        "managed_from_fill_ledger": 3,
        "quarantined_outside_managed": 0,
        "unexplained_unmanaged": 0,
        "missing_recorded_stop_or_target": 0,
    }
    rows = [{
        "symbol": sym, "direction": "SHORT", "position_slot": slot,
        "receipts_24h": 65,
        "structurally_invalid_receipts": 0,
        "missing_independent_quote_receipt_link": 0,
        "absent_prior_anchor_rows": 0,
        "observed_gaps_over_35m": 0,
        "longest_observed_gap_seconds": "2100",
        "latest_24h_receipt": "2026-10-23T11:25:00+00:00",
    } for sym, slot in (("NIGHTUSDT", 1), ("SOONUSDT", 1), ("SOONUSDT", 2))]
    return ledger, rows


def check(ledger=None, rows=None, now=NOW):
    default_ledger, default_rows = fixture()
    return gate.evaluate_deadman_readiness(
        ledger=default_ledger if ledger is None else ledger,
        position_rows=default_rows if rows is None else rows,
        checked_at_utc=now,
    )


def all_reasons(out):
    return {reason for event in out["redacted_incident_candidates"]
            for reason in event["reasons"]}


def assert_zero_live_authority(out):
    for field in ("independent_asof_inventory_authenticated",
                  "independent_quote_custody_authenticated",
                  "actual_alert_dispatched",
                  "actual_provider_acceptance_verified",
                  "actual_inbox_delivery_verified",
                  "operational_72h_pilot_qualified",
                  "scientific_pass_permitted",
                  "production_deployment_permitted",
                  "paper_admission_permitted",
                  "exchange_authority", "trade_permission"):
        assert out[field] is False, field
    assert out["frozen_maximum_monitor_gap_seconds"] == 2100
    assert out["order_path"] == "NONE" and out["new_spend_usd"] == 0


def test_clean_looking_supplied_rows_never_claim_authenticated_operations():
    result = check()
    assert result["status"] == "OFFLINE_STRUCTURAL_RECORDS_ONLY_NOT_AUTHENTICATED"
    assert not result["redacted_incident_candidates"]
    assert_zero_live_authority(result)


def test_35_minute_current_clock_exactly_allowed_and_one_second_late_rejected():
    # In synthetic evidence the last position attempt occurred at 11:25.
    assert check()["status"] == "OFFLINE_STRUCTURAL_RECORDS_ONLY_NOT_AUTHENTICATED"
    out=check(now="2026-10-23T12:00:01+00:00")
    assert out["status"] == "OFFLINE_FAIL_CLOSED_ALERT_CANDIDATES"
    assert sum("FROZEN_35M_CURRENT_POSITION_STALE" in e["reasons"]
               for e in out["redacted_incident_candidates"]) == 3
    assert_zero_live_authority(out)


def test_historical_35m_gap_not_erased_by_new_healthy_latest_record():
    ledger, rows = fixture()
    rows[0]["observed_gaps_over_35m"] = 1
    rows[0]["longest_observed_gap_seconds"] = "3585.3"
    result = check(ledger, rows)
    assert "FROZEN_35M_HISTORICAL_GAP" in all_reasons(result)
    assert "FROZEN_35M_OBSERVATION_GAP_OR_UNKNOWN" in all_reasons(result)
    assert_zero_live_authority(result)


def test_25_residuals_21_quarantined_one_partial_are_critical_even_when_three_look_clean():
    ledger, rows = fixture()
    ledger.update(
        all_cohort_residual_count=25,
        quarantined_outside_managed=21,
        unexplained_unmanaged=1,
        missing_recorded_stop_or_target=3,
    )
    result = check(ledger, rows)
    assert result["position_rows"] == 3
    assert "QUARANTINED_POSITIVE_RESIDUALS_NOT_CLOSED" in result["run_blockers"]
    assert "UNPROTECTED_PARTIAL_OR_RESIDUAL_INCIDENT" in result["run_blockers"]
    assert "MISSING_RECORDED_PROTECTION_LEG" in result["run_blockers"]
    assert result["redacted_incident_candidates"][-1]["delivery_state"] == (
        "NOT_SENT_SYNTHETIC_DIAGNOSTIC")
    assert_zero_live_authority(result)


def test_missing_quote_provenance_and_unusable_paper_receipt_are_not_pass():
    ledger, rows = fixture()
    rows[0]["missing_independent_quote_receipt_link"] = 65
    rows[1]["structurally_invalid_receipts"] = 6
    result = check(ledger, rows)
    assert "INDEPENDENT_QUOTE_CUSTODY_MISSING" in all_reasons(result)
    assert "UNUSABLE_RECORDED_POSITION_ATTEMPTS" in all_reasons(result)
    assert not result["actual_alert_dispatched"]


def test_missing_historical_anchor_or_any_observation_fails_closed():
    ledger, rows=fixture()
    rows[0]["absent_prior_anchor_rows"]=1
    rows[1]["receipts_24h"]=0
    rows[1]["latest_24h_receipt"]=None
    result=check(ledger,rows)
    assert "PRIOR_MONITORING_CHAIN_UNKNOWN" in all_reasons(result)
    assert "POSITION_OBSERVATIONS_MISSING" in all_reasons(result)


def test_wrong_managed_rowset_and_duplicate_position_cannot_hide_missing_obligation():
    ledger, rows=fixture()
    result=check(ledger,rows[:2])
    assert "LEDGER_MANAGED_RECEIPT_SET_MISMATCH" in result["run_blockers"]
    rows[2]=deepcopy(rows[1])
    result=check(ledger,rows)
    assert "DUPLICATE_POSITION_ROW" in result["run_blockers"]
    assert_zero_live_authority(result)


def test_empty_or_unreadable_inventory_is_not_evidence_of_empty_positions():
    ledger, rows=fixture()
    ledger.update(all_cohort_residual_count=0,managed_from_fill_ledger=0)
    result=check(ledger,[])
    assert "EMPTY_MANAGED_VIEW_NOT_INDEPENDENT_EMPTY_PROOF" in result["run_blockers"]
    assert_zero_live_authority(result)
    result=check({},[])
    assert "ALL_COHORT_LEDGER_COUNTS_UNKNOWN" in result["run_blockers"]
    assert_zero_live_authority(result)


def test_future_clock_invalid_counts_and_invalid_duration_never_become_safe():
    ledger, rows=fixture()
    rows[0]["latest_24h_receipt"]="2026-10-23T12:01:00Z"
    rows[1]["longest_observed_gap_seconds"]="nan"
    rows[2]["receipts_24h"]=True
    result=check(ledger,rows)
    assert "OBSERVATION_CLOCK_FROM_FUTURE" in all_reasons(result)
    assert "FROZEN_35M_OBSERVATION_GAP_OR_UNKNOWN" in all_reasons(result)
    assert "POSITION_OBSERVATIONS_MISSING" in all_reasons(result)
    assert_zero_live_authority(result)


def test_sql_is_select_only_and_checks_both_24h_window_edges():
    sql=(ROOT/"ops/reviews/successor_p0_position_continuity_edges_readonly_20261023.sql").read_text()
    active="\n".join(line for line in sql.splitlines()
                     if not line.lstrip().startswith("--"))
    assert re.match(r"\s*WITH\s+clock\s+AS\s*\(", active, re.I)
    assert active.count(";")==1
    assert not re.search(
        r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|CALL|COPY|EXECUTE)\b",
        active, re.I,
    )
    for field in (
        "absent_prior_anchor_rows", "observed_gaps_over_35m",
        "current_observation_age_seconds", "missing_independent_quote_receipt_link",
        "frozen_observation_max_gap_seconds",
        "live_critical_alert_delivery_verified", "scientific_test_promotion_authorized",
        "s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'",
    ):
        assert field in active
    assert "2100 AS frozen_observation_max_gap_seconds" in active


def test_no_production_import_or_hidden_sending():
    text=SOURCE.read_text(encoding="utf-8")
    for banned in ("requests", "smtplib", "psycopg", "supabase", "send_message",
                   "create_order", "execute_sql(", "import os", "import socket"):
        assert banned not in text
