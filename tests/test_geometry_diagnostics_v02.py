from pathlib import Path

SQL = Path('geometry_diagnostics_v02.sql').read_text()


def test_v02_preserves_shadow_only_no_execution_authority():
    required = [
        "geometry-diagnostics-v0.2-volatility-context",
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


def test_v02_adds_observed_spread_and_atr_context_without_thresholds():
    required = [
        "{behaviour,spread_pct}",
        "{timeframes,15m,indicators,atr_pct}",
        "{timeframes,1H,indicators,atr_pct}",
        "research_stop_distance_pct",
        "stop_to_spread_multiple",
        "stop_to_atr_15m_multiple",
        "stop_to_atr_1h_multiple",
        "research_rr_is_theoretical",
    ]
    for marker in required:
        assert marker in SQL

    # The new volatility ratios are descriptive evidence only. No hardcoded
    # minimum spread/ATR multiple may become an execution gate in this patch.
    forbidden_threshold_phrases = [
        "min_stop_to_spread",
        "min_stop_to_atr",
        "max_stop_to_atr",
        "STOP_TO_SPREAD_TOO_LOW",
        "STOP_TO_ATR_TOO_LOW",
    ]
    for marker in forbidden_threshold_phrases:
        assert marker not in SQL


def test_v02_runs_diagnostics_before_existing_controlled_stage():
    geometry_call = "v_geometry := private.alpha_hunter_capture_geometry_diagnostics();"
    stage_call = "v_stage := private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',p_reference_at);"
    assert geometry_call in SQL
    assert stage_call in SQL
    assert SQL.index(geometry_call) < SQL.index(stage_call)


def test_hourly_cron_schedule_is_preserved_and_only_command_is_repointed():
    assert "alpha-hunter-money-entry-stage-hourly" in SQL
    assert "cron.alter_job" in SQL
    assert "command := 'select private.alpha_hunter_run_money_entry_stage_with_geometry(clock_timestamp());'" in SQL
    # This patch must not reschedule the canonical :13 stage.
    assert "schedule :=" not in SQL
