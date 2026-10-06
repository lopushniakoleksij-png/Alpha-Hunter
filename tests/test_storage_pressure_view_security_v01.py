from pathlib import Path

SQL = Path("ops/sql/storage_pressure_view_security_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_storage_pressure_view_is_security_invoker():
    assert "alter view public.alpha_hunter_storage_pressure_v01" in SQL
    assert "security_invoker=true" in SQL


def test_storage_pressure_view_is_not_publicly_exposed():
    assert "from public,anon,authenticated,service_role" in SQL
    assert "grant select on public.alpha_hunter_storage_pressure_v01" in SQL
    assert "to service_role" in SQL


def test_security_patch_has_no_trading_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
