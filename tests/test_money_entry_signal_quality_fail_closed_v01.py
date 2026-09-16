from pathlib import Path

SQL = Path('money_entry_signal_quality_fail_closed_v01.sql').read_text()


def test_eligible_stage_requires_positive_signal_quality():
    assert 'if new.stage_eligible is true then' in SQL
    assert 'new.scanner_direction_aligned is not true' in SQL
    assert 'new.scanner_momentum_confirmed is not true' in SQL
    assert 'new.scanner_data_integrity_pass is not true' in SQL
    assert "new.stage_status := 'NO_T0'" in SQL
    assert 'new.stage_eligible := false' in SQL


def test_missing_and_false_states_are_explicit_blockers():
    for blocker in [
        'SCANNER_DIRECTION_ALIGNMENT_NOT_CAPTURED',
        'SCANNER_DIRECTION_NOT_ALIGNED',
        'SCANNER_MOMENTUM_NOT_CAPTURED',
        'SCANNER_MOMENTUM_NOT_CONFIRMED',
        'SCANNER_DATA_INTEGRITY_NOT_CAPTURED',
        'SCANNER_DATA_INTEGRITY_NOT_VERIFIED',
    ]:
        assert blocker in SQL


def test_guard_preserves_shadow_only_no_trade_permission_boundary():
    lowered = SQL.lower()
    assert 'new.shadow_only is not true or new.trade_permission is not false' in lowered
    assert "raise exception 'money entry signal-quality safety boundary violation'" in lowered
    assert 'new.shadow_only := true' not in lowered
    assert 'new.trade_permission := false' not in lowered
    assert 'trade_permission=true' not in lowered
    assert 'trade_permission = true' not in lowered
    for forbidden in ['place_order', 'place-order', '/api/v2/mix/order/', '/api/v3/trade/']:
        assert forbidden not in lowered


def test_guard_is_insert_time_and_does_not_rewrite_history():
    assert 'before insert on public.alpha_hunter_money_entry_stage_snapshots' in SQL
    assert 'update public.alpha_hunter_money_entry_stage_snapshots' not in SQL.lower()
    assert 'delete from public.alpha_hunter_money_entry_stage_snapshots' not in SQL.lower()


def test_guard_adds_traceable_evidence():
    assert "'signal_quality_fail_closed', true" in SQL
    assert "'signal_quality_fail_closed_reasons', v_reasons" in SQL
    assert "'signal_quality_guard_version', 'money-entry-signal-quality-v0.1'" in SQL
