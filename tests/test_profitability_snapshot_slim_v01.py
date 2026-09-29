from pathlib import Path

SQL_PATH = Path("ops/sql/profitability_snapshot_slim_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8").lower()


def test_slim_snapshot_mirror_is_private_and_bounded():
    assert "private.alpha_hunter_snapshot_slim_v01" in SQL
    assert "trg_ah_capture_snapshot_slim_v01" in SQL
    assert "min(a.started_at_utc)-interval '1 hour'" in SQL
    assert "clock_timestamp()-interval '7 days'" in SQL


def test_slim_payload_contains_only_gate_metadata():
    for key in [
        "validation_identity",
        "previous_snapshot_context",
        "catalyst_summary",
        "multi_strategy_summary",
    ]:
        assert key in SQL


def test_fast_views_are_derived_from_current_production_definitions():
    for source in [
        "public.alpha_hunter_strategy_paper_economics_v01",
        "public.alpha_hunter_profitability_validation_status_v01",
        "public.alpha_hunter_profitability_cadence_integrity_v01",
        "public.alpha_hunter_profitability_sample_integrity_v01",
    ]:
        assert f"pg_get_viewdef(\n    '{source}'::regclass" in SQL
    assert "security_invoker=true,security_barrier=true" in SQL


def test_fast_views_substitute_only_snapshot_path():
    assert "private.alpha_hunter_strategy_paper_economics_fast_v01" in SQL
    assert "private.alpha_hunter_profitability_validation_status_fast_v01" in SQL
    assert "private.alpha_hunter_profitability_cadence_integrity_fast_v01" in SQL
    assert "private.alpha_hunter_profitability_sample_integrity_fast_v01" in SQL
    assert "replace(v_def,'alpha_hunter_snapshots','private.alpha_hunter_snapshot_slim_v01')" in SQL


def test_v04_refresh_uses_fast_gate_views():
    assert "alpha_hunter_refresh_test_engine_v04()" in SQL
    assert "realtime-test-engine-db-v0.4-slim" in SQL
    for view in [
        "private.alpha_hunter_profitability_validation_status_fast_v01",
        "private.alpha_hunter_profitability_cadence_integrity_fast_v01",
        "private.alpha_hunter_profitability_sample_integrity_fast_v01",
    ]:
        assert view in SQL


def test_v04_remains_fail_closed_and_non_trading():
    for marker in [
        "validated_execution_cost_model_missing",
        "realistic_net_r_claim_not_permitted",
        "cadence_integrity_failed",
        "sample_integrity_failed",
        "'trade_permission',false",
        "'production_promotion_permitted',false",
        "'order_path','none'",
    ]:
        assert marker in SQL

    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
