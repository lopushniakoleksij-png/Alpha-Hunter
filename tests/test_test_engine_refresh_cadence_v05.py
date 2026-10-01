from pathlib import Path

SQL = Path("ops/sql/test_engine_refresh_cadence_v05.sql").read_text(encoding="utf-8").lower()


def test_refresh_stays_inside_existing_freshness_gate():
    assert "5,25,45 * * * *" in SQL
    assert "alpha_hunter_refresh_test_engine_v04" in SQL


def test_refresh_cadence_does_not_change_trade_authority():
    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
