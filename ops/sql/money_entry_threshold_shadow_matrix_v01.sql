-- Alpha Hunter Money Entry threshold shadow matrix v0.1
--
-- Mission:
--   Break the circular dependency between exact T0/T1/T2 labels and numeric
--   threshold validation.
--
-- Important:
--   Exact T0/T1/T2 production labels require an ACTIVE validated threshold set.
--   Therefore they MUST NOT be used to discover the thresholds themselves.
--
-- This layer reconstructs the pre-threshold evidence gate from immutable
-- Money Scorecard candidates + signal features, then attaches evaluated 24H
-- outcomes. Numeric thresholds remain unset and no stage/trade is authorized.
--
-- Pilot boundary:
--   The pilot data cutoff is frozen to the existing DRAFT evidence snapshot.
--   A future numeric threshold tuple must be derived from rows at/before that
--   cutoff, frozen, and only then tested on a later holdout.

create table if not exists private.alpha_hunter_money_entry_threshold_shadow_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  pilot_data_cutoff_utc timestamptz not null,
  horizon_hours integer not null check(horizon_hours=24),
  status text not null check(status in (
    'PILOT_ANALYSIS_ONLY',
    'NUMERIC_THRESHOLDS_FROZEN',
    'HOLDOUT_COLLECTING',
    'HOLDOUT_COMPLETE',
    'RETIRED'
  )),
  threshold_set_id text not null,
  numeric_thresholds_frozen boolean not null default false,
  holdout_start_utc timestamptz,
  holdout_end_utc timestamptz,
  primary_endpoint text not null,
  inclusion_contract jsonb not null,
  validation_contract jsonb not null,
  scientific_role text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(
    (numeric_thresholds_frozen=false and holdout_start_utc is null)
    or
    (numeric_thresholds_frozen=true and holdout_start_utc is not null)
  )
);

