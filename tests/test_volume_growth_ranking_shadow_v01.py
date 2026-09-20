from pathlib import Path

SQL = Path("volume_growth_ranking_shadow_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_challenger_uses_only_universe_candidate_time_evidence():
    assert "alpha_hunter_universe_hourly" in SQL
    forbidden = [
        "alpha_hunter_big_mover_answer_key",
        "alpha_hunter_forward_missed_mover_audit",
        "signal_outcomes",
        "sealed_outcome",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_volume_growth_formula_and_hour_gap_are_frozen():
    required = [
        "between 3000 and 4200",
        "ln(b.quote_volume_24h/b.previous_quote_volume_24h)",
        "order by f.volume_log_growth desc,f.symbol",
        "volume_growth_rank<=30",
        "VOLUME_GROWTH_TOP30_ZERO_EXTRA_SCAN",
    ]
    for marker in required:
        assert marker in SQL


def test_production_selector_is_control_only_not_mutated():
    assert "u.deep_scan_selected as production_deep_scan_selected" in SQL
    assert "false as production_selector_changed" in SQL
    forbidden = [
        "update public.alpha_hunter_universe_hourly",
        "insert into public.alpha_hunter_universe_hourly",
        "delete from public.alpha_hunter_universe_hourly",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_claim_ceiling_blocks_trade_and_promotion():
    required = [
        "false as outcome_evidence_used",
        "false as t0_authorized",
        "false as threshold_change_permitted",
        "false as production_promotion_permitted",
        "true as shadow_only",
        "false as trade_permission",
        "'NONE'::text as order_path",
        "SHADOW_RANKING_CHALLENGER_ONLY_NOT_EXECUTION_EDGE",
    ]
    for marker in required:
        assert marker in SQL


def test_view_is_service_role_read_only_security_invoker():
    assert "security_invoker=true" in LOWER
    assert "grant select on public.alpha_hunter_volume_growth_ranking_shadow_v01" in LOWER
    assert "to service_role" in LOWER
