-- Alpha Hunter emerging-participation source-consistent challenger v0.2
--
-- Scientific successor to PR #253.
--
-- Existing project concept, not a newly invented threshold:
--   alpha_hunter.analysis.build_intelligence_score labels participation PARTIAL
--   when:
--     1H volume anomaly state in (ELEVATED,HIGH)
--       OR open_interest_change_pct > 0
--
-- Existing CONFIRMED participation is preserved separately.
--
-- Scientific purpose:
--   Test whether the pre-existing PARTIAL concept contains forward predictive
--   information before ever mapping it to Money Entry T1.
--
-- Source-integrity repair:
--   * NEW forward-only challenger spec/version;
--   * binds only to source-consistent participation universe endpoint v0.2;
--   * source endpoint must remain UNIVERSE_T0_TO_UNIVERSE_ENDPOINT;
--   * no v0.1 endpoint candidate/outcome dependency;
--   * explicit endpoint coverage/censor/pending accounting in scorecard;
--   * no historical backfill.
--
-- It does NOT define T1, acceptance, trigger, expansion, thresholds,
-- production promotion, or trade permission.

create table if not exists private.alpha_hunter_participation_emerging_universe_specs_v02 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  rule_version text not null,
  source_endpoint_spec_id text not null
    check(source_endpoint_spec_id='PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02'),
  source_endpoint_contract text not null
    check(source_endpoint_contract='UNIVERSE_T0_TO_UNIVERSE_ENDPOINT'),
  primary_horizon_hours integer not null check(primary_horizon_hours in (1,4,12,24)),
  minimum_evaluated_candidates integer not null check(minimum_evaluated_candidates>0),
  minimum_distinct_symbols integer not null check(minimum_distinct_symbols>0),
  minimum_distinct_utc_days integer not null check(minimum_distinct_utc_days>0),
  status text not null check(status in ('COLLECTING','PAUSED','COMPLETE')),
  rule_definition jsonb not null,
  scientific_role text not null,
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  t1_stage_mapping_permitted boolean not null default false
    check(t1_stage_mapping_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into private.alpha_hunter_participation_emerging_universe_specs_v02(
  spec_id,registered_at_utc,rule_version,source_endpoint_spec_id,
  source_endpoint_contract,primary_horizon_hours,minimum_evaluated_candidates,
  minimum_distinct_symbols,minimum_distinct_utc_days,status,rule_definition,
  scientific_role,confirmatory_claim_permitted,t1_stage_mapping_permitted,
  threshold_derivation_permitted,production_promotion_permitted,
  shadow_only,trade_permission,order_path
) values (
  'PARTICIPATION-EMERGING-UNIVERSE-V02',
  clock_timestamp(),
  'analysis.py institutional_participation PARTIAL rule',
  'PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02',
  'UNIVERSE_T0_TO_UNIVERSE_ENDPOINT',
  24,
  200,
  50,
  10,
  'COLLECTING',
  jsonb_build_object(
    'emerging_if',
      'NOT_SCANNER_CONFIRMED AND (VOLUME_STATE_1H_IN_ELEVATED_HIGH OR OPEN_INTEREST_CHANGE_PCT_GT_0)',
    'confirmed_if',
      'SCANNER_PARTICIPATION_CONFIRMED_TRUE',
    'descriptive_inputs_only',true,
    'rule_origin','PREEXISTING_ALPHA_HUNTER_ANALYSIS_PARTIAL_CLASSIFICATION',
    'source_endpoint_spec_id','PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02',
    'source_endpoint_contract','UNIVERSE_T0_TO_UNIVERSE_ENDPOINT',
    'historical_backfill_permitted',false
  ),
  'FORWARD_SOURCE_CONSISTENT_PARTICIPATION_EMERGING_CHALLENGER',
  false,false,false,false,true,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_participation_emerging_universe_candidates_v02 (
  candidate_id text primary key,
  spec_id text not null
    references private.alpha_hunter_participation_emerging_universe_specs_v02(spec_id),
  endpoint_candidate_id text not null unique
    references private.alpha_hunter_participation_universe_endpoint_candidates_v02(candidate_id),
  diagnostic_id text not null,
  source_signal_id text not null,
  run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  candidate_direction text not null check(candidate_direction in ('LONG','SHORT')),
  source_classification text not null,
  scanner_participation_confirmed boolean,
  volume_state_1h text,
  volume_ratio_1h double precision,
  open_interest_change_pct double precision,
  challenger_class text not null check(
    challenger_class in (
      'SCANNER_CONFIRMED',
      'EMERGING_PARTIAL_CHALLENGER',
      'NOT_EMERGING'
    )
  ),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null
    default 'FORWARD_SOURCE_CONSISTENT_PARTICIPATION_EMERGING_CANDIDATE',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  t1_stage_mapping_permitted boolean not null default false
    check(t1_stage_mapping_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_part_emerging_universe_candidate_time_v02
  on private.alpha_hunter_participation_emerging_universe_candidates_v02(
    spec_id,captured_at_utc
  );

create table if not exists private.alpha_hunter_participation_emerging_universe_runs_v02 (
  run_id text primary key,
  spec_id text not null,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  candidate_rows_total integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  t1_stage_mapping_permitted boolean not null default false
    check(t1_stage_mapping_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_capture_participation_emerging_universe_v02()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_participation_emerging_universe_specs_v02%rowtype;
  v_endpoint_spec private.alpha_hunter_participation_universe_endpoint_specs_v02%rowtype;
  v_now timestamptz:=clock_timestamp();
  v_inserted integer:=0;
  v_total integer:=0;
  v_run_id text;
begin
  if not pg_try_advisory_xact_lock(
    hashtextextended('alpha-hunter-participation-emerging-universe-v02',0)
  ) then
    return jsonb_build_object(
      'status','RUN_ALREADY_ACTIVE',
      'shadow_only',true,
      'trade_permission',false,
      't1_stage_mapping_permitted',false
    );
  end if;

  select * into v_spec
  from private.alpha_hunter_participation_emerging_universe_specs_v02
  where spec_id='PARTICIPATION-EMERGING-UNIVERSE-V02'
    and status='COLLECTING';

  if v_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false,
      't1_stage_mapping_permitted',false
    );
  end if;

  select * into v_endpoint_spec
  from private.alpha_hunter_participation_universe_endpoint_specs_v02
  where spec_id=v_spec.source_endpoint_spec_id
    and status='COLLECTING';

  if v_endpoint_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SOURCE_ENDPOINT_SPEC',
      'shadow_only',true,
      'trade_permission',false,
      't1_stage_mapping_permitted',false
    );
  end if;

  if v_spec.source_endpoint_contract<>'UNIVERSE_T0_TO_UNIVERSE_ENDPOINT'
     or v_endpoint_spec.anchor_source_table<>'public.alpha_hunter_universe_hourly'
     or v_endpoint_spec.endpoint_source_table<>'public.alpha_hunter_universe_hourly'
     or v_endpoint_spec.required_source<>'PRIMARY_SCANNER_CACHED_TICKERS'
     or v_endpoint_spec.required_measurement_quality<>'CANONICAL_SCAN_TICKER_SNAPSHOT'
     or v_endpoint_spec.endpoint_max_lag_minutes<>30
     or v_endpoint_spec.horizons_hours<>array[1,4,12,24]
     or v_endpoint_spec.primary_return_contract<>v_spec.source_endpoint_contract
     or v_spec.registered_at_utc<v_endpoint_spec.registered_at_utc
  then
    return jsonb_build_object(
      'status','FROZEN_SOURCE_CONTRACT_MISMATCH',
      'shadow_only',true,
      'trade_permission',false,
      't1_stage_mapping_permitted',false,
      'production_promotion_permitted',false
    );
  end if;

  with source_rows as (
    select
      ep.candidate_id as endpoint_candidate_id,
      ep.diagnostic_id,
      ep.source_signal_id,
      ep.source_run_id as run_id,
      ep.captured_at_utc,
      ep.symbol,
      ep.candidate_direction,
      ep.classification as source_classification,
      ep.scanner_participation_confirmed,
      ep.volume_state_1h,
      ep.volume_ratio_1h,
      case
        when (sf.source_payload->>'open_interest_change_pct')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload->>'open_interest_change_pct')::double precision
      end as open_interest_change_pct
    from private.alpha_hunter_participation_universe_endpoint_candidates_v02 ep
    left join public.alpha_hunter_signal_features sf
      on sf.signal_id=ep.source_signal_id
    where ep.spec_id=v_endpoint_spec.spec_id
      and ep.captured_at_utc>=v_spec.registered_at_utc
  ), classified as (
    select s.*,
      case
        when s.scanner_participation_confirmed is true
          then 'SCANNER_CONFIRMED'
        when upper(coalesce(s.volume_state_1h,'')) in ('ELEVATED','HIGH')
          or coalesce(s.open_interest_change_pct,0)>0
          then 'EMERGING_PARTIAL_CHALLENGER'
        else 'NOT_EMERGING'
      end as challenger_class
    from source_rows s
  ), inserted as (
    insert into private.alpha_hunter_participation_emerging_universe_candidates_v02(
      candidate_id,spec_id,endpoint_candidate_id,diagnostic_id,source_signal_id,
      run_id,captured_at_utc,symbol,candidate_direction,source_classification,
      scanner_participation_confirmed,volume_state_1h,volume_ratio_1h,
      open_interest_change_pct,challenger_class,evidence,
      confirmatory_claim_permitted,t1_stage_mapping_permitted,
      threshold_derivation_permitted,production_promotion_permitted,
      shadow_only,trade_permission,order_path
    )
    select
      'part-emerging-universe-v02-'||md5(
        v_spec.spec_id||'|'||c.endpoint_candidate_id
      ),
      v_spec.spec_id,
      c.endpoint_candidate_id,
      c.diagnostic_id,
      c.source_signal_id,
      c.run_id,
      c.captured_at_utc,
      c.symbol,
      c.candidate_direction,
      c.source_classification,
      c.scanner_participation_confirmed,
      c.volume_state_1h,
      c.volume_ratio_1h,
      c.open_interest_change_pct,
      c.challenger_class,
      jsonb_build_object(
        'rule_origin','PREEXISTING_ALPHA_HUNTER_ANALYSIS_PARTIAL_CLASSIFICATION',
        'source_endpoint_spec_id',v_endpoint_spec.spec_id,
        'source_endpoint_contract',v_endpoint_spec.primary_return_contract,
        'source_consistent_endpoint',true,
        'volume_partial_rule',
          upper(coalesce(c.volume_state_1h,'')) in ('ELEVATED','HIGH'),
        'oi_partial_rule',coalesce(c.open_interest_change_pct,0)>0,
        'future_outcome_used_for_classification',false,
        'historical_backfill_permitted',false
      ),
      false,false,false,false,true,false,'NONE'
    from classified c
    on conflict(endpoint_candidate_id) do nothing
    returning 1
  )
  select count(*) into v_inserted from inserted;

  select count(*) into v_total
  from private.alpha_hunter_participation_emerging_universe_candidates_v02
  where spec_id=v_spec.spec_id;

  v_run_id:='part-emerging-universe-v02-run-'||md5(v_now::text);

  insert into private.alpha_hunter_participation_emerging_universe_runs_v02(
    run_id,spec_id,checked_at_utc,candidates_inserted,candidate_rows_total,
    evidence,shadow_only,trade_permission,t1_stage_mapping_permitted,
    production_promotion_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_inserted,v_total,
    jsonb_build_object(
      'rule_version',v_spec.rule_version,
      'source_endpoint_spec_id',v_endpoint_spec.spec_id,
      'source_endpoint_contract',v_endpoint_spec.primary_return_contract,
      'source_consistent_endpoint',true,
      'historical_backfill_permitted',false,
      'classification_only_no_stage_mapping',true
    ),
    true,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','OK',
    'run_id',v_run_id,
    'candidates_inserted',v_inserted,
    'candidate_rows_total',v_total,
    'source_endpoint_spec_id',v_endpoint_spec.spec_id,
    'source_endpoint_contract',v_endpoint_spec.primary_return_contract,
    'shadow_only',true,
    'trade_permission',false,
    't1_stage_mapping_permitted',false,
    'threshold_derivation_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

create or replace view private.alpha_hunter_participation_emerging_universe_scorecard_v02
with (security_invoker=true,security_barrier=true)
as
with source_spec as (
  select *
  from private.alpha_hunter_participation_universe_endpoint_specs_v02
  where spec_id='PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02'
), matured as (
  select
    c.candidate_id,
    c.endpoint_candidate_id,
    c.challenger_class,
    c.symbol,
    c.captured_at_utc,
    h.horizon_hours
  from private.alpha_hunter_participation_emerging_universe_candidates_v02 c
  cross join source_spec s
  cross join lateral unnest(s.horizons_hours) h(horizon_hours)
  where c.captured_at_utc+make_interval(hours=>h.horizon_hours)
    +make_interval(mins=>s.endpoint_max_lag_minutes)<=clock_timestamp()
), joined as (
  select
    m.*,
    o.direction_adjusted_return_pct,
    o.positive_directional_return,
    o.endpoint_lag_seconds,
    (o.outcome_id is not null) as has_outcome,
    (f.failure_id is not null) as has_failure
  from matured m
  left join private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
    on o.candidate_id=m.endpoint_candidate_id
   and o.horizon_hours=m.horizon_hours
  left join private.alpha_hunter_participation_universe_endpoint_failures_v02 f
    on f.candidate_id=m.endpoint_candidate_id
   and f.horizon_hours=m.horizon_hours
)
select
  challenger_class,
  horizon_hours,
  count(*) as matured_rows,
  count(*) filter(where has_outcome) as evaluated_rows,
  count(*) filter(where has_failure) as censored_rows,
  count(*) filter(where not has_outcome and not has_failure)
    as pending_materialization_rows,
  count(distinct symbol) as symbols,
  count(distinct date_trunc('day',captured_at_utc)) as utc_days,
  100.0*count(*) filter(where has_outcome)
    /nullif(count(*) filter(where has_outcome or has_failure),0)
      as source_coverage_pct,
  avg(direction_adjusted_return_pct) filter(where has_outcome)
    as avg_direction_adjusted_return_pct,
  percentile_cont(0.5) within group(order by direction_adjusted_return_pct)
    filter(where has_outcome) as median_direction_adjusted_return_pct,
  100.0*count(*) filter(where has_outcome and positive_directional_return)
    /nullif(count(*) filter(where has_outcome),0)
      as positive_directional_pct,
  avg(endpoint_lag_seconds) filter(where has_outcome)
    as avg_endpoint_lag_seconds,
  max(endpoint_lag_seconds) filter(where has_outcome)
    as max_endpoint_lag_seconds,
  min(captured_at_utc) as first_candidate_at_utc,
  max(captured_at_utc) as latest_candidate_at_utc,
  false as confirmatory_claim_permitted,
  false as t1_stage_mapping_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'FORWARD_SOURCE_CONSISTENT_CHALLENGER_MEASUREMENT_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from joined
group by challenger_class,horizon_hours;

revoke all on private.alpha_hunter_participation_emerging_universe_specs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_universe_candidates_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_universe_runs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_universe_scorecard_v02
from public,anon,authenticated,service_role;
revoke all on function private.alpha_hunter_capture_participation_emerging_universe_v02()
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_participation_emerging_universe_specs_v02
to service_role;
grant select on private.alpha_hunter_participation_emerging_universe_candidates_v02
to service_role;
grant select on private.alpha_hunter_participation_emerging_universe_runs_v02
to service_role;
grant select on private.alpha_hunter_participation_emerging_universe_scorecard_v02
to service_role;
grant execute on function private.alpha_hunter_capture_participation_emerging_universe_v02()
to postgres;

-- Stacked shadow collector only. It depends on the source-consistent endpoint
-- collector at :16 and therefore runs at :17. It does not modify source jobs.
do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-participation-emerging-universe-v02'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-participation-emerging-universe-v02',
  '17 * * * *',
  $cmd$
    select private.alpha_hunter_capture_participation_emerging_universe_v02();
  $cmd$
);

-- No v0.1 endpoint candidate or outcome table is referenced.
-- No source-consistent endpoint candidate before this challenger registered_at_utc is admitted.
