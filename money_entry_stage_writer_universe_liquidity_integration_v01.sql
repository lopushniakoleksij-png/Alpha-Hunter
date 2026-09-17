-- Alpha Hunter P0 Money Entry single-writer canonical liquidity integration v0.1
-- Forward-only. No historical mutation/backfill. No thresholds activated or relaxed.
-- Requires the canonical universe ledger. Missing exact evidence stays NULL/fail-closed.

create or replace function private.alpha_hunter_stage_universe_liquidity(
  p_symbol text,
  p_source_run_id text,
  p_source_captured_at_utc timestamptz
)
returns table(
  observation_id text,
  observed_at_utc timestamptz,
  selection_run_id text,
  liquidity_pass boolean
)
language sql
stable
security definer
set search_path = ''
as $$
  select u.observation_id,u.observed_at_utc,u.selection_run_id,u.liquidity_pass
  from public.alpha_hunter_universe_hourly u
  where u.symbol=upper(p_symbol)
    and u.selection_run_id=p_source_run_id
    and u.observed_at_utc<=p_source_captured_at_utc
    and u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)
  order by u.observed_at_utc desc
  limit 1;
$$;
revoke all on function private.alpha_hunter_stage_universe_liquidity(text,text,timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_stage_universe_liquidity(text,text,timestamptz) to service_role;

create or replace function private.alpha_hunter_capture_money_entry_stage_snapshots(p_control_run_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_source_run_id text;
  v_threshold_id text;
  v_threshold_status text := 'NO_ACTIVE_VALIDATED_THRESHOLD_SET';
  v_max_t0_stop double precision;
  v_min_t0_r double precision;
  v_min_t1_r double precision;
  v_min_t2_r double precision;
  v_inserted integer := 0;
  v_status_counts jsonb := '{}'::jsonb;
  v_top_blockers jsonb := '[]'::jsonb;
begin
  if not exists(select 1 from public.alpha_hunter_control_plane_runs r where r.control_run_id=p_control_run_id) then
    raise exception 'control run does not exist: %',p_control_run_id;
  end if;

  select b.run_id into v_source_run_id
  from public.alpha_hunter_big_mover_money_entry_shadow b
  order by b.captured_at_utc desc limit 1;

  if v_source_run_id is null then
    return jsonb_build_object(
      'mode','MONEY_ENTRY_STAGE_SINGLE_WRITER','control_run_id',p_control_run_id,'run_id',null,
      'rows_inserted',0,'status','DATA_INSUFFICIENT','blocker','NO_MONEY_ENTRY_BRIDGE_RUN',
      'shadow_only',true,'trade_permission',false
    );
  end if;

  select t.threshold_set_id,t.status,t.max_t0_stop_distance_pct,t.min_t0_remaining_r,t.min_t1_remaining_r,t.min_t2_remaining_r
  into v_threshold_id,v_threshold_status,v_max_t0_stop,v_min_t0_r,v_min_t1_r,v_min_t2_r
  from public.alpha_hunter_money_entry_threshold_sets t
  where t.status='ACTIVE' and t.validated_at_utc is not null and t.activated_at_utc is not null
  order by t.activated_at_utc desc limit 1;
  if v_threshold_id is null then v_threshold_status := 'NO_ACTIVE_VALIDATED_THRESHOLD_SET'; end if;

  with src as (
    select
      b.*,
      sf.signal_id source_signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) source_payload,
      ul.observation_id universe_observation_id,
      ul.observed_at_utc universe_observed_at_utc,
      ul.selection_run_id universe_selection_run_id,
      ul.liquidity_pass universe_liquidity_pass
    from public.alpha_hunter_big_mover_money_entry_shadow b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
    left join lateral private.alpha_hunter_stage_universe_liquidity(
      b.symbol,b.run_id,b.captured_at_utc
    ) ul on true
    where b.run_id=v_source_run_id
      and b.research_status='SHADOW_QUEUE'
      and b.lifecycle in ('PRE_MOVER','IGNITION','EXPANSION')
  ), normalized as (
    select s.*,
      upper(nullif(s.source_payload#>>'{execution_setup,direction}','')) execution_setup_direction,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,structure_valid}') scanner_structure_valid,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,direction_aligned}') scanner_direction_aligned,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,momentum_confirmed}') scanner_momentum_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,participation_confirmed}') scanner_participation_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,data_integrity_min_88}') scanner_data_integrity_pass,
      s.universe_liquidity_pass liquidity_ok,
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,participation_emerging}',s.source_payload->>'participation_emerging')) participation_emerging,
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,acceptance_confirmed}',s.source_payload->>'acceptance_confirmed')) acceptance_confirmed,
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,trigger_confirmed}',s.source_payload->>'trigger_confirmed')) trigger_confirmed,
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,expansion_confirmed}',s.source_payload->>'expansion_confirmed')) expansion_confirmed,
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,open_position_conflict}',s.source_payload->>'open_position_conflict')) open_position_conflict,
      case when s.candidate_entry is not null and s.candidate_entry>0 and s.stop_price is not null then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0 end stop_distance_pct,
      case
        when s.direction='LONG' and s.candidate_entry is not null and s.stop_price is not null and s.target_price is not null and s.stop_price<s.candidate_entry and s.target_price>s.candidate_entry then true
        when s.direction='SHORT' and s.candidate_entry is not null and s.stop_price is not null and s.target_price is not null and s.stop_price>s.candidate_entry and s.target_price<s.candidate_entry then true
        else false
      end geometry_valid,
      case when s.direction='LONG' then s.direction_12h='BULLISH' when s.direction='SHORT' then s.direction_12h='BEARISH' else false end parent_12h_aligned,
      case when s.direction='LONG' then s.direction_1d='BULLISH' when s.direction='SHORT' then s.direction_1d='BEARISH' else false end parent_1d_aligned
    from src s
  ), evaluated as (
    select n.*,
      (select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
       from unnest(array[
         case when v_threshold_id is null then 'NO_ACTIVE_VALIDATED_THRESHOLD_SET' end,
         case when not n.parent_12h_aligned then case when n.direction_12h is null or n.direction_12h='DATA_UNAVAILABLE' then 'PARENT_12H_DATA_UNAVAILABLE' else 'PARENT_12H_NOT_ALIGNED' end end,
         case when not n.parent_1d_aligned then case when n.direction_1d is null or n.direction_1d='DATA_UNAVAILABLE' then 'PARENT_1D_DATA_UNAVAILABLE' else 'PARENT_1D_NOT_ALIGNED' end end,
         case when n.execution_setup_direction is null then 'SCANNER_EXECUTION_DIRECTION_MISSING' when n.execution_setup_direction<>n.direction then 'SCANNER_EXECUTION_DIRECTION_CONFLICT' end,
         case when n.liquidity_ok is null then 'LIQUIDITY_PASS_NOT_CAPTURED' when n.liquidity_ok is false then 'LIQUIDITY_NOT_VERIFIED' end,
         case when n.scanner_participation_confirmed is true or n.participation_emerging is true then null when n.scanner_participation_confirmed is null and n.participation_emerging is null then 'PARTICIPATION_EMERGING_NOT_CAPTURED' else 'PARTICIPATION_NOT_EMERGING' end,
         case when n.scanner_structure_valid is null then 'STRUCTURAL_INVALIDATION_VALIDITY_NOT_CAPTURED' when n.scanner_structure_valid is false then 'STRUCTURAL_INVALIDATION_NOT_VALID' end,
         case when n.open_position_conflict is null then 'OPEN_POSITION_CONFLICT_NOT_CAPTURED' when n.open_position_conflict is true then 'OPEN_POSITION_CONFLICT' end,
         case when not n.geometry_valid then 'EXECUTION_GEOMETRY_MISSING_OR_DIRECTION_INVALID' end,
         case when n.stop_distance_pct is null then 'STOP_DISTANCE_MISSING' end,
         case when n.execution_rr is null then 'REMAINING_R_MISSING' end,
         case when v_threshold_id is not null and n.stop_distance_pct is not null and n.stop_distance_pct>v_max_t0_stop then 'T0_STOP_GEOMETRY_TOO_WIDE' end
       ]) with ordinality u(x,ord) where x is not null) base_blockers,
      (select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
       from unnest(array[
         case when n.scanner_participation_confirmed is not true then 'T1_PARTICIPATION_NOT_CONFIRMED' end,
         case when n.acceptance_confirmed is null then 'T1_ACCEPTANCE_NOT_CAPTURED' when n.acceptance_confirmed is false then 'T1_ACCEPTANCE_NOT_CONFIRMED' end,
         case when n.trigger_confirmed is null then 'T1_TRIGGER_NOT_CAPTURED' when n.trigger_confirmed is false then 'T1_TRIGGER_NOT_CONFIRMED' end,
         case when n.expansion_confirmed is null then 'T2_EXPANSION_NOT_CAPTURED' when n.expansion_confirmed is false then 'T2_EXPANSION_NOT_CONFIRMED' end
       ]) with ordinality u(x,ord) where x is not null) next_blockers
    from normalized n
  ), staged as (
    select e.*,case
      when v_threshold_id is null then 'DATA_INSUFFICIENT'
      when jsonb_array_length(e.base_blockers)>0 then 'NO_T0'
      when e.scanner_participation_confirmed is true and e.acceptance_confirmed is true and e.trigger_confirmed is true and e.expansion_confirmed is true and e.execution_rr>=v_min_t2_r then 'T2_EXPANSION_CONFIRMED'
      when e.scanner_participation_confirmed is true and e.acceptance_confirmed is true and e.trigger_confirmed is true and e.execution_rr>=v_min_t1_r then 'T1_ACCEPTANCE_CONFIRMED'
      when e.execution_rr>=v_min_t0_r then 'T0_CONTROLLED_ENTRY'
      else 'NO_T0' end exact_stage
    from evaluated e
  ), ins as (
    insert into public.alpha_hunter_money_entry_stage_snapshots(
      stage_snapshot_id,control_run_id,source_run_id,source_bridge_id,source_signal_id,source_captured_at_utc,snapshot_at_utc,symbol,direction,
      stage_status,stage_eligible,threshold_set_id,threshold_status,direction_1h,direction_12h,direction_1d,lifecycle,research_status,bridge_status,
      scanner_state,decision_stage,market_phase,liquidity_state,candidate_entry,stop_price,target_price,stop_distance_pct,remaining_r,
      execution_setup_direction,scanner_structure_valid,scanner_direction_aligned,scanner_momentum_confirmed,scanner_participation_confirmed,
      scanner_data_integrity_pass,liquidity_ok,participation_emerging,acceptance_confirmed,trigger_confirmed,expansion_confirmed,open_position_conflict,
      blockers,next_stage_blockers,evidence,model_version,shadow_only,trade_permission
    )
    select
      md5('money-entry-stage-single-writer-v0.2-liquidity-bound|'||s.bridge_id),
      p_control_run_id,s.run_id,s.bridge_id,s.source_signal_id,s.captured_at_utc,clock_timestamp(),s.symbol,s.direction,
      s.exact_stage,s.exact_stage in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'),
      v_threshold_id,v_threshold_status,s.direction_1h,s.direction_12h,s.direction_1d,s.lifecycle,s.research_status,s.bridge_status,
      s.source_payload->>'state',s.source_payload#>>'{decision_trace,decision_stage}',s.source_payload->>'market_phase',s.liquidity_state,
      s.candidate_entry,s.stop_price,s.target_price,s.stop_distance_pct,s.execution_rr,s.execution_setup_direction,s.scanner_structure_valid,
      s.scanner_direction_aligned,s.scanner_momentum_confirmed,s.scanner_participation_confirmed,s.scanner_data_integrity_pass,s.liquidity_ok,
      s.participation_emerging,s.acceptance_confirmed,s.trigger_confirmed,s.expansion_confirmed,s.open_position_conflict,
      case when s.exact_stage='NO_T0' and v_threshold_id is not null and jsonb_array_length(s.base_blockers)=0 and s.execution_rr is not null and s.execution_rr<v_min_t0_r
        then s.base_blockers||jsonb_build_array('T0_REMAINING_R_TOO_LOW') else s.base_blockers end,
      s.next_blockers,
      jsonb_build_object(
        'source_bridge_model_version',s.model_version,
        'source_bridge_blockers',s.blockers,
        'thresholds_invented',false,
        'threshold_activation_required_for_numeric_stage_gate',v_threshold_id is null,
        'source_execution_checks',coalesce(s.source_payload#>'{execution_setup,checks}','{}'::jsonb),
        'source_execution_reason',s.source_payload#>>'{execution_setup,reason}',
        'source_next_required_condition',s.source_payload#>>'{decision_trace,next_required_condition}',
        'universe_liquidity_binding_source','CANONICAL_UNIVERSE_SAME_RUN_SAME_HOUR_NON_FUTURE',
        'universe_observation_id',s.universe_observation_id,
        'universe_observed_at_utc',s.universe_observed_at_utc,
        'universe_selection_run_id',s.universe_selection_run_id,
        'stable_episode_id_status','NOT_BOUND_TO_STABLE_EPISODE',
        'stage_snapshot_is_contemporaneous',true
      ),
      'money-entry-stage-single-writer-v0.2-liquidity-bound',true,false
    from staged s
    on conflict(source_bridge_id) do nothing
    returning stage_snapshot_id
  ) select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(stage_status,n),'{}'::jsonb) into v_status_counts
  from (select stage_status,count(*)::integer n from public.alpha_hunter_money_entry_stage_snapshots where source_run_id=v_source_run_id group by stage_status) q;

  select coalesce(jsonb_agg(jsonb_build_object('blocker',blocker,'count',n) order by n desc,blocker),'[]'::jsonb) into v_top_blockers
  from (
    select b.value#>>'{}' blocker,count(*)::integer n
    from public.alpha_hunter_money_entry_stage_snapshots s
    cross join lateral jsonb_array_elements(s.blockers) b(value)
    where s.source_run_id=v_source_run_id
    group by b.value order by n desc,b.value limit 12
  ) q;

  return jsonb_build_object(
    'mode','MONEY_ENTRY_STAGE_SINGLE_WRITER',
    'control_run_id',p_control_run_id,
    'run_id',v_source_run_id,
    'rows_inserted',v_inserted,
    'threshold_set_id',v_threshold_id,
    'threshold_status',v_threshold_status,
    'stage_status_counts',v_status_counts,
    'top_blockers',v_top_blockers,
    'universe_liquidity_binding','SAME_RUN_SAME_HOUR_NON_FUTURE',
    'exact_stage_claim_requires_active_validated_thresholds',true,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) to service_role;
