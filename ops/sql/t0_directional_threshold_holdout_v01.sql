-- Alpha Hunter directional T0 threshold holdout v0.1
--
-- Mission:
--   Break the Money Entry threshold circularity scientifically without
--   activating production thresholds.
--
-- Findings motivating this contract:
--   * global production threshold table is direction-agnostic;
--   * historical threshold-independent T0 base gate:
--       LONG = 222 rows
--       SHORT = 8 rows
--   * T1/T2 acceptance/trigger/expansion fields are not currently captured;
--   * therefore only LONG T0 has enough pilot evidence for a forward holdout.
--
-- LONG exploratory candidate:
--   max T0 stop distance = 15.0%
--   min T0 remaining-R   = 0.05
-- Pilot (pre-cost path-R, 3m stop/target-resolved):
--   n=113, symbols=61, mean=+0.127396R, SD=0.270180R,
--   median=+0.121411R, positive=85.84%, stop-survived=97.35%.
--
-- Internal temporal check:
--   derivation 17-19 Sep: n=40, mean=+0.0869R
--   internal validation 20-27 Sep: n=73, mean=+0.1496R
--
-- Confirmatory forward sample floor:
--   minimum economic effect = +0.05R
--   two-sided alpha = 0.05
--   target power = 0.80
--   pilot SD = 0.270180R
--   n = ceil(((1.96 + 0.8416)*0.270180/0.05)^2) = 230
--
-- Scientific boundary:
--   * no historical backfill;
--   * no active production threshold;
--   * no T1/T2 numeric inference;
--   * no realistic-net-R claim;
--   * no threshold activation or production promotion by this experiment.

