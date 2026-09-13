from pathlib import Path


SQL = Path("money_entry_progression_ledger_v02.sql").read_text(encoding="utf-8")


def test_progression_ledger_is_shadow_only_and_append_only():
    assert "alpha_hunter_money_entry_candidate_episodes" in SQL
    assert "alpha_hunter_money_entry_stage_progressions" in SQL
    assert "alpha_hunter_money_entry_progression_anomalies" in SQL
    assert SQL.count("check (shadow_only=true)") >= 3
    assert SQL.count("check (trade_permission=false)") >= 3
    assert SQL.count("before update or delete") >= 3
    assert "production_permissions_changed',false" in SQL
    assert "thresholds_activated_by_this_ledger',false" in SQL


def test_progression_freezes_required_money_entry_evidence():
    required = (
        "candidate_entry",
        "structural_invalidation_price",
        "stop_distance_pct",
        "remaining_r",
        "direction_1h",
        "direction_12h",
        "direction_1d",
        "liquidity_state",
        "liquidity_ok",
        "participation_emerging",
        "participation_confirmed",
        "acceptance_confirmed",
        "trigger_confirmed",
        "expansion_confirmed",
        "portfolio_risk_decision",
        "portfolio_exposure",
    )
    for field in required:
        assert field in SQL


def test_t0_anchors_episode_and_progression_is_monotonic():
    assert "t0_is_episode_anchor',true" in SQL
    assert "ORPHAN_STAGE_WITHOUT_T0" in SQL
    assert "STAGE_REGRESSION" in SQL
    assert "REPEATED_STAGE_IGNORED" in SQL
    assert "unique(candidate_episode_id,stage_rank)" in SQL
    assert "stage_jump" in SQL


def test_confirmation_tax_is_measured_from_t0_not_confidence():
    assert "confirmation_tax_r" in SQL
    assert "confirmation_price_tax_pct" in SQL
    assert "T0 remaining-R minus current-stage remaining-R" in SQL
    assert "Direction-normalized entry deterioration versus observed T0" in SQL


def test_progression_capture_runs_after_portfolio_risk_insert():
    assert "trg_ah_after_portfolio_risk_capture_progression" in SQL
    assert "after insert on public.alpha_hunter_portfolio_risk_assessments" in SQL
    assert "alpha_hunter_record_money_entry_progression(new.risk_assessment_id)" in SQL
    assert "risk_policy_id" in SQL
    assert "aggregate_open_risk_usdt" in SQL
    assert "symbol_position_conflict" in SQL
