-- Alpha Hunter Money Entry immutable stage single writer v0.1
--
-- This migration deliberately does NOT activate numeric T0/T1/T2 thresholds.
-- It begins contemporaneous immutable evidence capture, exposes the exact
-- missing fields that prevent stage assignment, expands the cloud control
-- plane to include MONEY_ENTRY_STAGE at :13, and links future scorecard
-- candidate snapshots to the exact stage record.
--
-- Safety invariants:
--   shadow_only=true
--   trade_permission=false
--   no order path
--   no threshold invention
--   no hindsight mutation

create table if not exists public.alpha_hunter_money_entry_threshold_sets (
  threshold_set_id text primary key,
  status text not null check (status in ('DRAFT','VALIDATED','ACTIVE','RETIRED')),
  max_t0_stop_distance_pct double precision,
  min_t0_remaining_r double precision,
  min_t1_remaining_r double precision,
  min_t2_remaining_r double precision,
  evidence_reference jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence_reference)='object'),
  validated_at_utc timestamptz,
  activated_at_utc timestamptz,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  check (
    status='DRAFT'
    or (
      max_t0_stop_distance_pct is not null and max_t0_stop_distance_pct > 0
      and min_t0_remaining_r is not null and min_t0_remaining_r > 0
      and min_t1_remaining_r is not null and min_t1_remaining_r > 0
      and min_t2_remaining_r is not null and min_t2_remaining_r > 0
    )
  ),
  check (
    status<>'ACTIVE'
    or (
      validated_at_utc is not null
      and activated_at_utc is not null
      and evidence_reference <> '{}'::jsonb
    )
  )
);

create unique index if not exists uq_ah_money_entry_one_active_threshold_set
  on public.alpha_hunter_money_entry_threshold_sets((status))
  where status='ACTIVE';

