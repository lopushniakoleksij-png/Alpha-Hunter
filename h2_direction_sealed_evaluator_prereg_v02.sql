-- Alpha Hunter H2 direction sealed evaluator preregistration v0.2
--
-- Supersedes v0.1 BEFORE any H2 outcome table exists or any H2 outcome access.
-- Reason: v0.1 used an exact 1m decision anchor but a 3m path source, which
-- could leave a 0-2 minute blind gap immediately after entry.
--
-- v0.2 fixes measurement integrity by using exact 1m path data in two
-- deterministic, non-overlapping 12h pages. No outcome is read here.

create table if not exists public.alpha_hunter_h2_direction_evaluator_specs_v02 (
  evaluator_spec_id text primary key,
  capture_spec_id text not null
    references public.alpha_hunter_h2_direction_specs_v01(spec_id),
  supersedes_evaluator_spec_id text not null,
  preregistered_at_utc timestamptz not null default clock_timestamp(),
  status text not null default 'PREREGISTERED_LOCKED'
    check(status='PREREGISTERED_LOCKED'),
  analysis_window_hours integer not null check(analysis_window_hours=24),
  legacy_confirmation_window_hours integer not null
    check(legacy_confirmation_window_hours=24),
  observation_independence_hours integer not null
    check(observation_independence_hours=24),
  path_interval_minutes integer not null check(path_interval_minutes=1),
  path_page_hours integer not null check(path_page_hours=12),
  path_page_count integer not null check(path_page_count=2),
  exact_anchor_alignment_required boolean not null default true
    check(exact_anchor_alignment_required=true),
  path_source text not null
    check(path_source='BITGET_PUBLIC_V3_1M_CANDLES'),
  path_pagination_rule text not null
    check(path_pagination_rule='TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE'),
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
    check(evaluator_contract_version='h2-direction-sealed-evaluator-prereg-v0.2')
);

