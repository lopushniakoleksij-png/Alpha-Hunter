-- Alpha Hunter H2 closed-candle absolute economic evaluator prereg v0.3
--
-- Issue #315.
--
-- This evaluator is preregistered BEFORE any corrected H2 v0.2 outcome table
-- or outcome access exists. It is bound cryptographically to the exact H2 v0.2
-- capture spec and asks only whether corrected H2 itself has positive economic
-- expectancy after a separately validated execution-cost model.
--
-- It intentionally does NOT claim H2 superiority over the legacy scanner.
-- Candidate-time audit found materially earlier legacy alignment for a
-- nontrivial subset of projected H2 opportunities; any relative comparator
-- therefore requires a separate preregistration with an unbiased timing rule.
--
-- Scientific boundary:
--   * preregistration only;
--   * no outcome table;
--   * no outcome collector/evaluator implementation;
--   * no result access;
--   * no cost-model activation;
--   * no R3/threshold/trading/production authority.

create table if not exists public.alpha_hunter_h2_closed_evaluator_specs_v03 (
  evaluator_spec_id text primary key
    check(evaluator_spec_id='AH-H2-CLOSED-ABSOLUTE-SEALED-EVALUATOR-PREREG-V03'),
  capture_spec_id text not null
    check(capture_spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'),
  capture_spec_hash text not null check(capture_spec_hash ~ '^[0-9a-f]{64}$'),
  preregistered_at_utc timestamptz not null default clock_timestamp(),
  status text not null check(status='PREREGISTERED_LOCKED'),

  analysis_window_hours integer not null check(analysis_window_hours=24),
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
    check(primary_metric='H2_POLICY_REALISTIC_COST_ADJUSTED_NET_R'),
  primary_effect_statistic text not null
    check(primary_effect_statistic='MEAN_H2_POLICY_NET_R'),
  minimum_economic_effect_r numeric(10,4) not null
    check(minimum_economic_effect_r=0.1000),
  alpha numeric(10,4) not null check(alpha=0.0500),
  confidence_level numeric(10,4) not null check(confidence_level=0.9500),
  bootstrap_replicates integer not null check(bootstrap_replicates=10000),
  inference_method text not null
    check(inference_method='UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY'),

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
    check(direction_guardrail='LONG_AND_SHORT_MEAN_NET_R_MUST_BOTH_BE_NONNEGATIVE'),
  concentration_guardrail text not null
    check(concentration_guardrail='REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_MEAN_MUST_REMAIN_POSITIVE'),
  multiplicity_policy text not null
    check(multiplicity_policy='ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE'),

  support_rule jsonb not null check(jsonb_typeof(support_rule)='object'),
  falsification_rule jsonb not null check(jsonb_typeof(falsification_rule)='object'),
  evaluator_contract jsonb not null check(jsonb_typeof(evaluator_contract)='object'),

  sealed_path_collection_permitted boolean not null default true
    check(sealed_path_collection_permitted=true),
  outcome_access_permitted boolean not null default false
    check(outcome_access_permitted=false),
  primary_results_exposed boolean not null default false
    check(primary_results_exposed=false),
  confirmatory_analysis_permitted boolean not null default false
    check(confirmatory_analysis_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  legacy_superiority_claim_permitted boolean not null default false
    check(legacy_superiority_claim_permitted=false),
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
    check(evaluator_contract_version='h2-closed-absolute-evaluator-prereg-v0.3')
);

alter table public.alpha_hunter_h2_closed_evaluator_specs_v03 enable row level security;

revoke all on public.alpha_hunter_h2_closed_evaluator_specs_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_closed_evaluator_specs_v03
  to service_role;

drop trigger if exists trg_ah_h2_closed_evaluator_specs_append_only_v03
  on public.alpha_hunter_h2_closed_evaluator_specs_v03;
create trigger trg_ah_h2_closed_evaluator_specs_append_only_v03
before update or delete on public.alpha_hunter_h2_closed_evaluator_specs_v03
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_register_h2_closed_evaluator_v03()
returns void
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_id constant text := 'AH-H2-CLOSED-ABSOLUTE-SEALED-EVALUATOR-PREREG-V03';
  v_capture_id constant text := 'AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02';
  v_capture public.alpha_hunter_h2_direction_specs_v02%rowtype;
  v_support jsonb;
  v_falsification jsonb;
  v_contract jsonb;
  v_hash text;
  v_existing public.alpha_hunter_h2_closed_evaluator_specs_v03%rowtype;
begin
  select *
  into v_capture
  from public.alpha_hunter_h2_direction_specs_v02
  where spec_id=v_capture_id;

  if v_capture.spec_id is null then
    raise exception 'corrected H2 v0.2 capture preregistration missing';
  end if;

  if v_capture.capture_contract_version
       <>'h2-direction-architecture-closed-capture-v0.2'
     or v_capture.candidate_cooldown_hours<>24
     or v_capture.maximum_source_age_minutes<>15
     or v_capture.minimum_anchor_observations<>100
     or v_capture.minimum_symbols<>30
     or v_capture.minimum_utc_days<>20
     or v_capture.minimum_anchors_per_direction<>25
     or v_capture.maximum_collection_days<>60
     or v_capture.outcome_access_permitted<>false
     or v_capture.confirmatory_analysis_permitted<>false
     or v_capture.independent_replication_required<>true
     or v_capture.t0_authorized<>false
     or v_capture.threshold_change_permitted<>false
     or v_capture.production_promotion_permitted<>false
     or v_capture.shadow_only<>true
     or v_capture.trade_permission<>false
     or v_capture.order_path<>'NONE'
  then
    raise exception 'corrected H2 v0.2 capture contract mismatch';
  end if;

  v_support := jsonb_build_object(
    'decision_state','SUPPORTED_SHADOW_ONLY',
    'required_capture_maturity_gate',true,
    'required_validated_cost_model',true,
    'minimum_mean_realistic_net_r',0.10,
    'primary_95pct_ci_lower_bound_must_exceed',0.0,
    'long_mean_realistic_net_r_must_be_nonnegative',true,
    'short_mean_realistic_net_r_must_be_nonnegative',true,
    'top_positive_symbol_removed_mean_must_remain_positive',true,
    'independent_replication_required_before_production_review',true,
    'legacy_superiority_claim_permitted',false
  );

  v_falsification := jsonb_build_object(
    'decision_state','FALSIFIED',
    'condition_any',jsonb_build_array(
      'PRIMARY_95PCT_CI_UPPER_BOUND_BELOW_OR_EQUAL_ZERO',
      'MEAN_REALISTIC_NET_R_BELOW_OR_EQUAL_MINUS_0_10R'
    ),
    'inconclusive_otherwise',true
  );

  v_contract := jsonb_build_object(
    'observation_unit',
      'first corrected H2-triggered symbol-direction anchor after 24h cooldown',
    'capture_spec_id',v_capture_id,
    'capture_spec_hash',v_capture.spec_hash,
    'capture_contract_version',v_capture.capture_contract_version,
    'analysis_window',
      'exact 24h from persisted H2 decision anchor',
    'path_source',
      'public Bitget 1m candles aligned exactly to persisted H2 decision anchor',
    'pagination',
      'two nonoverlapping 12h pages; each page requires complete exact one-minute coverage',
    'entry_anchor',
      'persisted exact public Bitget 1m open at/after H2 decision_available_at_utc; not a fill claim',
    'frozen_geometry',
      'contemporaneously captured 15m structural stop and 4H target from corrected H2 v0.2',
    'barrier_rule',
      'target-first => frozen target R; stop-first => -1R; stop+target same 1m candle => conservative -1R',
    'no_barrier_rule',
      'direction-adjusted 24h terminal 1m close converted to R using frozen structural risk',
    'cost_rule',
      'one independently validated execution-cost model must be frozen before any economic unseal; otherwise DATA_INSUFFICIENT',
    'cost_model_currently_validated',false,
    'inference',
      'mean H2 realistic net R; 10000 UTC-day block bootstrap replicates; symbol concentration sensitivity required',
    'missingness',
      'no imputation; missing required minute or required cost input => DATA_INSUFFICIENT',
    'direction_guardrail',
      'LONG and SHORT mean realistic net R must both be nonnegative',
    'legacy_comparison',
      'NOT PART OF THIS PRIMARY EVALUATOR; any H2-vs-legacy superiority claim requires separate preregistration before outcome access',
    'claim_ceiling',
      'SUPPORTED_SHADOW_ONLY requires independent replication and separate production review; no trading authority'
  );

  v_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'evaluator_spec_id',v_id,
        'capture_spec_id',v_capture_id,
        'capture_spec_hash',v_capture.spec_hash,
        'analysis_window_hours',24,
        'observation_independence_hours',24,
        'path_interval_minutes',1,
        'path_page_hours',12,
        'path_page_count',2,
        'exact_anchor_alignment_required',true,
        'path_source','BITGET_PUBLIC_V3_1M_CANDLES',
        'path_pagination_rule','TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE',
        'primary_metric','H2_POLICY_REALISTIC_COST_ADJUSTED_NET_R',
        'primary_effect_statistic','MEAN_H2_POLICY_NET_R',
        'minimum_economic_effect_r',0.10,
        'alpha',0.05,
        'confidence_level',0.95,
        'bootstrap_replicates',10000,
        'inference_method','UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY',
        'support_rule',v_support,
        'falsification_rule',v_falsification,
        'evaluator_contract',v_contract,
        'version','h2-closed-absolute-evaluator-prereg-v0.3'
      )::text,
      'sha256'
    ),
    'hex'
  );

  select *
  into v_existing
  from public.alpha_hunter_h2_closed_evaluator_specs_v03
  where evaluator_spec_id=v_id;

  if found then
    if v_existing.capture_spec_hash is distinct from v_capture.spec_hash
       or v_existing.spec_hash is distinct from v_hash
       or v_existing.evaluator_contract is distinct from v_contract
    then
      raise exception 'H2 closed evaluator v0.3 prereg conflict for %',v_id;
    end if;
    return;
  end if;

  insert into public.alpha_hunter_h2_closed_evaluator_specs_v03(
    evaluator_spec_id,capture_spec_id,capture_spec_hash,status,
    analysis_window_hours,observation_independence_hours,
    path_interval_minutes,path_page_hours,path_page_count,
    exact_anchor_alignment_required,path_source,path_pagination_rule,
    primary_metric,primary_effect_statistic,minimum_economic_effect_r,
    alpha,confidence_level,bootstrap_replicates,inference_method,
    ambiguous_intrabar_policy,terminal_if_no_barrier_policy,
    validated_cost_model_required,cost_model_selection_rule,
    missing_data_policy,direction_guardrail,concentration_guardrail,
    multiplicity_policy,support_rule,falsification_rule,evaluator_contract,
    sealed_path_collection_permitted,outcome_access_permitted,
    primary_results_exposed,confirmatory_analysis_permitted,
    realistic_net_r_claim_permitted,legacy_superiority_claim_permitted,
    independent_replication_required,t0_authorized,
    threshold_change_permitted,production_promotion_permitted,
    shadow_only,trade_permission,order_path,spec_hash,evaluator_contract_version
  ) values (
    v_id,v_capture_id,v_capture.spec_hash,'PREREGISTERED_LOCKED',
    24,24,1,12,2,true,'BITGET_PUBLIC_V3_1M_CANDLES',
    'TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE',
    'H2_POLICY_REALISTIC_COST_ADJUSTED_NET_R','MEAN_H2_POLICY_NET_R',0.1000,
    0.0500,0.9500,10000,'UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY',
    'CONSERVATIVE_STOP_FIRST_MINUS_1R','DIRECTION_ADJUSTED_HORIZON_CLOSE_R',
    true,'SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL',
    'DATA_INSUFFICIENT_NO_IMPUTATION',
    'LONG_AND_SHORT_MEAN_NET_R_MUST_BOTH_BE_NONNEGATIVE',
    'REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_MEAN_MUST_REMAIN_POSITIVE',
    'ONE_PRIMARY_ECONOMIC_METRIC_ALPHA_0_05_SECONDARIES_DESCRIPTIVE',
    v_support,v_falsification,v_contract,
    true,false,false,false,false,false,true,false,false,false,true,false,'NONE',
    v_hash,'h2-closed-absolute-evaluator-prereg-v0.3'
  );