insert into private.alpha_hunter_money_entry_threshold_shadow_specs_v01(
  spec_id,registered_at_utc,pilot_data_cutoff_utc,horizon_hours,status,
  threshold_set_id,numeric_thresholds_frozen,holdout_start_utc,holdout_end_utc,
  primary_endpoint,inclusion_contract,validation_contract,scientific_role,
  shadow_only,trade_permission,production_promotion_permitted,order_path
) values (
  'ME-THRESH-SHADOW-PILOT-V01',
  clock_timestamp(),
  timestamptz '2026-09-29 15:59:34.163232+00',
  24,
  'PILOT_ANALYSIS_ONLY',
  'ME-THRESH-DRAFT-R3-20260929',
  false,
  null,
  null,
  'PATH_R_PRE_COST_WITH_STOP_TARGET_ORDERING',
  jsonb_build_object(
    'source','private.alpha_hunter_money_entry_calibration_cohort_v01',
    'horizon_hours',24,
    'evaluation_status','EVALUATED',
    'calibration_eligible_required',true,
    'candidate_at_or_before_pilot_cutoff',true,
    'geometry_source','SCANNER_EXECUTION_SETUP',
    'direction_bound_required',true,
    'research_geometry_promoted',false,
    'shadow_only',true,
    'trade_permission',false
  ),
  jsonb_build_object(
    'pilot_only',true,
    'numeric_thresholds_must_be_frozen_before_holdout',true,
    'holdout_rows_must_be_strictly_after_holdout_start',true,
    'primary_endpoint','PATH_R_PRE_COST_WITH_STOP_TARGET_ORDERING',
    'secondary_endpoints',jsonb_build_array(
      'STOP_SURVIVED',
      'TARGET_HIT',
      'CONFIRMATION_TAX_R',
      'REMAINING_R'
    ),
    'candidate_threshold_fields',jsonb_build_array(
      'MAX_T0_STOP_DISTANCE_PCT',
      'MIN_T0_REMAINING_R',
      'MIN_T1_REMAINING_R',
      'MIN_T2_REMAINING_R'
    ),
    'no_threshold_activation_from_pilot',true,
    'validated_execution_cost_model_required_for_realistic_net_r',true,
    'independent_replication_required_before_production_promotion',true
  ),
  'NON_CIRCULAR_THRESHOLD_DISCOVERY_MATRIX',
  true,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create or replace view private.alpha_hunter_money_entry_threshold_shadow_matrix_v01
with (security_invoker=true,security_barrier=true)
as
with src as (
  select
    cal.scorecard_id,
    cal.run_id,
    cal.candidate_at_utc,
    cal.symbol,
    cal.direction,
    cal.candidate_entry,
    cal.stop_price,
    cal.target_price,
    cal.risk_distance_pct,
    cal.initial_remaining_r,
    cal.horizon_hours,
    cal.evaluation_status,
    cal.mfe_pct,
    cal.mae_pct,
    cal.stop_hit,
    cal.stop_survived,
    cal.target_hit,
    cal.path_resolution,
    cal.path_r_pre_cost,
    cal.remaining_r,
    cal.confirmation_tax_r,
    cal.candidate_path_outcome,
    cal.calibration_eligible,
    cal.calibration_eligibility_status,
    c.lifecycle,
    c.research_status,
    c.bridge_status,
    c.direction_12h,
    c.direction_1d,
    c.liquidity_state,
    c.frozen_evidence,
    sf.source_payload
  from private.alpha_hunter_money_entry_calibration_cohort_v01 cal
  join public.alpha_hunter_big_mover_money_scorecard_candidates c
    using(scorecard_id)
  left join lateral (
    select s.source_payload
    from public.alpha_hunter_signal_features s
    where s.run_id=cal.run_id
      and s.symbol=cal.symbol
    order by abs(extract(epoch from(s.captured_at_utc-cal.candidate_at_utc))) asc
    limit 1
  ) sf on true
  where cal.horizon_hours=24
    and cal.evaluation_status='EVALUATED'
), normalized as (
  select
    s.*,
    upper(nullif(s.source_payload#>>'{execution_setup,direction}',''))
      as execution_setup_direction,
    private.alpha_hunter_text_bool(
      s.source_payload#>>'{execution_setup,checks,structure_valid}'
    ) as scanner_structure_valid,
    private.alpha_hunter_text_bool(
      s.source_payload#>>'{execution_setup,checks,direction_aligned}'
    ) as scanner_direction_aligned,
    private.alpha_hunter_text_bool(
      s.source_payload#>>'{execution_setup,checks,momentum_confirmed}'
    ) as scanner_momentum_confirmed,
    private.alpha_hunter_text_bool(
      s.source_payload#>>'{execution_setup,checks,participation_confirmed}'
    ) as scanner_participation_confirmed,
    private.alpha_hunter_text_bool(
      s.source_payload#>>'{execution_setup,checks,data_integrity_min_88}'
    ) as scanner_data_integrity_pass,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,liquidity_ok}',
      s.source_payload#>>'{execution_setup,checks,liquidity_pass}',
      s.source_payload->>'liquidity_pass'
    )) as liquidity_ok,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,participation_emerging}',
      s.source_payload->>'participation_emerging'
    )) as participation_emerging,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,acceptance_confirmed}',
      s.source_payload->>'acceptance_confirmed'
    )) as acceptance_confirmed,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,trigger_confirmed}',
      s.source_payload->>'trigger_confirmed'
    )) as trigger_confirmed,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,expansion_confirmed}',
      s.source_payload->>'expansion_confirmed'
    )) as expansion_confirmed,
    private.alpha_hunter_text_bool(coalesce(
      s.source_payload#>>'{execution_setup,checks,open_position_conflict}',
      s.source_payload->>'open_position_conflict'
    )) as open_position_conflict,
    case
      when s.direction='LONG' then s.direction_12h='BULLISH'
      when s.direction='SHORT' then s.direction_12h='BEARISH'
      else false
    end as parent_12h_aligned,
    case
      when s.direction='LONG' then s.direction_1d='BULLISH'
      when s.direction='SHORT' then s.direction_1d='BEARISH'
      else false
    end as parent_1d_aligned
  from src s
), gated as (
  select
    n.*,
    (
      n.calibration_eligible
      and n.lifecycle in ('PRE_MOVER','IGNITION','EXPANSION')
      and n.research_status='SHADOW_QUEUE'
      and n.parent_12h_aligned
      and n.parent_1d_aligned
      and n.execution_setup_direction=n.direction
      and n.scanner_direction_aligned is true
      and n.scanner_momentum_confirmed is true
      and n.scanner_data_integrity_pass is true
      and n.liquidity_ok is true
      and (
        n.scanner_participation_confirmed is true
        or n.participation_emerging is true
      )
      and n.scanner_structure_valid is true
      and coalesce(n.open_position_conflict,false)=false
      and n.risk_distance_pct is not null
      and n.risk_distance_pct>0
      and n.initial_remaining_r is not null
      and n.initial_remaining_r>0
    ) as t0_non_numeric_gate,
    (
      n.scanner_participation_confirmed is true
      and n.acceptance_confirmed is true
      and n.trigger_confirmed is true
    ) as t1_confirmation_gate,
    (
      n.scanner_participation_confirmed is true
      and n.acceptance_confirmed is true
      and n.trigger_confirmed is true
      and n.expansion_confirmed is true
    ) as t2_confirmation_gate
  from normalized n
)
select
  g.*,
  (g.candidate_at_utc <= s.pilot_data_cutoff_utc) as pilot_row,
  (
    s.numeric_thresholds_frozen
    and s.holdout_start_utc is not null
    and g.candidate_at_utc > s.holdout_start_utc
  ) as holdout_row,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  false as exact_t0_t1_t2_claim_permitted,
  'NONE'::text as order_path
from gated g
cross join private.alpha_hunter_money_entry_threshold_shadow_specs_v01 s
where s.spec_id='ME-THRESH-SHADOW-PILOT-V01';

revoke all on private.alpha_hunter_money_entry_threshold_shadow_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_money_entry_threshold_shadow_matrix_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_money_entry_threshold_shadow_specs_v01
to service_role;
grant select on private.alpha_hunter_money_entry_threshold_shadow_matrix_v01
to service_role;

-- Deliberately absent:
--   * no numeric threshold tuple
--   * no threshold-set update
--   * no VALIDATED/ACTIVE status change
--   * no exact T0/T1/T2 label
--   * no order/trade/risk authority
