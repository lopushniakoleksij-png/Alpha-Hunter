-- Alpha Hunter protection reconciliation audit v0.1
-- Forward-only audit of immutable canonical open-position evidence.
-- No exchange/network call. No order authority. No historical mutation.

create table if not exists public.alpha_hunter_protection_reconciliation_events_v01 (
  event_id text primary key,
  position_snapshot_id text not null,
  account_snapshot_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null,
  observation_status text not null,
  protection_state text not null check (
    protection_state in (
      'OBSERVED_BOTH',
      'OBSERVED_STOP_ONLY',
      'OBSERVED_TP_ONLY',
      'NONE_OBSERVED',
      'UNKNOWN'
    )
  ),
  stop_loss_observed text,
  take_profit_observed text,
  stop_loss_source text,
  take_profit_source text,
  stop_order_count integer not null default 0 check (stop_order_count >= 0),
  take_profit_order_count integer not null default 0 check (take_profit_order_count >= 0),
  position_field_gap_detected boolean not null default false,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  model_version text not null default 'protection-reconciliation-audit-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_protection_reconciliation_events_v01
  enable row level security;

revoke all on table public.alpha_hunter_protection_reconciliation_events_v01
  from public,anon,authenticated;

grant select,insert on table public.alpha_hunter_protection_reconciliation_events_v01
  to service_role;

create index if not exists idx_ah_protection_recon_symbol_time
  on public.alpha_hunter_protection_reconciliation_events_v01(
    symbol,captured_at_utc desc
  );

drop trigger if exists trg_ah_protection_reconciliation_events_append_only
  on public.alpha_hunter_protection_reconciliation_events_v01;
create trigger trg_ah_protection_reconciliation_events_append_only
before update or delete on public.alpha_hunter_protection_reconciliation_events_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_materialize_protection_reconciliation_v01()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_orders jsonb := case
    when jsonb_typeof(new.evidence->'exchange_protection_orders_observed')='array'
      then new.evidence->'exchange_protection_orders_observed'
    else '[]'::jsonb
  end;
  v_observation_status text := upper(coalesce(
    nullif(new.evidence->>'exchange_protection_observation_status',''),
    'UNKNOWN'
  ));
  v_stop text := nullif(btrim(coalesce(
    new.evidence->>'exchange_stop_loss_observed',''
  )),'');
  v_take text := nullif(btrim(coalesce(
    new.evidence->>'exchange_take_profit_observed',''
  )),'');
  v_stop_source text := nullif(btrim(coalesce(
    new.evidence->>'exchange_stop_loss_source',''
  )),'');
  v_take_source text := nullif(btrim(coalesce(
    new.evidence->>'exchange_take_profit_source',''
  )),'');
  v_stop_order_count integer := 0;
  v_take_order_count integer := 0;
  v_stop_present boolean := false;
  v_take_present boolean := false;
  v_state text := 'UNKNOWN';
  v_gap boolean := false;
begin
  select count(*)::integer into v_stop_order_count
  from jsonb_array_elements(v_orders) o(value)
  where lower(coalesce(o.value->>'plan_type','')) in ('loss_plan','pos_loss');

  select count(*)::integer into v_take_order_count
  from jsonb_array_elements(v_orders) o(value)
  where lower(coalesce(o.value->>'plan_type','')) in ('profit_plan','pos_profit');

  v_stop_present := v_stop is not null or v_stop_order_count > 0;
  v_take_present := v_take is not null or v_take_order_count > 0;
  v_gap := coalesce(v_stop_source,'')='PENDING_TPSL'
        or coalesce(v_take_source,'')='PENDING_TPSL';

  if v_observation_status <> 'CONNECTED' then
    v_state := 'UNKNOWN';
  elsif v_stop_present and v_take_present then
    v_state := 'OBSERVED_BOTH';
  elsif v_stop_present then
    v_state := 'OBSERVED_STOP_ONLY';
  elsif v_take_present then
    v_state := 'OBSERVED_TP_ONLY';
  else
    v_state := 'NONE_OBSERVED';
  end if;

  insert into public.alpha_hunter_protection_reconciliation_events_v01(
    event_id,
    position_snapshot_id,
    account_snapshot_id,
    captured_at_utc,
    symbol,
    direction,
    observation_status,
    protection_state,
    stop_loss_observed,
    take_profit_observed,
    stop_loss_source,
    take_profit_source,
    stop_order_count,
    take_profit_order_count,
    position_field_gap_detected,
    details,
    model_version,
    shadow_only,
    trade_permission
  ) values (
    substr(
      encode(
        extensions.digest(
          'protection-reconciliation-audit-v0.1|' || new.position_snapshot_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    ),
    new.position_snapshot_id,
    new.account_snapshot_id,
    new.captured_at_utc,
    new.symbol,
    new.direction,
    v_observation_status,
    v_state,
    v_stop,
    v_take,
    v_stop_source,
    v_take_source,
    v_stop_order_count,
    v_take_order_count,
    v_gap,
    jsonb_build_object(
      'exchange_protection_absence_confirmed',
        coalesce(
          (new.evidence->>'exchange_protection_absence_confirmed')::boolean,
          false
        ),
      'protection_order_count',jsonb_array_length(v_orders),
      'structural_stop_inferred_from_exchange_stop',
        coalesce(
          (new.evidence->>'structural_stop_inferred_from_exchange_stop')::boolean,
          false
        ),
      'source',new.evidence->>'source',
      'forward_only',true,
      'no_exchange_call',true
    ),
    'protection-reconciliation-audit-v0.1',
    true,
    false
  )
  on conflict(event_id) do nothing;

  return new;
exception when others then
  -- Audit failure must not block canonical position persistence.
  return new;
end;
$$;

revoke all on function private.alpha_hunter_materialize_protection_reconciliation_v01()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_materialize_protection_reconciliation_v01()
  to service_role;

drop trigger if exists trg_ah_materialize_protection_reconciliation_v01
  on public.alpha_hunter_open_position_snapshots;
create trigger trg_ah_materialize_protection_reconciliation_v01
after insert on public.alpha_hunter_open_position_snapshots
for each row execute function private.alpha_hunter_materialize_protection_reconciliation_v01();


create or replace view public.alpha_hunter_protection_reconciliation_current_v01
with (security_invoker=true,security_barrier=true) as
with base as (
  select
    p.position_snapshot_id,
    p.account_snapshot_id,
    p.captured_at_utc,
    a.evidence->>'canonical_run_id' as canonical_run_id,
    p.symbol,
    p.direction,
    p.quantity,
    p.average_entry,
    p.mark_price,
    upper(coalesce(
      nullif(p.evidence->>'exchange_protection_observation_status',''),
      'UNKNOWN'
    )) as observation_status,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_stop_loss_observed',''
    )),'') as stop_loss_observed,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_take_profit_observed',''
    )),'') as take_profit_observed,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_stop_loss_source',''
    )),'') as stop_loss_source,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_take_profit_source',''
    )),'') as take_profit_source,
    case
      when jsonb_typeof(p.evidence->'exchange_protection_orders_observed')='array'
        then p.evidence->'exchange_protection_orders_observed'
      else '[]'::jsonb
    end as protection_orders
  from public.alpha_hunter_open_position_snapshots p
  left join public.alpha_hunter_account_state_snapshots a
    on a.account_snapshot_id=p.account_snapshot_id
),
counts as (
  select
    b.*,
    (
      select count(*)::integer
      from jsonb_array_elements(b.protection_orders) o(value)
      where lower(coalesce(o.value->>'plan_type','')) in ('loss_plan','pos_loss')
    ) as stop_order_count,
    (
      select count(*)::integer
      from jsonb_array_elements(b.protection_orders) o(value)
      where lower(coalesce(o.value->>'plan_type','')) in ('profit_plan','pos_profit')
    ) as take_profit_order_count
  from base b
),
classified as (
  select
    c.*,
    (c.stop_loss_observed is not null or c.stop_order_count>0) as stop_present,
    (c.take_profit_observed is not null or c.take_profit_order_count>0) as take_profit_present,
    (
      coalesce(c.stop_loss_source,'')='PENDING_TPSL'
      or coalesce(c.take_profit_source,'')='PENDING_TPSL'
    ) as position_field_gap_detected
  from counts c
)
select
  position_snapshot_id,
  account_snapshot_id,
  captured_at_utc,
  canonical_run_id,
  symbol,
  direction,
  quantity,
  average_entry,
  mark_price,
  observation_status,
  case
    when observation_status <> 'CONNECTED' then 'UNKNOWN'
    when stop_present and take_profit_present then 'OBSERVED_BOTH'
    when stop_present then 'OBSERVED_STOP_ONLY'
    when take_profit_present then 'OBSERVED_TP_ONLY'
    else 'NONE_OBSERVED'
  end as protection_state,
  stop_loss_observed,
  take_profit_observed,
  stop_loss_source,
  take_profit_source,
  stop_order_count,
  take_profit_order_count,
  position_field_gap_detected,
  protection_orders,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from classified;

revoke all on public.alpha_hunter_protection_reconciliation_current_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_protection_reconciliation_current_v01
  to service_role;
