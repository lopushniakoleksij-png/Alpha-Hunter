from pathlib import Path

SQL = Path("scientific_holdout_v02_common_support_status.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_monitor_uses_only_v02_candidate_time_bindings():
    required = [
        "AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02",
        "alpha_hunter_scientific_holdout_bindings",
        "decision_available_at_utc",
        "group_name in ('TEST','CONTROL_POOL')",
    ]
    for marker in required:
        assert marker in SQL


def test_monitor_matches_frozen_exact_support_and_24h_caliper():
    required = [
        "y.direction=x.direction",
        "y.lifecycle=x.lifecycle",
        "y.liquidity_state=x.liquidity_state",
        "y.candidate_quality_status=x.candidate_quality_status",
        "<= 24*3600",
    ]
    for marker in required:
        assert marker in SQL


def test_monitor_does_not_freeze_pairs_or_read_outcomes():
    required = [
        "false as matched_pairs_frozen",
        "false as outcomes_read",
        "false as confirmatory_analysis_permitted",
        "false as production_promotion_permitted",
        "NON_BINDING_CANDIDATE_TIME_COMMON_SUPPORT_ONLY",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "primary_return",
        "secondary_return",
        "realistic_net_r",
        "sealed_outcome",
        "insert into public.alpha_hunter_scientific_holdout",
        "update public.alpha_hunter_scientific_holdout",
        "delete from public.alpha_hunter_scientific_holdout",
        "trade_permission=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_upper_bound_is_not_labelled_as_matched_pairs():
    assert "exact_stratum_upper_bound_pairs" in SQL
    assert "matched_pairs_frozen" in SQL
    assert "false as matched_pairs_frozen" in SQL


def test_view_is_service_role_read_only():
    assert "security_invoker=true" in LOWER
    assert "grant select on public.alpha_hunter_scientific_holdout_v02_common_support_status" in LOWER
    assert "to service_role" in LOWER
