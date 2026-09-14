-- Alpha Hunter Money Entry progression ledger v0.2
-- Shadow-only, append-only evidence path for observed T0 -> T1 -> T2 progression.
-- This migration does not activate thresholds, change production permissions,
-- select leverage, or authorize order execution.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_money_entry_candidate_episodes (
  candidate_episode_id text primary key,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  opened_stage_snapshot_id text not null unique references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id),
  opened_risk_assessment_id text not null unique references public.alpha_hunter_portfolio_risk_assessments(risk_assessment_id),
  opened_control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  source_run_id text not null,
  opened_at_utc timestamptz not null,
  t0_entry_price double precision,
  t0_structural_invalidation_price double precision,
  t0_stop_distance_pct double precision,
  t0_remaining_r double precision,
  model_version text not null default 'money-entry-progression-ledger-v0.2',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists public.alpha_hunter_money_entry_stage_progressions (
  progression_id text primary key,
  candidate_episode_id text not null references public.alpha_hunter_money_entry_candidate_episodes(candidate_episode_id),
  stage_snapshot_id text not null unique references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id),
  risk_assessment_id text not null unique references public.alpha_hunter_portfolio_risk_assessments(risk_assessment_id),
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  source_run_id text not null,
  source_bridge_id text not null,
  source_captured_at_utc timestamptz not null,
  progressed_at_utc timestamptz not null default clock_timestamp(),
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  stage_status text not null check (stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED')),
  stage_rank smallint not null check (stage_rank between 1 and 3),
  previous_progression_id text references public.alpha_hunter_money_entry_stage_progressions(progression_id),
  previous_stage_status text,
  previous_stage_rank smallint not null default 0 check (previous_stage_rank between 0 and 3),
  stage_jump boolean not null default false,
  candidate_entry double precision,
  structural_invalidation_price double precision,
  stop_distance_pct double precision,
  remaining_r double precision,
  confirmation_tax_r double precision,
  confirmation_price_tax_pct double precision,
  direction_1h text,
  direction_12h text,
  direction_1d text,
  lifecycle text,
  market_phase text,
  liquidity_state text,
  liquidity_ok boolean,
  participation_emerging boolean,
  participation_confirmed boolean,
  acceptance_confirmed boolean,
  trigger_confirmed boolean,
  expansion_confirmed boolean,
  open_position_conflict boolean,
  portfolio_risk_decision text,
  portfolio_exposure jsonb not null default '{}'::jsonb check (jsonb_typeof(portfolio_exposure)='object'),
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'money-entry-progression-ledger-v0.2',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  unique(candidate_episode_id,stage_rank)
);

create table if not exists public.alpha_hunter_money_entry_progression_anomalies (
  anomaly_id text primary key,
  risk_assessment_id text references public.alpha_hunter_portfolio_risk_assessments(risk_assessment_id),
  stage_snapshot_id text references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id),
  candidate_episode_id text references public.alpha_hunter_money_entry_candidate_episodes(candidate_episode_id),
  control_run_id text,
  symbol text,
  direction text,
  observed_stage_status text,
  anomaly_type text not null,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  model_version text not null default 'money-entry-progression-ledger-v0.2',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_money_entry_candidate_episodes enable row level security;
alter table public.alpha_hunter_money_entry_stage_progressions enable row level security;
alter table public.alpha_hunter_money_entry_progression_anomalies enable row level security;

revoke all on table public.alpha_hunter_money_entry_candidate_episodes from public,anon,authenticated;
revoke all on table public.alpha_hunter_money_entry_stage_progressions from public,anon,authenticated;
revoke all on table public.alpha_hunter_money_entry_progression_anomalies from public,anon,authenticated;
grant select on table public.alpha_hunter_money_entry_candidate_episodes to service_role;
grant select on table public.alpha_hunter_money_entry_stage_progressions to service_role;
grant select on table public.alpha_hunter_money_entry_progression_anomalies to service_role;

create index if not exists idx_ah_me_episode_symbol_direction
  on public.alpha_hunter_money_entry_candidate_episodes(symbol,direction,opened_at_utc desc);
create index if not exists idx_ah_me_progression_episode
  on public.alpha_hunter_money_entry_stage_progressions(candidate_episode_id,stage_rank);
create index if not exists idx_ah_me_progression_symbol_direction
  on public.alpha_hunter_money_entry_stage_progressions(symbol,direction,progressed_at_utc desc);
