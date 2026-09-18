-- Alpha Hunter canonical account-ledger materialization v0.1
-- Forward-only: materializes account/position evidence when a NEW canonical scanner
-- snapshot is inserted. No historical backfill and no exchange/network call.
-- Missing or malformed private-account evidence is persisted fail-closed and can
-- never grant READY or trade permission.

create table if not exists public.alpha_hunter_account_ledger_materialization_events (
  event_id text primary key,
  run_id text not null,
  captured_at_utc timestamptz not null,
  status text not null check (status in (
    'MATERIALIZED_CONNECTED',
    'MATERIALIZED_DISCONNECTED',
    'MATERIALIZED_INSUFFICIENT',
    'FAILED'
  )),
  account_snapshot_id text,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  model_version text not null default 'canonical-account-ledger-materialization-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_account_ledger_materialization_events enable row level security;
revoke all on table public.alpha_hunter_account_ledger_materialization_events from public,anon,authenticated;
grant select,insert on table public.alpha_hunter_account_ledger_materialization_events to service_role;

create index if not exists idx_ah_account_materialization_events_time
  on public.alpha_hunter_account_ledger_materialization_events(captured_at_utc desc);

drop trigger if exists trg_ah_account_materialization_events_append_only
  on public.alpha_hunter_account_ledger_materialization_events;
create trigger trg_ah_account_materialization_events_append_only
before update or delete on public.alpha_hunter_account_ledger_materialization_events
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_materialize_account_ledger_from_snapshot()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_private jsonb := coalesce(new.payload->'private_account','{}'::jsonb);
  v_scanner_status text;
  v_account_snapshot_id text;
  v_usdt_account jsonb;
  v_positions jsonb := '[]'::jsonb;
  v_position_count integer := 0;
  v_claimed_position_count integer;
  v_invalid_positions integer := 0;
  v_distinct_positions integer := 0;
  v_schema_errors jsonb := '[]'::jsonb;
  v_schema_validated boolean := false;
  v_complete boolean := false;
  v_connection_status text := 'DATA_INSUFFICIENT';
  v_event_status text := 'MATERIALIZED_INSUFFICIENT';
  v_equity double precision;
  v_available double precision;
  v_unrealized double precision;
  v_locked text;
begin
  v_account_snapshot_id := substr(
    encode(
      extensions.digest(
        'canonical-account-ledger-v0.1|' || new.run_id,
        'sha256'
      ),
      'hex'
    ),
    1,
    32
  );

  if jsonb_typeof(v_private) <> 'object' then
    v_private := '{}'::jsonb;
    v_schema_errors := v_schema_errors || jsonb_build_array('PRIVATE_ACCOUNT_NOT_OBJECT');
  end if;

  v_scanner_status := upper(coalesce(nullif(v_private->>'status',''),'MISSING'));

  if v_scanner_status = 'CONNECTED' then
    if jsonb_typeof(v_private->'accounts') <> 'array' then
      v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNTS_NOT_LIST');
    else
      select a.value into v_usdt_account
      from jsonb_array_elements(v_private->'accounts') a(value)
      where jsonb_typeof(a.value)='object'
        and upper(coalesce(a.value->>'margin_coin',''))='USDT'
      limit 1;

      if v_usdt_account is null then
        v_schema_errors := v_schema_errors || jsonb_build_array('USDT_ACCOUNT_MISSING');
      else
        v_equity := private.alpha_hunter_text_float(v_usdt_account->>'account_equity');
        v_available := private.alpha_hunter_text_float(v_usdt_account->>'available');
        v_unrealized := private.alpha_hunter_text_float(v_usdt_account->>'unrealized_pl');
        v_locked := v_usdt_account->>'locked';

        if v_equity is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_ACCOUNT_EQUITY_INVALID');
        end if;
        if v_available is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_AVAILABLE_INVALID');
        end if;
        if v_unrealized is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_UNREALIZED_PL_INVALID');
        end if;
      end if;
    end if;

    if jsonb_typeof(v_private->'open_positions') <> 'array' then
      v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITIONS_NOT_LIST');
    else
      v_positions := v_private->'open_positions';
      v_position_count := jsonb_array_length(v_positions);

      if coalesce(v_private->>'open_position_count','') ~ '^[0-9]+$' then
        v_claimed_position_count := (v_private->>'open_position_count')::integer;
        if v_claimed_position_count <> v_position_count then
          v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_COUNT_CLAIM_MISMATCH');
        end if;
      else
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_COUNT_CLAIM_INVALID');
      end if;

      select count(*)::integer into v_invalid_positions
      from jsonb_array_elements(v_positions) p(value)
      where jsonb_typeof(p.value)<>'object'
         or nullif(upper(coalesce(p.value->>'symbol','')),'') is null
         or lower(coalesce(p.value->>'hold_side','')) not in ('long','short')
         or private.alpha_hunter_text_float(p.value->>'total') is null
         or private.alpha_hunter_text_float(p.value->>'total')=0;

      if v_invalid_positions > 0 then
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_SCHEMA_INVALID');
      end if;

      select count(distinct (
        upper(coalesce(p.value->>'symbol','')) || '|' || lower(coalesce(p.value->>'hold_side',''))
      ))::integer into v_distinct_positions
      from jsonb_array_elements(v_positions) p(value)
      where jsonb_typeof(p.value)='object';

      if v_distinct_positions <> v_position_count then
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_DUPLICATE_SYMBOL_DIRECTION');
      end if;
    end if;

    v_schema_validated := jsonb_array_length(v_schema_errors)=0;
    v_complete := v_schema_validated;
    if v_complete then
      v_connection_status := 'CONNECTED_READ_ONLY';
      v_event_status := 'MATERIALIZED_CONNECTED';
    else
      v_connection_status := 'DATA_INSUFFICIENT';
      v_event_status := 'MATERIALIZED_INSUFFICIENT';
    end if;

  elsif v_scanner_status = 'NOT_CONFIGURED' then
    v_connection_status := 'DISCONNECTED';
    v_schema_errors := v_schema_errors || jsonb_build_array('PRIVATE_API_NOT_CONFIGURED');
    v_event_status := 'MATERIALIZED_DISCONNECTED';
  else
    v_connection_status := 'DATA_INSUFFICIENT';
    v_schema_errors := v_schema_errors || jsonb_build_array(
      'SCANNER_PRIVATE_ACCOUNT_STATUS_' || v_scanner_status
    );
    v_event_status := 'MATERIALIZED_INSUFFICIENT';
  end if;

  insert into public.alpha_hunter_account_state_snapshots(
    account_snapshot_id,captured_at_utc,equity_usdt,available_usdt,margin_used_usdt,
    unrealized_pnl_usdt,daily_realized_pnl_usdt,source,connection_status,
    schema_validated,complete,evidence,shadow_only,trade_permission
  ) values (
    v_account_snapshot_id,
    new.collected_at_utc,
    case when v_complete then v_equity end,
    case when v_complete then v_available end,
    null,
    case when v_complete then v_unrealized end,
    null,
    'CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE',
    v_connection_status,
    v_schema_validated,
    v_complete,
    jsonb_build_object(
      'model_version','canonical-account-ledger-v0.1',
      'materialization_model_version','canonical-account-ledger-materialization-v0.1',
      'canonical_run_id',new.run_id,
      'scanner_private_account_status',v_scanner_status,
      'account_count',case when jsonb_typeof(v_private->'accounts')='array' then jsonb_array_length(v_private->'accounts') else null end,
      'scanner_open_position_count',v_private->'open_position_count',
      'persisted_open_position_count',case when v_complete then v_position_count else 0 end,
      'api_permission_probe_status',v_private->>'api_permission_probe_status',
      'api_permission_probe_error',v_private->>'api_permission_probe_error',
      'api_permission_type',v_private->>'api_permission_type',
      'api_permissions',case when jsonb_typeof(v_private->'api_permissions')='array' then v_private->'api_permissions' else '[]'::jsonb end,
      'permission_metadata_is_trade_authority',false,
      'locked_observed',case when v_usdt_account is null then null else v_locked end,
      'margin_used_inferred_from_locked',false,
      'daily_realized_pnl_invented',false,
      'schema_errors',v_schema_errors,
      'no_extra_bitget_request',true,
      'cached_payload_only',true,
      'materialized_at_snapshot_insert',true
    ),
    true,
    false
  ) on conflict(account_snapshot_id) do nothing;

  if v_complete and v_position_count>0 then
    insert into public.alpha_hunter_open_position_snapshots(
      position_snapshot_id,account_snapshot_id,captured_at_utc,symbol,direction,quantity,
      average_entry,mark_price,liquidation_price,notional_usdt,unrealized_pnl_usdt,
      source_position_id,structural_stop_price,planned_risk_usdt,strategy_event_id,
      source_order_intent_id,evidence,shadow_only,trade_permission
    )
    select
      substr(
        encode(
          extensions.digest(
            'canonical-account-ledger-v0.1|' || v_account_snapshot_id || '|' ||
            upper(p.value->>'symbol') || '|' ||
            case lower(p.value->>'hold_side') when 'long' then 'LONG' else 'SHORT' end,
            'sha256'
          ),
          'hex'
        ),
        1,
        32
      ),
      v_account_snapshot_id,
      new.collected_at_utc,
      upper(p.value->>'symbol'),
      case lower(p.value->>'hold_side') when 'long' then 'LONG' else 'SHORT' end,
      abs(private.alpha_hunter_text_float(p.value->>'total')),
      private.alpha_hunter_text_float(p.value->>'open_price_avg'),
      private.alpha_hunter_text_float(p.value->>'mark_price'),
      private.alpha_hunter_text_float(p.value->>'liquidation_price'),
      null,
      private.alpha_hunter_text_float(p.value->>'unrealized_pl'),
      null,
      null,
      null,
      null,
      null,
      jsonb_build_object(
        'source','CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE',
        'margin_mode',p.value->>'margin_mode',
        'leverage',p.value->>'leverage',
        'available_quantity',p.value->>'available',
        'break_even_price',p.value->>'break_even_price',
        'exchange_take_profit_observed',p.value->>'take_profit',
        'exchange_stop_loss_observed',p.value->>'stop_loss',
        'structural_stop_inferred_from_exchange_stop',false,
        'planned_risk_invented',false,
        'notional_invented',false,
        'no_extra_bitget_request',true,
        'materialized_at_snapshot_insert',true
      ),
      true,
      false
    from jsonb_array_elements(v_positions) p(value)
    on conflict(position_snapshot_id) do nothing;
  end if;

  insert into public.alpha_hunter_account_ledger_materialization_events(
    event_id,run_id,captured_at_utc,status,account_snapshot_id,details,
    model_version,shadow_only,trade_permission
  ) values (
    substr(
      encode(
        extensions.digest(
          'canonical-account-ledger-materialization-v0.1|' || new.run_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    ),
    new.run_id,
    new.collected_at_utc,
    v_event_status,
    v_account_snapshot_id,
    jsonb_build_object(
      'scanner_private_account_status',v_scanner_status,
      'connection_status',v_connection_status,
      'schema_validated',v_schema_validated,
      'complete',v_complete,
      'schema_errors',v_schema_errors,
      'position_count',case when v_complete then v_position_count else 0 end,
      'api_permission_probe_status',v_private->>'api_permission_probe_status',
      'api_permission_type',v_private->>'api_permission_type',
      'permission_metadata_is_trade_authority',false,
      'snapshot_persistence_preserved',true,
      'no_exchange_call',true
    ),
    'canonical-account-ledger-materialization-v0.1',
    true,
    false
  ) on conflict(event_id) do nothing;

  return new;
exception when others then
  -- Account-ledger failure must never destroy the canonical market snapshot.
  begin
    insert into public.alpha_hunter_account_ledger_materialization_events(
      event_id,run_id,captured_at_utc,status,account_snapshot_id,details,
      model_version,shadow_only,trade_permission
    ) values (
      substr(
        encode(
          extensions.digest(
            'canonical-account-ledger-materialization-v0.1|' || new.run_id,
            'sha256'
          ),
          'hex'
        ),
        1,
        32
      ),
      new.run_id,
      new.collected_at_utc,
      'FAILED',
      v_account_snapshot_id,
      jsonb_build_object(
        'sqlstate',sqlstate,
        'error',left(sqlerrm,1000),
        'snapshot_persistence_preserved',true,
        'readiness_fail_closed',true,
        'no_exchange_call',true
      ),
      'canonical-account-ledger-materialization-v0.1',
      true,
      false
    ) on conflict(event_id) do nothing;
  exception when others then
    null;
  end;
  return new;
end;
$$;

revoke all on function private.alpha_hunter_materialize_account_ledger_from_snapshot() from public,anon,authenticated;
grant execute on function private.alpha_hunter_materialize_account_ledger_from_snapshot() to service_role;

drop trigger if exists trg_ah_materialize_account_ledger_from_snapshot
  on public.alpha_hunter_snapshots;
create trigger trg_ah_materialize_account_ledger_from_snapshot
after insert on public.alpha_hunter_snapshots
for each row execute function private.alpha_hunter_materialize_account_ledger_from_snapshot();
