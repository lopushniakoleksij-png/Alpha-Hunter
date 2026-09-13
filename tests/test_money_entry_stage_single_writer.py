from pathlib import Path

SQL = Path('money_entry_stage_single_writer.sql').read_text()


def test_no_threshold_values_are_activated_or_invented():
    assert 'create table if not exists public.alpha_hunter_money_entry_threshold_sets' in SQL
    assert "where t.status='ACTIVE'" in SQL
    assert "NO_ACTIVE_VALIDATED_THRESHOLD_SET" in SQL
    assert 'insert into public.alpha_hunter_money_entry_threshold_sets' not in SQL.lower()
    # Old PR #6 fixture numbers must not be ported as production threshold values.
    assert 'max_t0_stop_distance_pct,3.0' not in SQL.replace(' ', '')
    assert 'min_t0_remaining_r,3.0' not in SQL.replace(' ', '')
    assert 'min_t1_remaining_r,2.0' not in SQL.replace(' ', '')
    assert 'min_t2_remaining_r,1.5' not in SQL.replace(' ', '')


def test_stage_evidence_is_append_only_and_fail_closed():
    assert 'alpha_hunter_money_entry_stage_snapshots' in SQL
    assert 'trg_ah_money_entry_stage_snapshots_append_only' in SQL
    assert "stage_status in (\n    'DATA_INSUFFICIENT','NO_T0','T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'" in SQL
    assert 'check (shadow_only=true)' in SQL
    assert 'check (trade_permission=false)' in SQL


def test_missing_live_bindings_are_explicit_blockers_not_assumptions():
    for blocker in [
        'LIQUIDITY_PASS_NOT_CAPTURED',
        'PARTICIPATION_EMERGING_NOT_CAPTURED',
        'OPEN_POSITION_CONFLICT_NOT_CAPTURED',
        'STRUCTURAL_INVALIDATION_VALIDITY_NOT_CAPTURED',
        'T1_ACCEPTANCE_NOT_CAPTURED',
        'T1_TRIGGER_NOT_CAPTURED',
        'T2_EXPANSION_NOT_CAPTURED',
    ]:
        assert blocker in SQL


def test_scanner_direction_must_match_research_direction():
    assert 'SCANNER_EXECUTION_DIRECTION_MISSING' in SQL
    assert 'SCANNER_EXECUTION_DIRECTION_CONFLICT' in SQL
    assert 'execution_setup_direction<>n.direction' in SQL


def test_control_plane_has_single_writer_between_bridge_and_scorecard():
    assert "when 'MONEY_ENTRY_BRIDGE' then 3" in SQL
    assert "when 'MONEY_ENTRY_STAGE' then 4" in SQL
    assert "when 'MONEY_SCORECARD' then 5" in SQL
    assert "when 4 then 'MONEY_ENTRY_BRIDGE'" in SQL
    assert "when 5 then 'MONEY_ENTRY_STAGE'" in SQL
    assert "alpha-hunter-money-entry-stage-hourly','13 * * * *'" in SQL
    assert 'expected_stage_count,5' in SQL


def test_future_scorecard_candidates_link_exact_stage_snapshot():
    assert 'money_entry_stage_snapshot_id text references public.alpha_hunter_money_entry_stage_snapshots' in SQL
    assert 'left join public.alpha_hunter_money_entry_stage_snapshots ms on ms.source_bridge_id=b.bridge_id' in SQL
    assert "'money_entry_stage_snapshot_id',s.stage_snapshot_id" in SQL
    assert "'EXACT_STAGE_SNAPSHOT_LINKED_PENDING_OUTCOME'" in SQL


def test_stage_writer_is_single_source_and_contemporaneous():
    assert "where b.run_id=v_source_run_id" in SQL
    assert "md5('money-entry-stage-single-writer-v0.1|'||s.bridge_id)" in SQL
    assert "'stage_snapshot_is_contemporaneous',true" in SQL
    assert "'stable_episode_id_status','NOT_BOUND_TO_STABLE_EPISODE'" in SQL


def test_no_live_execution_or_order_route_is_added():
    lowered = SQL.lower()
    for forbidden in [
        'trade_permission=true',
        'shadow_only=false',
        'production_execution_enabled=true',
        'place-order',
        'place_order',
        '/api/v2/mix/order/place-order',
    ]:
        assert forbidden not in lowered