create table if not exists public.alpha_hunter_h2_direction_evaluator_supersessions_v01 (
  supersession_id text primary key,
  previous_evaluator_spec_id text not null,
  replacement_evaluator_spec_id text not null,
  superseded_at_utc timestamptz not null default clock_timestamp(),
  reason text not null,
  previous_outcome_table_existed boolean not null default false
    check(previous_outcome_table_existed=false),
  previous_outcome_accessed boolean not null default false
    check(previous_outcome_accessed=false),
  tuning_to_observed_outcome_permitted boolean not null default false
    check(tuning_to_observed_outcome_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  unique(previous_evaluator_spec_id,replacement_evaluator_spec_id)
);

alter table public.alpha_hunter_h2_direction_evaluator_specs_v02 enable row level security;
alter table public.alpha_hunter_h2_direction_evaluator_supersessions_v01 enable row level security;

revoke all on public.alpha_hunter_h2_direction_evaluator_specs_v02
  from public,anon,authenticated;
revoke all on public.alpha_hunter_h2_direction_evaluator_supersessions_v01
  from public,anon,authenticated;
grant select on public.alpha_hunter_h2_direction_evaluator_specs_v02
  to service_role;
grant select on public.alpha_hunter_h2_direction_evaluator_supersessions_v01
  to service_role;

drop trigger if exists trg_ah_h2_evaluator_specs_v02_append_only
  on public.alpha_hunter_h2_direction_evaluator_specs_v02;
create trigger trg_ah_h2_evaluator_specs_v02_append_only
before update or delete on public.alpha_hunter_h2_direction_evaluator_specs_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_h2_evaluator_supersessions_append_only
  on public.alpha_hunter_h2_direction_evaluator_supersessions_v01;
create trigger trg_ah_h2_evaluator_supersessions_append_only
before update or delete on public.alpha_hunter_h2_direction_evaluator_supersessions_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_register_h2_evaluator_v02()
returns void
language plpgsql
security definer
set search_path=''
as $$
declare
  v_id constant text := 'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02';
  v_prev constant text := 'AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V01';
  v_capture constant text := 'AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01';
  v_support jsonb;
  v_falsification jsonb;
  v_contract jsonb;
  v_hash text;
  v_existing public.alpha_hunter_h2_direction_evaluator_specs_v02%rowtype;
begin
  if not exists(
    select 1 from public.alpha_hunter_h2_direction_evaluator_specs_v01
    where evaluator_spec_id=v_prev
  ) then
    raise exception 'prior evaluator prereg missing: %',v_prev;
  end if;

  if exists(
    select 1
    from information_schema.tables
    where table_schema='public'
      and table_name='alpha_hunter_h2_direction_outcomes_sealed_v01'
  ) then
    raise exception 'cannot supersede after H2 outcome table creation';
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
    'supersedes',v_prev,
    'supersession_reason',
      'v0.1 exact 1m decision anchor plus 3m path source could create a 0-2 minute post-entry blind gap; corrected before any outcome table or outcome access',
    'observation_unit',
      'first H2-triggered symbol-direction anchor after 24h cooldown',
    'legacy_policy',
      'first legacy_scanner_aligned observation for same symbol-direction at or after H2 anchor and strictly before H2 anchor + 24h; if absent => NO_TRADE_0R',
    'opportunity_window',
      'both H2 and legacy evaluated only until H2 exact decision anchor + 24h',
    'path_source',
      'public Bitget 1m candles aligned exactly to persisted 1m decision anchor',
    'pagination',
      'two nonoverlapping 12h pages; each page requires exactly 720 one-minute candles with no gaps',
    'h2_entry_anchor',
      'persisted exact public Bitget 1m open at/after H2 decision_available_at_utc',
    'legacy_entry_anchor',
      'persisted exact public Bitget 1m open at/after legacy decision_available_at_utc',
    'frozen_geometry',
      'use contemporaneously captured 15m structural stop and 4H target belonging to each policy entry',
    'barrier_rule',
      'target-first => frozen target R; stop-first => -1R; stop+target in same 1m candle => conservative -1R',
    'no_barrier_rule',
      'direction-adjusted H2-window terminal 1m close converted to R using frozen structural risk',
    'cost_rule',
      'same independently validated frozen cost model applied to both policies; if unavailable, confirmatory economic verdict is DATA_INSUFFICIENT',
    'inference',
      'mean paired policy net-R delta; 10,000 UTC-day block bootstrap replicates; symbol concentration sensitivity required',
    'missingness',
      'no imputation; any missing required minute makes that policy path DATA_INSUFFICIENT',
    'claim_ceiling',
      'SUPPORTED_SHADOW_ONLY requires independent replication and separate production review; no trading authority'
  );

  v_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'evaluator_spec_id',v_id,
        'capture_spec_id',v_capture,
        'supersedes_evaluator_spec_id',v_prev,
        'analysis_window_hours',24,
        'legacy_confirmation_window_hours',24,
        'observation_independence_hours',24,
        'path_interval_minutes',1,
        'path_page_hours',12,
        'path_page_count',2,
        'exact_anchor_alignment_required',true,
        'path_source','BITGET_PUBLIC_V3_1M_CANDLES',
        'path_pagination_rule','TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE',
        'primary_metric','POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA',
        'primary_effect_statistic','MEAN_H2_MINUS_LEGACY_POLICY_NET_R',
        'minimum_economic_effect_r',0.10,
        'alpha',0.05,
        'confidence_level',0.95,
        'bootstrap_replicates',10000,
        'false_start_noninferiority_margin_pp',10.0,
        'support_rule',v_support,
        'falsification_rule',v_falsification,
        'evaluator_contract',v_contract,
        'version','h2-direction-sealed-evaluator-prereg-v0.2'
      )::text,
      'sha256'
    ),
    'hex'
  );

  select * into v_existing
  from public.alpha_hunter_h2_direction_evaluator_specs_v02
  where evaluator_spec_id=v_id;

  if found then
    if v_existing.spec_hash is distinct from v_hash
       or v_existing.evaluator_contract is distinct from v_contract then
      raise exception 'H2 evaluator v0.2 prereg conflict for %',v_id;
    end if;
    return;
  end if;

  insert into public.alpha_hunter_h2_direction_evaluator_specs_v02(
    evaluator_spec_id,capture_spec_id,supersedes_evaluator_spec_id,
    analysis_window_hours,legacy_confirmation_window_hours,
    observation_independence_hours,path_interval_minutes,path_page_hours,
    path_page_count,exact_anchor_alignment_required,path_source,
    path_pagination_rule,primary_metric,primary_effect_statistic,
    minimum_economic_effect_r,alpha,confidence_level,bootstrap_replicates,
    inference_method,false_start_metric,false_start_noninferiority_margin_pp,
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
    v_id,v_capture,v_prev,
    24,24,24,1,12,2,true,'BITGET_PUBLIC_V3_1M_CANDLES',
    'TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE',
    'POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA',
    'MEAN_H2_MINUS_LEGACY_POLICY_NET_R',
    0.1000,0.0500,0.9500,10000,
    'UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY',
    'STOP_FIRST_OR_AMBIGUOUS_BEFORE_TARGET_WITHIN_24H',10.0000,
    'NO_TRADE_0R',true,'CONSERVATIVE_STOP_FIRST_MINUS_1R',
    'DIRECTION_ADJUSTED_HORIZON_CLOSE_R',
    true,'SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL',
    'DATA_INSUFFICIENT_NO_IMPUTATION',
    'LONG_AND_SHORT_MEAN_DELTA_MUST_BOTH_BE_NONNEGATIVE',
    'REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_SIGN_MUST_REMAIN_POSITIVE',
    'ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE',
    v_support,v_falsification,v_contract,
    true,false,false,false,true,false,false,false,true,false,'NONE',
    v_hash,'h2-direction-sealed-evaluator-prereg-v0.2'
  );

  insert into public.alpha_hunter_h2_direction_evaluator_supersessions_v01(
    supersession_id,previous_evaluator_spec_id,replacement_evaluator_spec_id,
    reason,previous_outcome_table_existed,previous_outcome_accessed,
    tuning_to_observed_outcome_permitted,shadow_only,trade_permission
  ) values (
    pg_catalog.md5('h2-evaluator-supersession-v0.1|'||v_prev||'|'||v_id),
    v_prev,v_id,
    'MEASUREMENT_INTEGRITY_EXACT_1M_ANCHOR_REQUIRES_EXACT_1M_PATH_ALIGNMENT_BEFORE_ANY_OUTCOME_ACCESS',
    false,false,false,true,false
  )
  on conflict(previous_evaluator_spec_id,replacement_evaluator_spec_id) do nothing;