create index if not exists idx_ah_me_progression_control_run
  on public.alpha_hunter_money_entry_stage_progressions(control_run_id,progressed_at_utc desc);
create index if not exists idx_ah_me_progression_anomaly_control_run
  on public.alpha_hunter_money_entry_progression_anomalies(control_run_id,created_at desc);

drop trigger if exists trg_ah_me_candidate_episodes_append_only on public.alpha_hunter_money_entry_candidate_episodes;
create trigger trg_ah_me_candidate_episodes_append_only
before update or delete on public.alpha_hunter_money_entry_candidate_episodes
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_me_stage_progressions_append_only on public.alpha_hunter_money_entry_stage_progressions;
create trigger trg_ah_me_stage_progressions_append_only
before update or delete on public.alpha_hunter_money_entry_stage_progressions
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_me_progression_anomalies_append_only on public.alpha_hunter_money_entry_progression_anomalies;
create trigger trg_ah_me_progression_anomalies_append_only
before update or delete on public.alpha_hunter_money_entry_progression_anomalies
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_money_entry_stage_rank(p_stage text)
returns smallint
language sql
immutable
set search_path = ''
as $$
  select case upper(coalesce(p_stage,''))
    when 'T0_CONTROLLED_ENTRY' then 1::smallint
    when 'T1_ACCEPTANCE_CONFIRMED' then 2::smallint
    when 'T2_EXPANSION_CONFIRMED' then 3::smallint
    else 0::smallint end;
