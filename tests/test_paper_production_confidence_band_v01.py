from pathlib import Path

SQL = Path("ops/sql/paper_production_confidence_band_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_policy_matches_user_band_and_existing_rr_floor():
    assert "65.0" in SQL
    assert "70.0" in SQL
    assert "5.0" in SQL
    assert "'paper-prod-65-70-rr5-v01'" in SQL


def test_confidence_is_not_mislabeled_as_validated_win_rate():
    assert "'alpha_hunter_signal_confidence_not_validated_win_rate'" in SQL
    assert "'empirical_win_rate_claim_permitted',false" in SQL
    assert "'model_confidence_not_validated_win_rate'" in SQL


def test_paper_trade_is_forward_only():
    assert "after insert on public.alpha_hunter_signals" in SQL
    assert "do not backfill historical signals" in SQL
    assert "greatest(clock_timestamp(),new.detected_at_utc)" in SQL


def test_geometry_and_rr_fail_closed():
    assert "new.reward_risk<p.minimum_reward_risk" in SQL
    assert "new.stop_loss<new.entry_price and new.entry_price<new.take_profit" in SQL
    assert "new.take_profit<new.entry_price and new.entry_price<new.stop_loss" in SQL


def test_only_one_active_paper_trade():
    assert "max_active_paper_trades" in SQL
    assert "where state='filled_paper'" in SQL


def test_no_live_exchange_authority():
    for marker in [
        "paper_only boolean not null default true",
        "live_order_authority boolean not null default false",
        "live_exchange_order_sent boolean not null default false",
        "trade_permission boolean not null default false",
        "'bitget_order_sent',false",
        "'live_money_permitted',false",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "live_exchange_order_sent=true",
    ]:
        assert forbidden not in SQL
