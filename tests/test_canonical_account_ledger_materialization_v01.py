from pathlib import Path

SQL = Path("canonical_account_ledger_materialization_v01.sql").read_text(encoding="utf-8")


def test_materialization_is_forward_only_snapshot_insert_trigger():
    assert "after insert on public.alpha_hunter_snapshots" in SQL.lower()
    assert "for each row execute function private.alpha_hunter_materialize_account_ledger_from_snapshot()" in SQL
    assert "update public.alpha_hunter_snapshots" not in SQL.lower()
    assert "delete from public.alpha_hunter_snapshots" not in SQL.lower()
    assert "backfill" in SQL.lower()


def test_identity_contract_matches_python_account_ledger_version():
    assert "'canonical-account-ledger-v0.1|' || new.run_id" in SQL
    assert "'canonical-account-ledger-v0.1|' || v_account_snapshot_id || '|'" in SQL
    assert "extensions.digest(" in SQL
    assert "'sha256'" in SQL
    assert "substr(" in SQL and "32" in SQL


def test_connected_requires_schema_validation_and_exact_position_count():
    required = [
        "upper(coalesce(a.value->>'margin_coin',''))='USDT'",
        "ACCOUNT_ACCOUNT_EQUITY_INVALID",
        "ACCOUNT_AVAILABLE_INVALID",
        "ACCOUNT_UNREALIZED_PL_INVALID",
        "OPEN_POSITION_COUNT_CLAIM_MISMATCH",
        "OPEN_POSITION_SCHEMA_INVALID",
        "OPEN_POSITION_DUPLICATE_SYMBOL_DIRECTION",
        "v_schema_validated := jsonb_array_length(v_schema_errors)=0",
        "v_connection_status := 'CONNECTED_READ_ONLY'",
    ]
    for text in required:
        assert text in SQL


def test_not_configured_is_explicitly_disconnected_and_not_verified():
    assert "elsif v_scanner_status = 'NOT_CONFIGURED'" in SQL
    assert "v_connection_status := 'DISCONNECTED'" in SQL
    assert "PRIVATE_API_NOT_CONFIGURED" in SQL


def test_position_rows_do_not_invent_risk_or_structural_stop():
    assert "structural_stop_inferred_from_exchange_stop',false" in SQL
    assert "planned_risk_invented',false" in SQL
    assert "notional_invented',false" in SQL
    assert "daily_realized_pnl_invented',false" in SQL
    assert "margin_used_inferred_from_locked',false" in SQL


def test_no_exchange_or_http_path_is_added():
    lowered = SQL.lower()
    assert "api.bitget.com" not in lowered
    assert "http_post" not in lowered
    assert "http_get" not in lowered
    assert "place_order" not in lowered
    assert "submit_order" not in lowered
    assert "no_extra_bitget_request',true" in SQL
    assert "no_exchange_call',true" in SQL


def test_materialization_is_append_only_and_trade_permission_false():
    assert "alpha_hunter_account_ledger_materialization_events" in SQL
    assert "private.alpha_hunter_block_append_only_mutation()" in SQL
    assert "shadow_only boolean not null default true check (shadow_only=true)" in SQL
    assert "trade_permission boolean not null default false check (trade_permission=false)" in SQL
    assert "true,\n    false" in SQL


def test_ledger_failure_preserves_primary_snapshot_and_fails_readiness_closed():
    assert "exception when others then" in SQL
    assert "Account-ledger failure must never destroy the canonical market snapshot" in SQL
    assert "'snapshot_persistence_preserved',true" in SQL
    assert "'readiness_fail_closed',true" in SQL
    assert SQL.count("return new;") >= 2


def test_idempotent_with_python_writer():
    assert "on conflict(account_snapshot_id) do nothing" in SQL
    assert "on conflict(position_snapshot_id) do nothing" in SQL
    assert "on conflict(event_id) do nothing" in SQL
