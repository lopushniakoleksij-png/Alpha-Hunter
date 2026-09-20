-- Alpha Hunter H2 direction sealed evaluator preregistration v0.1
--
-- PREREGISTRATION ONLY.
-- This migration freezes the H2 evaluator before any H2 outcome access.
-- It does not create, query, expose, or analyze H2 outcomes.
--
-- Primary comparison:
--   H2 policy vs legacy-confirmation policy on the SAME original 24h opportunity.
--   The legacy policy gets no extra evaluation time for entering later.
--
-- Claim ceiling:
--   SUPPORTED_SHADOW_ONLY still requires independent replication and a separate
--   production review. No READY, T0, threshold, risk, leverage, trade permission,
--   production promotion, or live order path is granted here.

create table if not exists public.alpha_hunter_h2_direction_evaluator_specs_v01 (
  evaluator_spec_id text primary key,
  capture_spec_id text not null
    references public.alpha_hunter_h2_direction_specs_v01(spec_id),
  preregistered_at_utc timestamptz not null default clock_timestamp(),
  status text not null default 'PREREGISTERED_LOCKED'
    check(status='PREREGISTERED_LOCKED'),

  analysis_window_hours integer not null check(analysis_window_hours=24),
  legacy_confirmation_window_hours integer not null
    check(legacy_confirmation_window_hours=24),
  observation_independence_hours integer not null
    check(observation_independence_hours=24),

  primary_metric text not null
    check(primary_metric='POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA'),
  primary_effect_statistic text not null
    check(primary_effect_statistic='MEAN_H2_MINUS_LEGACY_POLICY_NET_R'),
  minimum_economic_effect_r numeric(10,4) not null
    check(minimum_economic_effect_r=0.1000),
  alpha numeric(10,4) not null check(alpha=0.0500),
  confidence_level numeric(10,4) not null check(confidence_level=0.9500),
  bootstrap_replicates integer not null check(bootstrap_replicates=10000),
  inference_method text not null
    check(inference_method='UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY'),

  false_start_metric text not null
    check(false_start_metric='STOP_FIRST_OR_AMBIGUOUS_BEFORE_TARGET_WITHIN_24H'),
  false_start_noninferiority_margin_pp numeric(10,4) not null
    check(false_start_noninferiority_margin_pp=10.0000),

  legacy_no_confirmation_policy text not null
    check(legacy_no_confirmation_policy='NO_TRADE_0R'),
  same_opportunity_window boolean not null default true
    check(same_opportunity_window=true),
  ambiguous_intrabar_policy text not null
    check(ambiguous_intrabar_policy='CONSERVATIVE_STOP_FIRST_MINUS_1R'),
  terminal_if_no_barrier_policy text not null
    check(terminal_if_no_barrier_policy='DIRECTION_ADJUSTED_HORIZON_CLOSE_R'),

  validated_cost_model_required boolean not null default true
    check(validated_cost_model_required=true),
  cost_model_selection_rule text not null
    check(cost_model_selection_rule='SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL'),
  missing_data_policy text not null
    check(missing_data_policy='DATA_INSUFFICIENT_NO_IMPUTATION'),
  direction_guardrail text not null
    check(direction_guardrail='LONG_AND_SHORT_MEAN_DELTA_MUST_BOTH_BE_NONNEGATIVE'),
  concentration_guardrail text not null
    check(concentration_guardrail='REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_SIGN_MUST_REMAIN_POSITIVE'),
  multiplicity_policy text not null
    check(multiplicity_policy='ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE'),

  support_rule jsonb not null check(jsonb_typeof(support_rule)='object'),
  falsification_rule jsonb not null check(jsonb_typeof(falsification_rule)='object'),
  evaluator_contract jsonb not null check(jsonb_typeof(evaluator_contract)='object'),

  sealed_outcome_collection_permitted boolean not null default true
    check(sealed_outcome_collection_permitted=true),
  outcome_access_permitted boolean not null default false
    check(outcome_access_permitted=false),
  primary_results_exposed boolean not null default false
    check(primary_results_exposed=false),
  confirmatory_analysis_permitted boolean not null default false
    check(confirmatory_analysis_permitted=false),
  independent_replication_required boolean not null default true
    check(independent_replication_required=true),

  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),

  spec_hash text not null unique check(spec_hash ~ '^[0-9a-f]{64}$'),
  evaluator_contract_version text not null
    check(evaluator_contract_version='h2-direction-sealed-evaluator-prereg-v0.1')
);

alter table public.alpha_hunter_h2_direction_evaluator_specs_v01 enable row level security;
revoke all on public.alpha_hunter_h2_direction_evaluator_specs_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_direction_evaluator_specs_v01
  to service_role;

drop trigger if exists trg_ah_h2_evaluator_specs_append_only
  on public.alpha_hunter_h2_direction_evaluator_specs_v01;
