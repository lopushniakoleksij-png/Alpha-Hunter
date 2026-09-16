-- Alpha Hunter scientific forward holdout binder v0.1
--
-- This migration starts a prospective, capture-only scientific clock. It does
-- not evaluate outcomes, claim support, activate thresholds, promote research
-- geometry, change cron, or introduce an execution/order path.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_scientific_holdout_specs (
  spec_id text primary key,
  hypothesis_id text not null unique,
  registered_at_utc timestamptz not null default clock_timestamp(),
  collection_ends_at_utc timestamptz not null,
  status text not null default 'COLLECTING'
    check (status = 'COLLECTING'),
  primary_metric text not null
    check (primary_metric = 'decision_anchor_direction_adjusted_close_return_pct'),
  primary_horizon_hours integer not null check (primary_horizon_hours = 12),
  secondary_horizon_hours integer not null check (secondary_horizon_hours = 24),
  minimum_matched_pairs integer not null check (minimum_matched_pairs = 100),
  minimum_symbols integer not null check (minimum_symbols = 30),
  minimum_utc_days integer not null check (minimum_utc_days = 20),
  minimum_pairs_per_direction integer not null
    check (minimum_pairs_per_direction = 25),
  maximum_collection_days integer not null check (maximum_collection_days = 60),
  protocol jsonb not null check (jsonb_typeof(protocol) = 'object'),
  source_schema_fingerprint text not null
    check (source_schema_fingerprint ~ '^[0-9a-f]{64}$'),
  source_query_fingerprint text not null
    check (source_query_fingerprint ~ '^[0-9a-f]{64}$'),
  spec_hash text not null unique check (spec_hash ~ '^[0-9a-f]{64}$'),
  capture_contract_version text not null
    check (capture_contract_version = 'scientific-forward-holdout-v0.1'),
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted = false),
  order_path text not null default 'NONE' check (order_path = 'NONE'),
  check (collection_ends_at_utc = registered_at_utc + interval '60 days')
);

create table if not exists public.alpha_hunter_scientific_holdout_bindings (
  binding_id text primary key,
  spec_id text not null references public.alpha_hunter_scientific_holdout_specs(spec_id),
  scorecard_id text not null,
  source_bridge_id text not null,
  source_run_id text not null,
  registered_at_utc timestamptz not null,
  candidate_at_utc timestamptz not null,
  source_created_at_utc timestamptz not null,
  decision_available_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  scanner_direction text,
  group_name text not null
    check (group_name in ('TEST','CONTROL_POOL','EXCLUDED')),
  eligibility_reason text not null,
  raw_change_24h_pct double precision,
  lifecycle text not null,
  research_status text not null,
  bridge_status text not null,
  opportunity_timing text,
  geometry_valid boolean not null,
  similarity_score double precision,
  feature_coverage double precision,
  liquidity_state text,
  candidate_quality_status text,
  source_model_version text not null,
  source_bridge_model_version text,
  geometry_source text,
  geometry_direction_bound boolean,
  research_geometry_promoted boolean,
  source_schema_fingerprint text not null,
  source_query_fingerprint text not null,
  source_evidence_hash text not null
    check (source_evidence_hash ~ '^[0-9a-f]{64}$'),
  capture_contract_version text not null
    check (capture_contract_version = 'scientific-forward-holdout-v0.1'),
  holdout boolean not null default true check (holdout = true),
  data_quality_ok boolean not null,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted = false),
  order_path text not null default 'NONE' check (order_path = 'NONE'),
  captured_at_utc timestamptz not null default clock_timestamp(),
  unique (spec_id, scorecard_id),
  unique (spec_id, source_bridge_id),
  check (decision_available_at_utc >= source_created_at_utc),
  check (group_name = 'EXCLUDED' or data_quality_ok = true)
);

create table if not exists public.alpha_hunter_scientific_holdout_capture_failures (
  failure_id text primary key,
  spec_id text,
  scorecard_id text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  sqlstate text not null,
  error_message text not null,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted = false),
  order_path text not null default 'NONE' check (order_path = 'NONE')
);

alter table public.alpha_hunter_scientific_holdout_specs enable row level security;
alter table public.alpha_hunter_scientific_holdout_bindings enable row level security;
alter table public.alpha_hunter_scientific_holdout_capture_failures enable row level security;

revoke all on table public.alpha_hunter_scientific_holdout_specs
  from public, anon, authenticated, service_role;
revoke all on table public.alpha_hunter_scientific_holdout_bindings
  from public, anon, authenticated, service_role;
revoke all on table public.alpha_hunter_scientific_holdout_capture_failures
  from public, anon, authenticated, service_role;
grant select on table public.alpha_hunter_scientific_holdout_specs to service_role;
grant select on table public.alpha_hunter_scientific_holdout_bindings to service_role;
grant select on table public.alpha_hunter_scientific_holdout_capture_failures to service_role;

