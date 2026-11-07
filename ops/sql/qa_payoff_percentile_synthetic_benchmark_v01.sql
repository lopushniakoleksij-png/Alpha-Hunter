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

-- Reproduce one percentile aggregate 50 times (one per symbol) before and
-- after the index. This captures the repeated hot path, not just one EXPLAIN.
create temporary table qa_hotpath_latency (
  phase text not null,
  ordinal integer not null,
  elapsed_ms numeric not null,
  matched_rows integer not null
);
create or replace function pg_temp.qa_measure_hotpath(p_phase text)
returns void language plpgsql as $hotpath$
declare
  n integer;
  t0 timestamptz;
  nmatch integer;
  adverse_p50 float8;
  adverse_p75 float8;
  favorable_p50 float8;
  favorable_p90 float8;
begin
  for n in 1..50 loop
    t0 := clock_timestamp();
    select count(*)::integer,
      percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct),
      percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct),
      percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct),
      percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct)
    into nmatch,adverse_p50,adverse_p75,favorable_p50,favorable_p90
    from public.alpha_hunter_strategy_forward_outcomes_v01 o
    where o.horizon_hours=24 and o.strategy_id='S3' and o.direction='LONG'
      and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
      and o.path_measurement_quality='COMPLETE_ENOUGH'
      and o.ordering_ambiguous=false
      and o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00+00'
      and o.max_adverse_excursion_pct is not null
      and o.max_favorable_excursion_pct is not null;
    insert into qa_hotpath_latency values (
      p_phase,n,extract(epoch from clock_timestamp()-t0)*1000,nmatch
    );
  end loop;
end
$hotpath$;

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

\echo 'BASELINE repeated 50-symbol percentile queries'
select pg_temp.qa_measure_hotpath('baseline');

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

\echo 'CANDIDATE repeated 50-symbol percentile queries'
select pg_temp.qa_measure_hotpath('candidate');

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

\echo '50-symbol latency distribution — indicative synthetic benchmark only'
select phase,count(*) as queries,
  round(avg(elapsed_ms),2) as avg_ms,
  round((percentile_cont(0.50) within group(order by elapsed_ms))::numeric,2) as p50_ms,
  round((percentile_cont(0.95) within group(order by elapsed_ms))::numeric,2) as p95_ms,
  round((percentile_cont(0.99) within group(order by elapsed_ms))::numeric,2) as p99_ms,
  round(sum(elapsed_ms),2) as sum_50_ms,
  min(matched_rows) as min_matches, max(matched_rows) as max_matches
from qa_hotpath_latency group by phase order by phase;
do $validation$
begin
  if (select count(*) from qa_hotpath_latency where phase='baseline')<>50
    or (select count(*) from qa_hotpath_latency where phase='candidate')<>50
    or (select count(distinct matched_rows) from qa_hotpath_latency)<>1
    or (select min(matched_rows) from qa_hotpath_latency)<=0
  then raise exception 'REPEATED_PERCENTILE_BENCHMARK_INVALID'; end if;
  raise notice 'PASS: 50 baseline and 50 candidate hotpath calls, matched row counts consistent';
end $validation$;
