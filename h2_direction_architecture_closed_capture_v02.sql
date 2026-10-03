-- Alpha Hunter H2 direction architecture CLOSED-CANDLE capture v0.2
--
-- Scientific successor to H2 v0.1 after Issue #311 proved that v0.1 read the
-- still-forming source_payload.timeframes.15m.latest_candle instead of the
-- preregistered latest CLOSED 15m candle. v0.1 rows remain immutable and are
-- not imported into this cohort.
--
-- Hypothesis family:
--   12H + 1D = parent directional bias
--   1H       = timing/context
--   15m      = trigger/acceptance evidence, NOT a mandatory direction vote
--
-- Primary H2 trigger:
--   latest closed 15m candle closes on the directionally correct side of EMA9.
-- Stronger tag:
--   same candle crosses/reclaims EMA9 in the candidate direction.
--
-- Geometry reference:
--   15m local support/resistance stop + 4H structural target.
--
-- Scientific boundary:
--   CAPTURE ONLY. No outcomes are queried. No evaluator is created.
--   Decision anchors are collected only for the preregistered independent H2
--   cohort: first H2 trigger per symbol+direction, then >=24h cooldown.
--   Legacy scanner alignment is retained as a capture-time overlap tag only.
--   A separately preregistered sealed evaluator is required before H2 outcomes
--   can be read or any scientific support/falsification claim can be made.
--
-- Decision-price integrity:
--   The source scan price is retained only as provenance.
--   The H2 decision anchor is a separately persisted public Bitget 1m candle
--   open at the first exact minute at/after decision_available_at_utc.
--   It is never a fill claim.
--
-- Safety:
--   shadow_only=true
--   trade_permission=false
--   no T0/T1/T2 authorization
--   no threshold change
--   no production promotion
--   no order path

create table if not exists public.alpha_hunter_h2_direction_specs_v02 (
  spec_id text primary key,
  hypothesis_id text not null unique,
  registered_at_utc timestamptz not null default clock_timestamp(),
  collection_ends_at_utc timestamptz not null,
  status text not null default 'COLLECTING'
    check(status='COLLECTING'),
  null_hypothesis text not null,
  alternative_hypothesis text not null,
  architecture jsonb not null check(jsonb_typeof(architecture)='object'),
  candidate_cooldown_hours integer not null check(candidate_cooldown_hours=24),
  maximum_source_age_minutes integer not null
    check(maximum_source_age_minutes=15),
  minimum_anchor_observations integer not null
    check(minimum_anchor_observations=100),
  minimum_symbols integer not null check(minimum_symbols=30),
  minimum_utc_days integer not null check(minimum_utc_days=20),
  minimum_anchors_per_direction integer not null
    check(minimum_anchors_per_direction=25),
  maximum_collection_days integer not null check(maximum_collection_days=60),
  capture_maturity_gate_is_power_calculation boolean not null default false
    check(capture_maturity_gate_is_power_calculation=false),
  future_primary_metric text not null,
  future_false_start_metric text not null,
  evaluator_preregistration_required boolean not null default true
    check(evaluator_preregistration_required=true),
  outcome_access_permitted boolean not null default false
    check(outcome_access_permitted=false),
  confirmatory_analysis_permitted boolean not null default false
    check(confirmatory_analysis_permitted=false),
  independent_replication_required boolean not null default true
    check(independent_replication_required=true),
  spec_hash text not null unique check(spec_hash ~ '^[0-9a-f]{64}$'),
  capture_contract_version text not null
    check(capture_contract_version='h2-direction-architecture-closed-capture-v0.2'),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  check(collection_ends_at_utc=registered_at_utc+interval '60 days')
);


create table if not exists public.alpha_hunter_h2_direction_captures_v02 (
  capture_id text primary key,
  spec_id text not null
    references public.alpha_hunter_h2_direction_specs_v02(spec_id),
  diagnostic_id text not null,
  run_id text not null,
  source_signal_id text not null,
  source_captured_at_utc timestamptz not null,
  decision_available_at_utc timestamptz not null,
  captured_at_utc timestamptz not null default clock_timestamp(),

  symbol text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  scanner_direction text,
  opportunity_timing text,
  market_phase text,
  candidate_quality_status text,
  liquidity_state text,

  parent_direction_12h text,
  parent_direction_1d text,
  trend_1h text,
  trend_15m text,
  trend_4h text,

  source_scan_price double precision,
  source_scan_price_is_decision_anchor boolean not null default false
    check(source_scan_price_is_decision_anchor=false),

  candle_15m_open double precision,
  candle_15m_close double precision,
  candle_15m_low double precision,
  candle_15m_high double precision,
  ema9_15m double precision,
  trigger_candle_started_at_utc timestamptz,
  trigger_candle_closed_at_utc timestamptz,
  trigger_candle_confirmed_closed boolean not null default true
    check(trigger_candle_confirmed_closed=true),
  ema9_15m_source text not null
    check(ema9_15m_source='REVERSED_ONE_FORMING_BAR_STANDARD_EMA9'),
  source_snapshot_collected_at_utc timestamptz not null,
  source_snapshot_created_at_utc timestamptz not null,

  support_15m double precision,
  resistance_15m double precision,
  support_4h double precision,
  resistance_4h double precision,
  research_stop_15m double precision,
  research_target_4h double precision,
  rr_15m_stop_4h_target double precision,

  source_age_seconds double precision,
  source_fresh_for_15m_trigger boolean not null,
  parent_12h_1d_aligned boolean not null,
  timing_1h_aligned boolean not null,
  geometry_valid boolean not null,
  trigger_accept_fast_value boolean not null,
  trigger_ema9_reclaim boolean not null,
  trigger_structural_sweep_reclaim boolean not null,
  h2_context_eligible boolean not null,
  h2_triggered boolean not null,
  legacy_scanner_aligned boolean not null,
  rr_ge_5_at_source_geometry boolean,

  capture_class text not null,
  exclusion_reason text,
  source_geometry_model_version text not null,
  source_parent_model_version_12h text,
  source_parent_model_version_1d text,
  source_evidence_hash text not null
    check(source_evidence_hash ~ '^[0-9a-f]{64}$'),

  outcome_evidence_used boolean not null default false
    check(outcome_evidence_used=false),
  sealed_outcome_read boolean not null default false
    check(sealed_outcome_read=false),
  evaluator_active boolean not null default false
    check(evaluator_active=false),
  t0_authorized boolean not null default false check(t0_authorized=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),

  unique(spec_id,diagnostic_id),
  check(decision_available_at_utc>=source_captured_at_utc)
);