create index if not exists idx_ah_scientific_holdout_binding_match_pool
  on public.alpha_hunter_scientific_holdout_bindings(
    spec_id, group_name, source_run_id, direction, decision_available_at_utc
  );
create index if not exists idx_ah_scientific_holdout_binding_cooldown
  on public.alpha_hunter_scientific_holdout_bindings(
    spec_id, symbol, direction, decision_available_at_utc desc
  );

create or replace function private.alpha_hunter_block_scientific_holdout_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'scientific holdout evidence is append-only';
end;
$$;
revoke all on function private.alpha_hunter_block_scientific_holdout_mutation()
  from public, anon, authenticated, service_role;

drop trigger if exists trg_ah_scientific_holdout_specs_append_only
  on public.alpha_hunter_scientific_holdout_specs;
create trigger trg_ah_scientific_holdout_specs_append_only
before update or delete on public.alpha_hunter_scientific_holdout_specs
for each row execute function private.alpha_hunter_block_scientific_holdout_mutation();

drop trigger if exists trg_ah_scientific_holdout_bindings_append_only
  on public.alpha_hunter_scientific_holdout_bindings;
create trigger trg_ah_scientific_holdout_bindings_append_only
before update or delete on public.alpha_hunter_scientific_holdout_bindings
for each row execute function private.alpha_hunter_block_scientific_holdout_mutation();

drop trigger if exists trg_ah_scientific_holdout_failures_append_only
  on public.alpha_hunter_scientific_holdout_capture_failures;
create trigger trg_ah_scientific_holdout_failures_append_only
before update or delete on public.alpha_hunter_scientific_holdout_capture_failures
for each row execute function private.alpha_hunter_block_scientific_holdout_mutation();

create or replace function private.alpha_hunter_scientific_source_schema_fingerprint_v01()
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select pg_catalog.encode(
    extensions.digest(
      pg_catalog.string_agg(
        a.attname || ':' || pg_catalog.format_type(a.atttypid,a.atttypmod)
        || ':' || a.attnotnull::text,
        '|' order by a.attnum
      ),
      'sha256'
    ),
    'hex'
  )
  from pg_catalog.pg_attribute a
  where a.attrelid = pg_catalog.to_regclass(
          'public.alpha_hunter_big_mover_money_scorecard_candidates'
        )
    and a.attnum > 0
    and not a.attisdropped
    and a.attname = any(array[
      'scorecard_id','source_bridge_id','run_id','candidate_at_utc','created_at',
      'symbol','direction','raw_change_24h_pct','scanner_direction','geometry_valid',
      'lifecycle','research_status','bridge_status','opportunity_timing',
      'similarity_score','feature_coverage','liquidity_state','candidate_quality_status',
      'model_version','frozen_evidence','shadow_only','trade_permission'
    ]);
$$;
revoke all on function private.alpha_hunter_scientific_source_schema_fingerprint_v01()
  from public, anon, authenticated, service_role;