create table if not exists public.alpha_hunter_money_entry_stage_snapshots (
  stage_snapshot_id text primary key,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  source_run_id text not null,
  source_bridge_id text not null unique,
  source_signal_id text,
  source_captured_at_utc timestamptz not null,
  snapshot_at_utc timestamptz not null default clock_timestamp(),
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  stage_status text not null check (stage_status in (
    'DATA_INSUFFICIENT','NO_T0','T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'
  )),
  stage_eligible boolean not null default false,
  threshold_set_id text references public.alpha_hunter_money_entry_threshold_sets(threshold_set_id),
  threshold_status text not null,
  direction_1h text,
  direction_12h text,
  direction_1d text,
  lifecycle text,
  research_status text,
  bridge_status text,
  scanner_state text,
  decision_stage text,
  market_phase text,
  liquidity_state text,
  candidate_entry double precision,
  stop_price double precision,
  target_price double precision,
  stop_distance_pct double precision,
  remaining_r double precision,
  execution_setup_direction text,
  scanner_structure_valid boolean,
  scanner_direction_aligned boolean,
  scanner_momentum_confirmed boolean,
  scanner_participation_confirmed boolean,
  scanner_data_integrity_pass boolean,
  liquidity_ok boolean,
  participation_emerging boolean,
  acceptance_confirmed boolean,
  trigger_confirmed boolean,
  expansion_confirmed boolean,
  open_position_conflict boolean,
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  next_stage_blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(next_stage_blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'money-entry-stage-single-writer-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  check (
    (stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED') and stage_eligible=true)
    or
    (stage_status in ('DATA_INSUFFICIENT','NO_T0') and stage_eligible=false)
  )
);

create index if not exists idx_ah_money_entry_stage_run_time
  on public.alpha_hunter_money_entry_stage_snapshots(source_run_id,snapshot_at_utc desc);
create index if not exists idx_ah_money_entry_stage_symbol_time
  on public.alpha_hunter_money_entry_stage_snapshots(symbol,direction,snapshot_at_utc desc);
create index if not exists idx_ah_money_entry_stage_status_time
  on public.alpha_hunter_money_entry_stage_snapshots(stage_status,snapshot_at_utc desc);

alter table public.alpha_hunter_money_entry_threshold_sets enable row level security;
alter table public.alpha_hunter_money_entry_stage_snapshots enable row level security;
revoke all on table public.alpha_hunter_money_entry_threshold_sets from public,anon,authenticated;
revoke all on table public.alpha_hunter_money_entry_stage_snapshots from public,anon,authenticated;
grant select,insert on table public.alpha_hunter_money_entry_threshold_sets to service_role;
grant select,insert on table public.alpha_hunter_money_entry_stage_snapshots to service_role;

drop trigger if exists trg_ah_money_entry_threshold_sets_append_only on public.alpha_hunter_money_entry_threshold_sets;
create trigger trg_ah_money_entry_threshold_sets_append_only
before update or delete on public.alpha_hunter_money_entry_threshold_sets
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_money_entry_stage_snapshots_append_only on public.alpha_hunter_money_entry_stage_snapshots;
create trigger trg_ah_money_entry_stage_snapshots_append_only
before update or delete on public.alpha_hunter_money_entry_stage_snapshots
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_text_bool(p_value text)
returns boolean
language sql
immutable
security invoker
set search_path=''
as $$
  select case lower(trim(p_value))
    when 'true' then true
    when 'false' then false
    when '1' then true
    when '0' then false
    else null
  end;
$$;
revoke all on function private.alpha_hunter_text_bool(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_text_bool(text) to service_role;

create or replace function private.alpha_hunter_capture_money_entry_stage_snapshots(p_control_run_id text)
returns jsonb
language plpgsql
security definer
set search_path=''
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
  if not exists(
    select 1 from public.alpha_hunter_control_plane_runs r
    where r.control_run_id=p_control_run_id
  ) then
    raise exception 'control run does not exist: %',p_control_run_id;
  end if;

  select b.run_id into v_source_run_id
  from public.alpha_hunter_big_mover_money_entry_shadow b
  order by b.captured_at_utc desc
  limit 1;

  if v_source_run_id is null then
    return jsonb_build_object(
      'mode','MONEY_ENTRY_STAGE_SINGLE_WRITER','control_run_id',p_control_run_id,
      'run_id',null,'rows_inserted',0,'status','DATA_INSUFFICIENT',
      'blocker','NO_MONEY_ENTRY_BRIDGE_RUN','shadow_only',true,'trade_permission',false
    );
  end if;

  select t.threshold_set_id,t.status,t.max_t0_stop_distance_pct,t.min_t0_remaining_r,t.min_t1_remaining_r,t.min_t2_remaining_r
  into v_threshold_id,v_threshold_status,v_max_t0_stop,v_min_t0_r,v_min_t1_r,v_min_t2_r
  from public.alpha_hunter_money_entry_threshold_sets t
  where t.status='ACTIVE' and t.validated_at_utc is not null and t.activated_at_utc is not null
  order by t.activated_at_utc desc
  limit 1;

  if v_threshold_id is null then
    v_threshold_status := 'NO_ACTIVE_VALIDATED_THRESHOLD_SET';
  end if;

  with src as (
    select
      b.*,
      sf.signal_id as source_signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) as source_payload
    from public.alpha_hunter_big_mover_money_entry_shadow b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc
      limit 1
    ) sf on true
    where b.run_id=v_source_run_id
      and b.research_status='SHADOW_QUEUE'
      and b.lifecycle in ('PRE_MOVER','IGNITION','EXPANSION')
  ), normalized as (
    select
      s.*,
      upper(nullif(s.source_payload#>>'{execution_setup,direction}','')) as execution_setup_direction,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,structure_valid}') as scanner_structure_valid,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,direction_aligned}') as scanner_direction_aligned,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,momentum_confirmed}') as scanner_momentum_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,participation_confirmed}') as scanner_participation_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,data_integrity_min_88}') as scanner_data_integrity_pass,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,liquidity_ok}',
        s.source_payload#>>'{execution_setup,checks,liquidity_pass}',
        s.source_payload->>'liquidity_pass'
      )) as liquidity_ok,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,participation_emerging}',
        s.source_payload->>'participation_emerging'
      )) as participation_emerging,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,acceptance_confirmed}',
        s.source_payload->>'acceptance_confirmed'
      )) as acceptance_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,trigger_confirmed}',
        s.source_payload->>'trigger_confirmed'
      )) as trigger_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,expansion_confirmed}',
        s.source_payload->>'expansion_confirmed'
      )) as expansion_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,open_position_conflict}',
        s.source_payload->>'open_position_conflict'
      )) as open_position_conflict,
      case
        when s.candidate_entry is not null and s.candidate_entry>0 and s.stop_price is not null
          then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0
        else null
      end as stop_distance_pct,
      case
        when s.direction='LONG' and s.candidate_entry is not null and s.stop_price is not null and s.target_price is not null
          and s.stop_price<s.candidate_entry and s.target_price>s.candidate_entry then true
        when s.direction='SHORT' and s.candidate_entry is not null and s.stop_price is not null and s.target_price is not null
          and s.stop_price>s.candidate_entry and s.target_price<s.candidate_entry then true
        else false
      end as geometry_valid,
      case
        when s.direction='LONG' then s.direction_12h='BULLISH'
        when s.direction='SHORT' then s.direction_12h='BEARISH'
        else false
      end as parent_12h_aligned,
      case
        when s.direction='LONG' then s.direction_1d='BULLISH'
        when s.direction='SHORT' then s.direction_1d='BEARISH'
        else false
      end as parent_1d_aligned
    from src s
  ), evaluated as (
    select
      n.*,
      (
        select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
        from unnest(array[
          case when v_threshold_id is null then 'NO_ACTIVE_VALIDATED_THRESHOLD_SET' end,
          case when not n.parent_12h_aligned then case when n.direction_12h is null or n.direction_12h='DATA_UNAVAILABLE' then 'PARENT_12H_DATA_UNAVAILABLE' else 'PARENT_12H_NOT_ALIGNED' end end,
          case when not n.parent_1d_aligned then case when n.direction_1d is null or n.direction_1d='DATA_UNAVAILABLE' then 'PARENT_1D_DATA_UNAVAILABLE' else 'PARENT_1D_NOT_ALIGNED' end end,
          case when n.execution_setup_direction is null then 'SCANNER_EXECUTION_DIRECTION_MISSING' when n.execution_setup_direction<>n.direction then 'SCANNER_EXECUTION_DIRECTION_CONFLICT' end,
          case when n.liquidity_ok is null then 'LIQUIDITY_PASS_NOT_CAPTURED' when n.liquidity_ok is false then 'LIQUIDITY_NOT_VERIFIED' end,
          case
            when n.scanner_participation_confirmed is true or n.participation_emerging is true then null
            when n.scanner_participation_confirmed is null and n.participation_emerging is null then 'PARTICIPATION_EMERGING_NOT_CAPTURED'
            else 'PARTICIPATION_NOT_EMERGING'
          end,
          case when n.scanner_structure_valid is null then 'STRUCTURAL_INVALIDATION_VALIDITY_NOT_CAPTURED' when n.scanner_structure_valid is false then 'STRUCTURAL_INVALIDATION_NOT_VALID' end,
          case when n.open_position_conflict is null then 'OPEN_POSITION_CONFLICT_NOT_CAPTURED' when n.open_position_conflict is true then 'OPEN_POSITION_CONFLICT' end,
          case when not n.geometry_valid then 'EXECUTION_GEOMETRY_MISSING_OR_DIRECTION_INVALID' end,
          case when n.stop_distance_pct is null then 'STOP_DISTANCE_MISSING' end,
          case when n.execution_rr is null then 'REMAINING_R_MISSING' end,
          case when v_threshold_id is not null and n.stop_distance_pct is not null and n.stop_distance_pct>v_max_t0_stop then 'T0_STOP_GEOMETRY_TOO_WIDE' end
        ]) with ordinality u(x,ord)
        where x is not null
      ) as base_blockers,
      (
        select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
        from unnest(array[
          case when n.scanner_participation_confirmed is not true then 'T1_PARTICIPATION_NOT_CONFIRMED' end,
          case when n.acceptance_confirmed is null then 'T1_ACCEPTANCE_NOT_CAPTURED' when n.acceptance_confirmed is false then 'T1_ACCEPTANCE_NOT_CONFIRMED' end,
          case when n.trigger_confirmed is null then 'T1_TRIGGER_NOT_CAPTURED' when n.trigger_confirmed is false then 'T1_TRIGGER_NOT_CONFIRMED' end,
          case when n.expansion_confirmed is null then 'T2_EXPANSION_NOT_CAPTURED' when n.expansion_confirmed is false then 'T2_EXPANSION_NOT_CONFIRMED' end
        ]) with ordinality u(x,ord)
        where x is not null
      ) as next_blockers
    from normalized n
  ), staged as (
    select
      e.*,
      case
        when v_threshold_id is null then 'DATA_INSUFFICIENT'
        when jsonb_array_length(e.base_blockers)>0 then 'NO_T0'
        when e.scanner_participation_confirmed is true and e.acceptance_confirmed is true and e.trigger_confirmed is true
          and e.expansion_confirmed is true and e.execution_rr>=v_min_t2_r then 'T2_EXPANSION_CONFIRMED'
        when e.scanner_participation_confirmed is true and e.acceptance_confirmed is true and e.trigger_confirmed is true
          and e.execution_rr>=v_min_t1_r then 'T1_ACCEPTANCE_CONFIRMED'
        when e.execution_rr>=v_min_t0_r then 'T0_CONTROLLED_ENTRY'
        else 'NO_T0'
      end as exact_stage
    from evaluated e
  ), ins as (
    insert into public.alpha_hunter_money_entry_stage_snapshots(
      stage_snapshot_id,control_run_id,source_run_id,source_bridge_id,source_signal_id,
      source_captured_at_utc,snapshot_at_utc,symbol,direction,stage_status,stage_eligible,
      threshold_set_id,threshold_status,direction_1h,direction_12h,direction_1d,lifecycle,research_status,bridge_status,
      scanner_state,decision_stage,market_phase,liquidity_state,
      candidate_entry,stop_price,target_price,stop_distance_pct,remaining_r,execution_setup_direction,
      scanner_structure_valid,scanner_direction_aligned,scanner_momentum_confirmed,scanner_participation_confirmed,
      scanner_data_integrity_pass,liquidity_ok,participation_emerging,acceptance_confirmed,trigger_confirmed,
      expansion_confirmed,open_position_conflict,blockers,next_stage_blockers,evidence,model_version,shadow_only,trade_permission
    )
    select
      md5('money-entry-stage-single-writer-v0.1|'||s.bridge_id),
      p_control_run_id,s.run_id,s.bridge_id,s.source_signal_id,s.captured_at_utc,clock_timestamp(),s.symbol,s.direction,
      s.exact_stage,s.exact_stage in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'),
      v_threshold_id,v_threshold_status,s.direction_1h,s.direction_12h,s.direction_1d,s.lifecycle,s.research_status,s.bridge_status,
      s.source_payload->>'state',s.source_payload#>>'{decision_trace,decision_stage}',s.source_payload->>'market_phase',s.liquidity_state,
      s.candidate_entry,s.stop_price,s.target_price,s.stop_distance_pct,s.execution_rr,s.execution_setup_direction,
      s.scanner_structure_valid,s.scanner_direction_aligned,s.scanner_momentum_confirmed,s.scanner_participation_confirmed,
      s.scanner_data_integrity_pass,s.liquidity_ok,s.participation_emerging,s.acceptance_confirmed,s.trigger_confirmed,
      s.expansion_confirmed,s.open_position_conflict,
      case
        when s.exact_stage='NO_T0' and v_threshold_id is not null and jsonb_array_length(s.base_blockers)=0 and s.execution_rr is not null and s.execution_rr<v_min_t0_r
          then s.base_blockers||jsonb_build_array('T0_REMAINING_R_TOO_LOW')
        else s.base_blockers
      end,
      s.next_blockers,
      jsonb_build_object(
        'source_bridge_model_version',s.model_version,
        'source_bridge_blockers',s.blockers,
        'thresholds_invented',false,
        'threshold_activation_required_for_numeric_stage_gate',v_threshold_id is null,
        'source_execution_checks',coalesce(s.source_payload#>'{execution_setup,checks}','{}'::jsonb),
        'source_execution_reason',s.source_payload#>>'{execution_setup,reason}',
        'source_next_required_condition',s.source_payload#>>'{decision_trace,next_required_condition}',
        'stable_episode_id_status','NOT_BOUND_TO_STABLE_EPISODE',
        'stage_snapshot_is_contemporaneous',true
      ),
      'money-entry-stage-single-writer-v0.1',true,false
    from staged s
    on conflict(source_bridge_id) do nothing
    returning stage_snapshot_id
  )
  select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(stage_status,n),'{}'::jsonb)
  into v_status_counts
  from (
    select stage_status,count(*)::integer n
    from public.alpha_hunter_money_entry_stage_snapshots
    where source_run_id=v_source_run_id
    group by stage_status
  ) q;

  select coalesce(jsonb_agg(jsonb_build_object('blocker',blocker,'count',n) order by n desc,blocker),'[]'::jsonb)
  into v_top_blockers
  from (
    select b.value #>> '{}' as blocker,count(*)::integer n
    from public.alpha_hunter_money_entry_stage_snapshots s
    cross join lateral jsonb_array_elements(s.blockers) b(value)
    where s.source_run_id=v_source_run_id
    group by b.value
    order by n desc,b.value
    limit 12
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
    'exact_stage_claim_requires_active_validated_thresholds',true,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) to service_role;