create trigger trg_ah_h2_evaluator_specs_append_only
before update or delete on public.alpha_hunter_h2_direction_evaluator_specs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_register_h2_evaluator_v01()
returns void
language plpgsql
security definer
set search_path=''
as $$
declare
  v_id constant text := 'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V01';
  v_capture_spec constant text := 'AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01';
  v_support jsonb;
  v_falsification jsonb;
  v_contract jsonb;
  v_hash text;
  v_existing public.alpha_hunter_h2_direction_evaluator_specs_v01%rowtype;
begin
  if not exists(
    select 1 from public.alpha_hunter_h2_direction_specs_v01
    where spec_id=v_capture_spec
  ) then
    raise exception 'capture spec missing: %',v_capture_spec;
  end if;

  v_support := jsonb_build_object(
    'decision_state','SUPPORTED_SHADOW_ONLY',
    'required_capture_maturity_gate',true,
    'required_validated_cost_model',true,
    'minimum_mean_net_r_delta',0.10,
    'primary_95pct_ci_lower_bound_must_exceed',0.0,
    'false_start_noninferiority_margin_pp',10.0,
    'long_mean_delta_must_be_nonnegative',true,
    'short_mean_delta_must_be_nonnegative',true,
    'top_positive_symbol_removed_sign_must_remain_positive',true,
    'replication_required_before_any_production_review',true
  );

  v_falsification := jsonb_build_object(
    'decision_state','FALSIFIED',
    'condition_any',jsonb_build_array(
      'PRIMARY_95PCT_CI_UPPER_BOUND_BELOW_OR_EQUAL_ZERO',
      'MEAN_NET_R_DELTA_BELOW_OR_EQUAL_MINUS_0_10R',
      'FALSE_START_NONINFERIORITY_MARGIN_FAILED'
    ),
    'inconclusive_otherwise',true
  );

  v_contract := jsonb_build_object(
    'observation_unit',
      'first H2-triggered symbol-direction anchor after 24h cooldown',
    'legacy_policy',
      'first legacy_scanner_aligned observation for same symbol-direction at or after H2 anchor and strictly before H2 anchor + 24h; if absent => NO_TRADE_0R',
    'opportunity_window',
      'both H2 and legacy policies evaluated only until H2 decision anchor + 24h; legacy receives no extra time for entering late',
    'h2_entry_anchor',
      'persisted exact public Bitget 1m open at/after H2 decision_available_at_utc',
    'legacy_entry_anchor',
      'persisted exact public Bitget 1m open at/after legacy decision_available_at_utc',
    'frozen_geometry',
      'use contemporaneously captured 15m structural stop and 4H target belonging to each policy entry',
    'path_source',
      'public Bitget 3m candles; no fill claim; no exact intrabar ordering claim',
    'barrier_rule',
      'target-first => frozen target R; stop-first => -1R; stop+target in same 3m candle => conservative -1R',
    'no_barrier_rule',
      'direction-adjusted H2-window terminal close converted to R using frozen structural risk',
    'cost_rule',
      'same independently validated frozen cost model applied to both policies; if unavailable, confirmatory economic verdict is DATA_INSUFFICIENT',
    'funding_rule',
      'include only if validated cost model defines a deterministic hold-time funding treatment from independently validated evidence',
    'inference',
      'mean paired policy net-R delta; primary uncertainty by 10,000 UTC-day block bootstrap replicates; symbol-concentration sensitivity required',
    'multiplicity',
      'one primary economic metric at alpha 0.05; geometry, confirmation delay, RR tax, false-start components and trigger tags are secondary/descriptive except the preregistered false-start guardrail',
    'missingness',
      'no imputation; unresolved anchor/path/cost rows are DATA_INSUFFICIENT and reported',
    'shared_period_dependence',
      'H2 shares market periods with H1; no cross-hypothesis multiplicity claim or pooling is permitted',
    'claim_ceiling',
      'SUPPORTED_SHADOW_ONLY still requires independent replication and separate production review; never grants READY, threshold change, T0, risk expansion, trade permission, leverage or live execution'
  );

  v_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'evaluator_spec_id',v_id,
        'capture_spec_id',v_capture_spec,
        'analysis_window_hours',24,
        'legacy_confirmation_window_hours',24,
        'observation_independence_hours',24,
        'primary_metric','POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA',
        'primary_effect_statistic','MEAN_H2_MINUS_LEGACY_POLICY_NET_R',
        'minimum_economic_effect_r',0.10,
        'alpha',0.05,
        'confidence_level',0.95,
        'bootstrap_replicates',10000,
        'inference_method','UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY',
        'false_start_metric','STOP_FIRST_OR_AMBIGUOUS_BEFORE_TARGET_WITHIN_24H',
        'false_start_noninferiority_margin_pp',10.0,
        'legacy_no_confirmation_policy','NO_TRADE_0R',
        'same_opportunity_window',true,
        'ambiguous_intrabar_policy','CONSERVATIVE_STOP_FIRST_MINUS_1R',
        'terminal_if_no_barrier_policy','DIRECTION_ADJUSTED_HORIZON_CLOSE_R',
        'validated_cost_model_required',true,
        'cost_model_selection_rule','SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL',
        'missing_data_policy','DATA_INSUFFICIENT_NO_IMPUTATION',
        'direction_guardrail','LONG_AND_SHORT_MEAN_DELTA_MUST_BOTH_BE_NONNEGATIVE',
        'concentration_guardrail','REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_SIGN_MUST_REMAIN_POSITIVE',
        'multiplicity_policy','ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE',
        'support_rule',v_support,
        'falsification_rule',v_falsification,
        'evaluator_contract',v_contract,
        'version','h2-direction-sealed-evaluator-prereg-v0.1'
      )::text,
      'sha256'
    ),
    'hex'
  );

  select * into v_existing
  from public.alpha_hunter_h2_direction_evaluator_specs_v01
  where evaluator_spec_id=v_id;

  if found then
    if v_existing.spec_hash is distinct from v_hash
       or v_existing.support_rule is distinct from v_support
       or v_existing.falsification_rule is distinct from v_falsification
       or v_existing.evaluator_contract is distinct from v_contract then
      raise exception 'H2 evaluator prereg conflict for %',v_id;
    end if;
    return;
  end if;

  insert into public.alpha_hunter_h2_direction_evaluator_specs_v01(
    evaluator_spec_id,capture_spec_id,
    analysis_window_hours,legacy_confirmation_window_hours,
    observation_independence_hours,
    primary_metric,primary_effect_statistic,minimum_economic_effect_r,
    alpha,confidence_level,bootstrap_replicates,inference_method,
    false_start_metric,false_start_noninferiority_margin_pp,
    legacy_no_confirmation_policy,same_opportunity_window,
    ambiguous_intrabar_policy,terminal_if_no_barrier_policy,
    validated_cost_model_required,cost_model_selection_rule,
    missing_data_policy,direction_guardrail,concentration_guardrail,
    multiplicity_policy,support_rule,falsification_rule,evaluator_contract,
    sealed_outcome_collection_permitted,outcome_access_permitted,
    primary_results_exposed,confirmatory_analysis_permitted,
    independent_replication_required,t0_authorized,
    threshold_change_permitted,production_promotion_permitted,
    shadow_only,trade_permission,order_path,spec_hash,evaluator_contract_version
  ) values (
    v_id,v_capture_spec,
    24,24,24,
    'POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA',
    'MEAN_H2_MINUS_LEGACY_POLICY_NET_R',
    0.1000,0.0500,0.9500,10000,
    'UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY',
    'STOP_FIRST_OR_AMBIGUOUS_BEFORE_TARGET_WITHIN_24H',
    10.0000,
    'NO_TRADE_0R',true,
    'CONSERVATIVE_STOP_FIRST_MINUS_1R',
    'DIRECTION_ADJUSTED_HORIZON_CLOSE_R',
    true,'SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL',
    'DATA_INSUFFICIENT_NO_IMPUTATION',
    'LONG_AND_SHORT_MEAN_DELTA_MUST_BOTH_BE_NONNEGATIVE',
    'REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_SIGN_MUST_REMAIN_POSITIVE',
    'ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE',
    v_support,v_falsification,v_contract,
    true,false,false,false,true,
    false,false,false,true,false,'NONE',
    v_hash,'h2-direction-sealed-evaluator-prereg-v0.1'
  );
