from pathlib import Path

SQL = Path('money_entry_stage_universe_liquidity_binding_v01.sql').read_text()
WRITER = Path('money_entry_stage_single_writer.sql').read_text()


def test_binding_is_same_run_same_hour_and_non_future():
    assert 'u.selection_run_id=p_source_run_id' in SQL
    assert "u.observed_at_utc<=p_source_captured_at_utc" in SQL
    assert "u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)" in SQL


def test_binding_uses_canonical_universe_liquidity_only():
    assert 'public.alpha_hunter_universe_hourly' in SQL
    assert 'ul.liquidity_pass' in SQL
    assert 'Never fall back to another run/hour or' in SQL


def test_existing_writer_remains_fail_closed_when_liquidity_missing():
    assert "LIQUIDITY_PASS_NOT_CAPTURED" in WRITER
    assert "trade_permission boolean not null default false check (trade_permission=false)" in WRITER
    assert "shadow_only boolean not null default true check (shadow_only=true)" in WRITER


def test_no_historical_stage_mutation_or_scanner_added():
    lowered = SQL.lower()
    assert 'update public.alpha_hunter_money_entry_stage_snapshots' not in lowered
    assert 'delete from public.alpha_hunter_money_entry_stage_snapshots' not in lowered
    assert 'bitget' not in lowered
