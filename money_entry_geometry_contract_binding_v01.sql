-- Alpha Hunter Money Entry geometry-contract binding v0.1
--
-- Safety objective:
--   Thresholds may never authorize T0/T1/T2 against a geometry construction
--   different from the one they were validated for.
--
-- No numeric threshold is introduced here. Existing stage evidence remains
-- append-only and current exact stages remain fail-closed.

alter table public.alpha_hunter_money_entry_threshold_sets
  add column if not exists geometry_contract_id text;

alter table public.alpha_hunter_money_entry_stage_snapshots
  add column if not exists source_geometry_contract_id text,
  add column if not exists threshold_geometry_contract_id text;

do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid='public.alpha_hunter_money_entry_threshold_sets'::regclass
      and conname='ah_money_entry_threshold_geometry_required'
  ) then
    alter table public.alpha_hunter_money_entry_threshold_sets
      add constraint ah_money_entry_threshold_geometry_required
      check (
        status='DRAFT'
        or geometry_contract_id is not null
      );
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint
    where conrelid='public.alpha_hunter_money_entry_stage_snapshots'::regclass
      and conname='ah_money_entry_exact_stage_geometry_match'
  ) then
    alter table public.alpha_hunter_money_entry_stage_snapshots
      add constraint ah_money_entry_exact_stage_geometry_match
      check (
        stage_status not in (
          'T0_CONTROLLED_ENTRY',
          'T1_ACCEPTANCE_CONFIRMED',
          'T2_EXPANSION_CONFIRMED'
        )
        or (
          source_geometry_contract_id is not null
          and threshold_geometry_contract_id=source_geometry_contract_id
        )
      );
  end if;
end;
$$;

comment on column public.alpha_hunter_money_entry_threshold_sets.geometry_contract_id is
  'Immutable execution-geometry contract against which this threshold set was calibrated. Non-DRAFT sets require a value.';

comment on column public.alpha_hunter_money_entry_stage_snapshots.source_geometry_contract_id is
  'Geometry contract frozen by the contemporaneous Money Entry bridge source.';

comment on column public.alpha_hunter_money_entry_stage_snapshots.threshold_geometry_contract_id is
  'Geometry contract attached to the ACTIVE threshold set used for this stage evaluation.';

create or replace function private.alpha_hunter_run_big_mover_money_entry_bridge()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_run_id text;
  v_captured timestamptz;
  v_upserted integer := 0;
  v_top_long jsonb;
  v_top_short jsonb;
