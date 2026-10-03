-- Alpha Hunter participation full-universe endpoint cohort v0.2
--
-- Issue #307:
-- Deep-scan symbol snapshots create selection-dependent endpoint missingness.
--
-- Scientific repair:
--   * NEW forward-only cohort/spec; never silently substitute into v0.1;
--   * T0 anchor and endpoint both use public.alpha_hunter_universe_hourly;
--   * source = PRIMARY_SCANNER_CACHED_TICKERS;
--   * measurement_quality = CANONICAL_SCAN_TICKER_SNAPSHOT;
--   * T0 admission requires exact same-run, same-timestamp universe evidence;
--   * endpoint = first canonical universe observation at/after due within 30m;
--   * explicit immutable censoring when the 30m endpoint window is missed;
--   * direction-adjusted endpoint return only;
--   * no stop/target path, threshold, production, or trade authority.
--
-- No historical backfill into this cohort.

create table if not exists private.alpha_hunter_participation_universe_endpoint_specs_v02 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  anchor_source_table text not null
    check(anchor_source_table='public.alpha_hunter_universe_hourly'),
  endpoint_source_table text not null
    check(endpoint_source_table='public.alpha_hunter_universe_hourly'),
  required_source text not null
    check(required_source='PRIMARY_SCANNER_CACHED_TICKERS'),
  required_measurement_quality text not null
    check(required_measurement_quality='CANONICAL_SCAN_TICKER_SNAPSHOT'),
  endpoint_max_lag_minutes integer not null
    check(endpoint_max_lag_minutes=30),
  horizons_hours integer[] not null
    check(horizons_hours=array[1,4,12,24]),
  status text not null check(status in ('COLLECTING','PAUSED','COMPLETE')),
  primary_return_contract text not null
    check(primary_return_contract='UNIVERSE_T0_TO_UNIVERSE_ENDPOINT'),
  scientific_role text not null,
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into private.alpha_hunter_participation_universe_endpoint_specs_v02(
  spec_id,registered_at_utc,anchor_source_table,endpoint_source_table,
  required_source,required_measurement_quality,endpoint_max_lag_minutes,
  horizons_hours,status,primary_return_contract,scientific_role,
  confirmatory_claim_permitted,threshold_derivation_permitted,
  production_promotion_permitted,shadow_only,trade_permission,order_path
) values (
  'PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02',
  clock_timestamp(),
  'public.alpha_hunter_universe_hourly',
  'public.alpha_hunter_universe_hourly',
  'PRIMARY_SCANNER_CACHED_TICKERS',
  'CANONICAL_SCAN_TICKER_SNAPSHOT',
  30,
  array[1,4,12,24],
  'COLLECTING',
  'UNIVERSE_T0_TO_UNIVERSE_ENDPOINT',
  'FORWARD_SOURCE_CONSISTENT_PARTICIPATION_ENDPOINT_MEASUREMENT',
  false,false,false,true,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_participation_universe_endpoint_candidates_v02 (
  candidate_id text primary key,
  spec_id text not null references private.alpha_hunter_participation_universe_endpoint_specs_v02(spec_id),
  diagnostic_id text not null unique,
  source_signal_id text not null,
  source_run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  candidate_direction text not null check(candidate_direction in ('LONG','SHORT')),
  source_signal_direction text,
  source_signal_reference_price double precision,
  anchor_observation_id text not null,
  anchor_selection_run_id text not null,
  anchor_observed_at_utc timestamptz not null,
  anchor_price double precision not null check(anchor_price>0),
  anchor_vs_signal_diff_bps double precision,
  classification text not null,
  scanner_participation_confirmed boolean,
  scanner_participation_emerging boolean,
  volume_state_15m text,
  volume_ratio_15m double precision,
  volume_state_1h text,
  volume_ratio_1h double precision,
  volume_state_4h text,
  volume_ratio_4h double precision,
  behaviour_volume_ratio double precision,
  market_phase text,
  opportunity_timing text,
  liquidity_pass boolean,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_UNIVERSE_ENDPOINT_CANDIDATE',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(anchor_selection_run_id=source_run_id),
  check(anchor_observed_at_utc=captured_at_utc)
);

create index if not exists idx_ah_part_universe_endpoint_candidate_time_v02
  on private.alpha_hunter_participation_universe_endpoint_candidates_v02(
    spec_id,captured_at_utc
  );

create index if not exists idx_ah_part_universe_endpoint_candidate_symbol_v02
  on private.alpha_hunter_participation_universe_endpoint_candidates_v02(
    symbol,captured_at_utc
  );

create table if not exists private.alpha_hunter_participation_universe_endpoint_outcomes_v02 (
  outcome_id text primary key,
  candidate_id text not null
    references private.alpha_hunter_participation_universe_endpoint_candidates_v02(candidate_id),
  spec_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  due_at_utc timestamptz not null,
  endpoint_observation_id text not null,
  endpoint_selection_run_id text not null,
  endpoint_observed_at_utc timestamptz not null,
  endpoint_lag_seconds double precision not null
    check(endpoint_lag_seconds>=0 and endpoint_lag_seconds<=1800),
  endpoint_price double precision not null check(endpoint_price>0),
  raw_return_pct double precision not null,
  direction_adjusted_return_pct double precision not null,
  positive_directional_return boolean not null,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_UNIVERSE_ENDPOINT_OUTCOME',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique(candidate_id,horizon_hours)
);

create index if not exists idx_ah_part_universe_endpoint_outcome_horizon_v02
  on private.alpha_hunter_participation_universe_endpoint_outcomes_v02(
    spec_id,horizon_hours,endpoint_observed_at_utc
  );

create table if not exists private.alpha_hunter_participation_universe_endpoint_failures_v02 (
  failure_id text primary key,
  candidate_id text not null
    references private.alpha_hunter_participation_universe_endpoint_candidates_v02(candidate_id),
  spec_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  due_at_utc timestamptz not null,
  window_closed_at_utc timestamptz not null,
  failure_reason text not null
    check(failure_reason='NO_CANONICAL_UNIVERSE_ENDPOINT_WITHIN_30M'),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_UNIVERSE_ENDPOINT_CENSOR_RECORD',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique(candidate_id,horizon_hours)
);

create index if not exists idx_ah_part_universe_endpoint_failure_horizon_v02
  on private.alpha_hunter_participation_universe_endpoint_failures_v02(
    spec_id,horizon_hours,due_at_utc
  );

create table if not exists private.alpha_hunter_participation_universe_endpoint_runs_v02 (
  run_id text primary key,
  spec_id text not null,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  outcomes_inserted integer not null,
  failures_inserted integer not null,
  candidate_rows_total integer not null,
  outcome_rows_total integer not null,
  failure_rows_total integer not null,
  resolvable_backlog_rows integer not null,
  expired_uncensored_backlog_rows integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_participation_universe_endpoint_forward_v02()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_participation_universe_endpoint_specs_v02%rowtype;
  v_now timestamptz:=clock_timestamp();
  v_candidates_inserted integer:=0;
  v_outcomes_inserted integer:=0;
  v_failures_inserted integer:=0;
  v_candidate_total integer:=0;
  v_outcome_total integer:=0;
  v_failure_total integer:=0;
  v_resolvable_backlog integer:=0;
  v_expired_uncensored_backlog integer:=0;
  v_run_id text;
begin
  if not pg_try_advisory_xact_lock(
    hashtextextended('alpha-hunter-participation-universe-endpoint-v02',0)
  ) then
    return jsonb_build_object(
      'status','RUN_ALREADY_ACTIVE',
      'shadow_only',true,
      'trade_permission',false,
      'production_promotion_permitted',false
    );
  end if;

  select * into v_spec
  from private.alpha_hunter_participation_universe_endpoint_specs_v02
  where spec_id='PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02'
    and status='COLLECTING';

  if v_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  if v_spec.anchor_source_table<>'public.alpha_hunter_universe_hourly'
     or v_spec.endpoint_source_table<>'public.alpha_hunter_universe_hourly'
     or v_spec.required_source<>'PRIMARY_SCANNER_CACHED_TICKERS'
     or v_spec.required_measurement_quality<>'CANONICAL_SCAN_TICKER_SNAPSHOT'
     or v_spec.endpoint_max_lag_minutes<>30
     or v_spec.horizons_hours<>array[1,4,12,24]
     or v_spec.primary_return_contract<>'UNIVERSE_T0_TO_UNIVERSE_ENDPOINT'
  then
    return jsonb_build_object(
      'status','FROZEN_CONTRACT_MISMATCH',
      'shadow_only',true,
      'trade_permission',false,
      'production_promotion_permitted',false
    );
  end if;

  -- Forward-only admission. A candidate is admitted only when an exact
  -- same-run, same-timestamp canonical universe T0 observation exists.
  with inserted as (
    insert into private.alpha_hunter_participation_universe_endpoint_candidates_v02(
      candidate_id,spec_id,diagnostic_id,source_signal_id,source_run_id,
      captured_at_utc,symbol,candidate_direction,source_signal_direction,
      source_signal_reference_price,anchor_observation_id,anchor_selection_run_id,
      anchor_observed_at_utc,anchor_price,anchor_vs_signal_diff_bps,
      classification,scanner_participation_confirmed,scanner_participation_emerging,
      volume_state_15m,volume_ratio_15m,volume_state_1h,volume_ratio_1h,
      volume_state_4h,volume_ratio_4h,behaviour_volume_ratio,market_phase,
      opportunity_timing,liquidity_pass,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-universe-v02-'||md5(v_spec.spec_id||'|'||d.diagnostic_id),
      v_spec.spec_id,
      d.diagnostic_id,
      d.source_signal_id,
      d.run_id,
      d.captured_at_utc,
      d.symbol,
      d.candidate_direction,
      s.direction,
      s.reference_price,
      u.observation_id,
      u.selection_run_id,
      u.observed_at_utc,
      u.last_price,
      case
        when s.reference_price is not null and s.reference_price>0
          then 10000.0*(u.last_price/s.reference_price-1.0)
        else null
      end,
      d.classification,
      d.scanner_participation_confirmed,
      d.scanner_participation_emerging,
      d.volume_state_15m,
      d.volume_ratio_15m,
      d.volume_state_1h,
      d.volume_ratio_1h,
      d.volume_state_4h,
      d.volume_ratio_4h,
      d.behaviour_volume_ratio,
      d.market_phase,
      d.opportunity_timing,
      d.liquidity_pass,
      jsonb_build_object(
        'source_model_version',d.model_version,
        'source_signal_detected_at_utc',s.detected_at_utc,
        'anchor_source','public.alpha_hunter_universe_hourly',
        'anchor_source_name',v_spec.required_source,
        'anchor_measurement_quality',v_spec.required_measurement_quality,
        'anchor_contract','EXACT_SAME_RUN_SAME_TIMESTAMP_UNIVERSE_TICKER',
        'primary_return_contract',v_spec.primary_return_contract,
        'historical_backfill_permitted',false,
        'source_signal_reference_price_is_primary_anchor',false
      ),
      false,false,false,true,false,'NONE'
    from public.alpha_hunter_participation_diagnostics d
    join public.alpha_hunter_signals s
      on s.signal_id=d.source_signal_id
    join public.alpha_hunter_universe_hourly u
      on u.selection_run_id=d.run_id
     and u.symbol=d.symbol
     and u.observed_at_utc=d.captured_at_utc
     and u.source=v_spec.required_source
     and u.measurement_quality=v_spec.required_measurement_quality
     and u.last_price is not null
     and u.last_price>0
    where d.captured_at_utc>=v_spec.registered_at_utc
      and d.candidate_direction in ('LONG','SHORT')
      and (s.direction is null or s.direction=d.candidate_direction)
      and d.shadow_only=true
      and d.trade_permission=false
    on conflict(diagnostic_id) do nothing
    returning 1
  )
  select count(*) into v_candidates_inserted from inserted;

  -- Resolve endpoint evidence first; batching cannot be monopolized by rows
  -- without an admissible endpoint.
  with due as (
    select
      c.candidate_id,c.spec_id,c.symbol,c.candidate_direction,c.anchor_price,
      h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_universe_endpoint_candidates_v02 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)<=v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  ), resolved as (
    select
      d.*,
      u.observation_id as endpoint_observation_id,
      u.selection_run_id as endpoint_selection_run_id,
      u.observed_at_utc as endpoint_observed_at_utc,
      u.last_price as endpoint_price
    from due d
    join lateral (
      select
        uu.observation_id,uu.selection_run_id,uu.observed_at_utc,uu.last_price
      from public.alpha_hunter_universe_hourly uu
      where uu.symbol=d.symbol
        and uu.source=v_spec.required_source
        and uu.measurement_quality=v_spec.required_measurement_quality
        and uu.observed_at_utc>=d.due_at_utc
        and uu.observed_at_utc<=d.due_at_utc
          +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
        and uu.last_price is not null
        and uu.last_price>0
      order by uu.observed_at_utc,uu.observation_id
      limit 1
    ) u on true
    order by d.due_at_utc,d.candidate_id,d.horizon_hours
    limit 2000
  ), inserted as (
    insert into private.alpha_hunter_participation_universe_endpoint_outcomes_v02(
      outcome_id,candidate_id,spec_id,horizon_hours,due_at_utc,
      endpoint_observation_id,endpoint_selection_run_id,endpoint_observed_at_utc,
      endpoint_lag_seconds,endpoint_price,raw_return_pct,
      direction_adjusted_return_pct,positive_directional_return,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-universe-v02-outcome-'||md5(
        r.candidate_id||'|'||r.horizon_hours::text
      ),
      r.candidate_id,
      r.spec_id,
      r.horizon_hours,
      r.due_at_utc,
      r.endpoint_observation_id,
      r.endpoint_selection_run_id,
      r.endpoint_observed_at_utc,
      extract(epoch from(r.endpoint_observed_at_utc-r.due_at_utc)),
      r.endpoint_price,
      100.0*(r.endpoint_price/r.anchor_price-1.0),
      case
        when r.candidate_direction='SHORT'
          then -100.0*(r.endpoint_price/r.anchor_price-1.0)
        else 100.0*(r.endpoint_price/r.anchor_price-1.0)
      end,
      case
        when r.candidate_direction='SHORT'
          then -100.0*(r.endpoint_price/r.anchor_price-1.0)>0
        else 100.0*(r.endpoint_price/r.anchor_price-1.0)>0
      end,
      jsonb_build_object(
        'anchor_source','public.alpha_hunter_universe_hourly',
        'endpoint_source','public.alpha_hunter_universe_hourly',
        'source_name',v_spec.required_source,
        'measurement_quality',v_spec.required_measurement_quality,
        'endpoint_contract','FIRST_CANONICAL_UNIVERSE_TICKER_AT_OR_AFTER_DUE',
        'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
        'primary_return_contract',v_spec.primary_return_contract,
        'source_consistent',true,
        'stop_target_path_claim_permitted',false
      ),
      false,false,false,true,false,'NONE'
    from resolved r
    on conflict(candidate_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_outcomes_inserted from inserted;

  with due_expired as (
    select
      c.candidate_id,c.spec_id,c.symbol,h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
          as window_closed_at_utc
    from private.alpha_hunter_participation_universe_endpoint_candidates_v02 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)<v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from public.alpha_hunter_universe_hourly u
        where u.symbol=c.symbol
          and u.source=v_spec.required_source
          and u.measurement_quality=v_spec.required_measurement_quality
          and u.observed_at_utc>=
            c.captured_at_utc+make_interval(hours=>h.horizon_hours)
          and u.observed_at_utc<=
            c.captured_at_utc+make_interval(hours=>h.horizon_hours)
              +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
          and u.last_price is not null
          and u.last_price>0
      )
    order by due_at_utc,c.candidate_id,h.horizon_hours
    limit 2000
  ), inserted as (
    insert into private.alpha_hunter_participation_universe_endpoint_failures_v02(
      failure_id,candidate_id,spec_id,horizon_hours,due_at_utc,
      window_closed_at_utc,failure_reason,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-universe-v02-failure-'||md5(
        d.candidate_id||'|'||d.horizon_hours::text
      ),
      d.candidate_id,d.spec_id,d.horizon_hours,d.due_at_utc,
      d.window_closed_at_utc,
      'NO_CANONICAL_UNIVERSE_ENDPOINT_WITHIN_30M',
      jsonb_build_object(
        'endpoint_source','public.alpha_hunter_universe_hourly',
        'source_name',v_spec.required_source,
        'measurement_quality',v_spec.required_measurement_quality,
        'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
        'censored',true,
        'endpoint_return_claim_permitted',false,
        'stop_target_path_claim_permitted',false
      ),
      false,false,false,true,false,'NONE'
    from due_expired d
    on conflict(candidate_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_failures_inserted from inserted;

  select count(*) into v_candidate_total
  from private.alpha_hunter_participation_universe_endpoint_candidates_v02
  where spec_id=v_spec.spec_id;

  select count(*) into v_outcome_total
  from private.alpha_hunter_participation_universe_endpoint_outcomes_v02
  where spec_id=v_spec.spec_id;

  select count(*) into v_failure_total
  from private.alpha_hunter_participation_universe_endpoint_failures_v02
  where spec_id=v_spec.spec_id;

  with due as (
    select
      c.candidate_id,c.symbol,h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_universe_endpoint_candidates_v02 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)<=v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  )
  select count(*) into v_resolvable_backlog
  from due d
  where exists (
    select 1
    from public.alpha_hunter_universe_hourly u
    where u.symbol=d.symbol
      and u.source=v_spec.required_source
      and u.measurement_quality=v_spec.required_measurement_quality
      and u.observed_at_utc>=d.due_at_utc
      and u.observed_at_utc<=d.due_at_utc
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
      and u.last_price is not null
      and u.last_price>0
  );

  with due as (
    select
      c.candidate_id,c.symbol,h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_universe_endpoint_candidates_v02 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)<v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_universe_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  )
  select count(*) into v_expired_uncensored_backlog
  from due d
  where not exists (
    select 1
    from public.alpha_hunter_universe_hourly u
    where u.symbol=d.symbol
      and u.source=v_spec.required_source
      and u.measurement_quality=v_spec.required_measurement_quality
      and u.observed_at_utc>=d.due_at_utc
      and u.observed_at_utc<=d.due_at_utc
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
      and u.last_price is not null
      and u.last_price>0
  );

  v_run_id:='part-universe-v02-run-'||md5(v_now::text);

  insert into private.alpha_hunter_participation_universe_endpoint_runs_v02(
    run_id,spec_id,checked_at_utc,candidates_inserted,outcomes_inserted,
    failures_inserted,candidate_rows_total,outcome_rows_total,failure_rows_total,
    resolvable_backlog_rows,expired_uncensored_backlog_rows,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_candidates_inserted,v_outcomes_inserted,
    v_failures_inserted,v_candidate_total,v_outcome_total,v_failure_total,
    v_resolvable_backlog,v_expired_uncensored_backlog,
    jsonb_build_object(
      'model_version','participation-universe-endpoint-forward-v0.2',
      'anchor_contract','EXACT_SAME_RUN_SAME_TIMESTAMP_UNIVERSE_TICKER',
      'endpoint_contract','FIRST_CANONICAL_UNIVERSE_TICKER_AT_OR_AFTER_DUE',
      'source_name',v_spec.required_source,
      'measurement_quality',v_spec.required_measurement_quality,
      'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
      'historical_backfill_permitted',false,
      'threshold_derivation_permitted',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','OK',
    'run_id',v_run_id,
    'candidates_inserted',v_candidates_inserted,
    'outcomes_inserted',v_outcomes_inserted,
    'failures_inserted',v_failures_inserted,
    'candidate_rows_total',v_candidate_total,
    'outcome_rows_total',v_outcome_total,
    'failure_rows_total',v_failure_total,
    'resolvable_backlog_rows',v_resolvable_backlog,
    'expired_uncensored_backlog_rows',v_expired_uncensored_backlog,
    'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
    'shadow_only',true,
    'trade_permission',false,
    'threshold_derivation_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

create or replace view private.alpha_hunter_participation_universe_endpoint_scorecard_v02
with (security_invoker=true,security_barrier=true)
as
with spec as (
  select *
  from private.alpha_hunter_participation_universe_endpoint_specs_v02
  where spec_id='PARTICIPATION-UNIVERSE-ENDPOINT-FORWARD-V02'
), matured as (
  select
    c.candidate_id,c.classification,c.symbol,h.horizon_hours
  from private.alpha_hunter_participation_universe_endpoint_candidates_v02 c
  cross join spec s
  cross join lateral unnest(s.horizons_hours) h(horizon_hours)
  where c.spec_id=s.spec_id
    and c.captured_at_utc+make_interval(hours=>h.horizon_hours)
      +make_interval(mins=>s.endpoint_max_lag_minutes)<=clock_timestamp()
), joined as (
  select
    m.*,
    o.direction_adjusted_return_pct,
    o.positive_directional_return,
    o.endpoint_lag_seconds,
    (o.outcome_id is not null) as has_outcome,
    (f.failure_id is not null) as has_failure
  from matured m
  left join private.alpha_hunter_participation_universe_endpoint_outcomes_v02 o
    on o.candidate_id=m.candidate_id
   and o.horizon_hours=m.horizon_hours
  left join private.alpha_hunter_participation_universe_endpoint_failures_v02 f
    on f.candidate_id=m.candidate_id
   and f.horizon_hours=m.horizon_hours
)
select
  classification,
  horizon_hours,
  count(*) as matured_rows,
  count(*) filter(where has_outcome) as evaluated_rows,
  count(*) filter(where has_failure) as censored_rows,
  count(*) filter(where not has_outcome and not has_failure)
    as pending_materialization_rows,
  count(distinct symbol) as symbols,
  100.0*count(*) filter(where has_outcome)
    /nullif(count(*) filter(where has_outcome or has_failure),0)
      as source_coverage_pct,
  avg(direction_adjusted_return_pct) filter(where has_outcome)
    as avg_direction_adjusted_return_pct,
  percentile_cont(0.5) within group(order by direction_adjusted_return_pct)
    filter(where has_outcome) as median_direction_adjusted_return_pct,
  100.0*count(*) filter(where has_outcome and positive_directional_return)
    /nullif(count(*) filter(where has_outcome),0)
      as positive_directional_pct,
  avg(endpoint_lag_seconds) filter(where has_outcome)
    as avg_endpoint_lag_seconds,
  max(endpoint_lag_seconds) filter(where has_outcome)
    as max_endpoint_lag_seconds,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'FORWARD_SOURCE_CONSISTENT_ENDPOINT_MEASUREMENT_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from joined
group by classification,horizon_hours;

revoke all on private.alpha_hunter_participation_universe_endpoint_specs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_universe_endpoint_candidates_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_universe_endpoint_outcomes_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_universe_endpoint_failures_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_universe_endpoint_runs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_universe_endpoint_scorecard_v02
from public,anon,authenticated,service_role;
revoke all on function private.alpha_hunter_run_participation_universe_endpoint_forward_v02()
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_participation_universe_endpoint_specs_v02
to service_role;
grant select on private.alpha_hunter_participation_universe_endpoint_candidates_v02
to service_role;
grant select on private.alpha_hunter_participation_universe_endpoint_outcomes_v02
to service_role;
grant select on private.alpha_hunter_participation_universe_endpoint_failures_v02
to service_role;
grant select on private.alpha_hunter_participation_universe_endpoint_runs_v02
to service_role;
grant select on private.alpha_hunter_participation_universe_endpoint_scorecard_v02
to service_role;
grant execute on function private.alpha_hunter_run_participation_universe_endpoint_forward_v02()
to postgres;

-- Parallel shadow collector only. It does not replace or unschedule v0.1/v0.2
-- deep-scan-source collectors.
do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-participation-universe-endpoint-v02'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-participation-universe-endpoint-v02',
  '16 * * * *',
  $cmd$
    select private.alpha_hunter_run_participation_universe_endpoint_forward_v02();
  $cmd$
);

-- No v0.1 candidate or outcome row is updated/deleted.
-- No diagnostic before registered_at_utc is admitted.
-- Missing T0 universe evidence fails closed by non-admission.
