from pathlib import Path

SQL = Path('geometry_forward_science_view_v02.sql').read_text()


def test_v02_uses_scope_aligned_geometry_model_only():
    assert "geometry-diagnostics-v0.2.2-money-entry-scope-aligned" in SQL
    assert "geometry-diagnostics-v0.2.1-volatility-context" not in SQL
    assert "alpha_hunter_geometry_forward_observations_v02" in SQL
    assert "alpha_hunter_geometry_forward_status_v02" in SQL


def test_science_view_is_read_only_and_service_role_only():
    lower = SQL.lower()
    for marker in ["insert into", "update public.", "delete from", "cron.", "http_get(", "http_post("]:
        assert marker not in lower
    assert "with (security_invoker=true)" in SQL
    assert "revoke all on public.alpha_hunter_geometry_forward_observations_v02 from public,anon,authenticated" in SQL
    assert "grant select on public.alpha_hunter_geometry_forward_observations_v02 to service_role" in SQL
    assert "grant select on public.alpha_hunter_geometry_forward_status_v02 to service_role" in SQL


def test_no_execution_or_promotion_authority():
    required = [
        "false as exact_research_fill_claim_permitted",
        "false as confirmatory_claim_permitted",
        "false as threshold_derivation_permitted",
        "false as t0_authorized",
        "false as production_promotion_permitted",
        "true as shadow_only",
        "false as trade_permission",
    ]
    for marker in required:
        assert marker in SQL
    assert "trade_permission=true" not in SQL
    assert "production_execution_enabled=true" not in SQL


def test_path_order_remains_conservative():
    assert "BOTH_TOUCHED_PATH_ORDER_UNKNOWN" in SQL
    assert "MFE_MAE_TOUCH_TEST_REUSES_EXISTING_SCORECARD; BOTH_TOUCHED_HAS_UNKNOWN_ORDER" in SQL
    assert "TARGET_TOUCHED_ONLY" in SQL
    assert "STOP_TOUCHED_ONLY" in SQL
    assert "NEITHER_TOUCHED" in SQL


def test_existing_scorecard_is_reused_not_reimplemented():
    assert "alpha_hunter_big_mover_money_scorecard_candidates" in SQL
    assert "alpha_hunter_big_mover_money_scorecard_outcomes" in SQL
    assert "realistic_net_r_status" in SQL
    assert "No new market" not in SQL  # implementation is SQL views, not a second market path