end;
$function$;

revoke all on function private.alpha_hunter_register_h2_closed_evaluator_v03()
  from public,anon,authenticated,service_role;


create or replace view public.alpha_hunter_h2_closed_evaluator_prereg_status_v03
with (security_invoker=true,security_barrier=true)
as
select
  e.evaluator_spec_id,
  e.capture_spec_id,
  e.capture_spec_hash,
  e.preregistered_at_utc,
  e.status,
  e.analysis_window_hours,
  e.observation_independence_hours,
  e.path_interval_minutes,
  e.primary_metric,
  e.primary_effect_statistic,
  e.minimum_economic_effect_r,
  e.alpha,
  e.confidence_level,
  e.bootstrap_replicates,
  e.inference_method,
  e.validated_cost_model_required,
  e.legacy_superiority_claim_permitted,
  true as evaluator_preregistered,
  false as outcome_table_created,
  false as outcome_access_permitted,
  false as primary_results_exposed,
  false as confirmatory_analysis_permitted,
  false as realistic_net_r_claim_permitted,
  true as independent_replication_required,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  'COLLECT_CORRECTED_H2_V02; KEEP PATHS SEALED; VALIDATE EXECUTION COSTS; UNSEAL ONLY AFTER BOTH GATES'::text
    as next_gate
from public.alpha_hunter_h2_closed_evaluator_specs_v03 e
where e.evaluator_spec_id='AH-H2-CLOSED-ABSOLUTE-SEALED-EVALUATOR-PREREG-V03';

revoke all on public.alpha_hunter_h2_closed_evaluator_prereg_status_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_closed_evaluator_prereg_status_v03
  to service_role;


select private.alpha_hunter_register_h2_closed_evaluator_v03();

-- No corrected H2 outcome table, outcome collector, result reader, cost-model
-- activation, threshold mutation, production promotion, trade permission, or
-- order route is created by this preregistration.
