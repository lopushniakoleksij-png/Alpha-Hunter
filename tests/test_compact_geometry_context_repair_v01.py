from pathlib import Path

FEATURE = Path("alpha_hunter/feature_capture.py").read_text(encoding="utf-8")
SQL = Path("ops/sql/compact_geometry_context_repair_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_compact_payload_keeps_minimum_geometry_context():
    assert 'signal-source-v0.3-geometry-context' in FEATURE
    assert '_compact_timeframe_context' in FEATURE
    for marker in [
        '"15m"',
        '"1H"',
        '"4H"',
        '"support"',
        '"resistance"',
        '"atr_pct"',
        '"volume_anomaly"',
    ]:
        assert marker in FEATURE
    assert 'compact["timeframes"] = timeframes' in FEATURE


def test_db_bridge_uses_exact_run_and_symbol():
    assert "s.run_id=new.run_id" in SQL
    assert "s.symbol=new.symbol" in SQL
    assert "canonical_symbol_snapshot_exact_run_symbol" in SQL


def test_db_bridge_is_forward_only_and_fail_open():
    assert "before insert on public.alpha_hunter_signal_features" in SQL
    assert "no existing alpha_hunter_signal_features row is updated" in SQL
    assert "feature_insert_fail_open" in SQL
    assert "exception when others" in SQL
    assert "return new" in SQL


def test_db_bridge_does_not_duplicate_full_timeframes():
    assert "'full_raw_timeframes_duplicated',false" in SQL
    assert "last_closed_candle" not in SQL
    assert "latest_candle" not in SQL


def test_no_trade_or_promotion_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
