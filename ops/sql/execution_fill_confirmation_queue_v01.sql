begin;

-- Alpha Hunter exact fill confirmation queue v0.1.
--
-- Purpose:
--   Surface evidence-complete candidate pairs between a prospectively frozen
--   Alpha Hunter decision and an immutable real Bitget OPEN fill.
--
-- This is NOT attribution. Candidate pairs remain unverified until the operator
-- explicitly confirms the exact fill through the existing binding RPC.
--
-- Integrity:
-- - current/latest activated sealed spec only;
-- - same symbol and direction-compatible opening side;
-- - exact order evidence and complete traceability required;
-- - order must be created after freeze and inside the sealed cadence window;
-- - fill must occur after the exact order was created;
-- - already-bound events/fills are excluded;
-- - ambiguity is exposed, never auto-resolved;
-- - no automatic binding, order path, trade permission, or promotion authority.

create or replace view public.alpha_hunter_execution_fill_confirmation_candidates_v01
with (security_invoker=true,security_barrier=true)
as
with active as (
  select
    a.spec_id,
    a.started_at_utc,
    coalesce(c.maximum_interval_minutes,35)::integer
      as maximum_interval_minutes
  from public.alpha_hunter_profitability_test_activations_v01 a
  left join public.alpha_hunter_profitability_cadence_contract_v01 c
    on c.spec_id=a.spec_id
  order by a.started_at_utc desc,a.activated_at_utc desc
  limit 1
),
base as (
  select
    d.execution_event_id,
    d.spec_id,
    d.decision_observation_id,
    d.strategy_instance_id,
    d.strategy_id,
    d.symbol,
    d.direction,
    d.action,
    d.frozen_at_utc,
    d.planned_entry_price,
    d.stop_price,
    d.target_price,
    d.reward_risk,
    d.best_bid,
    d.best_ask,
    d.midpoint,
    d.entry_cross_price,
    d.entry_cross_half_spread_bps,

    f.fill_evidence_id,
    f.traceability_run_id,
    f.fill_time_utc,
    f.trade_id,
    f.order_id,
    f.side,
    f.trade_side,
    f.trade_scope,
    f.price,
    f.base_volume,
    f.quote_volume,
    f.fee_amount,
    f.fee_coin,
    f.cost_fields_complete,

    o.order_evidence_id,
    o.order_identity_sha256,
    o.order_type,
    o.order_state,
    o.order_created_at_utc,
    o.order_average_price,
    o.origin_consistent,

    tr.complete as trace_complete,
    tr.schema_validated as trace_schema_validated,

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
    end as candidate_adverse_arrival_to_fill_bps,

    case
      when f.quote_volume is not null and f.quote_volume<>0
           and f.fee_amount is not null
        then abs(f.fee_amount/f.quote_volume)*10000.0
      else null
    end as realized_fee_bps,

    a.maximum_interval_minutes
  from active a
  join public.alpha_hunter_execution_decision_freezes_v01 d
    on d.spec_id=a.spec_id
   and d.frozen_at_utc>=a.started_at_utc
  join public.alpha_hunter_fill_evidence f
    on upper(f.symbol)=upper(d.symbol)
   and upper(coalesce(f.trade_side,''))='OPEN'
   and (
     (d.direction='LONG' and upper(f.side)='BUY')
     or
     (d.direction='SHORT' and upper(f.side)='SELL')
   )
  join public.alpha_hunter_execution_order_evidence_v01 o
    on o.fill_evidence_id=f.fill_evidence_id
  join public.alpha_hunter_fill_traceability_runs tr
    on tr.traceability_run_id=f.traceability_run_id
  where not exists (
      select 1
      from public.alpha_hunter_execution_fill_bindings_v01 b
      where b.execution_event_id=d.execution_event_id
         or b.fill_evidence_id=f.fill_evidence_id
    )
    and tr.complete=true
    and tr.schema_validated=true
    and o.order_evidence_id is not null
    and o.order_identity_sha256 is not null
    and o.order_created_at_utc is not null
    and o.origin_consistent=true
    and f.cost_fields_complete=true
    and o.order_created_at_utc>=d.frozen_at_utc
    and o.order_created_at_utc
        <=d.frozen_at_utc
          + make_interval(mins=>a.maximum_interval_minutes)
    and f.fill_time_utc>=o.order_created_at_utc
),
scored as (
  select
    b.*,
    count(*) over(partition by b.fill_evidence_id)
      as fill_candidate_count,
    count(*) over(partition by b.execution_event_id)
      as event_candidate_count,
    row_number() over(
      partition by b.fill_evidence_id
      order by b.freeze_to_order_seconds asc,b.frozen_at_utc desc,
               b.execution_event_id
    ) as fill_candidate_rank,
    row_number() over(
      partition by b.execution_event_id
      order by b.freeze_to_order_seconds asc,b.fill_time_utc asc,
               b.fill_evidence_id
    ) as event_candidate_rank
  from base b
)
select
  s.*,
  case
    when s.fill_candidate_count=1 and s.event_candidate_count=1
      then 'UNIQUE_EVIDENCE_COMPLETE_MATCH'
    else 'AMBIGUOUS_EVIDENCE_COMPLETE_MATCH'
  end as candidate_status,
  true as explicit_user_confirmation_required,
  false as automatic_binding_permitted,
  false as attribution_claim_permitted,
  false as slippage_claim_permitted,
  false as cost_model_activation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from scored s;