end;
$$;

revoke all on function private.alpha_hunter_register_h2_evaluator_v02()
  from public,anon,authenticated,service_role;

create or replace view public.alpha_hunter_h2_direction_evaluator_active_status_v02
with (security_invoker=true,security_barrier=true)
as
select
  e.evaluator_spec_id,
  e.capture_spec_id,
  e.supersedes_evaluator_spec_id,
  e.preregistered_at_utc,
  e.status,
  e.analysis_window_hours,
  e.path_interval_minutes,
  e.path_page_hours,
  e.path_page_count,
  e.exact_anchor_alignment_required,
  e.path_source,
  e.path_pagination_rule,
  e.primary_metric,
  e.minimum_economic_effect_r,
  e.alpha,
  e.confidence_level,
  e.bootstrap_replicates,
  e.false_start_noninferiority_margin_pp,
  e.spec_hash,
  e.evaluator_contract_version,
  true as evaluator_preregistered,
  true as superseded_before_any_outcome_access,
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
  'BUILD_EXACT_1M_SEALED_OUTCOME_COLLECTOR'::text as next_gate
from public.alpha_hunter_h2_direction_evaluator_specs_v02 e
where e.evaluator_spec_id='AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02';

revoke all on public.alpha_hunter_h2_direction_evaluator_active_status_v02
  from public,anon,authenticated;
grant select on public.alpha_hunter_h2_direction_evaluator_active_status_v02
  to service_role;

select private.alpha_hunter_register_h2_evaluator_v02();
