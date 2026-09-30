-- Alpha Hunter T0 threshold forward holdout v0.1
--
-- Purpose:
--   Break the threshold-validation circularity without activating thresholds.
--
-- Pilot candidate (NOT VALIDATED):
--   min T0 remaining-R = 0.125
--   max T0 stop distance = 5.0%
--
-- Pilot evidence (calibration-only):
--   n=170, avg path-R pre-cost=+0.176385R, SD=0.621990R
--   control n=920, avg=+0.012756R, SD=0.314462R
--   pilot delta=+0.163629R
--   LONG n=104 avg=+0.23379R
--   SHORT n=66 avg=+0.08592R
--   pre-2026-09-20 avg=+0.05525R
--   post-2026-09-20 avg=+0.30336R
--
-- Confirmatory design:
--   prospective only, no backfill;
--   candidate-time inclusion uses no future outcome;
--   TEST = eligible candidate with remaining-R>=0.125 and stop<=5%;
--   CONTROL = same eligible candidate pool failing the TEST numeric rule;
--   primary endpoint = TEST mean path-R pre-cost minus CONTROL mean path-R pre-cost;
--   minimum economic delta = +0.10R;
--   alpha=0.05 two-sided; target power=0.80;
--   sample floors from pilot variance: TEST>=320, CONTROL>=1700;
--   minimum TEST diversity: >=14 UTC days, >=50 symbols,
--   >=120 LONG and >=80 SHORT.
--
-- T1/T2:
--   numeric thresholds remain NOT_ESTIMABLE and NULL.
--
-- Activation:
--   impossible from this script. Threshold set stays DRAFT.
--   Even a holdout PASS does not validate or activate production thresholds.
--   Independent replication + validated execution cost model remain required.