begin
  select b.run_id,max(b.captured_at_utc)
    into v_run_id,v_captured
  from public.alpha_hunter_big_mover_shadow b
  where b.run_id=(
    select b2.run_id
    from public.alpha_hunter_big_mover_shadow b2
    order by b2.captured_at_utc desc,b2.created_at desc limit 1
  )
  group by b.run_id;

  if v_run_id is null then
    raise exception 'no big-mover shadow run available';
  end if;

  with latest_shadow as (
    -- Multiple model versions may coexist for one run; choose one row deterministically.
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_shadow b
    where b.run_id=v_run_id
    order by b.symbol,b.direction,b.created_at desc,b.model_version desc
  ), source_rows as (
    select
      b.run_id,b.captured_at_utc,b.symbol,b.direction,b.similarity_score,b.feature_coverage,
      b.lifecycle,b.research_status,
      coalesce(
        b.raw_change_24h_pct,
        case when (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          then (sf.source_payload->>'change_24h_pct')::double precision end
      ) as raw_change_24h_pct,
      coalesce(b.direction_normalized_move_pct,b.current_move_pct) as direction_normalized_move_pct,
      upper(nullif(sf.direction,'')) as scanner_direction,
      upper(nullif(coalesce(sf.source_payload#>>'{timeframes,1H,trend}',sf.trend_1h),'')) as direction_1h,
      upper(nullif(coalesce(sf.source_payload#>>'{timeframes,4H,trend}',sf.trend_4h),'')) as direction_4h,
      sf.liquidity_state,
      sf.source_payload->>'opportunity_timing' as opportunity_timing,
      sf.source_payload->>'candidate_quality_status' as candidate_quality_status,
      sf.source_payload#>>'{execution_setup,geometry_contract_id}' as geometry_contract_id,
      case when (sf.source_payload#>>'{execution_setup,entry}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,entry}')::double precision end as candidate_entry,
      case when (sf.source_payload#>>'{execution_setup,stop}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,stop}')::double precision end as stop_price,
      case when (sf.source_payload#>>'{execution_setup,target}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,target}')::double precision end as target_price,
      case when (sf.source_payload#>>'{execution_setup,rr}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,rr}')::double precision end as execution_rr,
      coalesce(b.blockers,'[]'::jsonb) as signature_blockers
    from latest_shadow b
    left join lateral (
      select s.*
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
  ), evaluated as (
    select s.*,
      s.signature_blockers
      || case when s.direction_normalized_move_pct<-3 then '["CURRENT_MOVE_OPPOSES_DIRECTION"]'::jsonb else '[]'::jsonb end
      || case when s.scanner_direction is not null and s.scanner_direction<>s.direction then '["SCANNER_DIRECTION_CONFLICT"]'::jsonb else '[]'::jsonb end
      || case when s.liquidity_state is null then '["LIQUIDITY_STATE_MISSING"]'::jsonb else '[]'::jsonb end
      || case when s.candidate_entry is null or s.stop_price is null or s.execution_rr is null then '["EXECUTION_GEOMETRY_MISSING"]'::jsonb else '[]'::jsonb end
      || case when s.research_status<>'SHADOW_QUEUE' then '["NOT_IN_SHADOW_QUEUE"]'::jsonb else '[]'::jsonb end as all_blockers
    from source_rows s
  ), dedup as (
    select e.*,
      (select coalesce(jsonb_agg(distinct value),'[]'::jsonb) from jsonb_array_elements(e.all_blockers)) as blockers_dedup
    from evaluated e
  ), upserted as (
    insert into public.alpha_hunter_big_mover_money_entry_shadow(
      bridge_id,run_id,captured_at_utc,symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,scanner_direction,direction_1h,direction_4h,direction_12h,direction_1d,
      liquidity_state,opportunity_timing,candidate_quality_status,candidate_entry,stop_price,target_price,execution_rr,
      bridge_status,blockers,evidence,model_version,shadow_only,trade_permission,updated_at
    )
    select
      md5('big-mover-money-entry-bridge-v0.1|'||d.run_id||'|'||d.symbol||'|'||d.direction),
      d.run_id,d.captured_at_utc,d.symbol,d.direction,d.similarity_score,d.feature_coverage,d.lifecycle,d.research_status,
      d.raw_change_24h_pct,d.direction_normalized_move_pct,d.scanner_direction,d.direction_1h,d.direction_4h,null,null,
      d.liquidity_state,d.opportunity_timing,d.candidate_quality_status,d.candidate_entry,d.stop_price,d.target_price,d.execution_rr,
      case
        when d.direction_normalized_move_pct<-3 then 'WATCH'
        when jsonb_array_length(d.blockers_dedup)>0 then 'DATA_INSUFFICIENT'
        else 'READY_FOR_MONEY_ENTRY_EVAL'
      end,
      d.blockers_dedup,
      jsonb_build_object(
        'source','BIG_MOVER_SHADOW_PLUS_LIVE_SCANNER',
        'geometry_contract_id',d.geometry_contract_id,
        'thresholds_invented',false,
        't0_authorized',false,
        'trade_permission',false,
        'note','Bridge only. Exact T0/T1/T2 decision remains fail-closed until all Money Entry evidence and validated thresholds are present.'
      ),
      'big-mover-money-entry-bridge-v0.1',true,false,now()
    from dedup d
    on conflict(bridge_id) do update set
      captured_at_utc=excluded.captured_at_utc,
      similarity_score=excluded.similarity_score,
      feature_coverage=excluded.feature_coverage,
      lifecycle=excluded.lifecycle,
      research_status=excluded.research_status,
      raw_change_24h_pct=excluded.raw_change_24h_pct,
      direction_normalized_move_pct=excluded.direction_normalized_move_pct,
      scanner_direction=excluded.scanner_direction,
      direction_1h=excluded.direction_1h,
      direction_4h=excluded.direction_4h,
      direction_12h=null,
      direction_1d=null,
      liquidity_state=excluded.liquidity_state,
      opportunity_timing=excluded.opportunity_timing,
      candidate_quality_status=excluded.candidate_quality_status,
      candidate_entry=excluded.candidate_entry,
      stop_price=excluded.stop_price,
      target_price=excluded.target_price,
      execution_rr=excluded.execution_rr,
      bridge_status=excluded.bridge_status,
      blockers=excluded.blockers,
      evidence=excluded.evidence,
      shadow_only=true,
      trade_permission=false,
      updated_at=now()
    returning 1
  )
  select count(*) into v_upserted from upserted;

  select to_jsonb(x) into v_top_long from (
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='LONG'
    order by similarity_score desc nulls last limit 1
  ) x;

  select to_jsonb(x) into v_top_short from (
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='SHORT'
    order by similarity_score desc nulls last limit 1
  ) x;

  return jsonb_build_object(
    'mode','BIG_MOVER_TO_MONEY_ENTRY_SHADOW_BRIDGE',
    'run_id',v_run_id,'captured_at_utc',v_captured,'rows_upserted',v_upserted,
    'shadow_only',true,'trade_permission',false,'top_long',v_top_long,'top_short',v_top_short
  );
end;
$$;

revoke execute on function private.alpha_hunter_run_big_mover_money_entry_bridge() from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_big_mover_money_entry_bridge() to service_role;

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
  v_source_geometry_contract_id text;
  v_threshold_geometry_contract_id text;
  v_geometry_contract_distinct_count integer := 0;
  v_geometry_contract_missing_count integer := 0;
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

  select
    count(distinct nullif(b.evidence->>'geometry_contract_id','')),
    count(*) filter (
      where nullif(b.evidence->>'geometry_contract_id','') is null
    ),
    min(nullif(b.evidence->>'geometry_contract_id',''))
  into
    v_geometry_contract_distinct_count,
    v_geometry_contract_missing_count,
    v_source_geometry_contract_id
  from public.alpha_hunter_big_mover_money_entry_shadow b
  where b.run_id=v_source_run_id
    and b.research_status='SHADOW_QUEUE'
    and b.lifecycle in ('PRE_MOVER','IGNITION','EXPANSION');

  if v_geometry_contract_missing_count>0
     or v_source_geometry_contract_id is null then
    v_threshold_status := 'SOURCE_GEOMETRY_CONTRACT_MISSING';
  elsif v_geometry_contract_distinct_count<>1 then
    v_threshold_status := 'SOURCE_GEOMETRY_CONTRACT_MIXED';
  else
    select
      t.threshold_set_id,
      t.status,
      t.geometry_contract_id,
      t.max_t0_stop_distance_pct,
      t.min_t0_remaining_r,
      t.min_t1_remaining_r,
      t.min_t2_remaining_r
    into
      v_threshold_id,
      v_threshold_status,
      v_threshold_geometry_contract_id,
      v_max_t0_stop,
      v_min_t0_r,
      v_min_t1_r,
      v_min_t2_r
    from public.alpha_hunter_money_entry_threshold_sets t
    where t.status='ACTIVE' and t.validated_at_utc is not null and t.activated_at_utc is not null
      and t.geometry_contract_id=v_source_geometry_contract_id
    order by t.activated_at_utc desc,t.created_at desc
    limit 1;

    if v_threshold_id is null then
      v_threshold_status := 'NO_ACTIVE_VALIDATED_THRESHOLD_SET_FOR_GEOMETRY';
    end if;
  end if;

  with src as (
    select
      b.*,
      nullif(b.evidence->>'geometry_contract_id','') source_geometry_contract_id,
      sf.signal_id source_signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) source_payload
    from public.alpha_hunter_big_mover_money_entry_shadow b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
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
      private.alpha_hunter_text_bool(coalesce(s.source_payload#>>'{execution_setup,checks,liquidity_ok}',s.source_payload#>>'{execution_setup,checks,liquidity_pass}',s.source_payload->>'liquidity_pass')) liquidity_ok,
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
         case when v_threshold_id is null then v_threshold_status end,
         case
           when n.source_geometry_contract_id is null
             then 'SOURCE_GEOMETRY_CONTRACT_MISSING'
           when v_threshold_id is not null
             and n.source_geometry_contract_id<>v_threshold_geometry_contract_id
             then 'THRESHOLD_GEOMETRY_CONTRACT_MISMATCH'
         end,
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
      stage_status,stage_eligible,threshold_set_id,threshold_status,source_geometry_contract_id,threshold_geometry_contract_id,
      direction_1h,direction_12h,direction_1d,lifecycle,research_status,bridge_status,
      scanner_state,decision_stage,market_phase,liquidity_state,candidate_entry,stop_price,target_price,stop_distance_pct,remaining_r,
      execution_setup_direction,scanner_structure_valid,scanner_direction_aligned,scanner_momentum_confirmed,scanner_participation_confirmed,
      scanner_data_integrity_pass,liquidity_ok,participation_emerging,acceptance_confirmed,trigger_confirmed,expansion_confirmed,open_position_conflict,
      blockers,next_stage_blockers,evidence,model_version,shadow_only,trade_permission
    )
    select md5('money-entry-stage-single-writer-v0.1|'||s.bridge_id),p_control_run_id,s.run_id,s.bridge_id,s.source_signal_id,s.captured_at_utc,
      clock_timestamp(),s.symbol,s.direction,s.exact_stage,s.exact_stage in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'),
      v_threshold_id,v_threshold_status,s.source_geometry_contract_id,v_threshold_geometry_contract_id,
      s.direction_1h,s.direction_12h,s.direction_1d,s.lifecycle,s.research_status,s.bridge_status,
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
        'source_geometry_contract_id',s.source_geometry_contract_id,
        'threshold_geometry_contract_id',v_threshold_geometry_contract_id,
        'geometry_contract_match',
          (
            v_threshold_id is not null
            and s.source_geometry_contract_id is not null
            and s.source_geometry_contract_id=v_threshold_geometry_contract_id
          ),
        'thresholds_invented',false,
        'threshold_activation_required_for_numeric_stage_gate',v_threshold_id is null,
        'source_execution_checks',coalesce(s.source_payload#>'{execution_setup,checks}','{}'::jsonb),
        'source_execution_reason',s.source_payload#>>'{execution_setup,reason}',
        'source_next_required_condition',s.source_payload#>>'{decision_trace,next_required_condition}',
        'stable_episode_id_status','NOT_BOUND_TO_STABLE_EPISODE','stage_snapshot_is_contemporaneous',true
      ),'money-entry-stage-single-writer-v0.1',true,false
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
    'mode','MONEY_ENTRY_STAGE_SINGLE_WRITER','control_run_id',p_control_run_id,'run_id',v_source_run_id,'rows_inserted',v_inserted,
    'threshold_set_id',v_threshold_id,
    'threshold_status',v_threshold_status,
    'source_geometry_contract_id',v_source_geometry_contract_id,
    'threshold_geometry_contract_id',v_threshold_geometry_contract_id,
    'stage_status_counts',v_status_counts,'top_blockers',v_top_blockers,
    'exact_stage_claim_requires_active_validated_thresholds',true,'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) to service_role;
