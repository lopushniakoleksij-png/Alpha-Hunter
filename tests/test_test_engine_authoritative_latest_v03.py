from pathlib import Path

SQL = Path("test_engine_authoritative_latest_v03.sql").read_text(
    encoding="utf-8"
).lower()


def test_fresh_db_engine_is_preferred():
    assert "realtime-test-engine-db-v0.2" in SQL
    assert "interval '25 minutes'" in SQL
    assert "evaluated_at_utc desc" in SQL


def test_view_keeps_same_public_name():
    assert "create or replace view public.alpha_hunter_test_engine_latest_v01" in SQL


def test_view_does_not_change_trading_authority():
    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "trade_permission = true",
    ]
    for marker in forbidden:
        assert marker not in SQL
