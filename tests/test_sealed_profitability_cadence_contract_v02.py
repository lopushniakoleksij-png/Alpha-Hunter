from pathlib import Path

SQL = Path("sealed_profitability_cadence_contract_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_contract_allows_only_20m_or_60m_cadence():
    assert "expected_frequency_minutes in (20,60)" in SQL


def test_interval_bounds_are_relative_to_expected_frequency():
    assert "minimum_interval_minutes <= expected_frequency_minutes" in SQL
    assert "maximum_interval_minutes >= expected_frequency_minutes" in SQL
    assert "maximum_interval_minutes >= minimum_interval_minutes" in SQL


def test_contract_does_not_change_trade_authority():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in SQL
