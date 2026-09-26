from pathlib import Path

SQL_PATH = Path("ops/sql/bitget_account_scope_diagnostic_v02.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_v02_is_ops_only_and_outside_scientific_fingerprint():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SQL_PATH.name not in [p.name for p in Path(".").glob("*.sql")]


def test_v02_preserves_missing_historical_identity_as_unknown():
    assert "historical_identity_not_comparable" in LOWER
    assert "historical_fingerprint_observations" in LOWER
    assert "historical_subaccount_observations" in LOWER
    assert (
        "continuity_conflict_historical_identity_not_comparable"
        in LOWER
    )
    assert (
        "independently_verify_intended_bitget_account_or_subaccount_before_any_pinning_or_credential_change"
        in LOWER
    )


def test_v02_requires_direct_fingerprint_evidence_for_proven_mismatch():
    assert "proven_fingerprint_mismatch" in LOWER
    assert "historical_different_fingerprint_fill_runs" in LOWER
    assert "historical_same_fingerprint_fill_runs" in LOWER
    assert "proven_fingerprint_mismatch'" in LOWER


def test_v02_does_not_default_missing_subaccount_history_to_false():
    historical_segment = LOWER.split(
        "historical_fill_lane as (", 1
    )[1].split("fingerprint_comparison as (", 1)[0]
    assert "coalesce(" not in historical_segment[
        historical_segment.find("account_is_subaccount") :
    ]
    assert "historical_subaccount_observations" in historical_segment


def test_v02_does_not_expose_raw_bitget_identity_or_secrets():
    for marker in [
        "->>'uid'",
        "->>'userid'",
        "->>'user_id'",
        "->>'parentid'",
        "->>'parent_id'",
        "api_key",
        "secret_key",
        "passphrase",
    ]:
        assert marker not in LOWER


def test_v02_is_read_only_and_no_order_authority():
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


def test_v02_is_service_role_only():
    assert (
        "revoke all on public.alpha_hunter_bitget_account_scope_diagnostic_v02"
        in LOWER
    )
    assert (
        "grant select on public.alpha_hunter_bitget_account_scope_diagnostic_v02"
        in LOWER
    )
    assert "to service_role" in LOWER
