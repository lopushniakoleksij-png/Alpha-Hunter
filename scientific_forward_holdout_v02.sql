-- Alpha Hunter scientific forward holdout v0.2
--
-- Purpose:
--   Supersede the v0.1 MATCHING DESIGN prospectively after a pre-outcome
--   common-support audit showed zero matchable strata under its frozen rule.
--   v0.1 evidence remains immutable and untouched.
--
-- Scientific amendment boundary:
--   - NO primary or secondary outcomes were read to design this amendment.
--   - TEST/CONTROL assignment stays unchanged.
--   - Primary 12H endpoint stays unchanged.
--   - Sample / direction / symbol / day gates stay unchanged.
--   - Only the future 1:1 matching design changes.
--
-- v0.2 matching:
--   exact: direction, lifecycle, liquidity_state, candidate_quality_status
--   caliper: |decision time difference| <= 24 hours
--   nearest-neighbour distance:
--     abs(abs_move_test-abs_move_control)/5
--     + abs(similarity_test-similarity_control)/100
--     + abs(feature_coverage_test-feature_coverage_control)
--     + abs(time_gap_hours)/24
--   greedy 1:1 without replacement in TEST decision-time order.
--
-- bridge_status is deliberately NOT a matching covariate because the bridge
-- status itself encodes scanner-direction conflict and execution-geometry
-- availability, components entangled with the tested operational bundle.
-- source_run_id is deliberately NOT exact-matched because the pre-outcome
-- common-support audit demonstrated severe sparse-stratum starvation.

create or replace function private.alpha_hunter_capture_scientific_holdout_v02()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_spec public.alpha_hunter_scientific_holdout_specs%rowtype;
  v_decision_available_at timestamptz := clock_timestamp();
  v_schema_fingerprint text;
  v_query_fingerprint text;
  v_group_name text := 'EXCLUDED';
  v_reason text := 'UNCLASSIFIED';
  v_data_quality_ok boolean := false;
  v_direction_bound boolean;
  v_geometry_bound boolean;
  v_promoted_false boolean;
  v_source_hash text;