end;
$$;

revoke all on function private.alpha_hunter_register_h2_evaluator_v01()
  from public,anon,authenticated,service_role;

create or replace view public.alpha_hunter_h2_direction_evaluator_prereg_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  e.evaluator_spec_id,
  e.capture_spec_id,
  e.preregistered_at_utc,
  e.status,
  e.analysis_window_hours,
  e.legacy_confirmation_window_hours,
  e.observation_independence_hours,
  e.primary_metric,
  e.primary_effect_statistic,
  e.minimum_economic_effect_r,
  e.alpha,
  e.confidence_level,
  e.bootstrap_replicates,
  e.inference_method,
  e.false_start_metric,
  e.false_start_noninferiority_margin_pp,
  e.legacy_no_confirmation_policy,
  e.same_opportunity_window,
  e.ambiguous_intrabar_policy,
  e.terminal_if_no_barrier_policy,
  e.validated_cost_model_required,
  e.cost_model_selection_rule,
  e.missing_data_policy,
  e.direction_guardrail,
  e.concentration_guardrail,
  e.multiplicity_policy,
  e.spec_hash,
  e.evaluator_contract_version,
  true as evaluator_preregistered,
  false as outcome_access_permitted,
  false as primary_results_exposed,
  false as confirmatory_analysis_permitted,
  true as independent_replication_required,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  'BUILD_SEALED_OUTCOME_COLLECTOR_WITHOUT_EXPOSING_RESULTS'::text as next_gate
from public.alpha_hunter_h2_direction_evaluator_specs_v01 e
where e.evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V01';

revoke all on public.alpha_hunter_h2_direction_evaluator_prereg_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_direction_evaluator_prereg_status_v01
  to service_role;

select private.alpha_hunter_register_h2_evaluator_v01();
