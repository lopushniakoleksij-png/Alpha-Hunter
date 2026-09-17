from pathlib import Path

SQL = Path('geometry_forward_science_view_v01.sql').read_text()
LOWER = SQL.lower()


def test_geometry_forward_views_reuse_existing_scorecard_only():
    required = [
        'alpha_hunter_geometry_forward_observations_v01',
        'alpha_hunter_geometry_forward_status_v01',
        'alpha_hunter_geometry_diagnostics',
        'alpha_hunter_big_mover_money_scorecard_candidates',
        'alpha_hunter_big_mover_money_scorecard_outcomes',
        'mfe_pct',
        'mae_pct',
        'scorecard_unavailable_observations',
    ]
    for marker in required:
        assert marker in SQL


def test_recovered_geometry_path_logic_is_conservative():
    required = [
        'BOTH_TOUCHED_PATH_ORDER_UNKNOWN',
        'STOP_TOUCHED_ONLY',
        'TARGET_TOUCHED_ONLY',
        'NEITHER_TOUCHED',
        'OUTCOME_PENDING',
        'OUTCOME_DATA_INSUFFICIENT',
        'SCORECARD_UNAVAILABLE',
        'MFE_MAE_TOUCH_TEST_REUSES_EXISTING_SCORECARD; BOTH_TOUCHED_HAS_UNKNOWN_ORDER',
    ]
    for marker in required:
        assert marker in SQL


def test_research_geometry_never_becomes_execution_authority():
    required = [
        'false as exact_research_fill_claim_permitted',
        'false as confirmatory_claim_permitted',
        'false as threshold_derivation_permitted',
        'false as t0_authorized',
        'false as production_promotion_permitted',
        "'INSUFFICIENT_FOR_CONFIRMATORY_GEOMETRY_CLAIM'::text",
        'preregister a separate future holdout excluding these observations',
    ]
    for marker in required:
        assert marker in SQL


def test_views_are_read_only_service_role_surfaces():
    required = [
        'with (security_invoker=true)',
        'revoke all on public.alpha_hunter_geometry_forward_observations_v01 from public,anon,authenticated',
        'grant select on public.alpha_hunter_geometry_forward_status_v01 to service_role',
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        'insert into',
        'update ',
        'delete from',
        'http_get(',
        'trade_permission=true',
        'production_execution_enabled=true',
        '/api/v3/trade/place-order',
        '/api/v2/mix/order/place-order',
    ]
    for marker in forbidden:
        assert marker not in LOWER