revoke all on public.alpha_hunter_execution_fill_confirmation_candidates_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_fill_confirmation_candidates_v01
  to service_role;


create or replace view public.alpha_hunter_execution_fill_confirmation_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::bigint as candidate_pair_count,
  count(distinct execution_event_id)::bigint as frozen_events_with_candidates,
  count(distinct fill_evidence_id)::bigint as unbound_fills_with_candidates,
  count(*) filter(
    where candidate_status='UNIQUE_EVIDENCE_COMPLETE_MATCH'
  )::bigint as unique_candidate_pairs,
  count(*) filter(
    where candidate_status='AMBIGUOUS_EVIDENCE_COMPLETE_MATCH'
  )::bigint as ambiguous_candidate_pairs,
  (
    select count(*)::bigint
    from public.alpha_hunter_execution_fill_bindings_v01
  ) as explicit_fill_bindings,
  (
    select count(*)::bigint
    from public.alpha_hunter_verified_execution_attribution_v01
    where verified_alpha_hunter_execution=true
  ) as verified_alpha_hunter_executions,
  false as automatic_binding_permitted,
  true as explicit_user_confirmation_required,
  false as cost_model_activation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_execution_fill_confirmation_candidates_v01;

revoke all on public.alpha_hunter_execution_fill_confirmation_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_fill_confirmation_status_v01
  to service_role;


