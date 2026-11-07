-- ISOLATED POSTGRES BENCHMARK — Synthetic 495,000-row forward outcomes table.
-- No live data, no Supabase connection; timings are indicative only.
\timing on
create table public.alpha_hunter_strategy_forward_outcomes_v01 (
  episode_id text not null,
  horizon_hours integer not null,
  first_observed_at_utc timestamptz not null,
  strategy_id text not null,
  direction text not null,
  entry_trigger_status text not null,
  path_measurement_quality text not null,
  ordering_ambiguous boolean not null,
  evaluated_at_utc timestamptz not null,
  max_adverse_excursion_pct double precision,
  max_favorable_excursion_pct double precision,
  primary key (episode_id,horizon_hours)
);

insert into public.alpha_hunter_strategy_forward_outcomes_v01(
 episode_id,horizon_hours,first_observed_at_utc,strategy_id,direction,
 entry_trigger_status,path_measurement_quality,ordering_ambiguous,
 evaluated_at_utc,max_adverse_excursion_pct,max_favorable_excursion_pct
)
select 'qa-'||n,
  case when n%5=0 then 4 else 24 end,
  timestamptz '2026-09-01T00:00:00+00' + (n%220000)*interval '1 second',
  (array['S1','S2','S3','S4','S5','S6'])[(n%6)+1],
  case when (n/6)%2=0 then 'LONG' else 'SHORT' end,
  case when n%7=0 then 'NEVER_TRIGGERED' when n%3=0 then 'TRIGGERED_LIMIT'
       else 'TRIGGERED_EXECUTE_NOW' end,
  case when n%13=0 then 'INCOMPLETE' else 'COMPLETE_ENOUGH' end,
  n%17=0,
  timestamptz '2026-11-01T00:00:00+00' + (n%500000)*interval '1 second',
  (n%450)::float8/100.,
  (n%900)::float8/100.
from generate_series(1,495000) g(n);

-- Replica of representative existing access paths; does not reproduce triggers.
create index idx_ah_strategy_outcome_24h_time_episode_v02
on public.alpha_hunter_strategy_forward_outcomes_v01(first_observed_at_utc,episode_id)
where horizon_hours=24;
create index idx_ah_strategy_forward_outcome_strategy_v01
on public.alpha_hunter_strategy_forward_outcomes_v01(strategy_id,horizon_hours,evaluated_at_utc);
analyze public.alpha_hunter_strategy_forward_outcomes_v01;

\echo 'BASELINE: 495k synthetic outcomes, representative existing indexes'
explain (analyze,buffers,format text)
select
 count(*)::integer,
 percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct),
 percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct),
 percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct),
 percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct)
from public.alpha_hunter_strategy_forward_outcomes_v01 o
where o.horizon_hours=24 and o.strategy_id='S3' and o.direction='LONG'
  and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
  and o.path_measurement_quality='COMPLETE_ENOUGH'
  and o.ordering_ambiguous=false
  and o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00+00'
  and o.max_adverse_excursion_pct is not null
  and o.max_favorable_excursion_pct is not null;

create temporary table qa_percentiles_before as
select count(*)::integer as n,
 percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct) as adverse_p50,
 percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct) as adverse_p75,
 percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct) as favorable_p50,
 percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct) as favorable_p90
from public.alpha_hunter_strategy_forward_outcomes_v01 o
where o.horizon_hours=24 and o.strategy_id='S3' and o.direction='LONG'
  and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
  and o.path_measurement_quality='COMPLETE_ENOUGH'
  and o.ordering_ambiguous=false
  and o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00+00'
  and o.max_adverse_excursion_pct is not null
  and o.max_favorable_excursion_pct is not null;

\echo 'Installing candidate index ONLY on ephemeral Postgres'
\i ops/sql/strategy_payoff_percentile_hotpath_index_candidate_v01.sql
analyze public.alpha_hunter_strategy_forward_outcomes_v01;

\echo 'CANDIDATE: same synthetic workload and proposed index'
explain (analyze,buffers,format text)
select
 count(*)::integer,
 percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct),
 percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct),
 percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct),
 percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct)
from public.alpha_hunter_strategy_forward_outcomes_v01 o
where o.horizon_hours=24 and o.strategy_id='S3' and o.direction='LONG'
  and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
  and o.path_measurement_quality='COMPLETE_ENOUGH'
  and o.ordering_ambiguous=false
  and o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00+00'
  and o.max_adverse_excursion_pct is not null
  and o.max_favorable_excursion_pct is not null;

do $qa$
declare a record; b record;
begin
 select * into a from qa_percentiles_before;
 select count(*)::integer as n,
 percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct) as adverse_p50,
 percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct) as adverse_p75,
 percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct) as favorable_p50,
 percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct) as favorable_p90
 into b
 from public.alpha_hunter_strategy_forward_outcomes_v01 o
 where o.horizon_hours=24 and o.strategy_id='S3' and o.direction='LONG'
  and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
  and o.path_measurement_quality='COMPLETE_ENOUGH'
  and o.ordering_ambiguous=false
  and o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00+00'
  and o.max_adverse_excursion_pct is not null
  and o.max_favorable_excursion_pct is not null;
 if row(a.n,a.adverse_p50,a.adverse_p75,a.favorable_p50,a.favorable_p90)
    is distinct from row(b.n,b.adverse_p50,b.adverse_p75,b.favorable_p50,b.favorable_p90) then
   raise exception 'BENCHMARK_RESULT_CHANGED';
 end if;
 if a.n=0 then raise exception 'SYNTHETIC_BENCHMARK_FILTER_EMPTY'; end if;
 raise notice 'PASS: percentile results unchanged, matched outcomes=%',a.n;
end
$qa$;
