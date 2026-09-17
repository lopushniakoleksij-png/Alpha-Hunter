-- Alpha Hunter geometry diagnostics v0.2
-- Prospective shadow-only observability for early controlled-entry geometry.
-- Adds spread/ATR survivability context without creating execution thresholds,
-- granting T0/READY, changing risk policy, or adding any exchange/order call.

create or replace function private.alpha_hunter_capture_geometry_diagnostics()
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
  order by b.captured_at_utc desc limit 1;

  if v_run_id is null then
    return jsonb_build_object(
      'status','DATA_INSUFFICIENT',
      'blocker','NO_BRIDGE_RUN',
      'model_version','geometry-diagnostics-v0.2-volatility-context',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  with bridge as (
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_money_entry_shadow b
    where b.run_id=v_run_id
    order by b.symbol,b.direction,b.updated_at desc
  ), src as (
    select
      b.*,
      sf.signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) source_payload,
      case when (sf.source_payload->>'support') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload->>'support')::double precision end as support_price,
      case when (sf.source_payload->>'resistance') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload->>'resistance')::double precision end as resistance_price,
      case when (sf.source_payload#>>'{behaviour,spread_pct}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{behaviour,spread_pct}')::double precision end as spread_pct,
      case when (sf.source_payload#>>'{timeframes,15m,indicators,atr_pct}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{timeframes,15m,indicators,atr_pct}')::double precision end as atr_15m_pct,
      case when (sf.source_payload#>>'{timeframes,1H,indicators,atr_pct}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{timeframes,1H,indicators,atr_pct}')::double precision end as atr_1h_pct,
      sf.source_payload#>>'{timeframes,1H,indicators,volume_anomaly,state}' as volume_state_1h,
      sf.source_payload->>'market_phase' as market_phase,
      sf.source_payload->>'opportunity_timing' as opportunity_timing
    from bridge b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
  ), geom as (
    select s.*,
      case when s.direction='LONG' then s.support_price else s.resistance_price end as research_stop,
      case when s.direction='LONG' then s.resistance_price else s.support_price end as research_target
    from src s
  ), calc as (
    select g.*,
      (g.candidate_entry is not null and g.stop_price is not null and g.target_price is not null and g.execution_rr is not null and
       ((g.direction='LONG' and g.stop_price<g.candidate_entry and g.target_price>g.candidate_entry) or
        (g.direction='SHORT' and g.stop_price>g.candidate_entry and g.target_price<g.candidate_entry))) as explicit_complete,
      (g.candidate_entry is not null and g.research_stop is not null and g.research_target is not null and
       ((g.direction='LONG' and g.research_stop<g.candidate_entry and g.research_target>g.candidate_entry) or
        (g.direction='SHORT' and g.research_stop>g.candidate_entry and g.research_target<g.candidate_entry))) as research_recoverable,
      case when g.candidate_entry is not null and g.research_stop is not null and g.research_target is not null and abs(g.candidate_entry-g.research_stop)>0
        then abs(g.research_target-g.candidate_entry)/abs(g.candidate_entry-g.research_stop) end as research_rr_calc,
      case when g.candidate_entry is not null and g.candidate_entry>0 and g.research_stop is not null
        then abs(g.candidate_entry-g.research_stop)/g.candidate_entry*100.0 end as research_stop_distance_pct
    from geom g
  ), metrics as (
    select c.*,
      case when c.research_stop_distance_pct is not null and c.spread_pct is not null and c.spread_pct>0
        then c.research_stop_distance_pct/c.spread_pct end as stop_to_spread_multiple,
      case when c.research_stop_distance_pct is not null and c.atr_15m_pct is not null and c.atr_15m_pct>0
        then c.research_stop_distance_pct/c.atr_15m_pct end as stop_to_atr_15m_multiple,
      case when c.research_stop_distance_pct is not null and c.atr_1h_pct is not null and c.atr_1h_pct>0
        then c.research_stop_distance_pct/c.atr_1h_pct end as stop_to_atr_1h_multiple
    from calc c
  ), ins as (
    insert into public.alpha_hunter_geometry_diagnostics(
      diagnostic_id,run_id,source_signal_id,captured_at_utc,symbol,candidate_direction,scanner_direction,
      explicit_entry,explicit_stop,explicit_target,explicit_rr,support_price,resistance_price,research_stop,research_target,research_rr,
      explicit_geometry_complete,research_geometry_recoverable,classification,evidence,model_version,shadow_only,trade_permission
    )
    select
      md5('geometry-diagnostics-v0.2-volatility-context|'||m.run_id||'|'||m.symbol||'|'||m.direction),
      m.run_id,m.signal_id,m.captured_at_utc,m.symbol,m.direction,m.scanner_direction,
      m.candidate_entry,m.stop_price,m.target_price,m.execution_rr,m.support_price,m.resistance_price,m.research_stop,m.research_target,m.research_rr_calc,
      m.explicit_complete,m.research_recoverable,
      case
        when m.explicit_complete then 'EXPLICIT_EXECUTION_GEOMETRY'
        when m.research_recoverable then 'RESEARCH_SR_GEOMETRY_RECOVERABLE'
        when m.candidate_entry is null then 'ENTRY_MISSING'
        when m.support_price is null or m.resistance_price is null then 'SUPPORT_RESISTANCE_MISSING'
        else 'SUPPORT_RESISTANCE_DIRECTION_INVALID'
      end,
      jsonb_build_object(
        'purpose','prospective geometry coverage and survivability diagnostics only',
        'source_bridge_id',m.bridge_id,
        'source_bridge_status',m.bridge_status,
        'direction_source','BIG_MOVER_SIGNATURE_SHADOW',
        'parent_direction_12h',m.direction_12h,
        'parent_direction_1d',m.direction_1d,
        'liquidity_state',m.liquidity_state,
        'market_phase',m.market_phase,
        'opportunity_timing',m.opportunity_timing,
        'volume_state_1h',m.volume_state_1h,
        'research_stop_distance_pct',m.research_stop_distance_pct,
        'observed_spread_pct',m.spread_pct,
        'observed_atr_15m_pct',m.atr_15m_pct,
        'observed_atr_1h_pct',m.atr_1h_pct,
        'stop_to_spread_multiple',m.stop_to_spread_multiple,
        'stop_to_atr_15m_multiple',m.stop_to_atr_15m_multiple,
        'stop_to_atr_1h_multiple',m.stop_to_atr_1h_multiple,
        'research_rr_is_theoretical',true,
        'volatility_context_is_descriptive_only',true,
        'research_geometry_is_not_execution_permission',true,
        'thresholds_invented',false,
        'stage_eligibility_changed',false
      ),
      'geometry-diagnostics-v0.2-volatility-context',true,false
    from metrics m
    on conflict(diagnostic_id) do nothing
    returning classification
  ) select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(classification,n),'{}'::jsonb) into v_counts
  from (
    select classification,count(*)::integer n
    from public.alpha_hunter_geometry_diagnostics
    where run_id=v_run_id and model_version='geometry-diagnostics-v0.2-volatility-context'
    group by classification
  ) q;

  return jsonb_build_object(
    'status','CAPTURED',
    'run_id',v_run_id,
    'rows_inserted',v_inserted,
    'classification_counts',v_counts,
    'model_version','geometry-diagnostics-v0.2-volatility-context',
    'research_geometry_is_not_execution_permission',true,
    'volatility_context_is_descriptive_only',true,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_geometry_diagnostics() from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_geometry_diagnostics() to service_role;

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
  v_stage jsonb;
begin
  v_geometry := private.alpha_hunter_capture_geometry_diagnostics();
  if coalesce(v_geometry->>'trade_permission','false')<>'false'
     or coalesce(v_geometry->>'shadow_only','true')<>'true' then
    raise exception 'geometry diagnostics safety boundary violated';
  end if;

  v_stage := private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',p_reference_at);

  return jsonb_build_object(
    'mode','MONEY_ENTRY_STAGE_WITH_GEOMETRY_DIAGNOSTICS',
    'geometry',v_geometry,
    'stage',v_stage,
    'stage_eligibility_changed',false,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_run_money_entry_stage_with_geometry(timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_run_money_entry_stage_with_geometry(timestamptz) to service_role;

do $$
declare
  v_job_id bigint;
begin
  select j.jobid into v_job_id
  from cron.job j
  where j.jobname='alpha-hunter-money-entry-stage-hourly'
  limit 1;

  if v_job_id is null then
    raise exception 'alpha-hunter-money-entry-stage-hourly cron job not found';
  end if;

  perform cron.alter_job(
    job_id := v_job_id,
    command := 'select private.alpha_hunter_run_money_entry_stage_with_geometry(clock_timestamp());'
  );
end;
$$;
