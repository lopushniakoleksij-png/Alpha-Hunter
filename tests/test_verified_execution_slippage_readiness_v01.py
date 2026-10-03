from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/verified_execution_slippage_readiness_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_verified_slippage_readiness_sql_parses():
    assert parse_sql(SQL)


def test_only_verified_prospective_alpha_hunter_executions_enter_sample():
    required = [
        "alpha_hunter_verified_execution_attribution_v01",
        "verified_alpha_hunter_execution=true",
        "d.frozen_at_utc",
    ]
    # The view alias is v rather than d; exact prospective boundary is frozen_at.
    assert required[0] in LOWER
    assert required[1] in LOWER
    assert "v.frozen_at_utc>=a.started_at_utc" in LOWER


def test_calibration_floor_is_preregistered_and_segmented():
    required = [
        "30::integer as minimum_verified_execution_rows",
        "20::integer as minimum_verified_taker_rows",
        "10::integer as minimum_verified_maker_rows",
        "5::integer as minimum_verified_long_rows",
        "5::integer as minimum_verified_short_rows",
        "entry_slippage_calibration_sample_gate_met",
        "entry_calibration_30_total_20_taker_10_maker_5_each_direction",
    ]
    for marker in required:
        assert marker in LOWER


def test_entry_slippage_uses_adverse_nonnegative_distribution_without_erasing_signed_metric():
    assert "mean_signed_arrival_to_fill_bps" in LOWER
    assert "median_signed_arrival_to_fill_bps" in LOWER
    assert "greatest(signed_adverse_arrival_to_fill_bps,0)" in LOWER
    assert "p90_adverse_entry_slippage_bps" in LOWER
    assert "p95_adverse_entry_slippage_bps" in LOWER


def test_real_fee_and_latency_metrics_are_required():
    required = [
        "realized_fee_measured_rows",
        "median_realized_fee_bps",
        "p90_realized_fee_bps",
        "median_freeze_to_order_seconds",
        "p90_freeze_to_order_seconds",
        "median_order_to_fill_seconds",
        "p90_order_to_fill_seconds",
    ]
    for marker in required:
        assert marker in LOWER


def test_full_cost_path_remains_explicitly_incomplete():
    required = [
        "0::bigint as verified_exit_slippage_rows",
        "0::bigint as verified_post_fill_markout_rows",
        "false as exit_slippage_sample_gate_met",
        "false as adverse_selection_markout_gate_met",
        "false as realized_funding_path_gate_met",
        "false as missing_data_policy_frozen",
        "false as out_of_sample_replication_gate_met",
        "capture_exit_slippage_post_fill_markouts_funding_and_oos_replication",
    ]
    for marker in required:
        assert marker in LOWER


def test_readiness_v04_never_auto_activates_or_claims_realistic_net_r():
    required = [
        "alpha_hunter_execution_cost_validation_readiness_v04",
        "false as cost_model_activation_permitted",
        "false as realistic_net_r_model_activation_permitted",
        "false as realistic_net_r_claim_permitted",
        "do_not_activate_yet_capture_full_cost_path_and_oos_replication",
    ]
    for marker in required:
        assert marker in LOWER


def test_no_registry_mutation_or_exchange_authority():
    forbidden = [
        "insert into public.alpha_hunter_execution_cost_model_versions",
        "update public.alpha_hunter_execution_cost_model_versions",
        "delete from public.alpha_hunter_execution_cost_model_versions",
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_views_are_service_role_read_only():
    for view in [
        "alpha_hunter_verified_execution_slippage_status_v01",
        "alpha_hunter_execution_cost_validation_readiness_v04",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