$$;
revoke all on function private.alpha_hunter_money_entry_stage_rank(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_money_entry_stage_rank(text) to service_role;

create or replace function private.alpha_hunter_record_money_entry_progression(p_risk_assessment_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_risk public.alpha_hunter_portfolio_risk_assessments%rowtype;
  v_stage public.alpha_hunter_money_entry_stage_snapshots%rowtype;
  v_episode_id text;
  v_rank smallint;
  v_prev public.alpha_hunter_money_entry_stage_progressions%rowtype;
  v_prev_rank smallint := 0;
  v_t0_entry double precision;
  v_t0_remaining_r double precision;
  v_progression_id text;
  v_anomaly_id text;
  v_confirmation_tax_r double precision;
  v_confirmation_price_tax_pct double precision;
  v_stage_jump boolean := false;
begin
  select r.* into v_risk
  from public.alpha_hunter_portfolio_risk_assessments r
  where r.risk_assessment_id=p_risk_assessment_id;

  if not found then
    return jsonb_build_object('status','RISK_ASSESSMENT_NOT_FOUND','risk_assessment_id',p_risk_assessment_id,'shadow_only',true,'trade_permission',false);
  end if;

  select s.* into v_stage
  from public.alpha_hunter_money_entry_stage_snapshots s
  where s.stage_snapshot_id=v_risk.stage_snapshot_id;

  if not found then
    return jsonb_build_object('status','STAGE_SNAPSHOT_NOT_FOUND','risk_assessment_id',p_risk_assessment_id,'shadow_only',true,'trade_permission',false);
  end if;

  if v_risk.shadow_only is not true or v_risk.trade_permission is not false
     or v_stage.shadow_only is not true or v_stage.trade_permission is not false then
    return jsonb_build_object('status','SAFETY_BOUNDARY_REJECTED','risk_assessment_id',p_risk_assessment_id,'shadow_only',true,'trade_permission',false);
  end if;

  v_rank := private.alpha_hunter_money_entry_stage_rank(v_stage.stage_status);
  if v_stage.stage_eligible is not true or v_rank=0 then
    return jsonb_build_object('status','IGNORED_NON_PROGRESS_STAGE','stage_status',v_stage.stage_status,'shadow_only',true,'trade_permission',false);
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('AH_ME_PROGRESSION|'||v_stage.symbol||'|'||v_stage.direction,0)
  );

  select e.candidate_episode_id into v_episode_id
  from public.alpha_hunter_money_entry_candidate_episodes e
  where e.symbol=v_stage.symbol and e.direction=v_stage.direction
    and not exists(
      select 1 from public.alpha_hunter_money_entry_stage_progressions p
      where p.candidate_episode_id=e.candidate_episode_id and p.stage_rank=3
    )
  order by e.opened_at_utc desc
  limit 1;

  if v_rank=1 and v_episode_id is null then
    v_episode_id := md5('money-entry-candidate-episode-v0.2|'||v_stage.stage_snapshot_id);
    insert into public.alpha_hunter_money_entry_candidate_episodes(
      candidate_episode_id,symbol,direction,opened_stage_snapshot_id,opened_risk_assessment_id,
      opened_control_run_id,source_run_id,opened_at_utc,t0_entry_price,t0_structural_invalidation_price,
      t0_stop_distance_pct,t0_remaining_r,model_version,shadow_only,trade_permission
    ) values(
      v_episode_id,v_stage.symbol,v_stage.direction,v_stage.stage_snapshot_id,v_risk.risk_assessment_id,
      v_stage.control_run_id,v_stage.source_run_id,v_stage.source_captured_at_utc,v_stage.candidate_entry,v_stage.stop_price,
      v_stage.stop_distance_pct,v_stage.remaining_r,'money-entry-progression-ledger-v0.2',true,false
    ) on conflict(opened_stage_snapshot_id) do nothing;
  elsif v_rank>1 and v_episode_id is null then
    v_anomaly_id := md5('money-entry-progression-anomaly-v0.2|'||v_risk.risk_assessment_id||'|ORPHAN_STAGE_WITHOUT_T0');
    insert into public.alpha_hunter_money_entry_progression_anomalies(
      anomaly_id,risk_assessment_id,stage_snapshot_id,control_run_id,symbol,direction,observed_stage_status,anomaly_type,details,shadow_only,trade_permission
    ) values(
      v_anomaly_id,v_risk.risk_assessment_id,v_stage.stage_snapshot_id,v_stage.control_run_id,v_stage.symbol,v_stage.direction,v_stage.stage_status,
      'ORPHAN_STAGE_WITHOUT_T0',jsonb_build_object('stage_rank',v_rank,'reason','Progression ledger requires an observed T0 before T1/T2.'),true,false
    ) on conflict(anomaly_id) do nothing;
    return jsonb_build_object('status','ORPHAN_STAGE_WITHOUT_T0','stage_status',v_stage.stage_status,'shadow_only',true,'trade_permission',false);
  end if;

  if v_episode_id is null then
    select e.candidate_episode_id into v_episode_id
    from public.alpha_hunter_money_entry_candidate_episodes e
    where e.opened_stage_snapshot_id=v_stage.stage_snapshot_id;
  end if;

  select p.* into v_prev
  from public.alpha_hunter_money_entry_stage_progressions p
  where p.candidate_episode_id=v_episode_id
  order by p.stage_rank desc,p.progressed_at_utc desc
  limit 1;
  if found then v_prev_rank:=v_prev.stage_rank; else v_prev_rank:=0; end if;

  if v_rank < v_prev_rank then
    v_anomaly_id := md5('money-entry-progression-anomaly-v0.2|'||v_risk.risk_assessment_id||'|STAGE_REGRESSION');
    insert into public.alpha_hunter_money_entry_progression_anomalies(
      anomaly_id,risk_assessment_id,stage_snapshot_id,candidate_episode_id,control_run_id,symbol,direction,observed_stage_status,anomaly_type,details,shadow_only,trade_permission
    ) values(
      v_anomaly_id,v_risk.risk_assessment_id,v_stage.stage_snapshot_id,v_episode_id,v_stage.control_run_id,v_stage.symbol,v_stage.direction,v_stage.stage_status,
      'STAGE_REGRESSION',jsonb_build_object('previous_stage_status',v_prev.stage_status,'previous_stage_rank',v_prev_rank,'observed_stage_rank',v_rank),true,false
    ) on conflict(anomaly_id) do nothing;
    return jsonb_build_object('status','STAGE_REGRESSION_RECORDED','candidate_episode_id',v_episode_id,'shadow_only',true,'trade_permission',false);
  elsif v_rank = v_prev_rank then
    return jsonb_build_object('status','REPEATED_STAGE_IGNORED','candidate_episode_id',v_episode_id,'stage_status',v_stage.stage_status,'shadow_only',true,'trade_permission',false);
  end if;

  v_stage_jump := v_rank > v_prev_rank + 1;

  select p.candidate_entry,p.remaining_r into v_t0_entry,v_t0_remaining_r
  from public.alpha_hunter_money_entry_stage_progressions p
  where p.candidate_episode_id=v_episode_id and p.stage_rank=1
  limit 1;
  if not found and v_rank=1 then
    v_t0_entry:=v_stage.candidate_entry;
    v_t0_remaining_r:=v_stage.remaining_r;
  end if;

  if v_t0_remaining_r is not null and v_stage.remaining_r is not null then
    v_confirmation_tax_r:=v_t0_remaining_r-v_stage.remaining_r;
  end if;
  if v_t0_entry is not null and v_t0_entry>0 and v_stage.candidate_entry is not null and v_stage.candidate_entry>0 then
    v_confirmation_price_tax_pct:=case
      when v_stage.direction='LONG' then (v_stage.candidate_entry/v_t0_entry-1.0)*100.0
      when v_stage.direction='SHORT' then (v_t0_entry/v_stage.candidate_entry-1.0)*100.0
      else null end;
  end if;

  v_progression_id := md5('money-entry-progression-ledger-v0.2|'||v_episode_id||'|'||v_rank::text);
  insert into public.alpha_hunter_money_entry_stage_progressions(
    progression_id,candidate_episode_id,stage_snapshot_id,risk_assessment_id,control_run_id,source_run_id,source_bridge_id,
    source_captured_at_utc,progressed_at_utc,symbol,direction,stage_status,stage_rank,previous_progression_id,
    previous_stage_status,previous_stage_rank,stage_jump,candidate_entry,structural_invalidation_price,stop_distance_pct,remaining_r,
    confirmation_tax_r,confirmation_price_tax_pct,direction_1h,direction_12h,direction_1d,lifecycle,market_phase,
    liquidity_state,liquidity_ok,participation_emerging,participation_confirmed,acceptance_confirmed,trigger_confirmed,
    expansion_confirmed,open_position_conflict,portfolio_risk_decision,portfolio_exposure,blockers,evidence,model_version,shadow_only,trade_permission
  ) values(
    v_progression_id,v_episode_id,v_stage.stage_snapshot_id,v_risk.risk_assessment_id,v_stage.control_run_id,v_stage.source_run_id,v_stage.source_bridge_id,
    v_stage.source_captured_at_utc,clock_timestamp(),v_stage.symbol,v_stage.direction,v_stage.stage_status,v_rank,
    case when v_prev_rank>0 then v_prev.progression_id else null end,
    case when v_prev_rank>0 then v_prev.stage_status else null end,v_prev_rank,v_stage_jump,
    v_stage.candidate_entry,v_stage.stop_price,v_stage.stop_distance_pct,v_stage.remaining_r,v_confirmation_tax_r,v_confirmation_price_tax_pct,
    v_stage.direction_1h,v_stage.direction_12h,v_stage.direction_1d,v_stage.lifecycle,v_stage.market_phase,
    v_stage.liquidity_state,v_stage.liquidity_ok,v_stage.participation_emerging,v_stage.scanner_participation_confirmed,
    v_stage.acceptance_confirmed,v_stage.trigger_confirmed,v_stage.expansion_confirmed,v_stage.open_position_conflict,
    v_risk.risk_decision,
    jsonb_build_object(
      'risk_policy_id',v_risk.risk_policy_id,
      'risk_policy_status',v_risk.risk_policy_status,
      'account_snapshot_id',v_risk.account_snapshot_id,
      'account_state_status',v_risk.account_state_status,
      'position_ledger_status',v_risk.position_ledger_status,
      'current_available_usdt',v_risk.current_available_usdt,
      'monetary_risk_usdt',v_risk.monetary_risk_usdt,
      'derived_position_notional_usdt',v_risk.derived_position_notional_usdt,
      'open_position_count',v_risk.open_position_count,
      'aggregate_open_risk_usdt',v_risk.aggregate_open_risk_usdt,
      'daily_realized_pnl_usdt',v_risk.daily_realized_pnl_usdt,
      'symbol_position_conflict',v_risk.symbol_position_conflict,
      'aggregate_risk_complete',v_risk.aggregate_risk_complete,
      'risk_blockers',coalesce(v_risk.blockers,'[]'::jsonb)
    ),
    coalesce(v_stage.blockers,'[]'::jsonb),
    jsonb_build_object(
      'immutable_progression_snapshot',true,
      't0_is_episode_anchor',true,
      'stage_jump',v_stage_jump,
      'confirmation_tax_definition','T0 remaining-R minus current-stage remaining-R; positive means waiting consumed R.',
      'confirmation_price_tax_definition','Direction-normalized entry deterioration versus observed T0; positive means a worse later entry.',
      'production_permissions_changed',false,
      'thresholds_activated_by_this_ledger',false
    ),
    'money-entry-progression-ledger-v0.2',true,false
  ) on conflict(candidate_episode_id,stage_rank) do nothing;

  return jsonb_build_object(
    'status','PROGRESSION_RECORDED','candidate_episode_id',v_episode_id,'progression_id',v_progression_id,
    'stage_status',v_stage.stage_status,'stage_rank',v_rank,'previous_stage_rank',v_prev_rank,'stage_jump',v_stage_jump,
    'confirmation_tax_r',v_confirmation_tax_r,'confirmation_price_tax_pct',v_confirmation_price_tax_pct,
    'shadow_only',true,'trade_permission',false
  );
exception when others then
  begin
    v_anomaly_id := md5('money-entry-progression-anomaly-v0.2|'||coalesce(p_risk_assessment_id,'NULL')||'|TRIGGER_EXCEPTION');
    insert into public.alpha_hunter_money_entry_progression_anomalies(
      anomaly_id,risk_assessment_id,stage_snapshot_id,candidate_episode_id,control_run_id,symbol,direction,observed_stage_status,anomaly_type,details,shadow_only,trade_permission
    ) values(
      v_anomaly_id,p_risk_assessment_id,v_stage.stage_snapshot_id,v_episode_id,v_stage.control_run_id,v_stage.symbol,v_stage.direction,v_stage.stage_status,
      'TRIGGER_EXCEPTION',jsonb_build_object('error',left(sqlerrm,1000)),true,false
    ) on conflict(anomaly_id) do nothing;
  exception when others then null;
  end;
  return jsonb_build_object('status','SHADOW_LEDGER_EXCEPTION','error',left(sqlerrm,1000),'shadow_only',true,'trade_permission',false);
end;
$$;
revoke all on function private.alpha_hunter_record_money_entry_progression(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_record_money_entry_progression(text) to service_role;

create or replace function private.alpha_hunter_after_portfolio_risk_capture_progression()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform private.alpha_hunter_record_money_entry_progression(new.risk_assessment_id);
  return new;
end;
$$;
revoke all on function private.alpha_hunter_after_portfolio_risk_capture_progression() from public,anon,authenticated;

drop trigger if exists trg_ah_after_portfolio_risk_capture_progression on public.alpha_hunter_portfolio_risk_assessments;
create trigger trg_ah_after_portfolio_risk_capture_progression
after insert on public.alpha_hunter_portfolio_risk_assessments
for each row execute function private.alpha_hunter_after_portfolio_risk_capture_progression();

create or replace function private.alpha_hunter_backfill_money_entry_progressions()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_id text;
  v_result jsonb;
  v_seen integer:=0;
  v_recorded integer:=0;
  v_orphans integer:=0;
  v_regressions integer:=0;
begin
  for v_id in
    select r.risk_assessment_id
    from public.alpha_hunter_portfolio_risk_assessments r
    join public.alpha_hunter_money_entry_stage_snapshots s on s.stage_snapshot_id=r.stage_snapshot_id
    where s.stage_eligible=true
      and s.stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED')
    order by s.source_captured_at_utc,r.created_at
  loop
    v_seen:=v_seen+1;
    v_result:=private.alpha_hunter_record_money_entry_progression(v_id);
    if v_result->>'status'='PROGRESSION_RECORDED' then v_recorded:=v_recorded+1; end if;
    if v_result->>'status'='ORPHAN_STAGE_WITHOUT_T0' then v_orphans:=v_orphans+1; end if;
    if v_result->>'status'='STAGE_REGRESSION_RECORDED' then v_regressions:=v_regressions+1; end if;
  end loop;
  return jsonb_build_object(
    'mode','MONEY_ENTRY_PROGRESSION_BACKFILL','eligible_rows_seen',v_seen,'progressions_recorded',v_recorded,
    'orphans',v_orphans,'regressions',v_regressions,'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_backfill_money_entry_progressions() from public,anon,authenticated;
grant execute on function private.alpha_hunter_backfill_money_entry_progressions() to service_role;

comment on table public.alpha_hunter_money_entry_stage_progressions is
  'Append-only shadow ledger. One row per observed candidate progression stage (T0/T1/T2), anchored at first observed T0 and enriched with contemporaneous portfolio-risk context. Never grants trade permission.';
