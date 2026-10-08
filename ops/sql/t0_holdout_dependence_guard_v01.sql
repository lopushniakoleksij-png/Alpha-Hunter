-- Alpha Hunter T0 LONG forward holdout dependence guard v0.1
--
-- Registered before any 24H outcome has matured for ME-T0-LONG-HOLDOUT-V01.
--
-- Problem:
--   The holdout admits repeated observations of the same symbol across scans.
--   Candidate-level standard errors can therefore overstate independent sample
--   size if repeated symbol/time observations are correlated.
--
-- Confirmatory companion contract:
--   * original preregistered holdout scorecard must pass;
--   * candidate rows >= 230;
--   * distinct symbols >= 60;
--   * distinct UTC days >= 20;
--   * symbol-cluster mean >= +0.05R and lower95 > 0;
--   * UTC-day-cluster mean >= +0.05R and lower95 > 0;
--   * no threshold activation or production promotion is permitted here.
--
-- Each symbol/day receives equal weight inside its respective cluster check.
-- This is deliberately more conservative than treating every repeated scan as
-- an independent observation.

create table if not exists private.alpha_hunter_t0_dependence_contracts_v01 (
  contract_id text primary key,
  holdout_spec_id text not null unique,
  registered_at_utc timestamptz not null,
  minimum_candidate_rows integer not null,
  minimum_symbol_clusters integer not null,
  minimum_day_clusters integer not null,
  minimum_cluster_mean_r double precision not null,
  z_value double precision not null,
  require_original_gross_holdout_pass boolean not null,
  primary_independence_unit text not null,
  secondary_independence_unit text not null,
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
  check(minimum_candidate_rows>0),
  check(minimum_symbol_clusters>1),
  check(minimum_day_clusters>1),
  check(minimum_cluster_mean_r>0),
  check(z_value>0)
);

insert into private.alpha_hunter_t0_dependence_contracts_v01(
  contract_id,holdout_spec_id,registered_at_utc,
  minimum_candidate_rows,minimum_symbol_clusters,minimum_day_clusters,
  minimum_cluster_mean_r,z_value,require_original_gross_holdout_pass,
  primary_independence_unit,secondary_independence_unit,evidence,
  shadow_only,trade_permission,threshold_activation_permitted,
  production_promotion_permitted,realistic_net_r_claim_permitted,order_path
) values (
  'ME-T0-LONG-DEPENDENCE-GUARD-V01',
  'ME-T0-LONG-HOLDOUT-V01',
  clock_timestamp(),
  230,
  60,
  20,
  0.05,
  1.96,
  true,
  'SYMBOL_EQUAL_WEIGHT_CLUSTER_MEAN',
  'UTC_DAY_EQUAL_WEIGHT_CLUSTER_MEAN',
  jsonb_build_object(
    'scientific_role','PREREGISTERED_DEPENDENCE_HANDLING_COMPANION',
    'registered_before_holdout_outcomes_matured',true,
    'candidate_level_repeated_observations_treated_as_correlated',true,
    'symbol_cluster_rule','MEAN_R_PER_SYMBOL_THEN_EQUAL_WEIGHT_ACROSS_SYMBOLS',
    'utc_day_cluster_rule','MEAN_R_PER_UTC_DAY_THEN_EQUAL_WEIGHT_ACROSS_DAYS',
    'both_cluster_lower95_must_exceed_zero',true,
    'both_cluster_means_must_meet_minimum_effect_r',true,
    'historical_backfill_permitted',false,
    'threshold_activation_permitted',false,
    'validated_cost_model_required_for_realistic_net_r',true
  ),
  true,false,false,false,false,'NONE'
)
on conflict(contract_id) do nothing;