create table if not exists private.alpha_hunter_t0_threshold_holdout_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  collection_deadline_utc timestamptz not null,
  status text not null check(status in ('COLLECTING','READY_FOR_EVALUATION','EVALUATED','FAILED_SAMPLE_FLOOR','INVALID')),
  threshold_set_id text not null,
  min_t0_remaining_r double precision not null check(min_t0_remaining_r>0),
  max_t0_stop_distance_pct double precision not null check(max_t0_stop_distance_pct>0),
  t1_numeric_status text not null check(t1_numeric_status='NOT_ESTIMABLE'),
  t2_numeric_status text not null check(t2_numeric_status='NOT_ESTIMABLE'),
  primary_endpoint text not null,
  minimum_effect_delta_r double precision not null check(minimum_effect_delta_r>0),
  alpha_two_sided double precision not null check(alpha_two_sided>0 and alpha_two_sided<1),
  target_power double precision not null check(target_power>0 and target_power<1),
  minimum_test_rows integer not null check(minimum_test_rows>0),
  minimum_control_rows integer not null check(minimum_control_rows>0),
  minimum_test_utc_days integer not null check(minimum_test_utc_days>0),
  minimum_test_symbols integer not null check(minimum_test_symbols>0),
  minimum_test_long_rows integer not null check(minimum_test_long_rows>0),
  minimum_test_short_rows integer not null check(minimum_test_short_rows>0),
  pilot_cutoff_utc timestamptz not null,
  pilot_evidence jsonb not null,
  inclusion_contract jsonb not null,
  missing_data_policy jsonb not null,
  duplicate_policy jsonb not null,
  falsification_contract jsonb not null,
  scientific_role text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  threshold_activation_permitted boolean not null default false check(threshold_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists private.alpha_hunter_t0_threshold_holdout_candidates_v01 (
  membership_id text primary key,
  spec_id text not null references private.alpha_hunter_t0_threshold_holdout_specs_v01(spec_id),
  scorecard_id text not null unique,
  captured_at_utc timestamptz not null default clock_timestamp(),
  candidate_at_utc timestamptz not null,
  horizon_due_at_utc timestamptz not null,
  run_id text not null,
  symbol text not null,
  direction text not null,
  scanner_direction text,
  candidate_entry double precision,
  stop_price double precision,
  target_price double precision,
  risk_distance_pct double precision,
  initial_remaining_r double precision,
  group_name text not null check(group_name in ('TEST','CONTROL','EXCLUDED')),
  candidate_eligibility_status text not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  threshold_activation_permitted boolean not null default false check(threshold_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

create index if not exists idx_ah_t0_holdout_candidates_group_due_v01
  on private.alpha_hunter_t0_threshold_holdout_candidates_v01(spec_id,group_name,horizon_due_at_utc);

create table if not exists private.alpha_hunter_t0_threshold_holdout_outcomes_v01 (
  holdout_outcome_id text primary key,
  spec_id text not null,
  membership_id text not null unique
    references private.alpha_hunter_t0_threshold_holdout_candidates_v01(membership_id),
  scorecard_id text not null,
  group_name text not null,
  symbol text not null,
  direction text not null,
  candidate_at_utc timestamptz not null,
  evaluated_at_utc timestamptz,
  evaluation_status text,
  path_r_pre_cost double precision,
  stop_hit boolean,
  stop_survived boolean,
  target_hit boolean,
  candidate_path_outcome text,
  outcome_eligible boolean not null,
  outcome_eligibility_status text not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  threshold_activation_permitted boolean not null default false check(threshold_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists private.alpha_hunter_t0_threshold_holdout_evaluations_v01 (
  evaluation_id text primary key,
  spec_id text not null unique,
  evaluated_at_utc timestamptz not null,
  verdict text not null check(verdict in ('PASS_PRE_COST_FORWARD_HOLDOUT','FAIL_PRE_COST_FORWARD_HOLDOUT')),
  test_n integer not null,
  control_n integer not null,
  test_long_n integer not null,
  test_short_n integer not null,
  test_utc_days integer not null,
  test_symbols integer not null,
  test_avg_r double precision not null,
  test_lower95_mean_r double precision not null,
  control_avg_r double precision not null,
  delta_r double precision not null,
  test_long_avg_r double precision,
  test_short_avg_r double precision,
  test_positive_pct double precision,
  control_positive_pct double precision,
  evidence jsonb not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  threshold_activation_permitted boolean not null default false check(threshold_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false check(realistic_net_r_claim_permitted=false),
  independent_replication_required boolean not null default true check(independent_replication_required=true),
  validated_execution_cost_model_required boolean not null default true check(validated_execution_cost_model_required=true),
  order_path text not null default 'NONE' check(order_path='NONE')
);

insert into public.alpha_hunter_money_entry_threshold_sets(
  threshold_set_id,status,max_t0_stop_distance_pct,min_t0_remaining_r,
  min_t1_remaining_r,min_t2_remaining_r,evidence_reference,
  validated_at_utc,activated_at_utc,model_version,shadow_only,trade_permission
) values (
  'ME-THRESH-T0-HOLDOUT-20260930-V01',
  'DRAFT',
  5.0,
  0.125,
  null,
  null,
  jsonb_build_object(
    'scientific_role','PREREGISTERED_T0_ONLY_FORWARD_CHALLENGER',
    'numeric_thresholds_frozen',true,
    't0_min_remaining_r',0.125,
    't0_max_stop_distance_pct',5.0,
    't1_numeric_status','NOT_ESTIMABLE',
    't2_numeric_status','NOT_ESTIMABLE',
    'activation_permitted',false,
    'validation_permitted_from_pilot',false,
    'independent_replication_required',true,
    'validated_execution_cost_model_required',true,
    'source_calibration_view','private.alpha_hunter_money_entry_calibration_cohort_v01'
  ),
  null,null,
  'money-entry-t0-forward-holdout-v0.1',
  true,false
)
on conflict(threshold_set_id) do nothing;

insert into private.alpha_hunter_t0_threshold_holdout_specs_v01(
  spec_id,registered_at_utc,collection_deadline_utc,status,threshold_set_id,
  min_t0_remaining_r,max_t0_stop_distance_pct,t1_numeric_status,t2_numeric_status,
  primary_endpoint,minimum_effect_delta_r,alpha_two_sided,target_power,
  minimum_test_rows,minimum_control_rows,minimum_test_utc_days,minimum_test_symbols,
  minimum_test_long_rows,minimum_test_short_rows,pilot_cutoff_utc,
  pilot_evidence,inclusion_contract,missing_data_policy,duplicate_policy,
  falsification_contract,scientific_role,
  shadow_only,trade_permission,production_promotion_permitted,
  threshold_activation_permitted,realistic_net_r_claim_permitted,order_path
) values (
  'T0-THRESHOLD-FORWARD-HOLDOUT-V01',
  clock_timestamp(),
  clock_timestamp()+interval '45 days',
  'COLLECTING',
  'ME-THRESH-T0-HOLDOUT-20260930-V01',
  0.125,5.0,'NOT_ESTIMABLE','NOT_ESTIMABLE',
  'MEAN_PATH_R_PRE_COST_TEST_MINUS_CONTROL',
  0.10,0.05,0.80,
  320,1700,14,50,120,80,
  clock_timestamp(),
  jsonb_build_object(
    'pilot_total_n',1090,
    'pilot_test_n',170,
    'pilot_control_n',920,
    'pilot_test_prevalence_pct',15.60,
    'pilot_test_avg_r',0.176385,
    'pilot_test_sd_r',0.621990,
    'pilot_control_avg_r',0.012756,
    'pilot_control_sd_r',0.314462,
    'pilot_delta_r',0.163629,
    'pilot_test_long_n',104,
    'pilot_test_short_n',66,
    'pilot_pre_2026_09_20_avg_r',0.05525,
    'pilot_post_2026_09_20_avg_r',0.30336,
    'pilot_long_avg_r',0.23379,
    'pilot_short_avg_r',0.08592,
    'sample_floor_derivation','Two-sample normal approximation, two-sided alpha 0.05, power 0.80, minimum delta 0.10R, pilot SDs and pilot control:test ratio.',
    'pilot_used_for_candidate_generation_only',true
  ),
  jsonb_build_object(
    'candidate_time_only',true,
    'post_direction_binding_fix_required',true,
    'geometry_valid_required',true,
    'scanner_direction_equals_direction_required',true,
    'geometry_source_required','SCANNER_EXECUTION_SETUP',
    'geometry_direction_bound_required',true,
    'research_geometry_promoted_forbidden',true,
    'candidate_shadow_only_required',true,
    'candidate_trade_permission_false_required',true,
    'test_rule','initial_remaining_r>=0.125 AND risk_distance_pct<=5.0',
    'control_rule','same eligible pool but TEST rule false'
  ),
  jsonb_build_object(
    'candidate_missing_numeric_geometry','EXCLUDED',
    'missing_24h_outcome','PENDING_NOT_IMPUTED',
    'non_evaluated_outcome','INELIGIBLE_PRESERVED',
    'missing_path_r_pre_cost','INELIGIBLE_PRESERVED'
  ),
  jsonb_build_object(
    'candidate_unit','scorecard_id',
    'one_membership_per_scorecard',true,
    'one_24h_outcome_per_membership',true
  ),
  jsonb_build_object(
    'fail_if_delta_r_below',0.10,
    'fail_if_test_lower95_mean_r_lte',0.0,
    'fail_if_test_long_avg_r_lte',0.0,
    'fail_if_test_short_avg_r_lte',0.0,
    'pass_does_not_activate_thresholds',true,
    'validated_cost_model_required_before_realistic_net_r',true,
    'independent_replication_required',true
  ),
  'PREREGISTERED_T0_THRESHOLD_FORWARD_HOLDOUT',
  true,false,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create or replace function private.alpha_hunter_capture_t0_threshold_holdout_candidate_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_t0_threshold_holdout_specs_v01%rowtype;
  v_group text;
  v_status text;
  v_base_eligible boolean;
begin
  select * into v_spec
  from private.alpha_hunter_t0_threshold_holdout_specs_v01
  where status='COLLECTING'
  order by registered_at_utc desc
  limit 1;

  if v_spec.spec_id is null or new.candidate_at_utc<v_spec.registered_at_utc then
    return new;
  end if;

  v_base_eligible :=
       new.candidate_at_utc>=timestamptz '2026-09-13 16:56:10+00'
   and new.geometry_valid is true
   and new.scanner_direction is not null
   and new.scanner_direction=new.direction
   and new.frozen_evidence->>'geometry_source'='SCANNER_EXECUTION_SETUP'
   and coalesce((new.frozen_evidence->>'geometry_direction_bound')::boolean,false)
   and not coalesce((new.frozen_evidence->>'research_geometry_promoted')::boolean,false)
   and new.shadow_only is true
   and new.trade_permission is false
   and new.initial_remaining_r is not null
   and new.risk_distance_pct is not null;

  if not v_base_eligible then
    v_group:='EXCLUDED';
    v_status:=case
      when new.geometry_valid is not true then 'EXPLICIT_GEOMETRY_INVALID_OR_MISSING'
      when new.scanner_direction is null then 'SCANNER_DIRECTION_MISSING'
      when new.scanner_direction<>new.direction then 'SCANNER_DIRECTION_MISMATCH'
      when new.frozen_evidence->>'geometry_source' is distinct from 'SCANNER_EXECUTION_SETUP' then 'NON_SCANNER_EXECUTION_GEOMETRY'
      when not coalesce((new.frozen_evidence->>'geometry_direction_bound')::boolean,false) then 'GEOMETRY_NOT_DIRECTION_BOUND'
      when coalesce((new.frozen_evidence->>'research_geometry_promoted')::boolean,false) then 'RESEARCH_GEOMETRY_PROMOTED'
      when new.shadow_only is not true or new.trade_permission is not false then 'SAFETY_BOUNDARY_VIOLATION'
      when new.initial_remaining_r is null then 'INITIAL_REMAINING_R_MISSING'
      when new.risk_distance_pct is null then 'RISK_DISTANCE_PCT_MISSING'
      else 'BASE_INCLUSION_FAILED'
    end;
  elsif new.initial_remaining_r>=v_spec.min_t0_remaining_r
        and new.risk_distance_pct<=v_spec.max_t0_stop_distance_pct then
    v_group:='TEST';
    v_status:='ELIGIBLE_TEST';
  else
    v_group:='CONTROL';
    v_status:='ELIGIBLE_CONTROL';
  end if;

  insert into private.alpha_hunter_t0_threshold_holdout_candidates_v01(
    membership_id,spec_id,scorecard_id,captured_at_utc,candidate_at_utc,horizon_due_at_utc,
    run_id,symbol,direction,scanner_direction,candidate_entry,stop_price,target_price,
    risk_distance_pct,initial_remaining_r,group_name,candidate_eligibility_status,
    evidence,shadow_only,trade_permission,production_promotion_permitted,
    threshold_activation_permitted,realistic_net_r_claim_permitted,order_path
  ) values (
    't0-holdout-'||md5(v_spec.spec_id||'|'||new.scorecard_id),
    v_spec.spec_id,new.scorecard_id,clock_timestamp(),new.candidate_at_utc,
    new.candidate_at_utc+interval '24 hours',new.run_id,new.symbol,new.direction,
    new.scanner_direction,new.candidate_entry,new.stop_price,new.target_price,
    new.risk_distance_pct,new.initial_remaining_r,v_group,v_status,
    jsonb_build_object(
      'candidate_time_capture',true,
      'future_outcome_used_for_group_assignment',false,
      'threshold_set_id',v_spec.threshold_set_id,
      't1_numeric_status',v_spec.t1_numeric_status,
      't2_numeric_status',v_spec.t2_numeric_status
    ),
    true,false,false,false,false,'NONE'
  )
  on conflict(scorecard_id) do nothing;

  return new;
exception when others then
  return new;
end;
$function$;

revoke all on function private.alpha_hunter_capture_t0_threshold_holdout_candidate_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_capture_t0_threshold_holdout_candidate_v01
  on public.alpha_hunter_big_mover_money_scorecard_candidates;

create trigger trg_ah_capture_t0_threshold_holdout_candidate_v01
after insert on public.alpha_hunter_big_mover_money_scorecard_candidates
for each row execute function private.alpha_hunter_capture_t0_threshold_holdout_candidate_v01();

create or replace function private.alpha_hunter_capture_t0_threshold_holdout_outcomes_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_now timestamptz:=clock_timestamp();
  v_inserted integer:=0;
  v_test integer:=0;
  v_control integer:=0;
begin
  with source_rows as (
    select c.*,o.evaluated_at_utc,o.evaluation_status,o.path_r_pre_cost,
           o.stop_hit,o.stop_survived,o.target_hit,o.candidate_path_outcome,
           o.shadow_only as outcome_shadow_only,
           o.trade_permission as outcome_trade_permission
    from private.alpha_hunter_t0_threshold_holdout_candidates_v01 c
    join public.alpha_hunter_big_mover_money_scorecard_outcomes o
      on o.scorecard_id=c.scorecard_id
     and o.horizon_hours=24
    where c.group_name in ('TEST','CONTROL')
      and c.horizon_due_at_utc<=v_now
      and not exists(
        select 1
        from private.alpha_hunter_t0_threshold_holdout_outcomes_v01 x
        where x.membership_id=c.membership_id
      )
  ), inserted as (
    insert into private.alpha_hunter_t0_threshold_holdout_outcomes_v01(
      holdout_outcome_id,spec_id,membership_id,scorecard_id,group_name,symbol,direction,
      candidate_at_utc,evaluated_at_utc,evaluation_status,path_r_pre_cost,
      stop_hit,stop_survived,target_hit,candidate_path_outcome,
      outcome_eligible,outcome_eligibility_status,evidence,
      shadow_only,trade_permission,production_promotion_permitted,
      threshold_activation_permitted,realistic_net_r_claim_permitted,order_path
    )
    select
      't0-holdout-outcome-'||md5(s.membership_id),
      s.spec_id,s.membership_id,s.scorecard_id,s.group_name,s.symbol,s.direction,
      s.candidate_at_utc,s.evaluated_at_utc,s.evaluation_status,s.path_r_pre_cost,
      s.stop_hit,s.stop_survived,s.target_hit,s.candidate_path_outcome,
      (
        s.evaluation_status='EVALUATED'
        and s.path_r_pre_cost is not null
        and s.outcome_shadow_only is true
        and s.outcome_trade_permission is false
      ),
      case
        when s.evaluation_status<>'EVALUATED' then 'OUTCOME_NOT_EVALUATED'
        when s.path_r_pre_cost is null then 'PATH_R_PRE_COST_MISSING'
        when s.outcome_shadow_only is not true or s.outcome_trade_permission is not false then 'OUTCOME_SAFETY_BOUNDARY_VIOLATION'
        else 'ELIGIBLE'
      end,
      jsonb_build_object(
        'horizon_hours',24,
        'outcome_source','alpha_hunter_big_mover_money_scorecard_outcomes',
        'realistic_net_r_claim_permitted',false
      ),
      true,false,false,false,false,'NONE'
    from source_rows s
    on conflict(membership_id) do nothing
    returning group_name
  )
  select count(*),
         count(*) filter(where group_name='TEST'),
         count(*) filter(where group_name='CONTROL')
  into v_inserted,v_test,v_control
  from inserted;

  return jsonb_build_object(
    'inserted',v_inserted,
    'test_inserted',v_test,
    'control_inserted',v_control,
    'shadow_only',true,
    'trade_permission',false,
    'threshold_activation_permitted',false,
    'realistic_net_r_claim_permitted',false
  );
end;
$function$;

revoke all on function private.alpha_hunter_capture_t0_threshold_holdout_outcomes_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_capture_t0_threshold_holdout_outcomes_v01()
to postgres;

create or replace view private.alpha_hunter_t0_threshold_holdout_status_v01
with (security_invoker=true,security_barrier=true)
as
with s as (
  select * from private.alpha_hunter_t0_threshold_holdout_specs_v01
  order by registered_at_utc desc limit 1
), c as (
  select
    count(*) filter(where group_name='TEST') as test_candidates,
    count(*) filter(where group_name='CONTROL') as control_candidates,
    count(*) filter(where group_name='EXCLUDED') as excluded_candidates,
    count(distinct symbol) filter(where group_name='TEST') as test_symbols,
    count(distinct date_trunc('day',candidate_at_utc)) filter(where group_name='TEST') as test_utc_days,
    count(*) filter(where group_name='TEST' and direction='LONG') as test_long_candidates,
    count(*) filter(where group_name='TEST' and direction='SHORT') as test_short_candidates
  from private.alpha_hunter_t0_threshold_holdout_candidates_v01
  where spec_id=(select spec_id from s)
), o as (
  select
    count(*) filter(where group_name='TEST' and outcome_eligible) as test_outcomes,
    count(*) filter(where group_name='CONTROL' and outcome_eligible) as control_outcomes,
    count(*) filter(where group_name='TEST' and direction='LONG' and outcome_eligible) as test_long_outcomes,
    count(*) filter(where group_name='TEST' and direction='SHORT' and outcome_eligible) as test_short_outcomes,
    count(distinct symbol) filter(where group_name='TEST' and outcome_eligible) as test_outcome_symbols,
    count(distinct date_trunc('day',candidate_at_utc)) filter(where group_name='TEST' and outcome_eligible) as test_outcome_utc_days
  from private.alpha_hunter_t0_threshold_holdout_outcomes_v01
  where spec_id=(select spec_id from s)
)
select
  s.spec_id,s.registered_at_utc,s.collection_deadline_utc,s.status,
  s.threshold_set_id,s.min_t0_remaining_r,s.max_t0_stop_distance_pct,
  s.t1_numeric_status,s.t2_numeric_status,
  c.test_candidates,c.control_candidates,c.excluded_candidates,
  o.test_outcomes,o.control_outcomes,o.test_long_outcomes,o.test_short_outcomes,
  o.test_outcome_symbols,o.test_outcome_utc_days,
  (
    o.test_outcomes>=s.minimum_test_rows
    and o.control_outcomes>=s.minimum_control_rows
    and o.test_outcome_utc_days>=s.minimum_test_utc_days
    and o.test_outcome_symbols>=s.minimum_test_symbols
    and o.test_long_outcomes>=s.minimum_test_long_rows
    and o.test_short_outcomes>=s.minimum_test_short_rows
  ) as sample_gate_ready,
  greatest(
    0,
    (select count(*)
     from private.alpha_hunter_t0_threshold_holdout_candidates_v01 x
     where x.spec_id=s.spec_id
       and x.group_name in ('TEST','CONTROL')
       and x.horizon_due_at_utc<=clock_timestamp()
       and not exists(
         select 1 from private.alpha_hunter_t0_threshold_holdout_outcomes_v01 y
         where y.membership_id=x.membership_id
       ))
  ) as due_without_outcome,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  false as threshold_activation_permitted,
  false as realistic_net_r_claim_permitted,
  'NONE'::text as order_path
from s cross join c cross join o;

create or replace function private.alpha_hunter_evaluate_t0_threshold_holdout_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_status record;
  v_spec private.alpha_hunter_t0_threshold_holdout_specs_v01%rowtype;
  v_test_n integer;
  v_control_n integer;
  v_test_long_n integer;
  v_test_short_n integer;
  v_days integer;
  v_symbols integer;
  v_test_avg double precision;
  v_test_sd double precision;
  v_test_lower95 double precision;
  v_control_avg double precision;
  v_delta double precision;
  v_long_avg double precision;
  v_short_avg double precision;
  v_test_positive double precision;
  v_control_positive double precision;
  v_verdict text;
  v_eval_id text;
begin
  select * into v_status
  from private.alpha_hunter_t0_threshold_holdout_status_v01;

  if v_status.spec_id is null then
    return jsonb_build_object('status','SPEC_NOT_FOUND');
  end if;

  select * into v_spec
  from private.alpha_hunter_t0_threshold_holdout_specs_v01
  where spec_id=v_status.spec_id;

  if v_status.sample_gate_ready is not true then
    return jsonb_build_object(
      'status','SAMPLE_GATE_NOT_READY',
      'test_outcomes',v_status.test_outcomes,
      'control_outcomes',v_status.control_outcomes,
      'test_long_outcomes',v_status.test_long_outcomes,
      'test_short_outcomes',v_status.test_short_outcomes,
      'test_outcome_symbols',v_status.test_outcome_symbols,
      'test_outcome_utc_days',v_status.test_outcome_utc_days,
      'threshold_activation_permitted',false,
      'trade_permission',false
    );
  end if;

  select
    count(*) filter(where group_name='TEST'),
    count(*) filter(where group_name='CONTROL'),
    count(*) filter(where group_name='TEST' and direction='LONG'),
    count(*) filter(where group_name='TEST' and direction='SHORT'),
    count(distinct date_trunc('day',candidate_at_utc)) filter(where group_name='TEST'),
    count(distinct symbol) filter(where group_name='TEST'),
    avg(path_r_pre_cost) filter(where group_name='TEST'),
    stddev_samp(path_r_pre_cost) filter(where group_name='TEST'),
    avg(path_r_pre_cost) filter(where group_name='CONTROL'),
    avg(path_r_pre_cost) filter(where group_name='TEST' and direction='LONG'),
    avg(path_r_pre_cost) filter(where group_name='TEST' and direction='SHORT'),
    100.0*count(*) filter(where group_name='TEST' and path_r_pre_cost>0)
      /nullif(count(*) filter(where group_name='TEST'),0),
    100.0*count(*) filter(where group_name='CONTROL' and path_r_pre_cost>0)
      /nullif(count(*) filter(where group_name='CONTROL'),0)
  into
    v_test_n,v_control_n,v_test_long_n,v_test_short_n,v_days,v_symbols,
    v_test_avg,v_test_sd,v_control_avg,v_long_avg,v_short_avg,
    v_test_positive,v_control_positive
  from private.alpha_hunter_t0_threshold_holdout_outcomes_v01
  where spec_id=v_spec.spec_id and outcome_eligible;

  v_test_lower95:=v_test_avg-1.96*v_test_sd/sqrt(v_test_n);
  v_delta:=v_test_avg-v_control_avg;

  v_verdict:=case
    when v_delta>=v_spec.minimum_effect_delta_r
      and v_test_lower95>0
      and v_long_avg>0
      and v_short_avg>0
    then 'PASS_PRE_COST_FORWARD_HOLDOUT'
    else 'FAIL_PRE_COST_FORWARD_HOLDOUT'
  end;

  v_eval_id:='t0-threshold-eval-'||md5(v_spec.spec_id);

  insert into private.alpha_hunter_t0_threshold_holdout_evaluations_v01(
    evaluation_id,spec_id,evaluated_at_utc,verdict,
    test_n,control_n,test_long_n,test_short_n,test_utc_days,test_symbols,
    test_avg_r,test_lower95_mean_r,control_avg_r,delta_r,
    test_long_avg_r,test_short_avg_r,test_positive_pct,control_positive_pct,
    evidence,shadow_only,trade_permission,production_promotion_permitted,
    threshold_activation_permitted,realistic_net_r_claim_permitted,
    independent_replication_required,validated_execution_cost_model_required,order_path
  ) values (
    v_eval_id,v_spec.spec_id,clock_timestamp(),v_verdict,
    v_test_n,v_control_n,v_test_long_n,v_test_short_n,v_days,v_symbols,
    v_test_avg,v_test_lower95,v_control_avg,v_delta,
    v_long_avg,v_short_avg,v_test_positive,v_control_positive,
    jsonb_build_object(
      'primary_endpoint',v_spec.primary_endpoint,
      'minimum_effect_delta_r',v_spec.minimum_effect_delta_r,
      'alpha_two_sided',v_spec.alpha_two_sided,
      'target_power',v_spec.target_power,
      'pre_cost_only',true,
      'pilot_reused_for_confirmation',false,
      'threshold_table_status_after_evaluation','DRAFT',
      't1_numeric_status','NOT_ESTIMABLE',
      't2_numeric_status','NOT_ESTIMABLE'
    ),
    true,false,false,false,false,true,true,'NONE'
  )
  on conflict(spec_id) do nothing;

  return jsonb_build_object(
    'status','EVALUATED',
    'verdict',v_verdict,
    'test_n',v_test_n,
    'control_n',v_control_n,
    'test_avg_r',v_test_avg,
    'test_lower95_mean_r',v_test_lower95,
    'control_avg_r',v_control_avg,
    'delta_r',v_delta,
    'test_long_avg_r',v_long_avg,
    'test_short_avg_r',v_short_avg,
    'threshold_activation_permitted',false,
    'realistic_net_r_claim_permitted',false,
    'independent_replication_required',true
  );
end;
$function$;

revoke all on function private.alpha_hunter_evaluate_t0_threshold_holdout_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_evaluate_t0_threshold_holdout_v01()
to postgres;

revoke all on private.alpha_hunter_t0_threshold_holdout_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_outcomes_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_evaluations_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_status_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_t0_threshold_holdout_specs_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_candidates_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_outcomes_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_evaluations_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_status_v01 to service_role;

do $cron$
declare r record;
begin
  for r in
    select jobid from cron.job
    where jobname='alpha-hunter-t0-threshold-holdout-outcomes-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-t0-threshold-holdout-outcomes-v01',
  '56 * * * *',
  $cmd$
    select private.alpha_hunter_capture_t0_threshold_holdout_outcomes_v01();
  $cmd$
);

-- No historical scorecard candidate is inserted or backfilled.
-- This script does not set threshold status to VALIDATED or ACTIVE.
