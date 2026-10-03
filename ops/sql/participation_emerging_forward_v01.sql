-- Alpha Hunter emerging-participation forward challenger v0.1
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
-- This experiment is forward-only and binds to the timestamp-correct
-- participation endpoint ledger v0.1.
--
-- It does NOT define T1, acceptance, trigger, expansion, or trade permission.

create table if not exists private.alpha_hunter_participation_emerging_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  rule_version text not null,
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

insert into private.alpha_hunter_participation_emerging_specs_v01(
  spec_id,registered_at_utc,rule_version,primary_horizon_hours,
  minimum_evaluated_candidates,minimum_distinct_symbols,minimum_distinct_utc_days,
  status,rule_definition,scientific_role,
  confirmatory_claim_permitted,t1_stage_mapping_permitted,
  threshold_derivation_permitted,production_promotion_permitted,
  shadow_only,trade_permission,order_path
) values (
  'PARTICIPATION-EMERGING-PARTIAL-V01',
  clock_timestamp(),
  'analysis.py institutional_participation PARTIAL rule',
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
    'historical_backfill_permitted',false
  ),
  'FORWARD_PARTICIPATION_EMERGING_CHALLENGER',
  false,false,false,false,true,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_participation_emerging_candidates_v01 (
  candidate_id text primary key,
  spec_id text not null
    references private.alpha_hunter_participation_emerging_specs_v01(spec_id),
  endpoint_candidate_id text not null unique
    references private.alpha_hunter_participation_endpoint_candidates_v01(candidate_id),
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
  scientific_role text not null default 'FORWARD_PARTICIPATION_EMERGING_CANDIDATE',
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

create index if not exists idx_ah_part_emerging_candidate_time_v01
  on private.alpha_hunter_participation_emerging_candidates_v01(
    spec_id,captured_at_utc
  );

create table if not exists private.alpha_hunter_participation_emerging_runs_v01 (
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

create or replace function private.alpha_hunter_capture_participation_emerging_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_participation_emerging_specs_v01%rowtype;
  v_now timestamptz:=clock_timestamp();
  v_inserted integer:=0;
  v_total integer:=0;
  v_run_id text;
begin
  select * into v_spec
  from private.alpha_hunter_participation_emerging_specs_v01
  where spec_id='PARTICIPATION-EMERGING-PARTIAL-V01'
    and status='COLLECTING';

  if v_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false,
      't1_stage_mapping_permitted',false
    );
  end if;

  with source_rows as (
    select
      ep.candidate_id as endpoint_candidate_id,
      ep.diagnostic_id,
      ep.source_signal_id,
      ep.run_id,
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
    from private.alpha_hunter_participation_endpoint_candidates_v01 ep
    left join public.alpha_hunter_signal_features sf
      on sf.signal_id=ep.source_signal_id
    where ep.captured_at_utc>=v_spec.registered_at_utc
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
    insert into private.alpha_hunter_participation_emerging_candidates_v01(
      candidate_id,spec_id,endpoint_candidate_id,diagnostic_id,source_signal_id,
      run_id,captured_at_utc,symbol,candidate_direction,source_classification,
      scanner_participation_confirmed,volume_state_1h,volume_ratio_1h,
      open_interest_change_pct,challenger_class,evidence,
      confirmatory_claim_permitted,t1_stage_mapping_permitted,
      threshold_derivation_permitted,production_promotion_permitted,
      shadow_only,trade_permission,order_path
    )
    select
      'part-emerging-'||md5(v_spec.spec_id||'|'||c.endpoint_candidate_id),
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
  from private.alpha_hunter_participation_emerging_candidates_v01
  where spec_id=v_spec.spec_id;

  v_run_id:='part-emerging-run-'||md5(v_now::text);

  insert into private.alpha_hunter_participation_emerging_runs_v01(
    run_id,spec_id,checked_at_utc,candidates_inserted,candidate_rows_total,
    evidence,shadow_only,trade_permission,t1_stage_mapping_permitted,
    production_promotion_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_inserted,v_total,
    jsonb_build_object(
      'rule_version',v_spec.rule_version,
      'historical_backfill_permitted',false,
      'classification_only_no_stage_mapping',true
    ),
    true,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'run_id',v_run_id,
    'candidates_inserted',v_inserted,
    'candidate_rows_total',v_total,
    'shadow_only',true,
    'trade_permission',false,
    't1_stage_mapping_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_capture_participation_emerging_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_capture_participation_emerging_v01()
to postgres;

create or replace view private.alpha_hunter_participation_emerging_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  c.challenger_class,
  o.horizon_hours,
  count(*) as evaluated_rows,
  count(distinct c.symbol) as symbols,
  count(distinct date_trunc('day',c.captured_at_utc)) as utc_days,
  avg(o.direction_adjusted_return_pct) as avg_direction_adjusted_return_pct,
  percentile_cont(0.5) within group(order by o.direction_adjusted_return_pct)
    as median_direction_adjusted_return_pct,
  100.0*count(*) filter(where o.positive_directional_return)
    /nullif(count(*),0) as positive_directional_pct,
  min(c.captured_at_utc) as first_candidate_at_utc,
  max(c.captured_at_utc) as latest_candidate_at_utc,
  false as confirmatory_claim_permitted,
  false as t1_stage_mapping_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'FORWARD_CHALLENGER_MEASUREMENT_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from private.alpha_hunter_participation_emerging_candidates_v01 c
join private.alpha_hunter_participation_endpoint_outcomes_v01 o
  on o.candidate_id=c.endpoint_candidate_id
group by c.challenger_class,o.horizon_hours;

revoke all on private.alpha_hunter_participation_emerging_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_emerging_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_participation_emerging_specs_v01
to service_role;
grant select on private.alpha_hunter_participation_emerging_candidates_v01
to service_role;
grant select on private.alpha_hunter_participation_emerging_runs_v01
to service_role;
grant select on private.alpha_hunter_participation_emerging_scorecard_v01
to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-participation-emerging-forward-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-participation-emerging-forward-v01',
  '15 * * * *',
  $cmd$
    select private.alpha_hunter_capture_participation_emerging_v01();
  $cmd$
);

-- No endpoint candidate observed before registered_at_utc is admitted.