create or replace view private.alpha_hunter_t0_threshold_dependence_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
with contract as (
  select *
  from private.alpha_hunter_t0_dependence_contracts_v01
  where contract_id='ME-T0-LONG-DEPENDENCE-GUARD-V01'
), eligible as (
  select
    h.spec_id,
    h.holdout_candidate_id,
    h.symbol,
    h.candidate_at_utc::date as utc_day,
    o.path_r_pre_cost
  from private.alpha_hunter_t0_threshold_holdout_candidates_v01 h
  join private.alpha_hunter_t0_threshold_holdout_outcomes_v01 o
    on o.holdout_candidate_id=h.holdout_candidate_id
  join contract c on c.holdout_spec_id=h.spec_id
  where h.numeric_threshold_pass is true
    and o.path_r_pre_cost is not null
), candidate_stats as (
  select
    count(*) as candidate_rows,
    count(distinct symbol) as distinct_symbols,
    count(distinct utc_day) as distinct_utc_days,
    avg(path_r_pre_cost) as candidate_mean_r,
    stddev_samp(path_r_pre_cost) as candidate_sd_r
  from eligible
), symbol_means as (
  select symbol,avg(path_r_pre_cost) as cluster_mean_r,count(*) as cluster_rows
  from eligible
  group by symbol
), symbol_stats as (
  select
    count(*) as symbol_clusters,
    avg(cluster_mean_r) as symbol_mean_r,
    stddev_samp(cluster_mean_r) as symbol_sd_r,
    max(cluster_rows) as max_rows_per_symbol
  from symbol_means
), day_means as (
  select utc_day,avg(path_r_pre_cost) as cluster_mean_r,count(*) as cluster_rows
  from eligible
  group by utc_day
), day_stats as (
  select
    count(*) as day_clusters,
    avg(cluster_mean_r) as day_mean_r,
    stddev_samp(cluster_mean_r) as day_sd_r,
    max(cluster_rows) as max_rows_per_day
  from day_means
), original as (
  select *
  from private.alpha_hunter_t0_threshold_holdout_scorecard_v01
  where spec_id='ME-T0-LONG-HOLDOUT-V01'
)
select
  c.contract_id,
  c.holdout_spec_id as spec_id,
  c.registered_at_utc,
  cs.candidate_rows,
  cs.distinct_symbols,
  cs.distinct_utc_days,
  cs.candidate_mean_r,
  case
    when cs.candidate_rows>=2 and cs.candidate_sd_r is not null
    then cs.candidate_mean_r-c.z_value*cs.candidate_sd_r/sqrt(cs.candidate_rows::double precision)
  end as candidate_mean_lower95,
  ss.symbol_clusters,
  ss.symbol_mean_r,
  ss.symbol_sd_r,
  case
    when ss.symbol_clusters>=2 and ss.symbol_sd_r is not null
    then ss.symbol_mean_r-c.z_value*ss.symbol_sd_r/sqrt(ss.symbol_clusters::double precision)
  end as symbol_mean_lower95,
  ss.max_rows_per_symbol,
  ds.day_clusters,
  ds.day_mean_r,
  ds.day_sd_r,
  case
    when ds.day_clusters>=2 and ds.day_sd_r is not null
    then ds.day_mean_r-c.z_value*ds.day_sd_r/sqrt(ds.day_clusters::double precision)
  end as day_mean_lower95,
  ds.max_rows_per_day,
  o.gross_holdout_pass as original_gross_holdout_pass,
  case
    when c.require_original_gross_holdout_pass and o.gross_holdout_pass is not true then false
    when cs.candidate_rows<c.minimum_candidate_rows then false
    when ss.symbol_clusters<c.minimum_symbol_clusters then false
    when ds.day_clusters<c.minimum_day_clusters then false
    when ss.symbol_mean_r is null or ss.symbol_mean_r<c.minimum_cluster_mean_r then false
    when ds.day_mean_r is null or ds.day_mean_r<c.minimum_cluster_mean_r then false
    when ss.symbol_clusters<2 or ss.symbol_sd_r is null then false
    when ds.day_clusters<2 or ds.day_sd_r is null then false
    when ss.symbol_mean_r-c.z_value*ss.symbol_sd_r/sqrt(ss.symbol_clusters::double precision)<=0 then false
    when ds.day_mean_r-c.z_value*ds.day_sd_r/sqrt(ds.day_clusters::double precision)<=0 then false
    else true
  end as dependence_safe_gross_holdout_pass,
  false as threshold_activation_permitted,
  false as production_promotion_permitted,
  false as realistic_net_r_claim_permitted,
  'PRE_COST_DEPENDENCE_ADJUSTED_FORWARD_HOLDOUT_ONLY'::text as claim_ceiling,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from contract c
cross join candidate_stats cs
cross join symbol_stats ss
cross join day_stats ds
left join original o on o.spec_id=c.holdout_spec_id;

revoke all on private.alpha_hunter_t0_dependence_contracts_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_t0_threshold_dependence_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_t0_dependence_contracts_v01
to service_role;
grant select on private.alpha_hunter_t0_threshold_dependence_scorecard_v01
to service_role;

-- This companion never changes the original holdout candidates or outcomes.
