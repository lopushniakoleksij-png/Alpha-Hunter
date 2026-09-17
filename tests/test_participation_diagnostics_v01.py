from pathlib import Path

SQL = Path('participation_diagnostics_v01.sql').read_text()


def test_participation_diagnostics_are_candidate_level_and_append_only():
    required = [
        'alpha_hunter_participation_diagnostics',
        'alpha_hunter_capture_participation_diagnostics',
        'candidate_direction text not null',
        'alpha_hunter_block_append_only_mutation',
        'enable row level security',
        'revoke all on table public.alpha_hunter_participation_diagnostics from public,anon,authenticated',
    ]
    for marker in required:
        assert marker in SQL


def test_no_participation_threshold_is_invented_or_activated():
    assert "participation_threshold_validated',false" in SQL
    assert "participation_decision_derived_by_diagnostics',false" in SQL
    assert "volume_evidence_is_descriptive_only',true" in SQL
    assert "thresholds_invented',false" in SQL
    assert 'min_participation' not in SQL
    assert "status='ACTIVE'" not in SQL


def test_volume_context_is_frozen_without_granting_permission():
    required = [
        "{timeframes,15m,indicators,volume_anomaly,state}",
        "{timeframes,1H,indicators,volume_anomaly,state}",
        "{timeframes,4H,indicators,volume_anomaly,state}",
        'DESCRIPTIVE_VOLUME_EVIDENCE_PRESENT_DECISION_UNDERIVED',
        'SCANNER_PARTICIPATION_CONFIRMED',
        'SCANNER_PARTICIPATION_EMERGING',
        'PARTICIPATION_DATA_ABSENT',
    ]
    for marker in required:
        assert marker in SQL


def test_existing_stage_writer_remains_the_authority():
    assert "private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',p_reference_at)" in SQL
    assert 'stage_eligibility_changed' in SQL
    assert 'private.alpha_hunter_capture_money_entry_stage_snapshots' not in SQL


def test_safety_boundary_is_unchanged():
    required = [
        'shadow_only boolean not null default true check (shadow_only=true)',
        'trade_permission boolean not null default false check (trade_permission=false)',
        "diagnostics_are_not_execution_permission',true",
        'grant execute on function private.alpha_hunter_capture_participation_diagnostics() to service_role',
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        'trade_permission=true',
        'production_execution_enabled=true',
        '/api/v3/trade/place-order',
        '/api/v2/mix/order/place-order',
        'http_get(',
    ]
    for marker in forbidden:
        assert marker not in SQL
