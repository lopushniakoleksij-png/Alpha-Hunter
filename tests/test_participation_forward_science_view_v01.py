from pathlib import Path

SQL = Path('participation_forward_science_view_v01.sql').read_text()


def test_forward_views_are_read_only_and_service_role_only():
    required = [
        'alpha_hunter_participation_forward_observations_v01',
        'alpha_hunter_participation_forward_status_v01',
        'with (security_invoker=true)',
        'revoke all on public.alpha_hunter_participation_forward_observations_v01 from public,anon,authenticated',
        'revoke all on public.alpha_hunter_participation_forward_status_v01 from public,anon,authenticated',
        'grant select on public.alpha_hunter_participation_forward_status_v01 to service_role',
    ]
    for marker in required:
        assert marker in SQL


def test_views_bind_diagnostics_to_existing_forward_outcomes():
    required = [
        'alpha_hunter_participation_diagnostics',
        'alpha_hunter_signal_outcomes',
        'o.signal_id=d.source_signal_id',
        'horizon_hours=1',
        'horizon_hours=4',
        'horizon_hours=12',
        'horizon_hours=24',
        'direction_adjusted_return_pct',
    ]
    for marker in required:
        assert marker in SQL


def test_exploratory_cohort_cannot_be_used_as_confirmatory_or_threshold_authority():
    required = [
        "'EXPLORATORY_PROSPECTIVE'::text",
        'false as confirmatory_claim_permitted',
        'false as threshold_derivation_permitted',
        'false as production_promotion_permitted',
        "'NO_CONFIRMATORY_CLAIM_THIS_COHORT'::text",
        'separately preregistered future holdout',
    ]
    for marker in required:
        assert marker in SQL


def test_no_execution_or_mutation_path_is_added():
    forbidden = [
        'insert into',
        'update ',
        'delete from',
        'trade_permission=true',
        'production_execution_enabled=true',
        '/api/v3/trade/place-order',
        '/api/v2/mix/order/place-order',
        'http_get(',
    ]
    lowered = SQL.lower()
    for marker in forbidden:
        assert marker.lower() not in lowered
