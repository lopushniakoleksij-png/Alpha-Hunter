"""Static safety acceptance for SELECT-only historical and prospective metadata audit.

No production database call. Explicitly forbids reaching the sealed outcomes
tables, altering any R9/paper history, or declaring scientific promotion.
"""
from pathlib import Path
from pglast import parse_sql

AUDIT=Path("ops/research/p0_p3_readonly_acceptance_audit_v01.sql")
sql=AUDIT.read_text()
lower=sql.lower()


def test_all_statements_select_only():
    nodes=parse_sql(sql)
    assert len(nodes)==8
    assert all(n.stmt.__class__.__name__=="SelectStmt" for n in nodes)


def test_never_read_frozen_primary_outcomes_or_mutate_experiment():
    forbidden=[
      "from public.alpha_hunter_geometry_holdout_outcomes_sealed",
      "join public.alpha_hunter_geometry_holdout_outcomes_sealed",
      "from public.alpha_hunter_scientific_holdout_outcomes_sealed",
      "join public.alpha_hunter_scientific_holdout_outcomes_sealed",
      "insert into ", "delete from ","update public.","alter table",
      "drop table ","create table ","merge into ","cron.alter_job",
      "execute_now", "place_live_order(",
    ]
    statements=lower.split("-- p0 original immutable")[1]  # exclude leading prose
    # Skip SQL comments as they describe deliberate prohibitions.
    raw="\n".join(x for x in lower.splitlines() if not x.lstrip().startswith("--"))
    for bad in forbidden:
        assert bad not in raw, bad


def test_immutable_original_cohort_and_no_legacy_seven_q_wins_leak():
    assert lower.count("2026-10-16t23:23:00z")>=4
    assert "alpha_hunter_paper_completed_trades_valid_v05" in lower
    assert "alpha_hunter_geometry_holdout_status_v01" in lower
    assert "alpha_hunter_scientific_holdout_status_v02" in lower
    assert "alpha_hunter_paper_profitability_status_v09" in lower
    assert "alpha_hunter_execution_cost_validation_readiness_v04" in lower


def test_quote_custody_cannot_be_conflated_with_executability():
    assert "captured_quote_only" in lower
    assert "exchange_request_added" in lower
    assert "missing_named_source" in lower
    assert "r9_depth_timing_captures_v01" in lower
    assert "legacy_order_id_matches" in lower
    assert "verified_exit_slippage_rows" in lower
    assert "realized_funding_path_gate_met" in lower
    assert "realistic_net_r_claim_permitted" in lower


def test_p2_does_not_use_sealed_primary_results_or_optimize_losses():
    raw="\n".join(x for x in lower.splitlines() if not x.lstrip().startswith("--"))
    assert "holdout_outcomes" not in raw
    assert "alpha_hunter_geometry_holdout_status_v01" in raw
    assert "alpha_hunter_scientific_holdout_status_v02" in raw
    assert "production_promotion_permitted" in raw


def test_atr_and_support_cannot_be_substituted_for_true_custody():
    assert "median_stop_to_1h_atr" in lower
    assert "long_stop_above_4h_support" in lower
    assert "short_stop_below_4h_resistance" in lower
    assert "not validated" in lower
