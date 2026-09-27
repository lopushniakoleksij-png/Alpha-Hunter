from pathlib import Path

PATH = Path(
    "ops/sql/v14_watchdog_control_plane_semantics_explicit_v03.sql"
)
SQL = PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_explicit_watchdog_migration_is_ops_only():
    assert PATH.parent.as_posix() == "ops/sql"
    assert "create or replace view public.alpha_hunter_v14_watchdog_status_v01" in LOWER
    assert "security_invoker=true" in LOWER
    assert "security_barrier=true" in LOWER


def test_failed_only_control_plane_warning_semantics():
    marker = "legacy_control_plane_not_passing"
    idx = LOWER.index(marker)
    context = LOWER[max(0, idx - 400):idx + 100]
    assert "legacy_control_plane_status" in context
    assert "failed" in context
    assert "degraded" not in context


def test_trade_authority_remains_disabled():
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
    for forbidden in [
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
    ]:
        assert forbidden not in LOWER
