from pathlib import Path

BASE_PATH = Path("ops/sql/v14_control_tower_watchdog_v01.sql")
MIGRATION_PATH = Path("ops/sql/v14_watchdog_storage_semantics_v02.sql")
BASE = BASE_PATH.read_text(encoding="utf-8").lower()
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_watchdog_reads_storage_growth_status_internally():
    assert "alpha_hunter_storage_growth_status_v01" in BASE
    assert "left join storage_growth g on true" in BASE


def test_active_compaction_regression_has_specific_warning():
    assert "storage_compaction_regression" in BASE
    assert "current_write_compaction_status" in BASE


def test_compact_current_writes_reclassify_to_historical_backlog():
    assert "storage_historical_toast_backlog_review_required" in BASE
    assert "current_writes_compact" in BASE


def test_generic_toast_warning_remains_fail_closed_without_growth_telemetry():
    assert "storage_live_toast_review_required" in BASE


def test_explicit_migration_preserves_watchdog_schema_and_safety():
    assert MIGRATION_PATH.parent.as_posix() == "ops/sql"
    assert "create or replace view public.alpha_hunter_v14_watchdog_status_v01" in MIGRATION
    assert "security_invoker=true" in MIGRATION
    assert "security_barrier=true" in MIGRATION
    assert "false as trade_permission" in MIGRATION
    assert "false as production_promotion_permitted" in MIGRATION
    assert "'none'::text as order_path" in MIGRATION


def test_storage_semantics_patch_does_not_add_mutation_or_trade_paths():
    for forbidden in [
        "delete from public.alpha_hunter_",
        "update public.alpha_hunter_",
        "vacuum full",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in MIGRATION
