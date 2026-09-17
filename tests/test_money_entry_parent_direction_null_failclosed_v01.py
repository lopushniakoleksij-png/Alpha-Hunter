from pathlib import Path

SQL = Path('money_entry_parent_direction_null_failclosed_v01.sql').read_text()


def test_null_parent_direction_is_explicitly_fail_closed():
    assert "n.parent_12h_aligned is not true" in SQL
    assert "n.parent_1d_aligned is not true" in SQL
    assert "PARENT_12H_DATA_UNAVAILABLE" in SQL
    assert "PARENT_1D_DATA_UNAVAILABLE" in SQL
    assert "case when not n.parent_12h_aligned" not in SQL
    assert "case when not n.parent_1d_aligned" not in SQL


def test_patch_refuses_unexpected_function_shape():
    assert "expected 12H parent-direction expression not found; refusing unsafe patch" in SQL
    assert "expected 1D parent-direction expression not found; refusing unsafe patch" in SQL
    assert "pg_get_functiondef('private.alpha_hunter_capture_money_entry_stage_snapshots(text)'::regprocedure)" in SQL


def test_safety_boundary_unchanged():
    required = [
        "money-entry-stage-single-writer-v0.4-parent-direction-null-failclosed",
        "revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) from public,anon,authenticated",
        "grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) to service_role",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
        "status='ACTIVE'",
    ]
    for marker in forbidden:
        assert marker not in SQL
