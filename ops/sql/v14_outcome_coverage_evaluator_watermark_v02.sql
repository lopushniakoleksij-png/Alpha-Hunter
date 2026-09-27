-- Alpha Hunter V14 outcome coverage evaluator watermark v0.2
--
-- Operations/scientific observability only, outside the sealed V14 fingerprint.
--
-- Corrects audit cadence semantics: an episode is considered due for a 24h
-- outcome only if it had matured by the start time of the latest successful
-- forward-outcome evaluator run. This prevents false "matured_without_24h"
-- counts for candidates that matured after the last evaluator and are simply
-- waiting for the next hourly :53 job.
--
-- No outcome/economics evidence is modified.

-- Alpha Hunter V14 outcome coverage audit v0.1
--
-- Operations/scientific observability only. Lives under ops/sql and is outside
-- the sealed V14 scientific fingerprint.
--
-- This view measures attrition between matured prospective candidate episodes,
-- produced 24h outcomes, complete path coverage, and counted paper-economics
-- rows. It does not modify the sealed forward-outcome evaluator or any evidence.

create or replace function private.alpha_hunter_latest_forward_outcome_evaluator_watermark_v01()
returns timestamptz
language sql
stable
security definer
set search_path=''
as $
  select d.start_time
  from cron.job_run_details d
  join cron.job j on j.jobid=d.jobid
  where j.jobname='alpha-hunter-strategy-forward-outcome-v01-hourly'
    and d.status='succeeded'
  order by d.start_time desc
  limit 1
$;

revoke all on function private.alpha_hunter_latest_forward_outcome_evaluator_watermark_v01()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_latest_forward_outcome_evaluator_watermark_v01()
  to service_role;


create or replace view public.alpha_hunter_v14_outcome_coverage_audit_v01
with (security_invoker=true,security_barrier=true) as
with active as (
  select
    e.spec_id,
    v.started_at_utc
  from public.alpha_hunter_test_engine_latest_v01 e
  join public.alpha_hunter_profitability_validation_status_v01 v
    on v.spec_id=e.spec_id
  order by e.evaluated_at_utc desc
  limit 1
),
evaluator_watermark as (
  select
    private.alpha_hunter_latest_forward_outcome_evaluator_watermark_v01()
      as evaluated_through_utc
),
candidate_episodes as (
  select distinct on (o.episode_id)
    o.episode_id,
    o.symbol,
    o.strategy_id,
    o.direction,
    o.first_candidate_at_utc
  from public.alpha_hunter_strategy_forward_outcomes_v01 o
  join active a
    on o.first_candidate_at_utc>=a.started_at_utc
  where o.first_candidate_at_utc is not null
  order by o.episode_id,o.horizon_hours asc,o.evaluated_at_utc asc
),
matured as (
  select c.*
  from candidate_episodes c
  cross join evaluator_watermark w
  where w.evaluated_through_utc is not null
    and c.first_candidate_at_utc+interval '24 hours'
      <=w.evaluated_through_utc
),
outcomes_24h as (
  select o.*
  from public.alpha_hunter_strategy_forward_outcomes_v01 o
  join active a
    on o.first_candidate_at_utc>=a.started_at_utc
  where o.horizon_hours=24
),
economics as (
  select e.*
  from public.alpha_hunter_strategy_paper_economics_v01 e
  join active a on e.spec_id=a.spec_id
),
stats as (
  select
    a.spec_id,
    a.started_at_utc,
    (select count(*) from matured)::integer
      as matured_candidate_episodes,
    (
      select count(*)
      from matured m
      left join outcomes_24h o using(episode_id)
      where o.episode_id is null
    )::integer as matured_without_24h_outcome,
    (select count(*) from outcomes_24h)::integer as outcome_24h_rows,
    (
      select count(*)
      from outcomes_24h
      where entry_trigger_status in (
        'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
      )
    )::integer as triggered_24h_rows,
    (
      select count(*)
      from outcomes_24h
      where path_measurement_quality='COMPLETE_ENOUGH'
    )::integer as complete_enough_24h_rows,
    (
      select count(*)
      from outcomes_24h
      where path_measurement_quality='INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
    )::integer as incomplete_candle_coverage_24h_rows,
    (
      select count(*)
      from outcomes_24h
      where ordering_ambiguous=true
    )::integer as ambiguous_24h_rows,
    (
      select count(*)
      from outcomes_24h
      where entry_trigger_status in (
        'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
      )
        and path_measurement_quality='COMPLETE_ENOUGH'
        and ordering_ambiguous=false
        and fill_price is not null
        and first_candidate_stop_price is not null
    )::integer as economics_prerequisite_rows,
    (select count(*) from economics)::integer as completed_paper_economics_rows,
    (select avg(path_coverage_pct) from outcomes_24h)
      as avg_24h_path_coverage_pct,
    (select min(path_coverage_pct) from outcomes_24h)
      as min_24h_path_coverage_pct,
    (select max(path_coverage_pct) from outcomes_24h)
      as max_24h_path_coverage_pct,
    (select min(evaluated_at_utc) from outcomes_24h)
      as first_24h_evaluated_at_utc,
    (select max(evaluated_at_utc) from outcomes_24h)
      as latest_24h_evaluated_at_utc
  from active a
)
select
  clock_timestamp() as checked_at_utc,
  s.*,
  case
    when s.matured_candidate_episodes=0 then null
    else 100.0*s.outcome_24h_rows::double precision
      /s.matured_candidate_episodes
  end as matured_to_24h_outcome_pct,
  case
    when s.outcome_24h_rows=0 then null
    else 100.0*s.complete_enough_24h_rows::double precision
      /s.outcome_24h_rows
  end as complete_enough_24h_pct,
  case
    when s.outcome_24h_rows=0 then null
    else 100.0*s.incomplete_candle_coverage_24h_rows::double precision
      /s.outcome_24h_rows
  end as incomplete_candle_coverage_24h_pct,
  case
    when s.matured_candidate_episodes=0 then null
    else 100.0*s.completed_paper_economics_rows::double precision
      /s.matured_candidate_episodes
  end as matured_to_counted_paper_trade_pct,
  case
    when s.outcome_24h_rows=0 then 'WAITING_FOR_FIRST_24H_OUTCOME'
    when s.outcome_24h_rows<10 then 'EARLY_SAMPLE'
    else 'MEASURED'
  end as coverage_measurement_status,
  'AUDIT_ONLY_NO_SEALED_EVALUATOR_CHANGE'::text as scientific_role,
  true as audit_only,
  false as profitability_rule_change_permitted,
  false as mutation_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from stats s;

revoke all on public.alpha_hunter_v14_outcome_coverage_audit_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v14_outcome_coverage_audit_v01
  to service_role;

