from pathlib import Path

BASE_PATH = Path("ops/sql/v14_control_tower_watchdog_v01.sql")
MIGRATION_PATH = Path(
    "ops/sql/v14_watchdog_control_plane_semantics_v02.sql"
)
BASE = BASE_PATH.read_text(encoding="utf-8")
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8")
BASE_LOWER = BASE.lower()
MIGRATION_LOWER = MIGRATION.lower()


def test_degraded_control_plane_is_not_labeled_not_passing():
    segment = BASE_LOWER.split(
        "legacy_control_plane_not_passing", 1
    )[0][-500:]
    assert "legacy_control_plane_status" in segment
    assert "='failed'" in segment.replace(" ", "")
    assert "degraded" not in segment


def test_failed_control_plane_still_emits_warning():
    assert "legacy_control_plane_not_passing" in BASE_LOWER
    assert "legacy_control_plane_status" in BASE_LOWER
    assert "failed" in BASE_LOWER


def test_migration_is_fail_closed_and_outside_fingerprint():
    assert MIGRATION_PATH.parent.as_posix() == "ops/sql"
    assert "expected v0.1 legacy-control-plane watchdog predicate not found" in MIGRATION_LOWER
    assert "refusing unsafe patch" in MIGRATION_LOWER
    assert "create or replace view public.alpha_hunter_v14_watchdog_status_v01" in MIGRATION_LOWER


def test_watchdog_semantics_patch_does_not_change_trade_authority():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
    ]
    for marker in forbidden:
        assert marker not in MIGRATION_LOWER