begin
  select * into v_spec
  from public.alpha_hunter_scientific_holdout_specs
  where spec_id = 'AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02'
    and status = 'COLLECTING';

  if not found then
    return new;
  end if;

  v_schema_fingerprint := private.alpha_hunter_scientific_source_schema_fingerprint_v01();
  v_query_fingerprint := pg_catalog.encode(
    extensions.digest(
      pg_catalog.pg_get_functiondef(
        pg_catalog.to_regprocedure(
          'private.alpha_hunter_capture_scientific_holdout_v02()'
        )
      ),
      'sha256'
    ),
    'hex'
  );
  v_direction_bound := new.scanner_direction is not null
    and upper(new.scanner_direction) = upper(new.direction);
  v_geometry_bound := new.geometry_valid is true
    and new.frozen_evidence->>'geometry_source' = 'SCANNER_EXECUTION_SETUP'
    and new.frozen_evidence @> '{"geometry_direction_bound":true}'::jsonb;
  v_promoted_false := new.frozen_evidence @> '{"research_geometry_promoted":false}'::jsonb;

  if new.shadow_only is not true or new.trade_permission is not false then
    v_reason := 'SAFETY_BOUNDARY_VIOLATION';
  elsif v_schema_fingerprint is distinct from v_spec.source_schema_fingerprint then
    v_reason := 'SOURCE_SCHEMA_DRIFT';
  elsif v_query_fingerprint is distinct from v_spec.source_query_fingerprint then
    v_reason := 'ASSIGNMENT_FUNCTION_DRIFT';
  elsif new.model_version is distinct from 'big-mover-money-scorecard-v0.2-stage-linked'
     or new.frozen_evidence->>'source_bridge_model_version'
          is distinct from 'big-mover-money-entry-bridge-v0.1' then
    v_reason := 'SOURCE_VERSION_DRIFT';
  elsif new.created_at <= v_spec.registered_at_utc
     or new.candidate_at_utc <= v_spec.registered_at_utc then
    v_reason := 'NOT_STRICTLY_POST_REGISTRATION';
  elsif v_decision_available_at > v_spec.collection_ends_at_utc
     or new.created_at > v_spec.collection_ends_at_utc
     or new.candidate_at_utc > v_spec.collection_ends_at_utc then
    v_reason := 'AFTER_COLLECTION_WINDOW';
  elsif new.raw_change_24h_pct is null
     or abs(new.raw_change_24h_pct) < 0.0
     or abs(new.raw_change_24h_pct) > 5.0 then
    v_reason := 'OUTSIDE_0_5_WINDOW';
  elsif upper(new.lifecycle) not in ('PRE_MOVER','IGNITION') then
    v_reason := 'LIFECYCLE_NOT_ELIGIBLE';
  elsif upper(coalesce(new.opportunity_timing,'')) <> 'EARLY' then
    v_reason := 'NOT_EARLY_TIMING';
  elsif upper(new.research_status) <> 'SHADOW_QUEUE' then
    v_reason := 'NOT_SHADOW_QUEUE';
  elsif not v_promoted_false then
    v_reason := 'PROMOTION_STATE_NOT_EXPLICITLY_FALSE';
  elsif new.liquidity_state is null
     or new.candidate_quality_status is null then
    v_reason := 'MATCH_STRATUM_MISSING';
  elsif new.similarity_score is null
     or new.similarity_score not between 0.0 and 100.0
     or new.feature_coverage is null
     or new.feature_coverage not between 0.0 and 1.0 then
    v_reason := 'MATCH_COVARIATE_MISSING';
  else
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        v_spec.spec_id || '|' || new.symbol || '|' || new.direction,
        0
      )
    );
    if exists (
      select 1
      from public.alpha_hunter_scientific_holdout_bindings b
      where b.spec_id = v_spec.spec_id
        and b.symbol = new.symbol
        and b.direction = new.direction
        and b.group_name in ('TEST','CONTROL_POOL')
        and b.decision_available_at_utc
              > v_decision_available_at - interval '24 hours'
    ) then
      v_reason := 'SYMBOL_DIRECTION_24H_COOLDOWN';
    elsif v_direction_bound and v_geometry_bound then
      v_group_name := 'TEST';
      v_reason := 'DIRECTION_AND_GEOMETRY_BOUND';
      v_data_quality_ok := true;
    else
      v_group_name := 'CONTROL_POOL';
      v_reason := case
        when not v_direction_bound and not v_geometry_bound
          then 'CONTROL_DIRECTION_AND_GEOMETRY_GAP'
        when not v_direction_bound then 'CONTROL_DIRECTION_GAP'
        else 'CONTROL_GEOMETRY_GAP'
      end;
      v_data_quality_ok := true;
    end if;
  end if;

  v_source_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'scorecard_id',new.scorecard_id,
        'source_bridge_id',new.source_bridge_id,
        'run_id',new.run_id,
        'candidate_at_utc',new.candidate_at_utc,
        'created_at',new.created_at,
        'symbol',new.symbol,
        'direction',new.direction,
        'raw_change_24h_pct',new.raw_change_24h_pct,
        'scanner_direction',new.scanner_direction,
        'geometry_valid',new.geometry_valid,
        'lifecycle',new.lifecycle,
        'research_status',new.research_status,
        'bridge_status',new.bridge_status,
        'opportunity_timing',new.opportunity_timing,
        'similarity_score',new.similarity_score,
        'feature_coverage',new.feature_coverage,
        'liquidity_state',new.liquidity_state,
        'candidate_quality_status',new.candidate_quality_status,
        'model_version',new.model_version,
        'source_bridge_model_version',new.frozen_evidence->>'source_bridge_model_version',
        'geometry_source',new.frozen_evidence->>'geometry_source',
        'geometry_direction_bound',new.frozen_evidence->'geometry_direction_bound',
        'research_geometry_promoted',new.frozen_evidence->'research_geometry_promoted',
        'shadow_only',new.shadow_only,
        'trade_permission',new.trade_permission
      )::text,
      'sha256'
    ),
    'hex'
  );

  insert into public.alpha_hunter_scientific_holdout_bindings(
    binding_id,spec_id,scorecard_id,source_bridge_id,source_run_id,
    registered_at_utc,candidate_at_utc,source_created_at_utc,
    decision_available_at_utc,symbol,direction,scanner_direction,
    group_name,eligibility_reason,raw_change_24h_pct,lifecycle,
    research_status,bridge_status,opportunity_timing,geometry_valid,
    similarity_score,feature_coverage,liquidity_state,candidate_quality_status,
    source_model_version,source_bridge_model_version,geometry_source,
    geometry_direction_bound,research_geometry_promoted,
    source_schema_fingerprint,source_query_fingerprint,source_evidence_hash,
    capture_contract_version,holdout,data_quality_ok,shadow_only,
    trade_permission,production_promotion_permitted,order_path
  ) values (
    pg_catalog.md5(v_spec.spec_id || '|' || new.scorecard_id),
    v_spec.spec_id,new.scorecard_id,new.source_bridge_id,new.run_id,
    v_spec.registered_at_utc,new.candidate_at_utc,new.created_at,
    v_decision_available_at,new.symbol,new.direction,new.scanner_direction,
    v_group_name,v_reason,new.raw_change_24h_pct,new.lifecycle,
    new.research_status,new.bridge_status,new.opportunity_timing,new.geometry_valid,
    new.similarity_score,new.feature_coverage,new.liquidity_state,
    new.candidate_quality_status,new.model_version,
    new.frozen_evidence->>'source_bridge_model_version',
    new.frozen_evidence->>'geometry_source',
    case when jsonb_typeof(new.frozen_evidence->'geometry_direction_bound')='boolean'
      then (new.frozen_evidence->>'geometry_direction_bound')::boolean end,
    case when jsonb_typeof(new.frozen_evidence->'research_geometry_promoted')='boolean'
      then (new.frozen_evidence->>'research_geometry_promoted')::boolean end,
    v_schema_fingerprint,v_query_fingerprint,v_source_hash,
    'scientific-forward-holdout-v0.1',true,v_data_quality_ok,true,false,false,'NONE'
  );

  return new;