create or replace function private.alpha_hunter_bind_execution_fill_v01(
  p_execution_event_id text,
  p_fill_evidence_id text,
  p_explicit_user_confirmation boolean
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  d public.alpha_hunter_execution_decision_freezes_v01%rowtype;
  f public.alpha_hunter_fill_evidence%rowtype;
  tr public.alpha_hunter_fill_traceability_runs%rowtype;
  o public.alpha_hunter_execution_order_evidence_v01%rowtype;
  b public.alpha_hunter_execution_fill_bindings_v01%rowtype;
  v_binding_id text;
  v_expected_side text;
  v_max_interval_minutes integer:=35;
begin
  if p_explicit_user_confirmation is not true then
    raise exception 'Exact fill binding requires explicit user confirmation';
  end if;

  select x.* into d
  from public.alpha_hunter_execution_decision_freezes_v01 x
  where x.execution_event_id = p_execution_event_id
  limit 1;

  if d.execution_event_id is null then
    raise exception 'Frozen execution event not found';
  end if;

  select coalesce(c.maximum_interval_minutes,35)::integer
    into v_max_interval_minutes
  from public.alpha_hunter_profitability_cadence_contract_v01 c
  where c.spec_id=d.spec_id
  limit 1;

  v_max_interval_minutes:=coalesce(v_max_interval_minutes,35);

  select x.* into b
  from public.alpha_hunter_execution_fill_bindings_v01 x
  where x.execution_event_id = p_execution_event_id
     or x.fill_evidence_id = p_fill_evidence_id
  order by x.created_at asc
  limit 1;

  if b.binding_id is not null then
    if b.execution_event_id = p_execution_event_id
       and b.fill_evidence_id = p_fill_evidence_id then
      return jsonb_build_object(
        'binding_id', b.binding_id,
        'execution_event_id', b.execution_event_id,
        'fill_evidence_id', b.fill_evidence_id,
        'bound_at_utc', b.bound_at_utc,
        'already_bound', true,
        'trade_permission', false,
        'production_promotion_permitted', false,
        'order_path', 'NONE'
      );
    end if;

    raise exception
      'Execution event or fill evidence is already bound to a different record';
  end if;

  select x.* into f
  from public.alpha_hunter_fill_evidence x
  where x.fill_evidence_id = p_fill_evidence_id
  limit 1;

  if f.fill_evidence_id is null then
    raise exception 'Exact fill evidence not found';
  end if;

  if f.fill_time_utc < d.frozen_at_utc then
    raise exception
      'Retrospective attribution rejected: fill predates frozen decision';
  end if;

  if upper(f.symbol) <> upper(d.symbol) then
    raise exception 'Fill symbol does not match frozen decision';
  end if;

  if upper(coalesce(f.trade_side, '')) <> 'OPEN' then
    raise exception 'Fill is not an OPEN execution';
  end if;

  v_expected_side := case
    when d.direction = 'LONG' then 'BUY'
    when d.direction = 'SHORT' then 'SELL'
    else null
  end;

  if v_expected_side is null or upper(f.side) <> v_expected_side then
    raise exception 'Fill side does not match frozen decision direction';
  end if;

  select x.* into tr
  from public.alpha_hunter_fill_traceability_runs x
  where x.traceability_run_id = f.traceability_run_id
  limit 1;

  if tr.traceability_run_id is null
     or tr.complete is not true
     or tr.schema_validated is not true then
    raise exception 'Fill traceability is incomplete or schema-invalid';
  end if;

  select x.* into o
  from public.alpha_hunter_execution_order_evidence_v01 x
  where x.fill_evidence_id = f.fill_evidence_id
  order by x.observed_at_utc desc
  limit 1;

  if o.order_evidence_id is null
     or o.order_identity_sha256 is null
     or o.order_created_at_utc is null then
    raise exception 'Read-only exact order evidence is incomplete';
  end if;

  if o.order_created_at_utc < d.frozen_at_utc then
    raise exception
      'Retrospective attribution rejected: order predates frozen decision';
  end if;

  if o.order_created_at_utc
     > d.frozen_at_utc + make_interval(mins=>v_max_interval_minutes) then
    raise exception
      'Stale attribution rejected: order was created after the sealed decision freshness window';
  end if;

  if f.fill_time_utc < o.order_created_at_utc then
    raise exception 'Order/fill time integrity error';
  end if;

  if o.origin_consistent is not true then
    raise exception 'Order/fill origin is not consistent';
  end if;

  if f.cost_fields_complete is not true then
    raise exception 'Fill cost fields are incomplete';
  end if;

  if not exists (
    select 1
    from public.alpha_hunter_execution_fill_confirmation_candidates_v01 c
    where c.execution_event_id=d.execution_event_id
      and c.fill_evidence_id=f.fill_evidence_id
  ) then
    raise exception
      'Exact pair is not a current evidence-complete confirmation candidate';
  end if;

  v_binding_id := 'bind-' || md5(
    d.execution_event_id || '|' || f.fill_evidence_id
  );

  insert into public.alpha_hunter_execution_fill_bindings_v01(
    binding_id,
    execution_event_id,
    fill_evidence_id,
    bound_at_utc,
    explicit_user_confirmation,
    confirmation_source,
    evidence,
    scientific_role,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_binding_id,
    d.execution_event_id,
    f.fill_evidence_id,
    clock_timestamp(),
    true,
    'USER_EXPLICIT',
    jsonb_build_object(
      'binding_mode', 'USER_EXPLICIT_EXACT_FILL',
      'exact_fill_evidence_id', f.fill_evidence_id,
      'exact_trade_id_selected', true,
      'exact_order_id_selected', true,
      'order_evidence_id', o.order_evidence_id,
      'order_identity_sha256', o.order_identity_sha256,
      'traceability_run_id', f.traceability_run_id,
      'trace_complete', true,
      'trace_schema_validated', true,
      'maximum_decision_to_order_minutes',v_max_interval_minutes,
      'decision_freshness_enforced',true,
      'candidate_queue_gate_passed',true,
      'symbol_time_proximity_attribution_permitted', false,
      'automatic_binding_permitted', false
    ),
    'EXPLICIT_USER_FILL_BINDING',
    true,
    false,
    false,
    'NONE'
  )
  returning * into b;

  return jsonb_build_object(
    'binding_id', b.binding_id,
    'execution_event_id', b.execution_event_id,
    'fill_evidence_id', b.fill_evidence_id,
    'trade_id', f.trade_id,
    'order_id', f.order_id,
    'symbol', f.symbol,
    'side', f.side,
    'fill_time_utc', f.fill_time_utc,
    'fill_price', f.price,
    'fee_amount', f.fee_amount,
    'fee_coin', f.fee_coin,
    'order_evidence_id', o.order_evidence_id,
    'order_identity_sha256', o.order_identity_sha256,
    'bound_at_utc', b.bound_at_utc,
    'verified_attribution_ready_for_view', true,
    'trade_permission', false,
    'production_promotion_permitted', false,
    'order_path', 'NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_bind_execution_fill_v01(
  text,text,boolean
) from public,anon,authenticated;

grant execute on function private.alpha_hunter_bind_execution_fill_v01(
  text,text,boolean
) to service_role;

commit;
