-- P0 explicit prospective decision -> exact Bitget fill binding.
-- This is evidence attribution only. It cannot create, modify, cancel or route an exchange order.

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

    raise exception 'Execution event or fill evidence is already bound to a different record';
  end if;

  select x.* into f
  from public.alpha_hunter_fill_evidence x
  where x.fill_evidence_id = p_fill_evidence_id
  limit 1;

  if f.fill_evidence_id is null then
    raise exception 'Exact fill evidence not found';
  end if;

  if f.fill_time_utc < d.frozen_at_utc then
    raise exception 'Retrospective attribution rejected: fill predates frozen decision';
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
    raise exception 'Retrospective attribution rejected: order predates frozen decision';
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

revoke all on function private.alpha_hunter_bind_execution_fill_v01(text,text,boolean)
from public, anon, authenticated;

grant execute on function private.alpha_hunter_bind_execution_fill_v01(text,text,boolean)
to service_role;

create or replace function public.alpha_hunter_bind_execution_fill_api_v01(
  p_execution_event_id text,
  p_fill_evidence_id text,
  p_explicit_user_confirmation boolean
)
returns jsonb
language sql
security invoker
set search_path = ''
as $$
  select private.alpha_hunter_bind_execution_fill_v01(
    p_execution_event_id,
    p_fill_evidence_id,
    p_explicit_user_confirmation
  );
$$;

revoke all on function public.alpha_hunter_bind_execution_fill_api_v01(text,text,boolean)
from public, anon, authenticated;

grant execute on function public.alpha_hunter_bind_execution_fill_api_v01(text,text,boolean)
to service_role;

comment on function public.alpha_hunter_bind_execution_fill_api_v01(text,text,boolean)
is 'Service-role-only explicit exact fill binding for a frozen Alpha Hunter decision. No proximity attribution; no exchange write authority.';