exception when others then
  begin
    insert into public.alpha_hunter_scientific_holdout_capture_failures(
      failure_id,spec_id,scorecard_id,sqlstate,error_message,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      pg_catalog.md5(
        coalesce(v_spec.spec_id,'NO_SPEC') || '|' || coalesce(new.scorecard_id,'NO_SCORECARD')
        || '|' || sqlstate || '|' || clock_timestamp()::text
      ),
      v_spec.spec_id,new.scorecard_id,sqlstate,left(sqlerrm,1000),true,false,false,'NONE'
    );
  exception when others then
    null;
  end;
  raise warning 'scientific holdout capture failed for scorecard %: %',
    new.scorecard_id, left(sqlerrm,500);
  return new;
end;
$$;


revoke all on function private.alpha_hunter_capture_scientific_holdout_v02()
  from public, anon, authenticated, service_role;

drop trigger if exists trg_ah_capture_scientific_holdout_v02
  on public.alpha_hunter_big_mover_money_scorecard_candidates;
create trigger trg_ah_capture_scientific_holdout_v02
after insert on public.alpha_hunter_big_mover_money_scorecard_candidates
for each row execute function private.alpha_hunter_capture_scientific_holdout_v02();

create or replace function private.alpha_hunter_register_scientific_holdout_v02()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_spec_id constant text := 'AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02';
  v_hypothesis_id constant text := 'H_EARLY_OPERATIONAL_BUNDLE_DISCRIMINATION_12H_V2';
  v_schema_fingerprint text;
  v_query_fingerprint text;
  v_spec_hash text;
  v_protocol jsonb;
  v_registered_at timestamptz;
  v_existing public.alpha_hunter_scientific_holdout_specs%rowtype;
