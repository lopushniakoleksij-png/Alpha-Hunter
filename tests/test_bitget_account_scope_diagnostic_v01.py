from pathlib import Path

SQL_PATH = Path("ops/sql/bitget_account_scope_diagnostic_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_scope_diagnostic_is_ops_only_and_outside_scientific_fingerprint():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SQL_PATH.name not in [p.name for p in Path(".").glob("*.sql")]


def test_scope_diagnostic_does_not_expose_raw_identity_values():
    assert "account_identity_fingerprint" in LOWER
    assert "uid" not in LOWER
    assert "parentid" not in LOWER
    assert "parent_id" not in LOWER
    assert "account_fp" not in LOWER
    assert "scientific_fingerprint" not in LOWER


def test_scope_diagnostic_requires_strong_contemporaneous_evidence():
    for marker in [
        "current_account_is_subaccount=true",
        "current_equity_usdt=0",
        "current_fill_count",
        "historical_fill_producing_runs_after_first_seen",
        "historical_max_equity_usdt",
        "complete=true",
        "schema_validated=true",
    ]:
        assert marker in LOWER


def test_scope_diagnostic_is_read_only_and_no_trade_authority():
    for marker in [
        "true as audit_only",
        "true as read_only",
        "true as shadow_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
        "security_invoker=true",
    ]:
        assert marker in LOWER

    for forbidden in [
        " insert ",
        " update ",
        " delete ",
        " truncate ",
        " alter table ",
        " drop table ",
        " place_order",
        " cancel_order",
        " modify_order",
        " set_leverage",
    ]:
        assert forbidden not in LOWER


def test_scope_diagnostic_has_precise_probable_mismatch_status():
    assert "probable_account_scope_mismatch" in LOWER
    assert "probable_account_scope_mismatch'" in LOWER
    assert (
        "verify_and_replace_render_bitget_read_only_credentials_with_intended_fill_producing_account"
        in LOWER
    )


def test_scope_diagnostic_is_service_role_only():
    assert "revoke all on public.alpha_hunter_bitget_account_scope_diagnostic_v01" in LOWER
    assert "grant select on public.alpha_hunter_bitget_account_scope_diagnostic_v01" in LOWER
    assert "to service_role" in LOWER
