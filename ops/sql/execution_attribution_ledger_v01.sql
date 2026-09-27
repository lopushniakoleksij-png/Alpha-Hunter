-- Alpha Hunter explicit execution-attribution ledger v0.1
--
-- Operations/scientific-evidence bridge only. Lives under ops/sql and is
-- outside the sealed V14 scientific fingerprint.
--
-- Purpose:
-- 1) freeze a prospective Alpha Hunter decision before any user execution;
-- 2) later bind one exact immutable Bitget fill only after explicit user
--    confirmation;
-- 3) verify attribution only when decision, order, fill, quote and timing
--    evidence are all consistent.
--
-- This migration never submits, changes, cancels or routes an exchange order.

create table if not exists public.alpha_hunter_execution_decision_freezes_v01 (
  execution_event_id text primary key,
  spec_id text not null,
  decision_observation_id text not null unique
    references public.alpha_hunter_shadow_decision_quotes_v01(observation_id)
    on delete restrict,
  strategy_instance_id text not null,
  decision_run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  action text not null check (action in ('EXECUTE_NOW','PLACE_LIMIT')),
  decision_observed_at_utc timestamptz not null,
  decision_captured_at_utc timestamptz not null,
  frozen_at_utc timestamptz not null default clock_timestamp(),
  reference_price numeric,
  planned_entry_price numeric,
  stop_price numeric,
  target_price numeric,
  reward_risk numeric,
  best_bid numeric not null,
  best_ask numeric not null,
  midpoint numeric not null,
  entry_cross_price numeric not null,
  entry_cross_half_spread_bps numeric,
  quote_complete boolean not null check (quote_complete=true),
  prospective_capture boolean not null check (prospective_capture=true),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'PROSPECTIVE_EXECUTION_ATTRIBUTION',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check (frozen_at_utc >= decision_captured_at_utc)
);

