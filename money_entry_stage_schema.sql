-- Alpha Hunter Money Entry stage evidence schema + single writer v0.1
-- No numeric T0/T1/T2 threshold set is activated by this file.

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
      max_t0_stop_distance_pct is not null and max_t0_stop_distance_pct>0
      and min_t0_remaining_r is not null and min_t0_remaining_r>0
      and min_t1_remaining_r is not null and min_t1_remaining_r>0
      and min_t2_remaining_r is not null and min_t2_remaining_r>0
    )
  ),
  check (
    status<>'ACTIVE'
    or (
      validated_at_utc is not null
      and activated_at_utc is not null
      and evidence_reference<>'{}'::jsonb
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

drop trigger if exists trg_ah_money_entry_threshold_sets_append_only
  on public.alpha_hunter_money_entry_threshold_sets;
create trigger trg_ah_money_entry_threshold_sets_append_only
before update or delete on public.alpha_hunter_money_entry_threshold_sets
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_money_entry_stage_snapshots_append_only
  on public.alpha_hunter_money_entry_stage_snapshots;
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
  v_threshold_status text:='NO_ACTIVE_VALIDATED_THRESHOLD_SET';
  v_max_t0_stop double precision;
  v_min_t0_r double precision;
  v_min_t1_r double precision;
  v_min_t2_r double precision;
  v_inserted integer:=0;
  v_status_counts jsonb:='{}'::jsonb;
  v_top_blockers jsonb:='[]'::jsonb;
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
      'mode','MONEY_ENTRY_STAGE_SINGLE_WRITER',
      'control_run_id',p_control_run_id,
      'run_id',null,
      'rows_inserted',0,
      'status','DATA_INSUFFICIENT',
      'blocker','NO_MONEY_ENTRY_BRIDGE_RUN',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  select
    t.threshold_set_id,t.status,t.max_t0_stop_distance_pct,
    t.min_t0_remaining_r,t.min_t1_remaining_r,t.min_t2_remaining_r
  into
    v_threshold_id,v_threshold_status,v_max_t0_stop,
    v_min_t0_r,v_min_t1_r,v_min_t2_r
  from public.alpha_hunter_money_entry_threshold_sets t
  where t.status='ACTIVE'
    and t.validated_at_utc is not null
    and t.activated_at_utc is not null
  order by t.activated_at_utc desc
  limit 1;

  if v_threshold_id is null then
    v_threshold_status:='NO_ACTIVE_VALIDATED_THRESHOLD_SET';
  end if;

  with src as (
    select
      b.*,
      sf.signal_id source_signal_id,
      coalesce(sf.source_payload,'{}'::jsonb) source_payload
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
      upper(nullif(s.source_payload#>>'{execution_setup,direction}','')) execution_setup_direction,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,structure_valid}') scanner_structure_valid,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,direction_aligned}') scanner_direction_aligned,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,momentum_confirmed}') scanner_momentum_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,participation_confirmed}') scanner_participation_confirmed,
      private.alpha_hunter_text_bool(s.source_payload#>>'{execution_setup,checks,data_integrity_min_88}') scanner_data_integrity_pass,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,liquidity_ok}',
        s.source_payload#>>'{execution_setup,checks,liquidity_pass}',
        s.source_payload->>'liquidity_pass'
      )) liquidity_ok,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,participation_emerging}',
        s.source_payload->>'participation_emerging'
      )) participation_emerging,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,acceptance_confirmed}',
        s.source_payload->>'acceptance_confirmed'
      )) acceptance_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,trigger_confirmed}',
        s.source_payload->>'trigger_confirmed'
      )) trigger_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,expansion_confirmed}',
        s.source_payload->>'expansion_confirmed'
      )) expansion_confirmed,
      private.alpha_hunter_text_bool(coalesce(
        s.source_payload#>>'{execution_setup,checks,open_position_conflict}',
        s.source_payload->>'open_position_conflict'
      )) open_position_conflict,
      case
        when s.candidate_entry is not null and s.candidate_entry>0 and s.stop_price is not null
          then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0
      end stop_distance_pct,
      case
        when s.direction='LONG'
          and s.candidate_entry is not null
          and s.stop_price is not null
          and s.target_price is not null
          and s.stop_price<s.candidate_entry
          and s.target_price>s.candidate_entry then true
        when s.direction='SHORT'
          and s.candidate_entry is not null
          and s.stop_price is not null
          and s.target_price is not null
          and s.stop_price>s.candidate_entry
          and s.target_price<s.candidate_entry then true
        else false
      end geometry_valid,
      case
        when s.direction='LONG' then s.direction_12h='BULLISH'
        when s.direction='SHORT' then s.direction_12h='BEARISH'
        else false
      end parent_12h_aligned,
      case
        when s.direction='LONG' then s.direction_1d='BULLISH'
        when s.direction='SHORT' then s.direction_1d='BEARISH'
        else false
      end parent_1d_aligned
    from src s
  ), evaluated as (
    select
      n.*,
      (
        select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
        from unnest(array[
          case when v_threshold_id is null then 'NO_ACTIVE_VALIDATED_THRESHOLD_SET' end,
          case when not n.parent_12h_aligned then
            case when n.direction_12h is null or n.direction_12h='DATA_UNAVAILABLE'
              then 'PARENT_12H_DATA_UNAVAILABLE'
              else 'PARENT_12H_NOT_ALIGNED'
            end
          end,
          case when not n.parent_1d_aligned then
            case when n.direction_1d is null or n.direction_1d='DATA_UNAVAILABLE'
              then 'PARENT_1D_DATA_UNAVAILABLE'
              else 'PARENT_1D_NOT_ALIGNED'
            end
          end,
          case
            when n.execution_setup_direction is null then 'SCANNER_EXECUTION_DIRECTION_MISSING'
            when n.execution_setup_direction<>n.direction then 'SCANNER_EXECUTION_DIRECTION_CONFLICT'
          end,
          case
            when n.liquidity_ok is null then 'LIQUIDITY_PASS_NOT_CAPTURED'
            when n.liquidity_ok is false then 'LIQUIDITY_NOT_VERIFIED'
          end,
          case
            when n.scanner_participation_confirmed is true or n.participation_emerging is true then null
            when n.scanner_participation_confirmed is null and n.participation_emerging is null
              then 'PARTICIPATION_EMERGING_NOT_CAPTURED'
            else 'PARTICIPATION_NOT_EMERGING'
          end,
          case
            when n.scanner_structure_valid is null then 'STRUCTURAL_INVALIDATION_VALIDITY_NOT_CAPTURED'
            when n.scanner_structure_valid is false then 'STRUCTURAL_INVALIDATION_NOT_VALID'
          end,
          case
            when n.open_position_conflict is null then 'OPEN_POSITION_CONFLICT_NOT_CAPTURED'
            when n.open_position_conflict is true then 'OPEN_POSITION_CONFLICT'
          end,
          case when not n.geometry_valid then 'EXECUTION_GEOMETRY_MISSING_OR_DIRECTION_INVALID' end,
          case when n.stop_distance_pct is null then 'STOP_DISTANCE_MISSING' end,
          case when n.execution_rr is null then 'REMAINING_R_MISSING' end,
          case
            when v_threshold_id is not null
              and n.stop_distance_pct is not null
              and n.stop_distance_pct>v_max_t0_stop
            then 'T0_STOP_GEOMETRY_TOO_WIDE'
          end
        ]) with ordinality u(x,ord)
        where x is not null
      ) base_blockers,
      (
        select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
        from unnest(array[
          case when n.scanner_participation_confirmed is not true then 'T1_PARTICIPATION_NOT_CONFIRMED' end,
          case
            when n.acceptance_confirmed is null then 'T1_ACCEPTANCE_NOT_CAPTURED'
            when n.acceptance_confirmed is false then 'T1_ACCEPTANCE_NOT_CONFIRMED'
          end,
          case
            when n.trigger_confirmed is null then 'T1_TRIGGER_NOT_CAPTURED'
            when n.trigger_confirmed is false then 'T1_TRIGGER_NOT_CONFIRMED'
          end,
          case
            when n.expansion_confirmed is null then 'T2_EXPANSION_NOT_CAPTURED'
            when n.expansion_confirmed is false then 'T2_EXPANSION_NOT_CONFIRMED'
          end
        ]) with ordinality u(x,ord)
        where x is not null
      ) next_blockers
    from normalized n
  ), staged as (
    select
      e.*,
      case
        when v_threshold_id is null then 'DATA_INSUFFICIENT'
        when jsonb_array_length(e.base_blockers)>0 then 'NO_T0'
        when e.scanner_participation_confirmed is true
          and e.acceptance_confirmed is true
          and e.trigger_confirmed is true
          and e.expansion_confirmed is true
          and e.execution_rr>=v_min_t2_r then 'T2_EXPANSION_CONFIRMED'
        when e.scanner_participation_confirmed is true
          and e.acceptance_confirmed is true
          and e.trigger_confirmed is true
          and e.execution_rr>=v_min_t1_r then 'T1_ACCEPTANCE_CONFIRMED'
        when e.execution_rr>=v_min_t0_r then 'T0_CONTROLLED_ENTRY'
        else 'NO_T0'
      end exact_stage
    from evaluated e
  ), ins as (
    insert into public.alpha_hunter_money_entry_stage_snapshots(
      stage_snapshot_id,control_run_id,source_run_id,source_bridge_id,source_signal_id,
      source_captured_at_utc,snapshot_at_utc,symbol,direction,stage_status,stage_eligible,
      threshold_set_id,threshold_status,direction_1h,direction_12h,direction_1d,
      lifecycle,research_status,bridge_status,scanner_state,decision_stage,market_phase,
      liquidity_state,candidate_entry,stop_price,target_price,stop_distance_pct,remaining_r,
      execution_setup_direction,scanner_structure_valid,scanner_direction_aligned,
      scanner_momentum_confirmed,scanner_participation_confirmed,scanner_data_integrity_pass,
      liquidity_ok,participation_emerging,acceptance_confirmed,trigger_confirmed,
      expansion_confirmed,open_position_conflict,blockers,next_stage_blockers,evidence,
      model_version,shadow_only,trade_permission
    )
    select
      md5('money-entry-stage-single-writer-v0.1|'||s.bridge_id),
      p_control_run_id,s.run_id,s.bridge_id,s.source_signal_id,s.captured_at_utc,
      clock_timestamp(),s.symbol,s.direction,s.exact_stage,
      s.exact_stage in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'),
      v_threshold_id,v_threshold_status,s.direction_1h,s.direction_12h,s.direction_1d,
      s.lifecycle,s.research_status,s.bridge_status,s.source_payload->>'state',
      s.source_payload#>>'{decision_trace,decision_stage}',s.source_payload->>'market_phase',
      s.liquidity_state,s.candidate_entry,s.stop_price,s.target_price,s.stop_distance_pct,
      s.execution_rr,s.execution_setup_direction,s.scanner_structure_valid,
      s.scanner_direction_aligned,s.scanner_momentum_confirmed,
      s.scanner_participation_confirmed,s.scanner_data_integrity_pass,s.liquidity_ok,
      s.participation_emerging,s.acceptance_confirmed,s.trigger_confirmed,
      s.expansion_confirmed,s.open_position_conflict,
      case
        when s.exact_stage='NO_T0'
          and v_threshold_id is not null
          and jsonb_array_length(s.base_blockers)=0
          and s.execution_rr is not null
          and s.execution_rr<v_min_t0_r
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

  select coalesce(
    jsonb_agg(jsonb_build_object('blocker',blocker,'count',n) order by n desc,blocker),
    '[]'::jsonb
  )
  into v_top_blockers
  from (
    select b.value#>>'{}' blocker,count(*)::integer n
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
revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text)
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text)
  to service_role;
