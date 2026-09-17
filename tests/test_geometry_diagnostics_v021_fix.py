from pathlib import Path

SQL = Path('geometry_diagnostics_v021_fix.sql').read_text()


def test_v021_uses_unique_scanner_aliases():
    required = [
        "source_volume_state_1h",
        "source_market_phase",
        "source_opportunity_timing",
        "'market_phase',m.source_market_phase",
        "'opportunity_timing',m.source_opportunity_timing",
        "'volume_state_1h',m.source_volume_state_1h",
    ]
    for marker in required:
        assert marker in SQL

    # Regression for the production-smoke ambiguity caught in v0.2.
    assert "as opportunity_timing" not in SQL
    assert "as market_phase" not in SQL
    assert "as volume_state_1h" not in SQL


def test_v021_preserves_shadow_only_contract():
    required = [
        "geometry-diagnostics-v0.2.1-volatility-context",
        "research_geometry_is_not_execution_permission",
        "volatility_context_is_descriptive_only",
        "stage_eligibility_changed',false",
        "thresholds_invented',false",
        "shadow_only',true",
        "trade_permission',false",
        "set search_path=''",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
        "insert into public.alpha_hunter_money_entry_threshold_sets",
        "update public.alpha_hunter_money_entry_threshold_sets",
        "create or replace function private.alpha_hunter_capture_money_entry_stage_snapshots",
    ]
    for marker in forbidden:
        assert marker not in SQL


def test_v021_preserves_hourly_schedule_and_wrapper_order():
    geometry_call = "v_geometry := private.alpha_hunter_capture_geometry_diagnostics();"
    stage_call = "v_stage := private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',p_reference_at);"
    assert geometry_call in SQL
    assert stage_call in SQL
    assert SQL.index(geometry_call) < SQL.index(stage_call)
    assert "alpha-hunter-money-entry-stage-hourly" in SQL
    assert "schedule :=" not in SQL