create table if not exists public.alpha_hunter_execution_fill_bindings_v01 (
  binding_id text primary key,
  execution_event_id text not null unique
    references public.alpha_hunter_execution_decision_freezes_v01(execution_event_id)
    on delete restrict,
  fill_evidence_id text not null unique
    references public.alpha_hunter_fill_evidence(fill_evidence_id)
    on delete restrict,
  bound_at_utc timestamptz not null default clock_timestamp(),
  explicit_user_confirmation boolean not null
    check (explicit_user_confirmation=true),
  confirmation_source text not null default 'USER_EXPLICIT'
    check (confirmation_source='USER_EXPLICIT'),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'EXPLICIT_USER_FILL_BINDING',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_execution_decision_freezes_v01
  enable row level security;
alter table public.alpha_hunter_execution_fill_bindings_v01
  enable row level security;

revoke all on table public.alpha_hunter_execution_decision_freezes_v01
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_execution_fill_bindings_v01
  from public,anon,authenticated,service_role;

grant select,insert on table public.alpha_hunter_execution_decision_freezes_v01
  to service_role;
grant select,insert on table public.alpha_hunter_execution_fill_bindings_v01
  to service_role;

drop trigger if exists trg_ah_execution_decision_freezes_append_only
  on public.alpha_hunter_execution_decision_freezes_v01;
create trigger trg_ah_execution_decision_freezes_append_only
before update or delete
on public.alpha_hunter_execution_decision_freezes_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_execution_fill_bindings_append_only
  on public.alpha_hunter_execution_fill_bindings_v01;
create trigger trg_ah_execution_fill_bindings_append_only
before update or delete
on public.alpha_hunter_execution_fill_bindings_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_execution_attribution_candidates_v01
with (security_invoker=true,security_barrier=true) as
with active as (
  select e.spec_id,v.started_at_utc,s.required_run_source
  from public.alpha_hunter_test_engine_latest_v01 e
  join public.alpha_hunter_profitability_validation_status_v01 v
    on v.spec_id=e.spec_id
  join public.alpha_hunter_profitability_test_specs_v01 s
    on s.spec_id=e.spec_id
  where v.test_activated=true
  limit 1
),
cadence as (
  select c.maximum_interval_minutes
  from public.alpha_hunter_profitability_cadence_integrity_v01 c
  join active a on a.spec_id=c.spec_id
  limit 1
),
latest_canonical as (
  select
    s.run_id,
    s.collected_at_utc
  from public.alpha_hunter_snapshots s
  join active a
    on s.payload->'validation_identity'->>'run_source'=a.required_run_source
  order by s.collected_at_utc desc
  limit 1
)
select
  a.spec_id,
  q.observation_id as decision_observation_id,
  q.strategy_instance_id,
  q.run_id as decision_run_id,
  q.symbol,
  q.strategy_id,
  q.direction,
  q.action,
  q.observed_at_utc as decision_observed_at_utc,
  q.captured_at_utc as decision_captured_at_utc,
  q.reference_price,
  q.planned_entry_price,
  s.stop_price,
  s.target_price,
  s.reward_risk,
  s.geometry_valid,
  q.best_bid,
  q.best_ask,
  q.midpoint,
  q.entry_cross_price,
  q.entry_cross_half_spread_bps,
  q.quote_complete,
  q.prospective_capture,
  q.run_source,
  q.git_commit,
  q.config_sha256,
  not exists (
    select 1
    from public.alpha_hunter_execution_decision_freezes_v01 f
    where f.decision_observation_id=q.observation_id
  ) as freeze_available,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from active a
join latest_canonical lc on true
left join cadence c on true
join public.alpha_hunter_shadow_decision_quotes_v01 q
  on q.run_source=a.required_run_source
 and q.run_id=lc.run_id
 and q.observed_at_utc>=a.started_at_utc
 and q.observed_at_utc<=clock_timestamp()
 and q.observed_at_utc>=clock_timestamp()
   - coalesce(c.maximum_interval_minutes,35)::double precision
     * interval '1 minute'
join public.alpha_hunter_strategy_observations_v01 s
  on s.observation_id=q.observation_id
where q.quote_complete=true
  and q.prospective_capture=true
  and q.action in ('EXECUTE_NOW','PLACE_LIMIT')
  and s.geometry_valid=true
  and s.direction=q.direction
  and s.action=q.action;

revoke all on public.alpha_hunter_execution_attribution_candidates_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_attribution_candidates_v01
  to service_role;


create or replace function private.alpha_hunter_freeze_execution_decision_v01(
  p_decision_observation_id text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  c public.alpha_hunter_execution_attribution_candidates_v01%rowtype;
  v_execution_event_id text;
  v_frozen_at timestamptz := clock_timestamp();
begin
  select x.* into c
  from public.alpha_hunter_execution_attribution_candidates_v01 x
  where x.decision_observation_id=p_decision_observation_id
    and x.freeze_available=true
  limit 1;

  if c.decision_observation_id is null then
    raise exception 'Decision is not a current prospective attribution candidate';
  end if;

  v_execution_event_id :=
    'exec-'||md5(c.decision_observation_id||'|'||v_frozen_at::text);

  insert into public.alpha_hunter_execution_decision_freezes_v01(
    execution_event_id,
    spec_id,
    decision_observation_id,
    strategy_instance_id,
    decision_run_id,
    symbol,
    strategy_id,
    direction,
    action,
    decision_observed_at_utc,
    decision_captured_at_utc,
    frozen_at_utc,
    reference_price,
    planned_entry_price,
    stop_price,
    target_price,
    reward_risk,
    best_bid,
    best_ask,
    midpoint,
    entry_cross_price,
    entry_cross_half_spread_bps,
    quote_complete,
    prospective_capture,
    evidence,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_execution_event_id,
    c.spec_id,
    c.decision_observation_id,
    c.strategy_instance_id,
    c.decision_run_id,
    c.symbol,
    c.strategy_id,
    c.direction,
    c.action,
    c.decision_observed_at_utc,
    c.decision_captured_at_utc,
    v_frozen_at,
    c.reference_price,
    c.planned_entry_price,
    c.stop_price,
    c.target_price,
    c.reward_risk,
    c.best_bid,
    c.best_ask,
    c.midpoint,
    c.entry_cross_price,
    c.entry_cross_half_spread_bps,
    true,
    true,
    jsonb_build_object(
      'source','SEALED_PROSPECTIVE_DECISION_QUOTE',
      'run_source',c.run_source,
      'git_commit',c.git_commit,
      'config_sha256',c.config_sha256,
      'symbol_time_proximity_attribution_permitted',false,
      'explicit_fill_binding_required',true
    ),
    true,
    false,
    false,
    'NONE'
  );

  return jsonb_build_object(
    'execution_event_id',v_execution_event_id,
    'decision_observation_id',c.decision_observation_id,
    'symbol',c.symbol,
    'direction',c.direction,
    'action',c.action,
    'frozen_at_utc',v_frozen_at,
    'fill_binding_status','WAITING_FOR_EXPLICIT_USER_CONFIRMED_FILL',
    'trade_permission',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_freeze_execution_decision_v01(text)
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_freeze_execution_decision_v01(text)
  to service_role;


create or replace function private.alpha_hunter_bind_user_confirmed_fill_v01(
  p_execution_event_id text,
  p_fill_evidence_id text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $$
declare
  d public.alpha_hunter_execution_decision_freezes_v01%rowtype;
  f public.alpha_hunter_fill_evidence%rowtype;
  v_direction_ok boolean;
  v_binding_id text;
begin
  select x.* into d
  from public.alpha_hunter_execution_decision_freezes_v01 x
  where x.execution_event_id=p_execution_event_id;

  if d.execution_event_id is null then
    raise exception 'Frozen execution decision not found';
  end if;

  select x.* into f
  from public.alpha_hunter_fill_evidence x
  where x.fill_evidence_id=p_fill_evidence_id;

  if f.fill_evidence_id is null then
    raise exception 'Immutable fill evidence not found';
  end if;

  if upper(coalesce(f.symbol,''))<>upper(d.symbol) then
    raise exception 'Fill symbol does not match frozen decision';
  end if;

  if upper(coalesce(f.trade_side,''))<>'OPEN' then
    raise exception 'Only an opening fill may bind to a frozen entry decision';
  end if;

  v_direction_ok := (
    (d.direction='LONG' and upper(coalesce(f.side,''))='BUY')
    or
    (d.direction='SHORT' and upper(coalesce(f.side,''))='SELL')
  );

  if not v_direction_ok then
    raise exception 'Fill side does not match frozen decision direction';
  end if;

  if f.fill_time_utc<d.frozen_at_utc then
    raise exception 'Retrospective attribution prohibited: fill predates decision freeze';
  end if;

  v_binding_id := 'bind-'||md5(d.execution_event_id||'|'||f.fill_evidence_id);

  insert into public.alpha_hunter_execution_fill_bindings_v01(
    binding_id,
    execution_event_id,
    fill_evidence_id,
    explicit_user_confirmation,
    confirmation_source,
    evidence,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_binding_id,
    d.execution_event_id,
    f.fill_evidence_id,
    true,
    'USER_EXPLICIT',
    jsonb_build_object(
      'binding_law','EXACT_FILL_ID_ONLY',
      'symbol_time_proximity_attribution_permitted',false,
      'retrospective_attribution_permitted',false
    ),
    true,
    false,
    false,
    'NONE'
  );

  return jsonb_build_object(
    'binding_id',v_binding_id,
    'execution_event_id',d.execution_event_id,
    'fill_evidence_id',f.fill_evidence_id,
    'binding_status','EXPLICIT_USER_CONFIRMED',
    'trade_permission',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_bind_user_confirmed_fill_v01(text,text)
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_bind_user_confirmed_fill_v01(text,text)
  to service_role;


create or replace view public.alpha_hunter_verified_execution_attribution_v01
with (security_invoker=true,security_barrier=true) as
select
  d.execution_event_id,
  d.spec_id,
  d.decision_observation_id,
  d.strategy_instance_id,
  d.decision_run_id,
  d.symbol,
  d.strategy_id,
  d.direction,
  d.action,
  d.decision_observed_at_utc,
  d.decision_captured_at_utc,
  d.frozen_at_utc,
  d.reference_price,
  d.planned_entry_price,
  d.stop_price,
  d.target_price,
  d.reward_risk,
  d.best_bid,
  d.best_ask,
  d.midpoint,
  d.entry_cross_price,
  d.entry_cross_half_spread_bps,
  b.binding_id,
  b.bound_at_utc,
  b.explicit_user_confirmation,
  f.fill_evidence_id,
  f.fill_time_utc,
  f.symbol as fill_symbol,
  f.side as fill_side,
  f.trade_side,
  f.trade_scope,
  f.price as fill_price,
  f.base_volume as fill_base_volume,
  f.quote_volume as fill_quote_volume,
  f.fee_amount,
  f.fee_coin,
  o.order_evidence_id,
  o.order_identity_sha256,
  o.order_type,
  o.order_state,
  o.order_created_at_utc,
  o.order_average_price,
  o.origin_consistent,
  tr.complete as fill_trace_complete,
  tr.schema_validated as fill_trace_schema_validated,
  extract(epoch from (o.order_created_at_utc-d.frozen_at_utc))
    as freeze_to_order_seconds,
  extract(epoch from (f.fill_time_utc-o.order_created_at_utc))
    as order_to_fill_seconds,
  case
    when d.direction='LONG' and d.entry_cross_price>0
      then ((f.price-d.entry_cross_price)/d.entry_cross_price)*10000.0
    when d.direction='SHORT' and d.entry_cross_price>0
      then ((d.entry_cross_price-f.price)/d.entry_cross_price)*10000.0
    else null
  end as signed_adverse_arrival_to_fill_bps,
  case
    when f.quote_volume is not null and f.quote_volume<>0
         and f.fee_amount is not null
      then abs(f.fee_amount/f.quote_volume)*10000.0
    else null
  end as realized_fee_bps,
  (
    b.explicit_user_confirmation=true
    and f.fill_time_utc>=d.frozen_at_utc
    and upper(f.symbol)=upper(d.symbol)
    and upper(f.trade_side)='OPEN'
    and (
      (d.direction='LONG' and upper(f.side)='BUY')
      or
      (d.direction='SHORT' and upper(f.side)='SELL')
    )
    and tr.complete=true
    and tr.schema_validated=true
    and o.order_evidence_id is not null
    and o.order_identity_sha256 is not null
    and o.order_created_at_utc>=d.frozen_at_utc
    and f.fill_time_utc>=o.order_created_at_utc
    and o.origin_consistent=true
  ) as verified_alpha_hunter_execution,
  case
    when o.order_evidence_id is null
      then 'WAITING_FOR_READ_ONLY_ORDER_DETAIL'
    when not coalesce(tr.complete,false)
      or not coalesce(tr.schema_validated,false)
      then 'FILL_TRACEABILITY_INCOMPLETE'
    when o.order_created_at_utc<d.frozen_at_utc
      then 'RETROSPECTIVE_ATTRIBUTION_REJECTED'
    when f.fill_time_utc<o.order_created_at_utc
      then 'ORDER_FILL_TIME_INTEGRITY_ERROR'
    when o.origin_consistent is not true
      then 'ORDER_FILL_ORIGIN_INCONSISTENT'
    else 'VERIFIED_EXPLICIT_ATTRIBUTION'
  end as attribution_status,
  (
    o.order_evidence_id is not null
    and d.entry_cross_price is not null
    and f.price is not null
  ) as arrival_slippage_measured,
  false as cost_model_validated,
  false as realistic_net_r_claim_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_execution_decision_freezes_v01 d
join public.alpha_hunter_execution_fill_bindings_v01 b
  on b.execution_event_id=d.execution_event_id
join public.alpha_hunter_fill_evidence f
  on f.fill_evidence_id=b.fill_evidence_id
left join public.alpha_hunter_execution_order_evidence_v01 o
  on o.fill_evidence_id=f.fill_evidence_id
left join public.alpha_hunter_fill_traceability_runs tr
  on tr.traceability_run_id=f.traceability_run_id;

revoke all on public.alpha_hunter_verified_execution_attribution_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_verified_execution_attribution_v01
  to service_role;


create or replace view public.alpha_hunter_execution_attribution_status_v01
with (security_invoker=true,security_barrier=true) as
select
  (select count(*) from public.alpha_hunter_execution_decision_freezes_v01)
    as frozen_decisions,
  (select count(*) from public.alpha_hunter_execution_fill_bindings_v01)
    as explicit_fill_bindings,
  (select count(*)
   from public.alpha_hunter_verified_execution_attribution_v01
   where verified_alpha_hunter_execution)
    as verified_alpha_hunter_executions,
  (select count(*)
   from public.alpha_hunter_verified_execution_attribution_v01
   where attribution_status='WAITING_FOR_READ_ONLY_ORDER_DETAIL')
    as waiting_for_order_detail,
  (select count(*)
   from public.alpha_hunter_execution_attribution_candidates_v01
   where freeze_available)
    as current_freeze_candidates,
  false as slippage_model_validated,
  false as cost_model_validated,
  false as realistic_net_r_claim_permitted,
  case
    when (select count(*)
          from public.alpha_hunter_verified_execution_attribution_v01
          where verified_alpha_hunter_execution)>0
      then 'FIRST_VERIFIED_EXECUTION_CAPTURED_MORE_SAMPLE_REQUIRED'
    when (select count(*)
          from public.alpha_hunter_execution_fill_bindings_v01)>0
      then 'WAITING_FOR_ORDER_DETAIL_OR_INTEGRITY_GATES'
    when (select count(*)
          from public.alpha_hunter_execution_decision_freezes_v01)>0
      then 'WAITING_FOR_EXPLICIT_USER_EXECUTION_AND_FILL_BINDING'
    else 'WAITING_FOR_FIRST_EXPLICIT_USER_SELECTED_ALPHA_HUNTER_TRADE'
  end as validation_status,
  'FREEZE_DECISION_BEFORE_USER_EXECUTION_THEN_BIND_EXACT_FILL'::text
    as next_gate,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path;

revoke all on public.alpha_hunter_execution_attribution_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_attribution_status_v01
  to service_role;