-- Link future scorecard candidate snapshots to the exact stage snapshot.
alter table public.alpha_hunter_big_mover_money_scorecard_candidates
  add column if not exists money_entry_stage_snapshot_id text references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id);

create or replace function private.alpha_hunter_seed_big_mover_money_scorecard()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_candidates integer := 0;
  v_outcomes integer := 0;
begin
  with src as (
    select
      b.*,
      ms.stage_snapshot_id,
      ms.stage_status as exact_stage_status,
      ms.blockers as exact_stage_blockers,
      ms.next_stage_blockers as exact_next_stage_blockers,
      case
        when b.direction='LONG' and b.candidate_entry is not null and b.stop_price is not null and b.target_price is not null
          and b.stop_price < b.candidate_entry and b.target_price > b.candidate_entry then true
        when b.direction='SHORT' and b.candidate_entry is not null and b.stop_price is not null and b.target_price is not null
          and b.stop_price > b.candidate_entry and b.target_price < b.candidate_entry then true
        else false
      end as geometry_ok
    from public.alpha_hunter_big_mover_money_entry_shadow b
    left join public.alpha_hunter_money_entry_stage_snapshots ms on ms.source_bridge_id=b.bridge_id
    where b.research_status='SHADOW_QUEUE'
      and b.lifecycle in ('PRE_MOVER','IGNITION')
  ), ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_candidates(
      scorecard_id,source_bridge_id,run_id,candidate_at_utc,symbol,direction,
      candidate_entry,stop_price,target_price,geometry_valid,risk_distance_abs,risk_distance_pct,initial_remaining_r,
      similarity_score,feature_coverage,lifecycle,research_status,bridge_status,
      raw_change_24h_pct,direction_normalized_move_pct,scanner_direction,
      direction_1h,direction_4h,direction_12h,direction_1d,liquidity_state,opportunity_timing,candidate_quality_status,
      bridge_blockers,frozen_evidence,stage_snapshot_status,t0_snapshot_available,t1_snapshot_available,t2_snapshot_available,
      money_entry_stage_snapshot_id,model_version,shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-v0.1|'||s.bridge_id),
      s.bridge_id,s.run_id,s.captured_at_utc,s.symbol,s.direction,
      s.candidate_entry,s.stop_price,s.target_price,s.geometry_ok,
      case when s.geometry_ok then abs(s.candidate_entry-s.stop_price) end,
      case when s.geometry_ok and s.candidate_entry<>0 then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0 end,
      case when s.geometry_ok and abs(s.candidate_entry-s.stop_price)>0
        then abs(s.target_price-s.candidate_entry)/abs(s.candidate_entry-s.stop_price) end,
      s.similarity_score,s.feature_coverage,s.lifecycle,s.research_status,s.bridge_status,
      s.raw_change_24h_pct,s.direction_normalized_move_pct,s.scanner_direction,
      s.direction_1h,s.direction_4h,s.direction_12h,s.direction_1d,s.liquidity_state,s.opportunity_timing,s.candidate_quality_status,
      s.blockers,
      coalesce(s.evidence,'{}'::jsonb) || jsonb_build_object(
        'frozen_from_bridge_at_utc',clock_timestamp(),
        'source_bridge_model_version',s.model_version,
        'geometry_valid_for_signature_direction',s.geometry_ok,
        'money_entry_stage_snapshot_id',s.stage_snapshot_id,
        'money_entry_stage_blockers',coalesce(s.exact_stage_blockers,'[]'::jsonb),
        'money_entry_next_stage_blockers',coalesce(s.exact_next_stage_blockers,'[]'::jsonb),
        'exact_stage_claim_permitted',s.exact_stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED')
      ),
      coalesce(s.exact_stage_status,'EXACT_T0_T1_T2_NOT_CAPTURED'),
      s.exact_stage_status='T0_CONTROLLED_ENTRY',
      s.exact_stage_status='T1_ACCEPTANCE_CONFIRMED',
      s.exact_stage_status='T2_EXPANSION_CONFIRMED',
      s.stage_snapshot_id,
      'big-mover-money-scorecard-v0.2-stage-linked',true,false
    from src s
    on conflict(source_bridge_id) do nothing
    returning 1
  ) select count(*) into v_candidates from ins;

  with ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_outcomes(
      outcome_id,scorecard_id,horizon_hours,horizon_due_at_utc,
      evaluation_status,realistic_net_r_status,confirmation_tax_status,
      t0_path_result,t1_path_result,t2_path_result,stage_outcome_status,
      evidence,shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-outcome-v0.1|'||c.scorecard_id||'|'||h.h::text),
      c.scorecard_id,h.h,c.candidate_at_utc + make_interval(hours=>h.h),
      'PENDING','UNVERIFIED_EXECUTION_COST_MODEL','NOT_LINKED',
      'NOT_EVALUABLE','NOT_EVALUABLE','NOT_EVALUABLE',
      case when c.money_entry_stage_snapshot_id is not null then 'EXACT_STAGE_SNAPSHOT_LINKED_PENDING_OUTCOME' else 'EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE' end,
      jsonb_build_object(
        'measurement_source','BITGET_PUBLIC_V3_3M_CANDLES',
        'money_entry_stage_snapshot_id',c.money_entry_stage_snapshot_id,
        'stage_snapshot_status',c.stage_snapshot_status,
        'exact_stage_claim_permitted',c.money_entry_stage_snapshot_id is not null
      ),
      true,false
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    cross join (values(1),(4),(12),(24)) h(h)
    on conflict(scorecard_id,horizon_hours) do nothing
    returning 1
  ) select count(*) into v_outcomes from ins;

  return jsonb_build_object(
    'mode','BIG_MOVER_FORWARD_MONEY_SCORECARD_SEED',
    'candidates_seeded',v_candidates,
    'outcomes_seeded',v_outcomes,
    'stage_linking','EXACT_IMMUTABLE_SNAPSHOT_WHEN_AVAILABLE',
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_seed_big_mover_money_scorecard() from public,anon,authenticated;
grant execute on function private.alpha_hunter_seed_big_mover_money_scorecard() to service_role;

-- Expand the cloud control plane from four stages to five while preserving
-- historical v0.1 rows whose expected_stage_count is four.
alter table public.alpha_hunter_control_plane_runs
  alter column expected_stage_count set default 5,
  alter column release_version set default 'cloud-control-plane-v0.2-money-entry-stage';
alter table public.alpha_hunter_control_plane_runs
  drop constraint if exists alpha_hunter_control_plane_runs_expected_stage_count_check;
alter table public.alpha_hunter_control_plane_runs
  add constraint alpha_hunter_control_plane_runs_expected_stage_count_check
  check (expected_stage_count in (4,5));

alter table public.alpha_hunter_control_plane_step_events
  drop constraint if exists alpha_hunter_control_plane_step_events_stage_name_check;
alter table public.alpha_hunter_control_plane_step_events
  add constraint alpha_hunter_control_plane_step_events_stage_name_check
  check (stage_name in ('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_ENTRY_STAGE','MONEY_SCORECARD'));
alter table public.alpha_hunter_control_plane_step_events
  drop constraint if exists alpha_hunter_control_plane_step_events_stage_order_check;
alter table public.alpha_hunter_control_plane_step_events
  add constraint alpha_hunter_control_plane_step_events_stage_order_check
  check (stage_order between 1 and 5);

create or replace function private.alpha_hunter_run_controlled_stage(p_stage text,p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_control_run_id text;
  v_hour timestamptz;
  v_stage text := upper(p_stage);
  v_stage_order integer;
  v_prev_stage text;
  v_attempt integer;
  v_started timestamptz;
  v_finished timestamptz;
  v_result jsonb := '{}'::jsonb;
  v_status text := 'PASS';
  v_error text;
  v_source_run_id text;
  v_existing record;
  v_prev_ok boolean := true;
  v_event_id text;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;

  v_stage_order := case v_stage
    when 'ANSWER_KEY' then 1
    when 'PARENT_DIRECTION' then 2
    when 'MONEY_ENTRY_BRIDGE' then 3
    when 'MONEY_ENTRY_STAGE' then 4
    when 'MONEY_SCORECARD' then 5
    else null
  end;
  if v_stage_order is null then raise exception 'unsupported Alpha Hunter controlled stage: %',p_stage; end if;
  v_prev_stage := case v_stage_order
    when 2 then 'ANSWER_KEY'
    when 3 then 'PARENT_DIRECTION'
    when 4 then 'MONEY_ENTRY_BRIDGE'
    when 5 then 'MONEY_ENTRY_STAGE'
    else null
  end;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|'||v_stage,0));

  insert into public.alpha_hunter_control_plane_runs(
    control_run_id,scheduled_hour_utc,started_at_utc,overall_status,expected_stage_count,release_version,payload
  ) values(
    v_control_run_id,v_hour,clock_timestamp(),'RUNNING',5,'cloud-control-plane-v0.2-money-entry-stage',
    jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour)
  ) on conflict(control_run_id) do nothing;

  select s.* into v_existing
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage and s.status in ('PASS','DEGRADED')
  order by s.attempt_no desc limit 1;
  if found then
    return jsonb_build_object(
      'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,'stage',v_stage,
      'status',v_existing.status,'deduplicated',true,'source_run_id',v_existing.source_run_id,
      'result',v_existing.result_payload,'shadow_only',true,'trade_permission',false
    );
  end if;

  if v_prev_stage is not null then
    select exists(
      select 1 from public.alpha_hunter_control_plane_step_events s
      where s.control_run_id=v_control_run_id and s.stage_name=v_prev_stage and s.status in ('PASS','DEGRADED')
    ) into v_prev_ok;
  end if;

  select coalesce(max(s.attempt_no),0)+1 into v_attempt
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage;

  v_started:=clock_timestamp();
  if not v_prev_ok then
    v_status:='SKIPPED';v_error:='PREDECESSOR_NOT_SUCCESSFUL:'||v_prev_stage;v_result:=jsonb_build_object('reason',v_error);
  else
    begin
      case v_stage
        when 'ANSWER_KEY' then
          v_result:=public.alpha_hunter_collect_big_mover_answer_key();
          v_source_run_id:=v_result#>>'{scoring,latest_feature_run_id}';
          if coalesce((v_result->>'ticker_count')::integer,0)<=0 then v_status:='FAILED';v_error:='NO_BITGET_TICKERS_RETURNED'; end if;
        when 'PARENT_DIRECTION' then
          v_result:=private.alpha_hunter_collect_big_mover_parent_direction();v_source_run_id:=v_result->>'run_id';
          if coalesce((v_result->>'failed_rows')::integer,0)>0 then v_status:='DEGRADED'; end if;
        when 'MONEY_ENTRY_BRIDGE' then
          v_result:=private.alpha_hunter_run_big_mover_money_entry_pipeline();v_source_run_id:=v_result->>'run_id';
        when 'MONEY_ENTRY_STAGE' then
          v_result:=private.alpha_hunter_capture_money_entry_stage_snapshots(v_control_run_id);v_source_run_id:=v_result->>'run_id';
          if coalesce(v_result->>'threshold_status','')='NO_ACTIVE_VALIDATED_THRESHOLD_SET' then v_status:='DEGRADED'; end if;
        when 'MONEY_SCORECARD' then
          v_result:=private.alpha_hunter_run_big_mover_money_scorecard();
          select r.source_run_id into v_source_run_id from public.alpha_hunter_control_plane_runs r where r.control_run_id=v_control_run_id;
          if coalesce((v_result->>'retryable_errors')::integer,0)>0 then v_status:='DEGRADED'; end if;
      end case;
      if coalesce(v_result->>'trade_permission','false')<>'false' or coalesce(v_result->>'shadow_only','true')<>'true' then
        v_status:='FAILED';v_error:=coalesce(v_error||';','')||'SAFETY_BOUNDARY_VIOLATION_IN_STAGE_RESULT';
      end if;
    exception when others then
      v_status:='FAILED';v_error:=left(sqlerrm,1000);v_result:=jsonb_build_object('exception',v_error);
    end;
  end if;

  v_finished:=clock_timestamp();
  v_event_id:=md5(v_control_run_id||'|'||v_stage||'|'||v_attempt::text||'|'||v_started::text);
  insert into public.alpha_hunter_control_plane_step_events(
    step_event_id,control_run_id,stage_name,stage_order,attempt_no,status,started_at_utc,finished_at_utc,duration_ms,
    source_run_id,result_payload,error,shadow_only,trade_permission
  ) values(
    v_event_id,v_control_run_id,v_stage,v_stage_order,v_attempt,v_status,v_started,v_finished,
    extract(epoch from(v_finished-v_started))*1000.0,v_source_run_id,coalesce(v_result,'{}'::jsonb),v_error,true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set source_run_id=case when r.source_run_id is null then v_source_run_id else r.source_run_id end,
      updated_at=clock_timestamp(),payload=r.payload||jsonb_build_object('last_stage',v_stage,'last_stage_status',v_status)
  where r.control_run_id=v_control_run_id;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,'stage',v_stage,'status',v_status,
    'attempt',v_attempt,'deduplicated',false,'source_run_id',v_source_run_id,'error',v_error,'result',v_result,
    'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_run_controlled_stage(text,timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_run_controlled_stage(text,timestamptz) to service_role;

create or replace function private.alpha_hunter_finalize_control_plane_hour(p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_control_run_id text;v_hour timestamptz;v_expected_count integer;
  v_pass integer:=0;v_degraded integer:=0;v_failed integer:=0;v_skipped integer:=0;
  v_missing jsonb:='[]'::jsonb;v_warnings jsonb:='[]'::jsonb;
  v_source_consistent boolean:=false;v_order_valid boolean:=false;
  v_latest_signal timestamptz;v_latest_answer timestamptz;v_latest_shadow timestamptz;
  v_freshness text:='DATA_INSUFFICIENT';v_safety text:='PASS';v_safety_violations integer:=0;
  v_status text;v_health_id text;v_incident_key text;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|FINALIZE',0));

  insert into public.alpha_hunter_control_plane_runs(
    control_run_id,scheduled_hour_utc,started_at_utc,overall_status,expected_stage_count,release_version,payload
  ) values(
    v_control_run_id,v_hour,clock_timestamp(),'RUNNING',5,'cloud-control-plane-v0.2-money-entry-stage',
    jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour)
  ) on conflict(control_run_id) do nothing;

  select r.expected_stage_count into v_expected_count from public.alpha_hunter_control_plane_runs r where r.control_run_id=v_control_run_id;

  with expected(stage_name,stage_order) as (
    select * from (values
      ('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5)
    ) v(stage_name,stage_order) where v_expected_count=5
    union all
    select * from (values
      ('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_SCORECARD',4)
    ) v(stage_name,stage_order) where v_expected_count=4
  ), latest as (
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  )
  select
    count(*) filter(where l.status='PASS'),count(*) filter(where l.status='DEGRADED'),
    count(*) filter(where l.status='FAILED'),count(*) filter(where l.status='SKIPPED'),
    coalesce(jsonb_agg(e.stage_name order by e.stage_order) filter(where l.stage_name is null or l.status not in('PASS','DEGRADED')),'[]'::jsonb)
  into v_pass,v_degraded,v_failed,v_skipped,v_missing
  from expected e left join latest l using(stage_name);

  with latest as (
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  )
  select coalesce(count(distinct source_run_id) filter(where source_run_id is not null)<=1,false)
  into v_source_consistent from latest;

  with expected(stage_name,stage_order) as (
    select * from (values
      ('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_ENTRY_STAGE',4),('MONEY_SCORECARD',5)
    ) v(stage_name,stage_order) where v_expected_count=5
    union all
    select * from (values
      ('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_SCORECARD',4)
    ) v(stage_name,stage_order) where v_expected_count=4
  ), latest as (
    select distinct on(s.stage_name) s.* from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id order by s.stage_name,s.attempt_no desc
  ), ordered as (
    select e.stage_order,l.finished_at_utc,lag(l.finished_at_utc) over(order by e.stage_order) prev_finished
    from expected e join latest l using(stage_name) where l.status in('PASS','DEGRADED')
  )
  select coalesce(count(*)=v_expected_count and bool_and(prev_finished is null or finished_at_utc>=prev_finished),false)
  into v_order_valid from ordered;

  select max(s.captured_at_utc) into v_latest_signal from public.alpha_hunter_signal_features s;
  select max(a.observed_at_utc) into v_latest_answer from public.alpha_hunter_big_mover_answer_key a;
  select max(b.captured_at_utc) into v_latest_shadow from public.alpha_hunter_big_mover_shadow b;
  if v_latest_signal is null or v_latest_answer is null or v_latest_shadow is null then v_freshness:='DATA_INSUFFICIENT';
  elsif clock_timestamp()-v_latest_signal>interval '90 minutes' or clock_timestamp()-v_latest_answer>interval '90 minutes' or clock_timestamp()-v_latest_shadow>interval '90 minutes' then v_freshness:='STALE';
  else v_freshness:='FRESH'; end if;

  select
    (select count(*) from public.alpha_hunter_big_mover_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_parent_direction_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_entry_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_money_entry_stage_snapshots x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_candidates x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_outcomes x where x.trade_permission<>false or x.shadow_only<>true)
  into v_safety_violations;
  if v_safety_violations>0 then v_safety:='FAIL'; end if;

  if jsonb_array_length(v_missing)>0 then v_warnings:=v_warnings||jsonb_build_array('MISSING_OR_UNSUCCESSFUL_STAGE'); end if;
  if not v_source_consistent then v_warnings:=v_warnings||jsonb_build_array('SOURCE_RUN_ID_MISMATCH'); end if;
  if not v_order_valid then v_warnings:=v_warnings||jsonb_build_array('STAGE_ORDER_NOT_PROVEN'); end if;
  if v_freshness<>'FRESH' then v_warnings:=v_warnings||jsonb_build_array('DATA_FRESHNESS_'||v_freshness); end if;
  if v_safety<>'PASS' then v_warnings:=v_warnings||jsonb_build_array('SAFETY_BOUNDARY_VIOLATION'); end if;

  v_status:=case
    when v_safety='FAIL' or jsonb_array_length(v_missing)>0 or v_failed>0 or v_skipped>0 or not v_source_consistent or not v_order_valid then 'FAILED'
    when v_degraded>0 or v_freshness<>'FRESH' then 'DEGRADED'
    else 'PASS'
  end;

  v_health_id:=md5(v_control_run_id||'|'||clock_timestamp()::text||'|'||v_status);
  insert into public.alpha_hunter_control_plane_health_events(
    health_event_id,control_run_id,checked_at_utc,status,stage_order_valid,source_run_consistent,data_freshness_status,
    safety_status,missing_stages,warnings,payload,shadow_only,trade_permission
  ) values(
    v_health_id,v_control_run_id,clock_timestamp(),v_status,v_order_valid,v_source_consistent,v_freshness,v_safety,v_missing,v_warnings,
    jsonb_build_object(
      'expected_stage_count',v_expected_count,
      'latest_signal_feature_utc',v_latest_signal,'latest_answer_key_utc',v_latest_answer,'latest_big_mover_shadow_utc',v_latest_shadow,
      'safety_violation_count',v_safety_violations,'freshness_contract','HOURLY_SOURCE_MAX_AGE_90_MINUTES',
      'expected_stage_order',case when v_expected_count=5 then jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_ENTRY_STAGE','MONEY_SCORECARD') else jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_SCORECARD') end
    ),true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set finalized_at_utc=clock_timestamp(),overall_status=v_status,passed_stage_count=v_pass,degraded_stage_count=v_degraded,
      failed_stage_count=v_failed,skipped_stage_count=v_skipped,data_freshness_status=v_freshness,safety_status=v_safety,
      updated_at=clock_timestamp(),payload=r.payload||jsonb_build_object('missing_stages',v_missing,'warnings',v_warnings,'latest_health_event_id',v_health_id)
  where r.control_run_id=v_control_run_id;

  v_incident_key:=v_control_run_id||'|CONTROL_PLANE_HEALTH';
  if v_status<>'PASS' then
    if not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN') then
      insert into public.alpha_hunter_production_incident_events(
        incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
      ) values(
        md5(v_incident_key||'|OPEN'),v_incident_key,v_control_run_id,'OPEN',
        case when v_safety='FAIL' then 'CRITICAL' when v_status='FAILED' then 'HIGH' else 'MEDIUM' end,
        'CONTROL_PLANE_HEALTH',clock_timestamp(),jsonb_build_object('status',v_status,'missing_stages',v_missing,'warnings',v_warnings,'safety_status',v_safety,'freshness_status',v_freshness),true,false
      );
    end if;
  elsif exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN')
    and not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='RESOLVED') then
      insert into public.alpha_hunter_production_incident_events(
        incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
      ) values(
        md5(v_incident_key||'|RESOLVED'),v_incident_key,v_control_run_id,'RESOLVED','INFO','CONTROL_PLANE_HEALTH',clock_timestamp(),
        jsonb_build_object('status','PASS','resolved_by_health_event_id',v_health_id),true,false
      );
  end if;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CLOUD_CONTROL_PLANE_FINALIZE','control_run_id',v_control_run_id,'expected_stage_count',v_expected_count,
    'status',v_status,'passed',v_pass,'degraded',v_degraded,'failed',v_failed,'skipped',v_skipped,'missing_stages',v_missing,
    'stage_order_valid',v_order_valid,'source_run_consistent',v_source_consistent,'data_freshness_status',v_freshness,
    'safety_status',v_safety,'warnings',v_warnings,'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) to service_role;

-- Add the :13 stage capture and keep the remaining stages staggered.
do $outer$
declare r record;
begin
  for r in
    select jobid from cron.job
    where jobname in(
      'alpha-hunter-big-mover-shadow-hourly','alpha-hunter-big-mover-parent-direction-hourly',
      'alpha-hunter-big-mover-money-entry-bridge-hourly','alpha-hunter-money-entry-stage-hourly',
      'alpha-hunter-big-mover-money-scorecard-hourly','alpha-hunter-control-plane-finalize-hourly'
    )
  loop perform cron.unschedule(r.jobid); end loop;

  perform cron.schedule('alpha-hunter-big-mover-shadow-hourly','10 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('ANSWER_KEY',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-parent-direction-hourly','11 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('PARENT_DIRECTION',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-money-entry-bridge-hourly','12 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-money-entry-stage-hourly','13 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_STAGE',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-big-mover-money-scorecard-hourly','14 * * * *',$cmd$select private.alpha_hunter_run_controlled_stage('MONEY_SCORECARD',clock_timestamp());$cmd$);
  perform cron.schedule('alpha-hunter-control-plane-finalize-hourly','20 * * * *',$cmd$select private.alpha_hunter_finalize_control_plane_hour(clock_timestamp());$cmd$);
end;
$outer$;
