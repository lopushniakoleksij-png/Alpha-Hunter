from pathlib import Path

SQL = Path("ops/sql/profit_retention_lifecycle_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_profit_retention_uses_observed_position_mfe_only():
    required = [
        "observed_peak_unrealized_pnl_usdt",
        "observed_peak_gross_capture_pct",
        "observed_peak_gross_giveback_pct",
        "observed_peak_fee_adjusted_capture_pct_ex_funding",
        "order by p.unrealized_pnl_usdt desc nulls last",
        "sampled canonical position snapshots",
    ]
    for marker in required:
        assert marker.lower() in LOWER


def test_completed_roundtrips_are_bound_by_symbol_direction_and_time():
    required = [
        "p.symbol=r.symbol",
        "p.direction=r.direction",
        "p.captured_at_utc >= r.opened_or_first_seen_at_utc",
        "p.captured_at_utc <= r.closed_at_utc",
        "where r.closed_at_utc is not null",
    ]
    for marker in required:
        assert marker in SQL


def test_last_observed_protection_and_stop_slippage_are_descriptive():
    required = [
        "last_stop_loss_observed",
        "last_take_profit_observed",
        "exit_vs_last_stop_adverse_bps",
        "observed_peak_to_stop_distance_pct",
    ]
    for marker in required:
        assert marker in SQL


def test_profit_claim_ceiling_preserves_funding_uncertainty():
    required = [
        "fee_adjusted_profit_ex_funding",
        "funding_coverage_complete",
        "funding_coverage_status",
        "full_economic_pnl_claim_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_management_changes_remain_prohibited():
    required = [
        "false as management_change_permitted",
        "false as stop_change_permitted",
        "false as target_change_permitted",
        "false as trade_permission",
        "'NONE'::text as order_path",
        "DESCRIPTIVE_OBSERVED_MFE_RETENTION_AUDIT",
    ]
    for marker in required:
        assert marker in SQL


def test_no_exchange_or_execution_authority_added():
    forbidden = [
        "api.bitget.com",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer(",
        "trade_permission=true",
        "trade_permission = true",
        "stop_change_permitted=true",
        "target_change_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_service_role_only_views():
    for view in [
        "alpha_hunter_profit_retention_lifecycle_v01",
        "alpha_hunter_profit_retention_status_v01",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