create or replace function private.alpha_hunter_register_scientific_holdout_v01()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_spec_id constant text := 'AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V01';
  v_hypothesis_id constant text := 'H_EARLY_OPERATIONAL_BUNDLE_DISCRIMINATION_12H_V1';
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
          'private.alpha_hunter_capture_scientific_holdout_v01()'
        )
      ),
      'sha256'
    ),
    'hex'
  );
  if v_query_fingerprint is null then
    raise exception 'scientific holdout capture function is unavailable';
  end if;

  v_protocol := jsonb_build_object(
    'design','prospective matched operational-bundle discrimination holdout; capture only in v0.1',
    'estimand','12H predictive discrimination of the complete contemporaneous scanner-direction plus direction-bound geometry bundle among otherwise-safe EARLY 0-5% candidates; no causal component claim',
    'test_rule','scanner_direction equals candidate direction; geometry valid; geometry_source SCANNER_EXECUTION_SETUP; geometry_direction_bound explicitly true',
    'control_pool_rule','same prospective EARLY safety and source contract, but at least one direction/geometry qualification is absent; no blanket not-eligible control',
    'assignment_inputs','candidate-time evidence only; outcomes are prohibited',
    'independence_rule','first qualifying symbol-direction observation after a 24-hour cooldown',
    'future_matching_rule','greedy 1:1 without replacement; process TEST rows by decision_available_at_utc then scorecard_id; exact source_run_id, direction, lifecycle, bridge_status, liquidity_state and candidate_quality_status; all exact fields must be non-null, similarity must be finite 0..100 and feature coverage finite 0..1; minimize standardized L1 distance abs(abs_move_test-abs_move_control)/5 + abs(similarity_test-similarity_control)/100 + abs(feature_coverage_test-feature_coverage_control); tie-break CONTROL by candidate_at_utc then scorecard_id; unmatched visible',
    'match_freeze_rule','freeze pairs before reading primary outcomes at the first scheduled UTC-day close when all gates are met, otherwise at day 60; use only bindings captured by that close',
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
    'confidence_interval_rule','95% UTC-day/source-run block-bootstrap lower bound must exceed zero',
    'missing_data_rule','both pair members require complete finite primary outcomes from the frozen metric and source; differential arm attrition above 10 percentage points is INCONCLUSIVE; no imputation',
    'multiplicity_rule','one confirmatory 12H endpoint only; 24H is descriptive secondary sensitivity; all subgroup analyses exploratory',
    'day_60_rule','if every sample and coverage gate is not met at the scheduled UTC-day close on day 60, conclude INCONCLUSIVE and do not extend or relax',
    'randomization_test','clustered paired label-swap: cluster key=(UTC date of decision_available_at_utc,source_run_id); draw one independent sign per cluster and multiply every pair difference in that cluster by the sign; each permuted statistic is the pair-weighted mean over all frozen pairs; observed statistic uses every sign +1; 100000 Monte Carlo draws; PRNG seed 2026091602; one-sided p=(1+count(permuted_stat>=observed_stat))/(100000+1)',
    'bootstrap','percentile paired cluster bootstrap: cluster key=(UTC date of decision_available_at_utc,source_run_id); sample the observed number of clusters with replacement and include every frozen pair in each sampled cluster; statistic is the pair-weighted mean difference; 100000 draws; PRNG seed 2026091601; 95% interval is empirical 2.5th and 97.5th percentiles',
    'inference','randomization p<=0.025 plus bootstrap lower bound above zero and effect>=0.50 percentage points; no unpaired evaluator; no peeking',
    'claim_ceiling','SUPPORTED IN SHADOW - INDEPENDENT REPLICATION REQUIRED; never READY, profitable, executable, or production-safe',
    'falsification','any safety/integrity breach, preregistration breach, assignment leakage, unsupported source drift, effect below 0.50 percentage points, CI lower bound not above zero, p-value above 0.025, excessive differential attrition, or failure to meet the frozen sample gate prevents support',
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
revoke all on function private.alpha_hunter_register_scientific_holdout_v01()
  from public, anon, authenticated, service_role;

create or replace function private.alpha_hunter_capture_scientific_holdout_v01()
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
  where spec_id = 'AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V01'
    and status = 'COLLECTING';

  if not found then
    return new;
  end if;

  v_schema_fingerprint := private.alpha_hunter_scientific_source_schema_fingerprint_v01();
  v_query_fingerprint := pg_catalog.encode(
    extensions.digest(
      pg_catalog.pg_get_functiondef(
        pg_catalog.to_regprocedure(
          'private.alpha_hunter_capture_scientific_holdout_v01()'
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
revoke all on function private.alpha_hunter_capture_scientific_holdout_v01()
  from public, anon, authenticated, service_role;

drop trigger if exists trg_ah_capture_scientific_holdout_v01
  on public.alpha_hunter_big_mover_money_scorecard_candidates;
create trigger trg_ah_capture_scientific_holdout_v01
after insert on public.alpha_hunter_big_mover_money_scorecard_candidates
for each row execute function private.alpha_hunter_capture_scientific_holdout_v01();

-- Register only after the complete capture function and trigger exist. This
-- prevents a post-registration interval in which canonical rows are unbound.
select private.alpha_hunter_register_scientific_holdout_v01();
drop function private.alpha_hunter_register_scientific_holdout_v01();

create or replace view public.alpha_hunter_scientific_holdout_status_v01
with (security_invoker = true, security_barrier = true)
as
select
  s.spec_id,
  s.hypothesis_id,
  'COLLECTING - NOT YET EVALUABLE'::text as scientific_status,
  s.registered_at_utc,
  s.collection_ends_at_utc,
  s.primary_metric,
  s.primary_horizon_hours,
  s.secondary_horizon_hours,
  count(b.binding_id) filter (where b.group_name='TEST') as test_bound,
  count(b.binding_id) filter (where b.group_name='CONTROL_POOL') as control_pool_bound,
  count(b.binding_id) filter (where b.group_name='EXCLUDED') as excluded,
  (select count(*)
   from public.alpha_hunter_scientific_holdout_capture_failures f
   where f.spec_id=s.spec_id) as capture_failures,
  s.minimum_matched_pairs,
  'CAPTURE_PROSPECTIVE_TEST_AND_CONTROL_POOL'::text as next_gate,
  'NONE'::text as scientific_conclusion,
  s.spec_hash,
  s.source_schema_fingerprint,
  s.source_query_fingerprint,
  s.shadow_only,
  s.trade_permission,
  s.production_promotion_permitted,
  s.order_path
from public.alpha_hunter_scientific_holdout_specs s
left join public.alpha_hunter_scientific_holdout_bindings b
  on b.spec_id=s.spec_id
group by s.spec_id;

revoke all on public.alpha_hunter_scientific_holdout_status_v01
  from public, anon, authenticated, service_role;
grant select on public.alpha_hunter_scientific_holdout_status_v01 to service_role;
