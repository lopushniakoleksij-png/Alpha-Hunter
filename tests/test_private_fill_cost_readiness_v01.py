from pathlib import Path

SQL = Path("private_fill_cost_readiness_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_private_fill_readiness_never_exposes_account_fingerprint():
    assert "account_identity_fingerprint" not in SQL
    assert "user_id" not in SQL
    assert "userid" not in SQL


def test_unpinned_or_mismatched_identity_blocks_readiness():
    required = [
        "blocked_account_identity_unpinned",
        "blocked_account_identity_mismatch",
        "account_identity_expected_configured",
        "account_identity_match",
    ]
    for marker in required:
        assert marker in SQL


def test_incomplete_fill_traceability_blocks_readiness():
    assert "blocked_fill_traceability_incomplete" in SQL
    assert "fill_traceability_complete" in SQL
    assert "fill_schema_validated" in SQL


def test_view_is_read_only_and_non_authoritative():
    required = [
        "true as audit_only",
        "true as read_only",
        "true as shadow_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL
