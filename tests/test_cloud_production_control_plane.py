from pathlib import Path

SQL = Path('alpha_hunter_cloud_control_plane.sql').read_text()


def test_fail_closed_flags_are_database_constrained():
    assert 'check (production_execution_enabled = false)' in SQL
    assert 'check (research_trade_permission = false)' in SQL
    assert SQL.count('check (trade_permission = false)') >= 3
    assert SQL.count('check (shadow_only = true)') >= 3


def test_controlled_stage_order_is_explicit():
    expected = [
        "when 'ANSWER_KEY' then 1",
        "when 'PARENT_DIRECTION' then 2",
        "when 'MONEY_ENTRY_BRIDGE' then 3",
        "when 'MONEY_SCORECARD' then 4",
    ]
    for token in expected:
        assert token in SQL
    assert "PREDECESSOR_NOT_SUCCESSFUL:" in SQL


def test_same_hour_stage_is_idempotent():
    assert "s.status in ('PASS','DEGRADED')" in SQL
    assert "'deduplicated',true" in SQL
    assert 'pg_advisory_xact_lock' in SQL


def test_evidence_streams_are_append_only():
    assert 'trg_ah_control_steps_append_only' in SQL
    assert 'trg_ah_control_health_append_only' in SQL
    assert 'trg_ah_incident_events_append_only' in SQL
    assert 'append-only Alpha Hunter evidence cannot be updated or deleted' in SQL


def test_private_definer_functions_pin_search_path():
    assert "create or replace function private.alpha_hunter_run_controlled_stage" in SQL
    assert "create or replace function private.alpha_hunter_finalize_control_plane_hour" in SQL
    assert SQL.count("security definer\nset search_path = ''") >= 2
    assert "alter function private.alpha_hunter_run_big_mover_money_scorecard() set search_path = '';" in SQL


def test_scheduler_routes_all_stages_through_control_plane():
    required = [
        "alpha-hunter-big-mover-shadow-hourly','10 * * * *'",
        "alpha-hunter-big-mover-parent-direction-hourly','11 * * * *'",
        "alpha-hunter-big-mover-money-entry-bridge-hourly','12 * * * *'",
        "alpha-hunter-big-mover-money-scorecard-hourly','14 * * * *'",
        "alpha-hunter-control-plane-finalize-hourly','20 * * * *'",
        "alpha_hunter_run_controlled_stage('ANSWER_KEY'",
        "alpha_hunter_run_controlled_stage('PARENT_DIRECTION'",
        "alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE'",
        "alpha_hunter_run_controlled_stage('MONEY_SCORECARD'",
    ]
    for token in required:
        assert token in SQL


def test_health_gate_checks_freshness_order_source_and_safety():
    for token in [
        'HOURLY_SOURCE_MAX_AGE_90_MINUTES',
        'SOURCE_RUN_ID_MISMATCH',
        'STAGE_ORDER_NOT_PROVEN',
        'SAFETY_BOUNDARY_VIOLATION',
        'MISSING_OR_UNSUCCESSFUL_STAGE',
    ]:
        assert token in SQL
    assert "when v_safety='FAIL'" in SQL
    assert "then 'FAILED'" in SQL


def test_no_order_or_private_exchange_path_added():
    lowered = SQL.lower()
    forbidden = [
        'place-order',
        'place_order',
        '/api/v2/mix/order/place-order',
        'automatic_trade_execution=true',
        'trade_permission=true',
    ]
    for token in forbidden:
        assert token not in lowered