begin
  v_schema_fingerprint := private.alpha_hunter_scientific_source_schema_fingerprint_v01();
  if v_schema_fingerprint is null then
    raise exception 'scientific holdout source schema is unavailable';
  end if;

  v_query_fingerprint := pg_catalog.encode(
    extensions.digest(
      pg_catalog.pg_get_functiondef(
        pg_catalog.to_regprocedure(
          'private.alpha_hunter_capture_scientific_holdout_v02()'
        )
      ),
      'sha256'
    ),
    'hex'
  );
  if v_query_fingerprint is null then
    raise exception 'scientific holdout v0.2 capture function is unavailable';
  end if;

  v_protocol := jsonb_build_object(
    'design','prospective matched operational-bundle discrimination holdout; v0.2 pre-outcome matching amendment',
    'supersedes_spec_id','AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V01',
    'supersession_reason','v0.1 frozen exact matching produced zero common-support strata in a candidate-time-only audit before outcome access',
    'amendment_data_used','candidate-time covariates and assignment labels only; no primary/secondary outcomes',
    'outcome_evidence_used_in_amendment',false,
    'estimand','12H predictive discrimination of the complete contemporaneous scanner-direction plus direction-bound geometry bundle among otherwise-safe EARLY 0-5% candidates; no causal component claim',
    'test_rule','scanner_direction equals candidate direction; geometry valid; geometry_source SCANNER_EXECUTION_SETUP; geometry_direction_bound explicitly true',
    'control_pool_rule','same prospective EARLY safety and source contract, but at least one direction/geometry qualification is absent; no blanket not-eligible control',
    'assignment_inputs','candidate-time evidence only; outcomes are prohibited',
    'independence_rule','first qualifying symbol-direction observation after a 24-hour cooldown',
    'future_matching_rule','greedy 1:1 without replacement; process TEST rows by decision_available_at_utc then scorecard_id; exact direction, lifecycle, liquidity_state and candidate_quality_status; require absolute decision-time gap <=24 hours; all exact fields must be non-null, raw move finite, similarity finite 0..100 and feature coverage finite 0..1; minimize abs(abs_move_test-abs_move_control)/5 + abs(similarity_test-similarity_control)/100 + abs(feature_coverage_test-feature_coverage_control) + abs(time_gap_hours)/24; tie-break CONTROL by decision_available_at_utc then scorecard_id; unmatched visible',
    'prohibited_matching_covariates',jsonb_build_array('bridge_status','source_run_id exact-match'),
    'bridge_status_exclusion_reason','bridge_status includes scanner-direction conflict and execution-geometry availability and is therefore entangled with the tested operational bundle',
    'source_run_exact_exclusion_reason','pre-outcome common-support audit showed exact source_run_id plus baseline strata starved matching; temporal comparability is enforced with a 24-hour caliper instead',
    'match_freeze_rule','freeze pairs before reading primary outcomes at the first scheduled UTC-day close when all gates are met, otherwise at day 60; use only v0.2 bindings captured by that close',
    'primary_measurement','reference open_time = ceil_3m(decision_available_at_utc); use first fully complete public Bitget 3m candle with open_time at or after that boundary and last fully complete candle with close_time at or before decision_available_at_utc plus 12 hours; LONG return_pct=100*(endpoint_close/reference_open-1); SHORT return_pct=100*(1-endpoint_close/reference_open)',
    'secondary_measurement','same decision anchor and source at 24 hours; sensitivity only, not independent replication',
    'prohibited_metrics',jsonb_build_array('path_r_pre_cost','candidate_path_outcome','realistic_net_r'),
    'minimum_matched_pairs',100,
    'minimum_symbols',30,
    'minimum_utc_days',20,
    'minimum_pairs_per_direction',25,
    'maximum_collection_days',60,
    'primary_statistic','paired mean TEST minus CONTROL return; one-sided alternative greater than zero; alpha 0.025',
    'minimum_effect_percentage_points',0.50,
    'confidence_interval_rule','95% paired UTC-day block-bootstrap lower bound must exceed zero',
    'missing_data_rule','both pair members require complete finite primary outcomes from the frozen metric and source; differential arm attrition above 10 percentage points is INCONCLUSIVE; no imputation',
    'multiplicity_rule','one confirmatory 12H endpoint only; 24H is descriptive secondary sensitivity; all subgroup analyses exploratory',
    'day_60_rule','if every sample and coverage gate is not met at the scheduled UTC-day close on day 60, conclude INCONCLUSIVE and do not extend or relax',
    'randomization_test','clustered paired label-swap: cluster key=UTC date of TEST decision_available_at_utc; draw one independent sign per UTC-day cluster and multiply every pair difference in that cluster by the sign; each permuted statistic is pair-weighted mean over all frozen pairs; 100000 Monte Carlo draws; PRNG seed 2026092002; one-sided p=(1+count(permuted_stat>=observed_stat))/(100000+1)',
    'bootstrap','percentile paired cluster bootstrap: cluster key=UTC date of TEST decision_available_at_utc; sample observed UTC-day clusters with replacement and include every frozen pair in each sampled cluster; pair-weighted mean difference; 100000 draws; PRNG seed 2026092001; 95% interval is empirical 2.5th and 97.5th percentiles',
    'inference','randomization p<=0.025 plus bootstrap lower bound above zero and effect>=0.50 percentage points; no unpaired evaluator; no peeking',
    'claim_ceiling','SUPPORTED IN SHADOW - INDEPENDENT REPLICATION REQUIRED; never READY, profitable, executable, or production-safe',
    'falsification','any safety/integrity breach, preregistration breach, assignment leakage, unsupported source drift, inadequate common support, effect below 0.50 percentage points, CI lower bound not above zero, p-value above 0.025, excessive differential attrition, or failure to meet the frozen sample gate prevents support',
    'source_model_version','big-mover-money-scorecard-v0.2-stage-linked',
    'source_bridge_model_version','big-mover-money-entry-bridge-v0.1',
    'capture_contract_version','scientific-forward-holdout-v0.1',
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );

  v_spec_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'spec_id',v_spec_id,
        'hypothesis_id',v_hypothesis_id,
        'protocol',v_protocol,
        'source_schema_fingerprint',v_schema_fingerprint,
        'source_query_fingerprint',v_query_fingerprint
      )::text,
      'sha256'
    ),
    'hex'
  );

  select * into v_existing
  from public.alpha_hunter_scientific_holdout_specs
  where spec_id = v_spec_id;

  if found then
    if v_existing.spec_hash is distinct from v_spec_hash
       or v_existing.protocol is distinct from v_protocol
       or v_existing.source_schema_fingerprint is distinct from v_schema_fingerprint
       or v_existing.source_query_fingerprint is distinct from v_query_fingerprint
       or v_existing.collection_ends_at_utc
            is distinct from v_existing.registered_at_utc + interval '60 days' then
      raise exception 'scientific holdout specification conflict for %', v_spec_id;
    end if;
  else
    v_registered_at := clock_timestamp();
    insert into public.alpha_hunter_scientific_holdout_specs(
      spec_id,hypothesis_id,registered_at_utc,collection_ends_at_utc,
      primary_metric,primary_horizon_hours,
      secondary_horizon_hours,minimum_matched_pairs,minimum_symbols,
      minimum_utc_days,minimum_pairs_per_direction,maximum_collection_days,
      protocol,source_schema_fingerprint,source_query_fingerprint,spec_hash,
      capture_contract_version,shadow_only,trade_permission,
      production_promotion_permitted,order_path
    ) values (
      v_spec_id,v_hypothesis_id,v_registered_at,v_registered_at + interval '60 days',
      'decision_anchor_direction_adjusted_close_return_pct',12,24,100,30,20,25,60,
      v_protocol,v_schema_fingerprint,v_query_fingerprint,v_spec_hash,
      'scientific-forward-holdout-v0.1',true,false,false,'NONE'
    );
  end if;
