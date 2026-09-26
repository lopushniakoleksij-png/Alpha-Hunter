from pathlib import Path

SQL_PATH = Path("ops/sql/v14_control_tower_watchdog_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_v14_watchdog_stays_outside_scientific_fingerprint():
    identity = Path("alpha_hunter/scientific_identity.py").read_text(
        encoding="utf-8"
    )
    assert "root.glob(\"*.sql\")" in identity
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SQL_PATH.name not in [
        path.name for path in Path(".").glob("*.sql")
    ]


def test_watchdog_has_hard_safety_authority_guards():
    required = [
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
        "safety_authority_violation",
        "check (trade_permission=false)",
        "check (production_promotion_permitted=false)",
        "check (order_path='none')",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_expected_scientific_gates_are_not_classified_as_critical():
    expected = [
        "minimum_30_day_duration_not_met",
        "minimum_100_paper_trades_not_met",
        "realistic_net_r_claim_not_yet_permitted",
    ]
    critical_segment = LOWER.split("as critical_alerts", 1)[0]
    for marker in expected:
        assert marker not in critical_segment
        assert marker in LOWER


def test_watchdog_detects_core_v14_integrity_failures():
    for marker in [
        "test_engine_stale",
        "canonical_scan_stale",
        "scientific_identity_drift",
        "cadence_integrity_failed",
        "profitability_test_invalidated",
        "test_engine_operational_blocked",
    ]:
        assert marker in LOWER


def test_watchdog_surfaces_known_non_scientific_blockers():
    for marker in [
        "bitget_fill_history_continuity_conflict",
        "bitget_account_identity_unpinned",
        "execution_cost_model_not_validated",
        "storage_live_toast_review_required",
        "legacy_control_plane_not_passing",
    ]:
        assert marker in LOWER


def test_watchdog_ledger_is_append_only_service_role_readable():
    assert "enable row level security" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert (
        "grant select on table public.alpha_hunter_v14_watchdog_events_v01"
        in LOWER
    )
    assert "to service_role" in LOWER


def test_watchdog_schedule_is_aligned_after_canonical_scan_windows():
    assert "'5,25,45 * * * *'" in SQL
    assert "alpha-hunter-v14-watchdog-v01" in SQL