create table if not exists private.alpha_hunter_t0_threshold_holdout_specs_v01 (
  spec_id text primary key,
  direction text not null check(direction in ('LONG','SHORT')),
  status text not null check(status in ('COLLECTING','DATA_COLLECTION_ONLY','PAUSED','COMPLETE')),
  registered_at_utc timestamptz not null,
  holdout_not_before_utc timestamptz not null,
  max_t0_stop_distance_pct double precision,
  min_t0_remaining_r double precision,
  min_t1_remaining_r double precision,
  min_t2_remaining_r double precision,
  primary_horizon_hours integer not null default 24 check(primary_horizon_hours=24),
  minimum_completed_candidates integer not null,
  minimum_distinct_symbols integer not null,
  minimum_distinct_utc_days integer not null,
  minimum_economic_effect_r double precision,
  alpha_two_sided double precision,
  target_power double precision,
  pilot_n integer,
  pilot_distinct_symbols integer,
  pilot_mean_r double precision,
  pilot_sd_r double precision,
  pilot_median_r double precision,
  pilot_positive_pct double precision,
  pilot_stop_survived_pct double precision,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_activation_permitted boolean not null default false
    check(threshold_activation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(holdout_not_before_utc>=registered_at_utc),
  check(max_t0_stop_distance_pct is null or max_t0_stop_distance_pct>0),
  check(min_t0_remaining_r is null or min_t0_remaining_r>=0),
  check(min_t1_remaining_r is null),
  check(min_t2_remaining_r is null)
);

insert into private.alpha_hunter_t0_threshold_holdout_specs_v01(
  spec_id,direction,status,registered_at_utc,holdout_not_before_utc,
  max_t0_stop_distance_pct,min_t0_remaining_r,min_t1_remaining_r,min_t2_remaining_r,
  primary_horizon_hours,minimum_completed_candidates,minimum_distinct_symbols,
  minimum_distinct_utc_days,minimum_economic_effect_r,alpha_two_sided,target_power,
  pilot_n,pilot_distinct_symbols,pilot_mean_r,pilot_sd_r,pilot_median_r,
  pilot_positive_pct,pilot_stop_survived_pct,evidence,
  shadow_only,trade_permission,threshold_activation_permitted,
  production_promotion_permitted,realistic_net_r_claim_permitted,order_path
)
values
(
  'ME-T0-LONG-HOLDOUT-V01',
  'LONG',
  'COLLECTING',
  clock_timestamp(),
  clock_timestamp(),
  15.0,
  0.05,
  null,
  null,
  24,
  230,
  60,
  20,
  0.05,
  0.05,
  0.80,
  113,
  61,
  0.127396,
  0.270180,
  0.121411,
  85.84,
  97.35,
  jsonb_build_object(
    'scientific_role','PREREGISTERED_FORWARD_T0_HOLDOUT',
    'direction_specific',true,
    'production_global_threshold_schema_is_direction_agnostic',true,
    'pilot_derivation_window','2026-09-17_to_2026-09-19',
    'pilot_internal_validation_window','2026-09-20_to_2026-09-27',
    'derivation_n',40,
    'derivation_mean_r',0.0869,
    'internal_validation_n',73,
    'internal_validation_mean_r',0.1496,
    'primary_endpoint','24H_PATH_R_PRE_COST',
    'path_source','BITGET_PUBLIC_V3_3M_CANDLES_STOP_TARGET_RESOLVED',
    'ambiguous_intrabar_excluded',true,
    'confirmatory_primary_rule','N_AND_DIVERSITY_GATES_MET_AND_MEAN_R_GE_0_05_AND_LOWER95_MEAN_R_GT_0',
    'secondary_rule','STOP_SURVIVED_PCT_GE_90',
    'cost_model_required_before_activation',true,
    't1_t2_numeric_thresholds_frozen',false,
    'historical_backfill_permitted',false
  ),
  true,false,false,false,false,'NONE'
),
(
  'ME-T0-SHORT-COLLECTION-V01',
  'SHORT',
  'DATA_COLLECTION_ONLY',
  clock_timestamp(),
  clock_timestamp(),
  null,
  null,
  null,
  null,
  24,
  100,
  40,
  10,
  null,
  null,
  null,
  8,
  8,
  null,
  null,
  null,
  null,
  null,
  jsonb_build_object(
    'scientific_role','FORWARD_SHORT_T0_DATA_COLLECTION_ONLY',
    'direction_specific',true,
    'historical_full_base_gate_rows',8,
    'numeric_threshold_inference_permitted',false,
    'minimum_rows_before_new_derivation_review',100,
    't1_t2_numeric_thresholds_frozen',false,
    'historical_backfill_permitted',false
  ),
  true,false,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_t0_threshold_holdout_candidates_v01 (
  holdout_candidate_id text primary key,
  spec_id text not null references private.alpha_hunter_t0_threshold_holdout_specs_v01(spec_id),
  scorecard_id text not null,
  stage_snapshot_id text not null,
  candidate_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  risk_distance_pct double precision not null,
  initial_remaining_r double precision not null,
  base_gate_pass boolean not null,
  numeric_threshold_pass boolean,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_activation_permitted boolean not null default false
    check(threshold_activation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  captured_at_utc timestamptz not null default clock_timestamp(),
  unique(spec_id,scorecard_id)
);

create index if not exists idx_ah_t0_holdout_candidate_due_v01
  on private.alpha_hunter_t0_threshold_holdout_candidates_v01(
    spec_id,candidate_at_utc
  );

create table if not exists private.alpha_hunter_t0_threshold_holdout_outcomes_v01 (
  holdout_outcome_id text primary key,
  holdout_candidate_id text not null unique
    references private.alpha_hunter_t0_threshold_holdout_candidates_v01(holdout_candidate_id),
  spec_id text not null,
  scorecard_id text not null,
  symbol text not null,
  direction text not null,
  evaluated_at_utc timestamptz not null,
  path_resolution text not null,
  path_r_pre_cost double precision not null,
  stop_survived boolean,
  target_hit boolean,
  positive_path boolean not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_activation_permitted boolean not null default false
    check(threshold_activation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists private.alpha_hunter_t0_threshold_holdout_runs_v01 (
  run_id text primary key,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  outcomes_inserted integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_activation_permitted boolean not null default false
    check(threshold_activation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

create or replace function private.alpha_hunter_run_t0_threshold_holdout_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_now timestamptz:=clock_timestamp();
  v_candidates integer:=0;
  v_outcomes integer:=0;
  v_run_id text;
begin
  with src as (
    select
      sp.spec_id,
      sp.direction as spec_direction,
      sp.status as spec_status,
      sp.holdout_not_before_utc,
      sp.max_t0_stop_distance_pct,
      sp.min_t0_remaining_r,
      c.scorecard_id,
      c.candidate_at_utc,
      c.symbol,
      c.direction,
      c.risk_distance_pct,
      c.initial_remaining_r,
      c.geometry_valid,
      c.scanner_direction,
      c.frozen_evidence,
      c.money_entry_stage_snapshot_id,
      c.shadow_only as candidate_shadow_only,
      c.trade_permission as candidate_trade_permission,
      s.direction_12h,
      s.direction_1d,
      s.execution_setup_direction,
      s.liquidity_ok,
      s.scanner_participation_confirmed,
      s.participation_emerging,
      s.scanner_structure_valid,
      s.open_position_conflict,
      s.candidate_entry,
      s.stop_price,
      s.target_price,
      s.shadow_only as stage_shadow_only,
      s.trade_permission as stage_trade_permission
    from private.alpha_hunter_t0_threshold_holdout_specs_v01 sp
    join public.alpha_hunter_big_mover_money_scorecard_candidates c
      on c.direction=sp.direction
     and c.candidate_at_utc>=sp.holdout_not_before_utc
    join public.alpha_hunter_money_entry_stage_snapshots s
      on s.stage_snapshot_id=c.money_entry_stage_snapshot_id
    where sp.status in ('COLLECTING','DATA_COLLECTION_ONLY')
  ), gated as (
    select src.*,
      (
        src.geometry_valid is true
        and src.scanner_direction=src.direction
        and src.frozen_evidence->>'geometry_source'='SCANNER_EXECUTION_SETUP'
        and coalesce((src.frozen_evidence->>'geometry_direction_bound')::boolean,false)
        and not coalesce((src.frozen_evidence->>'research_geometry_promoted')::boolean,false)
        and case when src.direction='LONG'
                 then src.direction_12h='BULLISH' and src.direction_1d='BULLISH'
                 when src.direction='SHORT'
                 then src.direction_12h='BEARISH' and src.direction_1d='BEARISH'
                 else false end
        and src.execution_setup_direction=src.direction
        and src.liquidity_ok is true
        and (
          src.scanner_participation_confirmed is true
          or src.participation_emerging is true
        )
        and src.scanner_structure_valid is true
        and coalesce(src.open_position_conflict,false)=false
        and src.candidate_entry is not null and src.candidate_entry>0
        and src.stop_price is not null
        and src.target_price is not null
        and src.risk_distance_pct is not null
        and src.initial_remaining_r is not null
        and src.candidate_shadow_only is true
        and src.candidate_trade_permission is false
        and src.stage_shadow_only is true
        and src.stage_trade_permission is false
      ) as base_gate_pass
    from src
  ), inserted as (
    insert into private.alpha_hunter_t0_threshold_holdout_candidates_v01(
      holdout_candidate_id,spec_id,scorecard_id,stage_snapshot_id,
      candidate_at_utc,symbol,direction,risk_distance_pct,initial_remaining_r,
      base_gate_pass,numeric_threshold_pass,evidence,
      shadow_only,trade_permission,threshold_activation_permitted,
      production_promotion_permitted,realistic_net_r_claim_permitted,order_path
    )
    select
      't0-holdout-'||md5(g.spec_id||'|'||g.scorecard_id),
      g.spec_id,
      g.scorecard_id,
      g.money_entry_stage_snapshot_id,
      g.candidate_at_utc,
      g.symbol,
      g.direction,
      g.risk_distance_pct,
      g.initial_remaining_r,
      g.base_gate_pass,
      case
        when g.spec_status='COLLECTING'
          and g.max_t0_stop_distance_pct is not null
          and g.min_t0_remaining_r is not null
        then g.base_gate_pass
          and g.risk_distance_pct<=g.max_t0_stop_distance_pct
          and g.initial_remaining_r>=g.min_t0_remaining_r
        else null
      end,
      jsonb_build_object(
        'base_gate_contract','MONEY_ENTRY_STAGE_V04_EXCLUDING_NUMERIC_THRESHOLD',
        'numeric_threshold_contract',
          case when g.spec_status='COLLECTING'
               then jsonb_build_object(
                 'max_t0_stop_distance_pct',g.max_t0_stop_distance_pct,
                 'min_t0_remaining_r',g.min_t0_remaining_r
               )
               else null end,
        'future_outcome_used_for_selection',false,
        'historical_backfill_permitted',false,
        't1_t2_numeric_thresholds_frozen',false
      ),
      true,false,false,false,false,'NONE'
    from gated g
    where g.base_gate_pass
    on conflict(spec_id,scorecard_id) do nothing
    returning 1
  )
  select count(*) into v_candidates from inserted;

  with due as (
    select h.*,o.evaluated_at_utc,o.path_resolution,o.path_r_pre_cost,
           o.stop_survived,o.target_hit
    from private.alpha_hunter_t0_threshold_holdout_candidates_v01 h
    join public.alpha_hunter_big_mover_money_scorecard_outcomes o
      on o.scorecard_id=h.scorecard_id
     and o.horizon_hours=24
    where o.evaluation_status='EVALUATED'
      and o.path_r_pre_cost is not null
      and o.path_resolution in ('STOP_FIRST','TARGET_FIRST','OPEN_AT_HORIZON')
      and not exists (
        select 1
        from private.alpha_hunter_t0_threshold_holdout_outcomes_v01 x
        where x.holdout_candidate_id=h.holdout_candidate_id
      )
  ), inserted as (
    insert into private.alpha_hunter_t0_threshold_holdout_outcomes_v01(
      holdout_outcome_id,holdout_candidate_id,spec_id,scorecard_id,symbol,direction,
      evaluated_at_utc,path_resolution,path_r_pre_cost,stop_survived,target_hit,
      positive_path,evidence,
      shadow_only,trade_permission,threshold_activation_permitted,
      production_promotion_permitted,realistic_net_r_claim_permitted,order_path
    )
    select
      't0-holdout-outcome-'||md5(d.holdout_candidate_id),
      d.holdout_candidate_id,d.spec_id,d.scorecard_id,d.symbol,d.direction,
      d.evaluated_at_utc,d.path_resolution,d.path_r_pre_cost,d.stop_survived,
      d.target_hit,d.path_r_pre_cost>0,
      jsonb_build_object(
        'measurement_source','EXISTING_IMMUTABLE_MONEY_SCORECARD_24H_OUTCOME',
        'pre_cost_only',true,
        'validated_cost_model',false,
        'realistic_net_r_claim_permitted',false
      ),
      true,false,false,false,false,'NONE'
    from due d
    on conflict(holdout_candidate_id) do nothing
    returning 1
  )
  select count(*) into v_outcomes from inserted;

  v_run_id:='t0-holdout-run-'||md5(v_now::text);

  insert into private.alpha_hunter_t0_threshold_holdout_runs_v01(
    run_id,checked_at_utc,candidates_inserted,outcomes_inserted,evidence,
    shadow_only,trade_permission,threshold_activation_permitted,
    production_promotion_permitted,order_path
  ) values (
    v_run_id,v_now,v_candidates,v_outcomes,
    jsonb_build_object(
      'model_version','directional-t0-threshold-holdout-v0.1',
      'historical_backfill_permitted',false,
      'threshold_activation_permitted',false
    ),
    true,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'run_id',v_run_id,
    'candidates_inserted',v_candidates,
    'outcomes_inserted',v_outcomes,
    'shadow_only',true,
    'trade_permission',false,
    'threshold_activation_permitted',false,
    'production_promotion_permitted',false,
    'realistic_net_r_claim_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_t0_threshold_holdout_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_t0_threshold_holdout_v01()
to postgres;

create or replace view private.alpha_hunter_t0_threshold_holdout_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
with joined as (
  select
    sp.*,
    h.holdout_candidate_id,
    h.symbol,
    h.candidate_at_utc,
    h.numeric_threshold_pass,
    o.path_r_pre_cost,
    o.stop_survived,
    o.target_hit,
    o.positive_path
  from private.alpha_hunter_t0_threshold_holdout_specs_v01 sp
  left join private.alpha_hunter_t0_threshold_holdout_candidates_v01 h
    on h.spec_id=sp.spec_id
  left join private.alpha_hunter_t0_threshold_holdout_outcomes_v01 o
    on o.holdout_candidate_id=h.holdout_candidate_id
), agg as (
  select
    spec_id,direction,status,max_t0_stop_distance_pct,min_t0_remaining_r,
    minimum_completed_candidates,minimum_distinct_symbols,minimum_distinct_utc_days,
    minimum_economic_effect_r,
    count(*) filter(
      where path_r_pre_cost is not null
        and (numeric_threshold_pass is true or status='DATA_COLLECTION_ONLY')
    ) as completed_rows,
    count(distinct symbol) filter(
      where path_r_pre_cost is not null
        and (numeric_threshold_pass is true or status='DATA_COLLECTION_ONLY')
    ) as distinct_symbols,
    count(distinct candidate_at_utc::date) filter(
      where path_r_pre_cost is not null
        and (numeric_threshold_pass is true or status='DATA_COLLECTION_ONLY')
    ) as distinct_utc_days,
    avg(path_r_pre_cost) filter(
      where numeric_threshold_pass is true and path_r_pre_cost is not null
    ) as mean_r,
    stddev_samp(path_r_pre_cost) filter(
      where numeric_threshold_pass is true and path_r_pre_cost is not null
    ) as sd_r,
    percentile_cont(0.5) within group(order by path_r_pre_cost) filter(
      where numeric_threshold_pass is true and path_r_pre_cost is not null
    ) as median_r,
    100.0*count(*) filter(
      where numeric_threshold_pass is true and positive_path
    )/nullif(count(*) filter(
      where numeric_threshold_pass is true and path_r_pre_cost is not null
    ),0) as positive_pct,
    100.0*count(*) filter(
      where numeric_threshold_pass is true and stop_survived
    )/nullif(count(*) filter(
      where numeric_threshold_pass is true and path_r_pre_cost is not null
    ),0) as stop_survived_pct
  from joined
  group by
    spec_id,direction,status,max_t0_stop_distance_pct,min_t0_remaining_r,
    minimum_completed_candidates,minimum_distinct_symbols,minimum_distinct_utc_days,
    minimum_economic_effect_r
)
select
  *,
  case
    when status<>'COLLECTING' then false
    when completed_rows<minimum_completed_candidates then false
    when distinct_symbols<minimum_distinct_symbols then false
    when distinct_utc_days<minimum_distinct_utc_days then false
    when mean_r is null or mean_r<minimum_economic_effect_r then false
    when sd_r is null or completed_rows<2 then false
    when mean_r-1.96*sd_r/sqrt(completed_rows)<=0 then false
    when stop_survived_pct<90.0 then false
    else true
  end as gross_holdout_pass,
  case
    when completed_rows>=2 and mean_r is not null and sd_r is not null
      then mean_r-1.96*sd_r/sqrt(completed_rows)
  end as mean_r_lower_95,
  false as threshold_activation_permitted,
  false as production_promotion_permitted,
  false as realistic_net_r_claim_permitted,
  'PRE_COST_FORWARD_HOLDOUT_ONLY'::text as claim_ceiling
from agg;

revoke all on private.alpha_hunter_t0_threshold_holdout_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_outcomes_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_holdout_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_t0_threshold_holdout_specs_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_candidates_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_outcomes_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_runs_v01 to service_role;
grant select on private.alpha_hunter_t0_threshold_holdout_scorecard_v01 to service_role;

do $cron$
declare r record;
begin
  for r in
    select jobid from cron.job
    where jobname='alpha-hunter-t0-threshold-holdout-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-t0-threshold-holdout-v01',
  '58 * * * *',
  $cmd$
    select private.alpha_hunter_run_t0_threshold_holdout_v01();
  $cmd$
);

-- No production threshold row is activated or numerically populated by this script.