end;
$$;

revoke all on function private.alpha_hunter_register_scientific_holdout_v02()
  from public, anon, authenticated, service_role;

-- Register only after the complete v0.2 capture function and trigger exist.
select private.alpha_hunter_register_scientific_holdout_v02();
drop function private.alpha_hunter_register_scientific_holdout_v02();

create or replace view public.alpha_hunter_scientific_holdout_status_v02
with (security_invoker=true,security_barrier=true)
as
select
  s.spec_id,
  s.hypothesis_id,
  'COLLECTING - V0.2 PROSPECTIVE MATCHING - NOT YET EVALUABLE'::text
    as scientific_status,
  s.registered_at_utc,
  s.collection_ends_at_utc,
  s.primary_metric,
  s.primary_horizon_hours,
  s.secondary_horizon_hours,
  count(b.binding_id) filter(where b.group_name='TEST') as test_bound,
  count(b.binding_id) filter(where b.group_name='CONTROL_POOL') as control_pool_bound,
  count(b.binding_id) filter(where b.group_name='EXCLUDED') as excluded,
  (select count(*) from public.alpha_hunter_scientific_holdout_capture_failures f
    where f.spec_id=s.spec_id) as capture_failures,
  s.minimum_matched_pairs,
  s.minimum_symbols,
  s.minimum_utc_days,
  s.minimum_pairs_per_direction,
  'CAPTURE_V02_PROSPECTIVE_TEST_AND_CONTROL_POOL; OUTCOMES PROHIBITED'::text
    as next_gate,
  'NONE'::text as scientific_conclusion,
  s.protocol->>'supersedes_spec_id' as supersedes_spec_id,
  s.protocol->>'supersession_reason' as supersession_reason,
  false as outcome_access_permitted,
  false as primary_results_exposed,
  false as confirmatory_analysis_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  s.spec_hash,
  s.source_schema_fingerprint,
  s.source_query_fingerprint
from public.alpha_hunter_scientific_holdout_specs s
left join public.alpha_hunter_scientific_holdout_bindings b
  on b.spec_id=s.spec_id
where s.spec_id='AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02'
group by s.spec_id,s.hypothesis_id,s.registered_at_utc,s.collection_ends_at_utc,
         s.primary_metric,s.primary_horizon_hours,s.secondary_horizon_hours,
         s.minimum_matched_pairs,s.minimum_symbols,s.minimum_utc_days,
         s.minimum_pairs_per_direction,s.protocol,s.spec_hash,
         s.source_schema_fingerprint,s.source_query_fingerprint;

revoke all on public.alpha_hunter_scientific_holdout_status_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_scientific_holdout_status_v02
  to service_role;
