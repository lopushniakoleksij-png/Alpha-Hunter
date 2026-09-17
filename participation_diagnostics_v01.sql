-- Alpha Hunter participation diagnostics v0.1
-- Prospective, candidate-level, shadow-only evidence capture.
-- Descriptive evidence only: this migration does NOT define or activate a
-- participation threshold and does NOT grant T0/T1/T2/READY or trade permission.

create table if not exists public.alpha_hunter_participation_diagnostics (
  diagnostic_id text primary key,
  run_id text not null,
  source_bridge_id text,
  source_signal_id text,
  captured_at_utc timestamptz not null,
  symbol text not null,
  candidate_direction text not null check (candidate_direction in ('LONG','SHORT')),
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
  classification text not null,
  evidence jsonb not null default '{}'::jsonb,
  model_version text not null default 'participation-diagnostics-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default now()
);

alter table public.alpha_hunter_participation_diagnostics enable row level security;
revoke all on table public.alpha_hunter_participation_diagnostics from public,anon,authenticated;
grant select,insert on table public.alpha_hunter_participation_diagnostics to service_role;

drop trigger if exists alpha_hunter_participation_diagnostics_append_only on public.alpha_hunter_participation_diagnostics;
create trigger alpha_hunter_participation_diagnostics_append_only
before update or delete on public.alpha_hunter_participation_diagnostics
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_capture_participation_diagnostics()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_run_id text;
  v_inserted integer:=0;
  v_counts jsonb:='{}'::jsonb;
