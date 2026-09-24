from pathlib import Path

SQL = Path("canonical_universe_scan_persistence_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_legacy_symbol_hour_uniqueness_is_removed():
    assert "drop constraint if exists" in SQL
    assert "alpha_hunter_universe_hourly_symbol_hour_bucket_utc_key" in SQL


def test_scan_identity_is_unique_per_symbol_and_selection_run():
    assert "unique index" in SQL
    assert "(symbol,selection_run_id)" in SQL
    assert "where selection_run_id is not null" in SQL


def test_hour_bucket_is_kept_only_for_aggregation_compatibility():
    assert "hour_bucket_utc remains an aggregation field" in SQL
    assert "selection_run_id" in SQL
    assert "canonical scan identity" in SQL


def test_migration_does_not_add_trade_authority():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in SQL
