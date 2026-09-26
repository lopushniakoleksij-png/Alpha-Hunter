from pathlib import Path

SQL = Path(
    "ops/sql/private_fill_history_continuity_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_private_fill_continuity_audit_is_read_only():
    required = [
        "alpha_hunter_private_fill_history_continuity_v01",
        "historical_fill_rows_same_window",
        "historical_fill_continuity_conflict",
        "historical_fill_continuity_conflict",
        "verify_render_bitget_account_before_pinning",
        "false as trade_permission",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "insert into public.",
        "update public.",
        "delete from public.",
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_continuity_conflict_requires_zero_current_and_prior_same_window_fills():
    assert "coalesce(c.fill_count,0)=0" in LOWER
    assert "coalesce(h.historical_fill_rows_same_window,0)>0" in LOWER
    assert "e.fill_time_utc>=c.window_start_utc" in LOWER
    assert "e.fill_time_utc<=c.window_end_utc" in LOWER
    assert "e.evidence->>'endpoint'" in LOWER
    assert "c.endpoint" in LOWER


def test_audit_does_not_claim_account_identity():
    comment = (
        "it does not assert account identity"
    )
    assert comment in LOWER
    assert "account_identity_fingerprint" not in LOWER
