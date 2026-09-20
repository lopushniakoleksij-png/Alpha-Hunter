from pathlib import Path

SQL = Path("realized_fee_evidence_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_realized_fee_uses_immutable_fill_evidence_only():
    assert "from public.alpha_hunter_fill_evidence f" in LOWER
    assert "abs(f.fee_amount)/f.quote_volume*10000.0" in SQL
    assert "f.cost_fields_complete=true" in SQL
    assert "f.quote_volume>0" in SQL
    assert "upper(coalesce(f.fee_coin,''))='USDT'" in SQL


def test_realized_fee_classification_is_descriptive_only():
    required = [
        "ACCOUNT_OBSERVED_TAKER_FEE",
        "ACCOUNT_OBSERVED_MAKER_FEE",
        "DESCRIPTIVE_ACCOUNT_OBSERVED_FEE_ONLY",
        "DESCRIPTIVE_ONLY_NOT_A_VALIDATED_COST_MODEL",
        "REQUIRES_SEPARATE_SLIPPAGE_AND_OUTCOME_VALIDATION",
    ]
    for marker in required:
        assert marker in SQL


def test_realized_fee_does_not_activate_cost_or_execution():
    forbidden = [
        "insert into public.alpha_hunter_execution_cost_model_versions",
        "status='ACTIVE'",
        "status = 'ACTIVE'",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "realistic_net_r is not null",
        "entry_slippage_bps",
        "exit_slippage_bps",
        "place_order",
        "cancel_order",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "false as cost_model_validated" in LOWER
    assert "false as cost_model_activation_permitted" in LOWER
    assert "false as slippage_inference_permitted" in LOWER
    assert "false as realistic_net_r_claim_permitted" in LOWER


def test_status_view_reports_distribution_not_single_magic_fee():
    required = [
        "count(*)::bigint as observed_fill_count",
        "count(distinct symbol)::bigint as distinct_symbols",
        "min(realized_fee_bps)",
        "percentile_cont(0.5)",
        "max(realized_fee_bps)",
        "stddev_pop(realized_fee_bps)",
        "avg(realized_fee_bps)",
    ]
    for marker in required:
        assert marker.lower() in LOWER


def test_views_are_service_role_only():
    required = [
        "revoke all on public.alpha_hunter_realized_fee_observations_v01",
        "revoke all on public.alpha_hunter_realized_fee_status_v01",
        "grant select on public.alpha_hunter_realized_fee_observations_v01",
        "grant select on public.alpha_hunter_realized_fee_status_v01",
        "to service_role",
    ]
    for marker in required:
        assert marker in LOWER
