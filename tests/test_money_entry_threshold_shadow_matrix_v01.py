from pathlib import Path

SQL = Path("ops/sql/money_entry_threshold_shadow_matrix_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_breaks_threshold_stage_circularity():
    assert "exact t0/t1/t2 production labels require an active validated threshold set" in SQL
    assert "non_circular_threshold_discovery_matrix" in SQL
    assert "exact_t0_t1_t2_claim_permitted" in SQL


def test_pilot_cutoff_is_frozen_before_holdout():
    assert "2026-09-29 15:59:34.163232+00" in SQL
    assert "'pilot_analysis_only'" in SQL
    assert "numeric_thresholds_must_be_frozen_before_holdout" in SQL
    assert "g.candidate_at_utc <= s.pilot_data_cutoff_utc" in SQL


def test_shadow_matrix_reconstructs_non_numeric_stage_gates():
    for marker in [
        "t0_non_numeric_gate",
        "t1_confirmation_gate",
        "t2_confirmation_gate",
        "scanner_direction_aligned",
        "scanner_momentum_confirmed",
        "scanner_data_integrity_pass",
        "liquidity_ok",
        "participation_emerging",
        "acceptance_confirmed",
        "trigger_confirmed",
        "expansion_confirmed",
    ]:
        assert marker in SQL


def test_uses_evaluated_clean_24h_outcomes():
    assert "cal.horizon_hours=24" in SQL
    assert "cal.evaluation_status='evaluated'" in SQL
    assert "cal.calibration_eligible" in SQL
    assert "path_r_pre_cost" in SQL
    assert "stop_survived" in SQL
    assert "target_hit" in SQL


def test_view_uses_security_invoker():
    assert "with (security_invoker=true,security_barrier=true)" in SQL


def test_no_numeric_threshold_or_activation_authority():
    for forbidden in [
        "update public.alpha_hunter_money_entry_threshold_sets",
        "status='validated'",
        "status = 'validated'",
        "status='active'",
        "status = 'active'",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
