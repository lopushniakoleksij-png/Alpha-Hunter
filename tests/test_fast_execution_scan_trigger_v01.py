from pathlib import Path

SQL = Path("fast_execution_scan_trigger_v01.sql").read_text().lower()


def test_fast_scan_keeps_trade_permission_false():
    assert "trade_permission boolean not null default false" in SQL
    assert "trade_permission',false" in SQL
    assert "trade_permission=true" not in SQL
    assert "trade_permission = true" not in SQL


def test_fast_scan_calls_scanner_not_exchange_order_path():
    assert "alpha-hunter-j5i3.onrender.com/api/run-scan" in SQL
    for forbidden in [
        "/api/v2/mix/order/",
        "/api/v3/trade/",
        "place_order",
        "place-order",
        "create_order",
    ]:
        assert forbidden not in SQL


def test_schedule_preserves_hourly_and_adds_only_three_offset_scans():
    assert "'7,27,47 * * * *'" in SQL
    assert "alpha-hunter-fast-execution-scan-v01" in SQL
    assert "protected top-of-hour production scan unchanged" in SQL


def test_trigger_has_append_only_audit_and_fail_visible_result():
    assert "alpha_hunter_fast_scan_trigger_events" in SQL
    assert "alpha_hunter_block_append_only_mutation" in SQL
    assert "exception when others" in SQL
    assert "'accepted',false" in SQL


def test_trigger_does_not_modify_strategy_thresholds():
    for forbidden in [
        "minimum_execution_reward_risk",
        "minimum_reward_risk",
        "minimum_execution_score",
        "minimum_discovery_score",
    ]:
        assert forbidden not in SQL
