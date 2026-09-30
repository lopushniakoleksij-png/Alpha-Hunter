from pathlib import Path

SQL = Path("ops/sql/restore_money_entry_progression_trigger_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_only_forward_trigger_restoration():
    assert "enable trigger trg_ah_after_portfolio_risk_capture_progression" in SQL
    assert "historical_backfill_permitted" in SQL
    assert "false as historical_backfill_permitted" in SQL


def test_backfill_function_is_not_invoked():
    assert "select private.alpha_hunter_backfill_money_entry_progressions" not in SQL
    assert "perform private.alpha_hunter_backfill_money_entry_progressions" not in SQL


def test_no_threshold_or_trade_authority():
    for marker in [
        "false as trade_permission",
        "false as threshold_activation_permitted",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "threshold_activation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_trigger_dependencies_must_exist():
    assert "required progression trigger is missing" in SQL
    assert "required progression trigger function is missing" in SQL
