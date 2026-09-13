from pathlib import Path


SQL = Path("big_mover_money_scorecard_runtime.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_scorecard_is_shadow_only_and_cannot_grant_trade_permission():
    assert "check (shadow_only = true)" in SQL
    assert "check (trade_permission = false)" in SQL
    assert "shadow_only',true" in SQL
    assert "trade_permission',false" in SQL


def test_scorecard_freezes_candidates_append_only():
    assert "money scorecard candidate snapshots are append-only" in SQL
    assert "before update or delete" in LOWER
    assert "source_bridge_id text not null unique" in LOWER


def test_forward_horizons_are_exactly_one_four_twelve_twenty_four_hours():
    assert "horizon_hours in (1,4,12,24)" in SQL
    assert "cross join (values(1),(4),(12),(24))" in LOWER
    assert "'horizons',jsonb_build_array(1,4,12,24)" in SQL


def test_path_measurement_uses_public_bitget_three_minute_candles():
    assert "api.bitget.com/api/v3/market/candles" in SQL
    assert "category=USDT-FUTURES" in SQL
    assert "interval=3m" in SQL
    assert "limit=1000" in SQL
    assert "BOTH_SAME_3M_CANDLE_AMBIGUOUS" in SQL


def test_money_fields_are_measured_without_inventing_exact_stages_or_costs():
    for field in (
        "mfe_pct",
        "mae_pct",
        "hit_3pct",
        "hit_5pct",
        "hit_10pct",
        "stop_survived",
        "remaining_r",
        "confirmation_tax_r",
        "path_r_pre_cost",
        "realistic_net_r",
        "t0_path_result",
        "t1_path_result",
        "t2_path_result",
    ):
        assert field in SQL
    assert "EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE" in SQL
    assert "UNVERIFIED_EXECUTION_COST_MODEL" in SQL
    assert "realistic_net_r=null" in LOWER


def test_security_definer_functions_are_private_and_revoked_from_public_roles():
    assert "function private.alpha_hunter_seed_big_mover_money_scorecard" in LOWER
    assert "function private.alpha_hunter_run_big_mover_money_scorecard" in LOWER
    assert "revoke all on function private.alpha_hunter_seed_big_mover_money_scorecard() from public, anon, authenticated" in LOWER
    assert "revoke all on function private.alpha_hunter_run_big_mover_money_scorecard() from public, anon, authenticated" in LOWER
    assert "alter table public.alpha_hunter_big_mover_money_scorecard_candidates enable row level security" in LOWER
    assert "alter table public.alpha_hunter_big_mover_money_scorecard_outcomes enable row level security" in LOWER


def test_scorecard_runs_after_discovery_parent_direction_and_bridge():
    assert "alpha-hunter-big-mover-money-scorecard-hourly" in SQL
    assert "'14 * * * *'" in SQL


def test_runtime_contains_no_order_submission_path():
    forbidden = (
        "place_order",
        "create_order",
        "submit_order",
        "/api/v2/mix/order/place-order",
        "/api/v3/trade/place-order",
    )
    for token in forbidden:
        assert token not in LOWER
