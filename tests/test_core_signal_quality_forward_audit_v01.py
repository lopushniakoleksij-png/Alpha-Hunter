from pathlib import Path

CONTRACT = Path('CORE_EXECUTION_SIGNAL_QUALITY_CONTRACT.md').read_text()
SQL = Path('money_entry_signal_quality_forward_audit_v01.sql').read_text()
GUARD = Path('money_entry_signal_quality_fail_closed_v01.sql').read_text()


def test_core_contract_is_permanent_and_fail_closed():
    assert 'CORE / PERMANENT / FAIL-CLOSED' in CONTRACT
    assert 'READY = EXECUTABLE CONFLUENCE, NOT CONFIDENCE.' in CONTRACT
    assert 'No momentum = no READY.' in CONTRACT
    for required in [
        'scanner_direction_aligned = true',
        'scanner_momentum_confirmed = true',
        'scanner_data_integrity_pass = true',
    ]:
        assert required in CONTRACT


def test_persistence_guard_enforces_the_same_contract():
    for field in [
        'new.scanner_direction_aligned is not true',
        'new.scanner_momentum_confirmed is not true',
        'new.scanner_data_integrity_pass is not true',
    ]:
        assert field in GUARD
    assert "new.stage_status := 'NO_T0'" in GUARD
    assert 'new.stage_eligible := false' in GUARD


def test_forward_audit_detects_all_signal_quality_violations():
    assert 'eligible_direction_failures' in SQL
    assert 'eligible_momentum_failures' in SQL
    assert 'eligible_integrity_failures' in SQL
    assert 'safety_boundary_violations' in SQL
    assert 'scanner_direction_aligned is not true' in SQL
    assert 'scanner_momentum_confirmed is not true' in SQL
    assert 'scanner_data_integrity_pass is not true' in SQL


def test_forward_audit_is_append_only_and_hourly():
    assert 'trg_ah_signal_quality_forward_audits_append_only' in SQL
    assert 'private.alpha_hunter_block_append_only_mutation()' in SQL
    assert "'22 * * * *'" in SQL
    assert "'alpha-hunter-signal-quality-forward-audit-hourly'" in SQL
    assert 'on conflict(hour_bucket_utc) do nothing' in SQL.lower()


def test_forward_audit_cannot_grant_trade_permission():
    lowered = SQL.lower()
    assert 'shadow_only boolean not null default true check (shadow_only=true)' in lowered
    assert 'trade_permission boolean not null default false check (trade_permission=false)' in lowered
    assert "'audit_is_execution_permission',false" in lowered
    assert "'shadow_only',true" in lowered
    assert "'trade_permission',false" in lowered
    for forbidden in [
        'trade_permission=true',
        'trade_permission = true',
        'place_order',
        'place-order',
        '/api/v2/mix/order/',
        '/api/v3/trade/',
    ]:
        assert forbidden not in lowered


def test_forward_test_tracks_explicit_signal_quality_blockers():
    for blocker in [
        'SCANNER_DIRECTION_ALIGNMENT_NOT_CAPTURED',
        'SCANNER_DIRECTION_NOT_ALIGNED',
        'SCANNER_MOMENTUM_NOT_CAPTURED',
        'SCANNER_MOMENTUM_NOT_CONFIRMED',
        'SCANNER_DATA_INTEGRITY_NOT_CAPTURED',
        'SCANNER_DATA_INTEGRITY_NOT_VERIFIED',
    ]:
        assert blocker in SQL
