from pathlib import Path

SQL = Path("money_entry_stage_writer_universe_liquidity_integration_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_liquidity_is_bound_from_canonical_universe_before_stage_evaluation():
    assert "alpha_hunter_stage_universe_liquidity(" in SQL
    assert "b.symbol,b.run_id,b.captured_at_utc" in SQL
    assert "s.universe_liquidity_pass liquidity_ok" in SQL
    assert "source_payload#>>'{execution_setup,checks,liquidity_ok}'" not in SQL
    assert "source_payload#>>'{execution_setup,checks,liquidity_pass}'" not in SQL


def test_binding_is_same_run_same_hour_and_non_future():
    assert "u.selection_run_id=p_source_run_id" in SQL
    assert "u.observed_at_utc<=p_source_captured_at_utc" in SQL
    assert "u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)" in SQL


def test_missing_liquidity_stays_fail_closed():
    assert "LIQUIDITY_PASS_NOT_CAPTURED" in SQL
    assert "LIQUIDITY_NOT_VERIFIED" in SQL
    assert "case when n.liquidity_ok is null" in LOWER


def test_immutable_binding_is_persisted_for_audit():
    assert "universe_observation_id" in SQL
    assert "universe_observed_at_utc" in SQL
    assert "universe_selection_run_id" in SQL
    assert "CANONICAL_UNIVERSE_SAME_RUN_SAME_HOUR_NON_FUTURE" in SQL


def test_no_threshold_or_live_execution_relaxation():
    assert "NO_ACTIVE_VALIDATED_THRESHOLD_SET" in SQL
    assert "exact_stage_claim_requires_active_validated_thresholds" in SQL
    assert "'shadow_only',true" in SQL
    assert "'trade_permission',false" in SQL
    assert "true,false" in SQL
    assert "bitget" not in LOWER
    assert "place_order" not in LOWER
    assert "submit_order" not in LOWER


def test_forward_only_no_historical_stage_rewrite():
    assert "update public.alpha_hunter_money_entry_stage_snapshots" not in LOWER
    assert "delete from public.alpha_hunter_money_entry_stage_snapshots" not in LOWER
    assert "on conflict(source_bridge_id) do nothing" in LOWER