create table if not exists public.alpha_hunter_h2_direction_anchor_prices_v02 (
  capture_id text primary key
    references public.alpha_hunter_h2_direction_captures_v02(capture_id),
  reference_expected_at_utc timestamptz not null,
  reference_candle_at_utc timestamptz not null,
  reference_open double precision not null check(reference_open>0),
  bid_price_at_collection double precision,
  ask_price_at_collection double precision,
  ticker_observed_at_utc timestamptz,
  measurement_source text not null
    check(measurement_source='BITGET_PUBLIC_V3_1M_CANDLES'),
  source_endpoint text not null
    check(source_endpoint='/api/v3/market/candles'),
  exact_expected_minute_required boolean not null default true
    check(exact_expected_minute_required=true),
  public_market_data_only boolean not null default true
    check(public_market_data_only=true),
  reference_price_is_fill_claim boolean not null default false
    check(reference_price_is_fill_claim=false),
  outcome_evidence_used boolean not null default false
    check(outcome_evidence_used=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);


create table if not exists public.alpha_hunter_h2_direction_capture_failures_v02 (
  failure_id text primary key,
  spec_id text,
  capture_id text,
  diagnostic_id text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  failure_class text not null,
  error_message text not null,
  outcome_evidence_used boolean not null default false
    check(outcome_evidence_used=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false)
);


alter table public.alpha_hunter_h2_direction_specs_v02 enable row level security;
alter table public.alpha_hunter_h2_direction_captures_v02 enable row level security;
alter table public.alpha_hunter_h2_direction_anchor_prices_v02 enable row level security;
alter table public.alpha_hunter_h2_direction_capture_failures_v02 enable row level security;

revoke all on table public.alpha_hunter_h2_direction_specs_v02
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_h2_direction_captures_v02
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_h2_direction_anchor_prices_v02
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_h2_direction_capture_failures_v02
  from public,anon,authenticated,service_role;

grant select on table public.alpha_hunter_h2_direction_specs_v02
  to service_role;
grant select on table public.alpha_hunter_h2_direction_captures_v02
  to service_role;
grant select on table public.alpha_hunter_h2_direction_anchor_prices_v02
  to service_role;
grant select on table public.alpha_hunter_h2_direction_capture_failures_v02
  to service_role;


drop trigger if exists trg_ah_h2_closed_specs_append_only_v02
  on public.alpha_hunter_h2_direction_specs_v02;
create trigger trg_ah_h2_closed_specs_append_only_v02
before update or delete on public.alpha_hunter_h2_direction_specs_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_h2_closed_captures_append_only_v02
  on public.alpha_hunter_h2_direction_captures_v02;
create trigger trg_ah_h2_closed_captures_append_only_v02
before update or delete on public.alpha_hunter_h2_direction_captures_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_h2_closed_anchor_prices_append_only_v02
  on public.alpha_hunter_h2_direction_anchor_prices_v02;
create trigger trg_ah_h2_closed_anchor_prices_append_only_v02
before update or delete on public.alpha_hunter_h2_direction_anchor_prices_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_h2_closed_failures_append_only_v02
  on public.alpha_hunter_h2_direction_capture_failures_v02;
create trigger trg_ah_h2_closed_failures_append_only_v02
before update or delete on public.alpha_hunter_h2_direction_capture_failures_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();


create index if not exists idx_ah_h2_closed_capture_time_v02
  on public.alpha_hunter_h2_direction_captures_v02(
    spec_id,decision_available_at_utc
  );

create index if not exists idx_ah_h2_closed_capture_cooldown_v02
  on public.alpha_hunter_h2_direction_captures_v02(
    spec_id,symbol,direction,decision_available_at_utc
  );

create index if not exists idx_ah_h2_closed_capture_trigger_v02
  on public.alpha_hunter_h2_direction_captures_v02(
    spec_id,h2_triggered,legacy_scanner_aligned
  );


create or replace function private.alpha_hunter_register_h2_direction_v02()
returns void
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec_id constant text := 'AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02';
  v_hypothesis_id constant text :=
    'H_PARENT_12H_1D_1H_TIMING_CLOSED_15M_ACCEPTANCE_VS_LEGACY_ALIGNMENT_V2';
  v_architecture jsonb;
  v_spec_hash text;
  v_registered_at timestamptz;
  v_existing public.alpha_hunter_h2_direction_specs_v02%rowtype;
begin
  v_architecture := jsonb_build_object(
    'research_question',
      'Does 12H+1D parent bias with 1H timing and 15m acceptance preserve more executable geometry than waiting for legacy full scanner alignment without creating an unacceptable false-start rate?',
    'test_direction_bias','12H and 1D parent directions must both align with candidate direction',
    'test_timing','1H trend must align with candidate direction',
    'test_opportunity_timing','EARLY',
    'test_15m_primary_trigger',
      'canonical exact-run/symbol LAST_CLOSED 15m close above completed-bar EMA9 for LONG or below completed-bar EMA9 for SHORT; 15m trend label is not a mandatory direction vote',
    'test_15m_stronger_tag',
      'same canonical last-closed 15m candle crosses/reclaims completed-bar EMA9 in candidate direction',
    'trigger_source_contract',
      'CANONICAL_SYMBOL_SNAPSHOT_EXACT_RUN_SYMBOL_LAST_CLOSED_CANDLE',
    'closed_ema9_contract',
      'reverse exactly one still-forming latest candle from standard EMA9 using alpha=2/(9+1)=0.2; fail closed unless latest is proven still open and prior candle proven closed',
    'v01_quarantine',
      'H2 v0.1 forming-candle captures are not imported and cannot satisfy v0.2 maturity',
    'test_geometry','15m local support/resistance invalidation with 4H structural target',
    'legacy_control_reference',
      'scanner_direction equals candidate direction is retained as a capture-time overlap tag only; legacy-only rows do not consume anchor collection capacity; any future standalone legacy-control sampler/evaluator must be separately preregistered before outcome access',
    'decision_anchor',
      'first exact public Bitget 1m candle open at or after decision_available_at_utc; source scan price is provenance only and never the decision anchor',
    'source_freshness',
      'all required source inputs must become available within 15 minutes of source_captured_at_utc',
    'candidate_independence_rule',
      'first H2-triggered symbol-direction reference after a 24-hour cooldown',
    'capture_maturity_gate',
      '100 anchors, 30 symbols, 20 UTC days, 25 LONG and 25 SHORT; operational maturity gate only, not a statistical power calculation',
    'future_primary_metric',
      'REALISTIC_COST_ADJUSTED_NET_R only after a validated cost/execution model exists; otherwise confirmatory economic conclusion prohibited',
    'future_false_start_metric',
      'predefined stop-first/invalidated-before-expansion rate from a separately preregistered sealed path evaluator',
    'future_evaluator_rule',
      'must be separately preregistered before any H2 outcome is accessed; this capture migration contains no outcome reader',
    'shared_data_warning',
      'H2 shares market periods with H1 geometry research; future inference must treat evidence as correlated and control multiplicity/dependence',
    'null_hypothesis',
      'H2 does not improve realistic cost-adjusted net R versus the legacy confirmation path, or any apparent geometry advantage is offset by false starts/adverse execution',
    'alternative_hypothesis',
      'H2 preserves materially more executable R than the legacy confirmation path while maintaining acceptable false-start and execution-cost behavior',
    'claim_ceiling',
      'CAPTURE_ONLY - NO SUPPORT/FALSIFICATION/READY/TRADE/PROMOTION CLAIM',
    'shadow_only',true,
    'trade_permission',false,
    't0_authorized',false,
    'threshold_change_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );

  v_spec_hash := pg_catalog.encode(
    extensions.digest(
      jsonb_build_object(
        'spec_id',v_spec_id,
        'hypothesis_id',v_hypothesis_id,
        'architecture',v_architecture,
        'cooldown_hours',24,
        'maximum_source_age_minutes',15,
        'minimum_anchor_observations',100,
        'minimum_symbols',30,
        'minimum_utc_days',20,
        'minimum_anchors_per_direction',25,
        'maximum_collection_days',60,
        'capture_contract_version','h2-direction-architecture-closed-capture-v0.2'
      )::text,
      'sha256'
    ),
    'hex'
  );

  select * into v_existing
  from public.alpha_hunter_h2_direction_specs_v02
  where spec_id=v_spec_id;

  if found then
    if v_existing.spec_hash is distinct from v_spec_hash
       or v_existing.architecture is distinct from v_architecture then
      raise exception 'H2 direction architecture spec conflict for %',v_spec_id;
    end if;
    return;
  end if;

  v_registered_at := clock_timestamp();

  insert into public.alpha_hunter_h2_direction_specs_v02(
    spec_id,hypothesis_id,registered_at_utc,collection_ends_at_utc,
    null_hypothesis,alternative_hypothesis,architecture,
    candidate_cooldown_hours,maximum_source_age_minutes,
    minimum_anchor_observations,minimum_symbols,minimum_utc_days,
    minimum_anchors_per_direction,maximum_collection_days,
    capture_maturity_gate_is_power_calculation,
    future_primary_metric,future_false_start_metric,
    evaluator_preregistration_required,outcome_access_permitted,
    confirmatory_analysis_permitted,independent_replication_required,
    spec_hash,capture_contract_version,shadow_only,trade_permission,
    t0_authorized,threshold_change_permitted,
    production_promotion_permitted,order_path
  ) values (
    v_spec_id,v_hypothesis_id,v_registered_at,v_registered_at+interval '60 days',
    v_architecture->>'null_hypothesis',
    v_architecture->>'alternative_hypothesis',
    v_architecture,
    24,15,100,30,20,25,60,false,
    'REALISTIC_COST_ADJUSTED_NET_R_AFTER_VALIDATED_COST_MODEL_ONLY',
    'STOP_FIRST_OR_INVALIDATED_BEFORE_EXPANSION_RATE',
    true,false,false,true,
    v_spec_hash,'h2-direction-architecture-closed-capture-v0.2',
    true,false,false,false,false,'NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_register_h2_direction_v02()
  from public,anon,authenticated,service_role;


create or replace function private.alpha_hunter_capture_h2_direction_v02()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_spec public.alpha_hunter_h2_direction_specs_v02%rowtype;
  v_inserted integer := 0;
  v_anchor_inserted integer := 0;
  v_anchor_failures integer := 0;
  r record;
  v_url text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_expected timestamptz;
  v_candle_at timestamptz;
  v_reference_open double precision;
  v_error text;
begin
  select * into v_spec
  from public.alpha_hunter_h2_direction_specs_v02
  where spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
    and status='COLLECTING';

  if not found then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  insert into public.alpha_hunter_h2_direction_captures_v02(
    capture_id,spec_id,diagnostic_id,run_id,source_signal_id,
    source_captured_at_utc,decision_available_at_utc,
    symbol,direction,scanner_direction,opportunity_timing,market_phase,
    candidate_quality_status,liquidity_state,
    parent_direction_12h,parent_direction_1d,
    trend_1h,trend_15m,trend_4h,
    source_scan_price,candle_15m_open,candle_15m_close,
    candle_15m_low,candle_15m_high,ema9_15m,
    trigger_candle_started_at_utc,trigger_candle_closed_at_utc,
    trigger_candle_confirmed_closed,ema9_15m_source,
    source_snapshot_collected_at_utc,source_snapshot_created_at_utc,
    support_15m,resistance_15m,support_4h,resistance_4h,
    research_stop_15m,research_target_4h,rr_15m_stop_4h_target,
    source_age_seconds,source_fresh_for_15m_trigger,
    parent_12h_1d_aligned,timing_1h_aligned,geometry_valid,
    trigger_accept_fast_value,trigger_ema9_reclaim,
    trigger_structural_sweep_reclaim,
    h2_context_eligible,h2_triggered,legacy_scanner_aligned,
    rr_ge_5_at_source_geometry,capture_class,exclusion_reason,
    source_geometry_model_version,
    source_parent_model_version_12h,source_parent_model_version_1d,
    source_evidence_hash,
    outcome_evidence_used,sealed_outcome_read,evaluator_active,
    t0_authorized,threshold_change_permitted,
    production_promotion_permitted,shadow_only,trade_permission,order_path
  )
  with source_raw as (
    select
      g.diagnostic_id,g.run_id,g.source_signal_id,g.captured_at_utc,
      g.created_at as geometry_created_at,
      g.symbol,g.candidate_direction as direction,g.scanner_direction,
      g.explicit_entry as source_scan_price,g.model_version as geometry_model_version,
      g.shadow_only as geometry_shadow_only,
      g.trade_permission as geometry_trade_permission,
      ss.collected_at_utc as snapshot_collected_at_utc,
      ss.created_at as snapshot_created_at_utc,
      ss.payload as snapshot_payload,
      upper(ss.payload#>>'{timeframes,1H,trend}') as trend_1h,
      upper(ss.payload#>>'{timeframes,15m,trend}') as trend_15m,
      upper(ss.payload#>>'{timeframes,4H,trend}') as trend_4h,
      ss.payload->>'opportunity_timing' as opportunity_timing,
      ss.payload->>'market_phase' as market_phase,
      ss.payload->>'candidate_quality_status' as candidate_quality_status,
      coalesce(
        ss.payload#>>'{pre_move,features,liquidity_state}',
        ss.payload->>'liquidity_state'
      ) as liquidity_state,
      case when (ss.payload#>>'{timeframes,15m,last_closed_candle,open}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,last_closed_candle,open}')::double precision end
        as candle_15m_open,
      case when (ss.payload#>>'{timeframes,15m,last_closed_candle,close}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,last_closed_candle,close}')::double precision end
        as candle_15m_close,
      case when (ss.payload#>>'{timeframes,15m,last_closed_candle,low}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,last_closed_candle,low}')::double precision end
        as candle_15m_low,
      case when (ss.payload#>>'{timeframes,15m,last_closed_candle,high}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,last_closed_candle,high}')::double precision end
        as candle_15m_high,
      case when (ss.payload#>>'{timeframes,15m,last_closed_candle,timestamp}') ~ '^[0-9]+$'
        then pg_catalog.to_timestamp(
          (ss.payload#>>'{timeframes,15m,last_closed_candle,timestamp}')::double precision/1000.0
        ) end as trigger_candle_started_at_utc,
      case when (ss.payload#>>'{timeframes,15m,latest_candle,timestamp}') ~ '^[0-9]+$'
        then pg_catalog.to_timestamp(
          (ss.payload#>>'{timeframes,15m,latest_candle,timestamp}')::double precision/1000.0
        ) end as forming_candle_started_at_utc,
      case when (ss.payload#>>'{timeframes,15m,latest_candle,close}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,latest_candle,close}')::double precision end
        as forming_candle_close,
      case when (ss.payload#>>'{timeframes,15m,indicators,ema_9}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,indicators,ema_9}')::double precision end
        as forming_ema9_15m,
      case when (ss.payload#>>'{timeframes,15m,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,support}')::double precision end
        as support_15m,
      case when (ss.payload#>>'{timeframes,15m,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,15m,resistance}')::double precision end
        as resistance_15m,
      case when (ss.payload#>>'{timeframes,4H,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,4H,support}')::double precision end
        as support_4h,
      case when (ss.payload#>>'{timeframes,4H,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ss.payload#>>'{timeframes,4H,resistance}')::double precision end
        as resistance_4h,
      p12.trend as parent_direction_12h,
      p12.model_version as parent_model_12h,
      p12.created_at as parent_created_12h,
      p1d.trend as parent_direction_1d,
      p1d.model_version as parent_model_1d,
      p1d.created_at as parent_created_1d
    from public.alpha_hunter_geometry_diagnostics g
    join lateral (
      select s.collected_at_utc,s.created_at,s.payload
      from public.alpha_hunter_symbol_snapshots s
      where s.run_id=g.run_id
        and s.symbol=g.symbol
        and s.collected_at_utc=g.captured_at_utc
        and s.trade_permission=false
      order by s.created_at desc
      limit 1
    ) ss on true
    left join lateral (
      select p.trend,p.model_version,p.created_at
      from public.alpha_hunter_big_mover_parent_direction_shadow p
      where p.run_id=g.run_id
        and p.symbol=g.symbol
        and p.direction=g.candidate_direction
        and p.timeframe='12H'
        and p.collection_status='PASS'
        and p.shadow_only=true
        and p.trade_permission=false
      order by p.created_at desc
      limit 1
    ) p12 on true
    left join lateral (
      select p.trend,p.model_version,p.created_at
      from public.alpha_hunter_big_mover_parent_direction_shadow p
      where p.run_id=g.run_id
        and p.symbol=g.symbol
        and p.direction=g.candidate_direction
        and p.timeframe='1D'
        and p.collection_status='PASS'
        and p.shadow_only=true
        and p.trade_permission=false
      order by p.created_at desc
      limit 1
    ) p1d on true
    where g.candidate_direction in ('LONG','SHORT')
      and g.created_at>v_spec.registered_at_utc
      and g.created_at<=v_spec.collection_ends_at_utc
      and not exists (
        select 1
        from public.alpha_hunter_h2_direction_captures_v02 c
        where c.spec_id=v_spec.spec_id
          and c.diagnostic_id=g.diagnostic_id
      )
  ),
  source as (
    select
      sr.*,
      sr.trigger_candle_started_at_utc+interval '15 minutes'
        as trigger_candle_closed_at_utc,
      (
        sr.trigger_candle_started_at_utc is not null
        and sr.forming_candle_started_at_utc is not null
        and sr.forming_candle_started_at_utc
              =sr.trigger_candle_started_at_utc+interval '15 minutes'
        and sr.snapshot_collected_at_utc
              >=sr.trigger_candle_started_at_utc+interval '15 minutes'
        and sr.snapshot_collected_at_utc
              <sr.forming_candle_started_at_utc+interval '15 minutes'
      ) as trigger_candle_confirmed_closed,
      case
        when sr.forming_ema9_15m is not null
          and sr.forming_candle_close is not null
          and sr.trigger_candle_started_at_utc is not null
          and sr.forming_candle_started_at_utc
                =sr.trigger_candle_started_at_utc+interval '15 minutes'
          and sr.snapshot_collected_at_utc
                >=sr.trigger_candle_started_at_utc+interval '15 minutes'
          and sr.snapshot_collected_at_utc
                <sr.forming_candle_started_at_utc+interval '15 minutes'
        then (sr.forming_ema9_15m-0.2*sr.forming_candle_close)/0.8
      end as ema9_15m
    from source_raw sr
  ),
  calc as (
    select
      s.*,
      greatest(
        s.geometry_created_at,
        s.snapshot_created_at_utc,
        s.parent_created_12h,
        s.parent_created_1d
      ) as decision_available_at_utc,
      case when s.direction='LONG' then s.support_15m else s.resistance_15m end
        as research_stop_15m,
      case when s.direction='LONG' then s.resistance_4h else s.support_4h end
        as research_target_4h,
      coalesce((
        (s.direction='LONG'
          and s.parent_direction_12h='BULLISH'
          and s.parent_direction_1d='BULLISH')
        or
        (s.direction='SHORT'
          and s.parent_direction_12h='BEARISH'
          and s.parent_direction_1d='BEARISH')
      ),false) as parent_aligned,
      coalesce((
        (s.direction='LONG' and s.trend_1h='BULLISH')
        or
        (s.direction='SHORT' and s.trend_1h='BEARISH')
      ),false) as timing_1h_aligned,
      (
        (s.direction='LONG'
          and s.candle_15m_close is not null
          and s.ema9_15m is not null
          and s.candle_15m_close>s.ema9_15m)
        or
        (s.direction='SHORT'
          and s.candle_15m_close is not null
          and s.ema9_15m is not null
          and s.candle_15m_close<s.ema9_15m)
      ) as accept_fast_value,
      (
        (s.direction='LONG'
          and s.candle_15m_open is not null
          and s.candle_15m_close is not null
          and s.ema9_15m is not null
          and s.candle_15m_open<=s.ema9_15m
          and s.candle_15m_close>s.ema9_15m)
        or
        (s.direction='SHORT'
          and s.candle_15m_open is not null
          and s.candle_15m_close is not null
          and s.ema9_15m is not null
          and s.candle_15m_open>=s.ema9_15m
          and s.candle_15m_close<s.ema9_15m)
      ) as ema9_reclaim,
      (
        (s.direction='LONG'
          and s.candle_15m_low is not null
          and s.candle_15m_close is not null
          and s.support_15m is not null
          and s.candle_15m_low<=s.support_15m
          and s.candle_15m_close>s.support_15m)
        or
        (s.direction='SHORT'
          and s.candle_15m_high is not null
          and s.candle_15m_close is not null
          and s.resistance_15m is not null
          and s.candle_15m_high>=s.resistance_15m
          and s.candle_15m_close<s.resistance_15m)
      ) as structural_sweep_reclaim
    from source s
  ),
  geometry as (
    select
      c.*,
      extract(epoch from(c.decision_available_at_utc-c.captured_at_utc))
        as source_age_seconds,
      (
        c.decision_available_at_utc-c.captured_at_utc
          <= make_interval(mins=>v_spec.maximum_source_age_minutes)
      ) as source_fresh,
      (
        c.source_scan_price is not null
        and c.source_scan_price>0
        and c.research_stop_15m is not null
        and c.research_target_4h is not null
        and (
          (c.direction='LONG'
            and c.research_stop_15m<c.source_scan_price
            and c.research_target_4h>c.source_scan_price)
          or
          (c.direction='SHORT'
            and c.research_stop_15m>c.source_scan_price
            and c.research_target_4h<c.source_scan_price)
        )
      ) as geometry_valid_at_source,
      case
        when c.source_scan_price is not null
         and c.source_scan_price>0
         and c.research_stop_15m is not null
         and c.research_target_4h is not null
         and abs(c.source_scan_price-c.research_stop_15m)>0
         and (
          (c.direction='LONG'
            and c.research_stop_15m<c.source_scan_price
            and c.research_target_4h>c.source_scan_price)
          or
          (c.direction='SHORT'
            and c.research_stop_15m>c.source_scan_price
            and c.research_target_4h<c.source_scan_price)
         )
        then abs(c.research_target_4h-c.source_scan_price)
          /abs(c.source_scan_price-c.research_stop_15m)
      end as rr_source
    from calc c
  ),
  classified as (
    select
      g.*,
      (
        g.geometry_shadow_only is true
        and g.geometry_trade_permission is false
        and coalesce(g.opportunity_timing='EARLY',false)
        and g.parent_aligned
        and g.timing_1h_aligned
        and g.geometry_valid_at_source
        and g.source_fresh
        and g.trigger_candle_confirmed_closed
        and g.ema9_15m is not null
      ) as h2_context,
      (
        coalesce(g.scanner_direction=g.direction,false)
        and g.geometry_valid_at_source
        and g.source_fresh
      ) as legacy_aligned
    from geometry g
  )
  select
    pg_catalog.md5(
      'h2-direction-architecture-closed-capture-v0.2|'
      ||v_spec.spec_id||'|'||x.diagnostic_id
    ),
    v_spec.spec_id,x.diagnostic_id,x.run_id,x.source_signal_id,
    x.captured_at_utc,x.decision_available_at_utc,
    x.symbol,x.direction,x.scanner_direction,x.opportunity_timing,x.market_phase,
    x.candidate_quality_status,x.liquidity_state,
    x.parent_direction_12h,x.parent_direction_1d,
    x.trend_1h,x.trend_15m,x.trend_4h,
    x.source_scan_price,
    x.candle_15m_open,x.candle_15m_close,x.candle_15m_low,x.candle_15m_high,
    x.ema9_15m,
    x.trigger_candle_started_at_utc,x.trigger_candle_closed_at_utc,
    x.trigger_candle_confirmed_closed,
    'REVERSED_ONE_FORMING_BAR_STANDARD_EMA9',
    x.snapshot_collected_at_utc,x.snapshot_created_at_utc,
    x.support_15m,x.resistance_15m,x.support_4h,x.resistance_4h,
    x.research_stop_15m,x.research_target_4h,x.rr_source,
    x.source_age_seconds,x.source_fresh,
    x.parent_aligned,x.timing_1h_aligned,x.geometry_valid_at_source,
    x.accept_fast_value,x.ema9_reclaim,x.structural_sweep_reclaim,
    x.h2_context,
    (x.h2_context and x.accept_fast_value),
    x.legacy_aligned,
    case when x.rr_source is not null then x.rr_source>=5.0 end,
    case
      when x.geometry_shadow_only is not true
        or x.geometry_trade_permission is not false
        then 'EXCLUDED_SAFETY'
      when x.parent_direction_12h is null or x.parent_direction_1d is null
        then 'EXCLUDED_PARENT_DATA_MISSING'
      when x.source_fresh is not true
        then 'EXCLUDED_SOURCE_STALE_FOR_15M_TRIGGER'
      when x.trigger_candle_confirmed_closed is not true
        or x.ema9_15m is null
        then 'EXCLUDED_CLOSED_15M_TRIGGER_SOURCE_INVALID'
      when x.opportunity_timing is distinct from 'EARLY'
        then 'OBSERVED_NOT_EARLY'
      when x.parent_aligned is not true
        then 'OBSERVED_PARENT_NOT_ALIGNED'
      when x.timing_1h_aligned is not true
        then 'OBSERVED_1H_NOT_ALIGNED'
      when x.geometry_valid_at_source is not true
        then 'OBSERVED_GEOMETRY_INVALID_AT_SOURCE'
      when x.accept_fast_value is not true
        then 'H2_CONTEXT_NO_15M_ACCEPTANCE'
      else 'H2_TRIGGERED'
    end,
    case
      when x.geometry_shadow_only is not true
        or x.geometry_trade_permission is not false
        then 'SAFETY_BOUNDARY'
      when x.parent_direction_12h is null or x.parent_direction_1d is null
        then 'PARENT_DATA_MISSING'
      when x.source_fresh is not true then 'SOURCE_STALE'
      when x.trigger_candle_confirmed_closed is not true
        or x.ema9_15m is null
        then 'CLOSED_15M_TRIGGER_SOURCE_INVALID'
      else null
    end,
    x.geometry_model_version,x.parent_model_12h,x.parent_model_1d,
    pg_catalog.encode(
      extensions.digest(
        jsonb_build_object(
          'diagnostic_id',x.diagnostic_id,
          'run_id',x.run_id,
          'symbol',x.symbol,
          'direction',x.direction,
          'decision_available_at_utc',x.decision_available_at_utc,
          'parent_12h',x.parent_direction_12h,
          'parent_1d',x.parent_direction_1d,
          'trend_1h',x.trend_1h,
          'trend_15m',x.trend_15m,
          'trend_4h',x.trend_4h,
          'trigger_candle_contract','LAST_CLOSED_CANONICAL_EXACT_RUN_SYMBOL',
          'trigger_candle_started_at_utc',x.trigger_candle_started_at_utc,
          'trigger_candle_closed_at_utc',x.trigger_candle_closed_at_utc,
          'trigger_candle_confirmed_closed',x.trigger_candle_confirmed_closed,
          'candle_15m_open',x.candle_15m_open,
          'candle_15m_close',x.candle_15m_close,
          'ema9_15m',x.ema9_15m,
          'ema9_15m_source','REVERSED_ONE_FORMING_BAR_STANDARD_EMA9',
          'source_snapshot_collected_at_utc',x.snapshot_collected_at_utc,
          'source_snapshot_created_at_utc',x.snapshot_created_at_utc,
          'stop_15m',x.research_stop_15m,
          'target_4h',x.research_target_4h,
          'source_scan_price',x.source_scan_price,
          'source_scan_price_is_decision_anchor',false,
          'outcome_evidence_used',false
        )::text,
        'sha256'
      ),
      'hex'
    ),
    false,false,false,false,false,false,true,false,'NONE'
  from classified x
  on conflict(spec_id,diagnostic_id) do nothing;

  get diagnostics v_inserted = row_count;

  for r in
    with recursive
    eligible as (
      select c.*
      from public.alpha_hunter_h2_direction_captures_v02 c
      where c.spec_id=v_spec.spec_id
        and c.h2_triggered=true
    ),
    seed as (
      select distinct on(symbol,direction)
        e.*
      from eligible e
      order by symbol,direction,decision_available_at_utc,capture_id
    ),
    cooldown as (
      select s.*
      from seed s

      union all

      select n.*
      from cooldown p
      join lateral (
        select e.*
        from eligible e
        where e.symbol=p.symbol
          and e.direction=p.direction
          and e.decision_available_at_utc
                >=p.decision_available_at_utc
                  +make_interval(hours=>v_spec.candidate_cooldown_hours)
        order by e.decision_available_at_utc,e.capture_id
        limit 1
      ) n on true
    )
    select c.capture_id,c.symbol,c.decision_available_at_utc
    from cooldown c
    where c.decision_available_at_utc<=clock_timestamp()-interval '2 minutes'
      and not exists (
        select 1
        from public.alpha_hunter_h2_direction_anchor_prices_v02 a
        where a.capture_id=c.capture_id
      )
    order by c.decision_available_at_utc,c.capture_id
    limit 20
  loop
    begin
      v_expected := pg_catalog.to_timestamp(
        ceil(extract(epoch from r.decision_available_at_utc)/60.0)*60.0
      );

      v_url := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=5',
        extensions.urlencode(r.symbol::varchar),
        floor(extract(epoch from(v_expected-interval '1 minute'))*1000)::bigint,
        floor(extract(epoch from(v_expected+interval '3 minutes'))*1000)::bigint
      );

      select (q).status,(q).content
      into v_status,v_content
      from (select extensions.http_get(v_url) q) h;

      if v_status<>200 then
        raise exception 'BITGET_HTTP_STATUS:%',v_status;
      end if;

      v_payload := v_content::jsonb;
      if coalesce(v_payload->>'code','')<>'00000' then
        raise exception 'BITGET_PAYLOAD_CODE:%',v_payload->>'code';
      end if;

      v_candle_at := null;
      v_reference_open := null;

      select
        pg_catalog.to_timestamp((bar->>0)::double precision/1000.0),
        (bar->>1)::double precision
      into v_candle_at,v_reference_open
      from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb)) bar
      where (bar->>0) ~ '^[0-9]+$'
        and (bar->>1)
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        and pg_catalog.to_timestamp((bar->>0)::double precision/1000.0)
              = v_expected
      limit 1;

      if v_candle_at is null or v_reference_open is null or v_reference_open<=0 then
        raise exception 'EXACT_REFERENCE_MINUTE_UNAVAILABLE';
      end if;

      insert into public.alpha_hunter_h2_direction_anchor_prices_v02(
        capture_id,reference_expected_at_utc,reference_candle_at_utc,
        reference_open,measurement_source,source_endpoint,
        exact_expected_minute_required,public_market_data_only,
        reference_price_is_fill_claim,outcome_evidence_used,
        shadow_only,trade_permission
      ) values (
        r.capture_id,v_expected,v_candle_at,v_reference_open,
        'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
        true,true,false,false,true,false
      )
      on conflict(capture_id) do nothing;

      if found then
        v_anchor_inserted := v_anchor_inserted+1;
      end if;

    exception when others then
      v_error := left(sqlerrm,1000);
      v_anchor_failures := v_anchor_failures+1;

      insert into public.alpha_hunter_h2_direction_capture_failures_v02(
        failure_id,spec_id,capture_id,failed_at_utc,
        failure_class,error_message,outcome_evidence_used,
        shadow_only,trade_permission
      ) values (
        pg_catalog.md5(
          'h2-direction-closed-anchor-failure-v0.2|'||r.capture_id||'|'
          ||clock_timestamp()::text
        ),
        v_spec.spec_id,r.capture_id,clock_timestamp(),
        case
          when v_error like 'BITGET_HTTP_STATUS:%' then 'BITGET_HTTP_ERROR'
          when v_error like 'BITGET_PAYLOAD_CODE:%' then 'BITGET_PAYLOAD_ERROR'
          when v_error='EXACT_REFERENCE_MINUTE_UNAVAILABLE'
            then 'EXACT_REFERENCE_MINUTE_UNAVAILABLE'
          else 'ANCHOR_COLLECTOR_ERROR'
        end,
        v_error,false,true,false
      );
    end;
  end loop;

  return jsonb_build_object(
    'spec_id',v_spec.spec_id,
    'mode','H2_CAPTURE_ONLY',
    'capture_rows_inserted',v_inserted,
    'anchor_prices_inserted',v_anchor_inserted,
    'anchor_failure_events',v_anchor_failures,
    'anchor_admission_contract','H2_TRIGGERED_24H_SYMBOL_DIRECTION_INDEPENDENT_ONLY',
    'legacy_only_anchor_admission',false,
    'outcome_evidence_used',false,
    'sealed_outcome_read',false,
    'evaluator_active',false,
    't0_authorized',false,
    'threshold_change_permitted',false,
    'production_promotion_permitted',false,
    'shadow_only',true,
    'trade_permission',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_h2_direction_v02()
  from public,anon,authenticated;


create or replace view public.alpha_hunter_h2_direction_capture_status_v02
with (security_invoker=true,security_barrier=true)
as
with recursive
spec as (
  select *
  from public.alpha_hunter_h2_direction_specs_v02
  where spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
  limit 1
),
eligible as (
  select c.*
  from public.alpha_hunter_h2_direction_captures_v02 c
  where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
    and c.h2_triggered=true
),
seed as (
  select distinct on(symbol,direction)
    e.*
  from eligible e
  order by symbol,direction,decision_available_at_utc,capture_id
),
cooldown as (
  select s.*
  from seed s

  union all

  select n.*
  from cooldown p
  join lateral (
    select e.*
    from eligible e
    where e.symbol=p.symbol
      and e.direction=p.direction
      and e.decision_available_at_utc
            >=p.decision_available_at_utc+interval '24 hours'
    order by e.decision_available_at_utc,e.capture_id
    limit 1
  ) n on true
),
anchored as (
  select c.*,a.reference_open,a.reference_candle_at_utc
  from cooldown c
  join public.alpha_hunter_h2_direction_anchor_prices_v02 a
    on a.capture_id=c.capture_id
),
agg as (
  select
    (select count(*) from public.alpha_hunter_h2_direction_captures_v02 c
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02')
      ::bigint as captured_rows,
    (select count(*) from public.alpha_hunter_h2_direction_captures_v02 c
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
        and c.h2_context_eligible)::bigint as h2_context_rows,
    (select count(*) from public.alpha_hunter_h2_direction_captures_v02 c
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
        and c.h2_triggered)::bigint as h2_triggered_rows,
    (select count(*) from public.alpha_hunter_h2_direction_captures_v02 c
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02'
        and c.legacy_scanner_aligned)::bigint as legacy_aligned_rows,
    (select count(*) from public.alpha_hunter_h2_direction_anchor_prices_v02 a
      join public.alpha_hunter_h2_direction_captures_v02 c
        on c.capture_id=a.capture_id
      where c.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02')
      ::bigint as anchor_prices_resolved,
    (select count(*) from public.alpha_hunter_h2_direction_capture_failures_v02 f
      where f.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CLOSED-CAPTURE-V02')
      ::bigint as capture_or_anchor_failure_events,
    (select count(*) from cooldown)::bigint as independent_h2_candidates,
    (select count(*) from cooldown c
      where not exists (
        select 1 from public.alpha_hunter_h2_direction_anchor_prices_v02 a
        where a.capture_id=c.capture_id
      )
    )::bigint as pending_independent_anchor_rows,
    (select count(*) from anchored)::bigint as independent_h2_anchors,
    (select count(distinct symbol) from anchored)::bigint as independent_symbols,
    (select count(distinct decision_available_at_utc::date) from anchored)
      ::bigint as utc_days,
    (select count(*) from anchored where direction='LONG')::bigint as long_anchors,
    (select count(*) from anchored where direction='SHORT')::bigint as short_anchors,
    (select count(*) from anchored where rr_15m_stop_4h_target>=5.0)
      ::bigint as source_geometry_rr5_anchors
)
select
  s.spec_id,
  s.hypothesis_id,
  s.registered_at_utc,
  s.collection_ends_at_utc,
  s.status,
  a.captured_rows,
  a.h2_context_rows,
  a.h2_triggered_rows,
  a.legacy_aligned_rows,
  a.anchor_prices_resolved,
  a.capture_or_anchor_failure_events,
  a.independent_h2_candidates,
  a.pending_independent_anchor_rows,
  a.independent_h2_anchors,
  100.0*a.independent_h2_anchors/nullif(a.independent_h2_candidates,0)
    as independent_anchor_resolution_pct,
  a.independent_symbols,
  a.utc_days,
  a.long_anchors,
  a.short_anchors,
  a.source_geometry_rr5_anchors,
  (
    a.independent_h2_anchors>=s.minimum_anchor_observations
    and a.independent_symbols>=s.minimum_symbols
    and a.utc_days>=s.minimum_utc_days
    and a.long_anchors>=s.minimum_anchors_per_direction
    and a.short_anchors>=s.minimum_anchors_per_direction
  ) as capture_maturity_gate_met,
  'CAPTURE_ONLY - CLOSED-CANDLE SOURCE CONTRACT - OUTCOMES LOCKED'::text
    as scientific_status,
  'COLLECT NEW V0.2 PROSPECTIVE H2 EVIDENCE; V0.1 DOES NOT COUNT; KEEP OUTCOMES SEALED'::text
    as next_gate,
  false as primary_results_exposed,
  false as outcome_access_permitted,
  false as confirmatory_analysis_permitted,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as independent_replication_required,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from spec s
cross join agg a;

revoke all on public.alpha_hunter_h2_direction_capture_status_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_direction_capture_status_v02
  to service_role;


select private.alpha_hunter_register_h2_direction_v02();


do $$
begin
  if not exists(
    select 1 from cron.job
    where jobname='alpha-hunter-h2-direction-closed-capture-v02'
  ) then
    perform cron.schedule(
      'alpha-hunter-h2-direction-closed-capture-v02',
      '22 */6 * * *',
      'select private.alpha_hunter_capture_h2_direction_v02();'
    );
  end if;
end;
$$;


-- V0.2 is a new forward-only cohort. It does not update/delete/import any v0.1
-- capture, anchor, failure, or status row and it does not unschedule v0.1.
-- Outcome access remains sealed and no trading authority is granted.
