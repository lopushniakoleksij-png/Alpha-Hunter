from pathlib import Path

SQL = Path("ops/sql/pause_endpoint_paper_calibration_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_endpoint_probability_is_not_kept_as_trade_win_probability():
    assert "endpoint_positive_rate_is_not_paper_trade_win_rate" in SQL
    assert "signal_outcome_class_in_win_big_win" in SQL
    assert "67.1428571428571" in SQL
    assert "58.5714285714286" in SQL
    assert "41.6666666666667" in SQL


def test_policy_is_paused_not_deleted():
    assert "set status='paused'" in SQL
    assert "cal-paper-watchshort-67-v01" in SQL
    assert "delete from private.alpha_hunter_calibrated_paper_policy_v01" not in SQL


def test_active_paper_order_blocks_policy_change():
    assert "cannot pause calibration policy while a paper order is active" in SQL
    assert "open_paper" in SQL
    assert "pending_limit_paper" in SQL


def test_no_replacement_policy_is_invented():
    assert "'new_active_calibrated_policy_created',false" in SQL


def test_fail_closed_no_execution_authority():
    assert "trade_permission boolean not null default false" in SQL
    assert "production_promotion_permitted boolean not null default false" in SQL
    assert "order_path text not null default 'none'" in SQL
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
