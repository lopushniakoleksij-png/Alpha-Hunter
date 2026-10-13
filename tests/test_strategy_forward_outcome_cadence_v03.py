from pathlib import Path

SQL = Path("ops/sql/strategy_forward_outcome_cadence_v03.sql").read_text(
    encoding="utf-8"
).lower()


def test_cadence_is_three_hourly():
    assert "53 */3 * * *" in SQL
    assert "alpha-hunter-strategy-forward-outcome-v01-hourly" in SQL
    assert "active := true" in SQL


def test_change_is_schedule_only():
    for forbidden in [
        "create or replace function",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
