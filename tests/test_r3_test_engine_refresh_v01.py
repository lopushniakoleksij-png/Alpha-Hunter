from pathlib import Path

SQL = Path("ops/sql/test_engine_direct_gates_v04.sql").read_text(
    encoding="utf-8"
).lower()


def test_refresh_selects_latest_activation():
    assert "order by a.activated_at_utc desc nulls last" in SQL


def test_cron_is_restored_at_safe_minute():
    assert "schedule := '59 * * * *'" in SQL
    assert "active := true" in SQL


def test_refresh_remains_monitor_only():
    for marker in [
        "'paper_only',true",
        "'trade_permission',false",
        "'production_promotion_permitted',false",
        "'order_path','none'",
    ]:
        assert marker in SQL


def test_no_exchange_write_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