begin
  select b.run_id into v_run_id
  from public.alpha_hunter_big_mover_money_entry_shadow b
  order by b.captured_at_utc desc
  limit 1;

  if v_run_id is null then
    return jsonb_build_object(
      'status','DATA_INSUFFICIENT',
      'blocker','NO_BRIDGE_RUN',
      'model_version','participation-diagnostics-v0.1',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  with bridge as (
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_money_entry_shadow b
    where b.run_id=v_run_id
      and b.research_status='SHADOW_QUEUE'
      and b.lifecycle in('PRE_MOVER','IGNITION','EXPANSION')
    order by b.symbol,b.direction,b.updated_at desc
  ), src as (
    select
      b.*,
      sf.signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) source_payload,
      ul.liquidity_pass,
      private.alpha_hunter_text_bool(sf.source_payload#>>'{execution_setup,checks,participation_confirmed}') scanner_participation_confirmed,
      private.alpha_hunter_text_bool(coalesce(sf.source_payload#>>'{execution_setup,checks,participation_emerging}',sf.source_payload->>'participation_emerging')) scanner_participation_emerging,
      sf.source_payload#>>'{timeframes,15m,indicators,volume_anomaly,state}' volume_state_15m,
      case when (sf.source_payload#>>'{timeframes,15m,indicators,volume_anomaly,ratio}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{timeframes,15m,indicators,volume_anomaly,ratio}')::double precision end volume_ratio_15m,
      sf.source_payload#>>'{timeframes,1H,indicators,volume_anomaly,state}' volume_state_1h,
      case when (sf.source_payload#>>'{timeframes,1H,indicators,volume_anomaly,ratio}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{timeframes,1H,indicators,volume_anomaly,ratio}')::double precision end volume_ratio_1h,
      sf.source_payload#>>'{timeframes,4H,indicators,volume_anomaly,state}' volume_state_4h,
      case when (sf.source_payload#>>'{timeframes,4H,indicators,volume_anomaly,ratio}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{timeframes,4H,indicators,volume_anomaly,ratio}')::double precision end volume_ratio_4h,
      case when (sf.source_payload#>>'{behaviour,volume_ratio}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{behaviour,volume_ratio}')::double precision end behaviour_volume_ratio,
      sf.source_payload->>'market_phase' source_market_phase,
      sf.source_payload->>'opportunity_timing' source_opportunity_timing
    from bridge b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc
      limit 1
    ) sf on true
    left join lateral private.alpha_hunter_stage_universe_liquidity(
      b.symbol,b.run_id,b.captured_at_utc
    ) ul on true
  ), classified as (
    select s.*,
      case
        when s.scanner_participation_confirmed is true then 'SCANNER_PARTICIPATION_CONFIRMED'
        when s.scanner_participation_emerging is true then 'SCANNER_PARTICIPATION_EMERGING'
        when s.volume_state_15m is not null or s.volume_ratio_15m is not null
          or s.volume_state_1h is not null or s.volume_ratio_1h is not null
          or s.volume_state_4h is not null or s.volume_ratio_4h is not null
          or s.behaviour_volume_ratio is not null
          then 'DESCRIPTIVE_VOLUME_EVIDENCE_PRESENT_DECISION_UNDERIVED'
        else 'PARTICIPATION_DATA_ABSENT'
      end classification
    from src s
  ), ins as (
    insert into public.alpha_hunter_participation_diagnostics(
      diagnostic_id,run_id,source_bridge_id,source_signal_id,captured_at_utc,symbol,candidate_direction,
      scanner_participation_confirmed,scanner_participation_emerging,
      volume_state_15m,volume_ratio_15m,volume_state_1h,volume_ratio_1h,volume_state_4h,volume_ratio_4h,
      behaviour_volume_ratio,market_phase,opportunity_timing,liquidity_pass,classification,evidence,model_version,shadow_only,trade_permission
    )
    select
      md5('participation-diagnostics-v0.1|'||c.run_id||'|'||c.symbol||'|'||c.direction),
      c.run_id,c.bridge_id,c.signal_id,c.captured_at_utc,c.symbol,c.direction,
      c.scanner_participation_confirmed,c.scanner_participation_emerging,
      c.volume_state_15m,c.volume_ratio_15m,c.volume_state_1h,c.volume_ratio_1h,c.volume_state_4h,c.volume_ratio_4h,
      c.behaviour_volume_ratio,c.source_market_phase,c.source_opportunity_timing,c.liquidity_pass,c.classification,
      jsonb_build_object(
        'purpose','prospective participation evidence capture only',
        'source_bridge_status',c.bridge_status,
        'source_lifecycle',c.lifecycle,
        'direction_12h',c.direction_12h,
        'direction_1d',c.direction_1d,
        'liquidity_state',c.liquidity_state,
        'participation_threshold_validated',false,
        'participation_decision_derived_by_diagnostics',false,
        'volume_evidence_is_descriptive_only',true,
        'thresholds_invented',false,
        'diagnostics_are_not_execution_permission',true,
        'stage_eligibility_changed',false
      ),
      'participation-diagnostics-v0.1',true,false
    from classified c
    on conflict(diagnostic_id) do nothing
    returning classification
  )
  select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(classification,n),'{}'::jsonb) into v_counts
  from (
    select classification,count(*)::integer n
    from public.alpha_hunter_participation_diagnostics
    where run_id=v_run_id and model_version='participation-diagnostics-v0.1'
    group by classification
  ) q;

  return jsonb_build_object(
    'status','CAPTURED',
    'run_id',v_run_id,
    'rows_inserted',v_inserted,
    'classification_counts',v_counts,
    'model_version','participation-diagnostics-v0.1',
    'participation_threshold_validated',false,
    'diagnostics_are_not_execution_permission',true,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_participation_diagnostics() from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_participation_diagnostics() to service_role;

-- Keep the existing scheduled wrapper name for compatibility; add participation capture
-- before the unchanged controlled MONEY_ENTRY_STAGE invocation.
create or replace function private.alpha_hunter_run_money_entry_stage_with_geometry(
  p_reference_at timestamptz default clock_timestamp()
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_geometry jsonb;
  v_participation jsonb;
  v_stage jsonb;
begin
  v_geometry := private.alpha_hunter_capture_geometry_diagnostics();
  if coalesce(v_geometry->>'trade_permission','false')<>'false'
     or coalesce(v_geometry->>'shadow_only','true')<>'true' then
    raise exception 'geometry diagnostics safety boundary violated';
  end if;

  v_participation := private.alpha_hunter_capture_participation_diagnostics();
  if coalesce(v_participation->>'trade_permission','false')<>'false'
     or coalesce(v_participation->>'shadow_only','true')<>'true' then
    raise exception 'participation diagnostics safety boundary violated';
  end if;

  v_stage := private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',p_reference_at);

  return jsonb_build_object(
    'mode','MONEY_ENTRY_STAGE_WITH_RESEARCH_DIAGNOSTICS',
    'geometry',v_geometry,
    'participation',v_participation,
    'stage',v_stage,
    'stage_eligibility_changed',false,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_run_money_entry_stage_with_geometry(timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_run_money_entry_stage_with_geometry(timestamptz) to service_role;
