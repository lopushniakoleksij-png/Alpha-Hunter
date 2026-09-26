-- Alpha Hunter sealed decision-time quote status v0.1
--
-- Separates all prospective quote captures from the subset eligible for the
-- sealed profitability cohort. Continuing/left-censored episodes remain
-- diagnostic only and never count as sealed execution-cost evidence.

create or replace view public.alpha_hunter_sealed_decision_quote_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  s.spec_id,
  s.required_run_source,
  a.started_at_utc,
  count(q.observation_id) as post_baseline_quote_rows,
  count(q.observation_id) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)<a.started_at_utc
  ) as left_censored_quote_rows,
  count(q.observation_id) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
  ) as sealed_eligible_quote_rows,
  count(q.observation_id) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
      and q.quote_complete
  ) as complete_sealed_eligible_quote_rows,
  count(q.observation_id) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
      and q.action='EXECUTE_NOW'
  ) as sealed_execute_now_quote_rows,
  count(q.observation_id) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
      and q.action='PLACE_LIMIT'
  ) as sealed_place_limit_quote_rows,
  min(q.observed_at_utc) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
  ) as first_sealed_quote_at_utc,
  max(q.observed_at_utc) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
  ) as latest_sealed_quote_at_utc,
  avg(q.entry_cross_half_spread_bps) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
      and q.quote_complete
  ) as avg_sealed_entry_cross_half_spread_bps,
  percentile_cont(0.9) within group(
    order by q.entry_cross_half_spread_bps
  ) filter(
    where coalesce(o.first_seen_at_utc,o.observed_at_utc)>=a.started_at_utc
      and q.quote_complete
  ) as p90_sealed_entry_cross_half_spread_bps,
  false as slippage_measured,
  false as fill_claim_permitted,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  'SEALED_POST_BASELINE_QUOTES_ONLY'::text as sample_boundary,
  'LEFT_CENSORED_QUOTES_DIAGNOSTIC_ONLY'::text as left_censor_policy,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_profitability_test_specs_v01 s
join public.alpha_hunter_profitability_test_activations_v01 a
  on a.spec_id=s.spec_id
left join public.alpha_hunter_shadow_decision_quotes_v01 q
  on q.observed_at_utc>=a.started_at_utc
 and q.run_source=s.required_run_source
left join public.alpha_hunter_strategy_observations_v01 o
  on o.observation_id=q.observation_id
group by s.spec_id,s.required_run_source,a.started_at_utc;

revoke all on public.alpha_hunter_sealed_decision_quote_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_sealed_decision_quote_status_v01
  to service_role;
