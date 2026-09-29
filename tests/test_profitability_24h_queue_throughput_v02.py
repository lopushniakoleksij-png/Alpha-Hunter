from pathlib import Path

SQL = Path("ops/sql/profitability_24h_queue_throughput_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_burst_reuses_bounded_queue_collector():
    assert "for v_pass in 1..3 loop" in SQL
    assert "alpha_hunter_capture_strategy_24h_queue_v01()" in SQL
    assert "'max_rows_per_pass',30" in SQL
    assert "'max_rows_per_run',90" in SQL


def test_burst_schedule_avoids_render_scan_boundaries():
    assert "schedule := '14,26,35 * * * *'" in SQL


def test_burst_stays_paper_only_and_no_trade_authority():
    assert "'paper_only',true" in SQL
    assert "'trade_permission',false" in SQL
    assert "'production_promotion_permitted',false" in SQL
    assert "'order_path','none'" in SQL
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
