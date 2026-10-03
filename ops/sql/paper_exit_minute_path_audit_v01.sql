begin;

-- Alpha Hunter paper protective-exit 1m path audit v0.1.
--
-- Purpose:
-- Reconstruct the first minute in which a completed clean paper position could
-- have touched its protective stop or target using public Bitget 1m history
-- candles. This is shadow evidence only and does NOT rewrite the recorded
-- paper exit or promote a counterfactual PnL claim.
--
-- Scientific ambiguity rules:
-- * if the entry-containing minute touches either protection after a non-boundary
--   entry timestamp, ordering relative to the fill is unknowable -> ambiguous;
-- * if the same later 1m candle touches both stop and target -> ambiguous;
-- * only a strictly earlier stop-vs-target minute is classified unambiguously.
--
-- Public GET only. No exchange write path. No production promotion authority.

create table if not exists public.alpha_hunter_paper_exit_minute_path_audit_v01 (
  audit_id text primary key,
  exit_fill_id text not null unique,
  entry_order_id text not null,
  decision_id text not null,
  symbol text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  recorded_exit_reason text not null,
  entry_completed_at_utc timestamptz not null,
  observed_exit_at_utc timestamptz not null,
  stop_trigger_price numeric not null check(stop_trigger_price>0),
  target_trigger_price numeric not null check(target_trigger_price>0),
  first_stop_touch_minute_utc timestamptz,
  first_target_touch_minute_utc timestamptz,
  inferred_first_touch_type text not null check(
    inferred_first_touch_type in (
      'STOP_LOSS',
      'TAKE_PROFIT',
      'ENTRY_MINUTE_ORDERING_AMBIGUOUS',
      'AMBIGUOUS_SAME_MINUTE',
      'NO_MINUTE_TOUCH_FOUND',
      'DATA_INSUFFICIENT'
    )
  ),
  inferred_first_touch_minute_utc timestamptz,
  first_touch_open numeric,
  first_touch_high numeric,
  first_touch_low numeric,
  first_touch_close numeric,
  minutes_entry_to_first_touch numeric,
  minutes_first_touch_to_observed_exit numeric,
  candle_count_checked integer not null default 0 check(candle_count_checked>=0),
  expected_candle_count integer not null default 0 check(expected_candle_count>=0),
  request_chunks integer not null default 0 check(request_chunks>=0),
  observed_exit_reason_matches boolean,
  measurement_source text not null default 'BITGET_PUBLIC_V3_1M_HISTORY_CANDLES',
  source_endpoint text not null default '/api/v3/market/history-candles',
  evidence jsonb not null default '{}'::jsonb check(jsonb_typeof(evidence)='object'),
  counterfactual_only boolean not null default true check(counterfactual_only=true),
  exit_model_change_permitted boolean not null default false
    check(exit_model_change_permitted=false),
  profitability_claim_permitted boolean not null default false
    check(profitability_claim_permitted=false),
  paper_only boolean not null default true check(paper_only=true),
  exchange_authority boolean not null default false check(exchange_authority=false),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at_utc timestamptz not null default clock_timestamp()
);

create table if not exists public.alpha_hunter_paper_exit_minute_path_failures_v01 (
  failure_id text primary key,
  exit_fill_id text,
  entry_order_id text,
  symbol text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  error_class text not null,
  error_message text not null,
  evidence jsonb not null default '{}'::jsonb check(jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check(paper_only=true),
  exchange_authority boolean not null default false check(exchange_authority=false),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

alter table public.alpha_hunter_paper_exit_minute_path_audit_v01
  enable row level security;
alter table public.alpha_hunter_paper_exit_minute_path_failures_v01
  enable row level security;

revoke all on public.alpha_hunter_paper_exit_minute_path_audit_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_paper_exit_minute_path_failures_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_exit_minute_path_audit_v01
  to service_role;
grant select on public.alpha_hunter_paper_exit_minute_path_failures_v01
  to service_role;

drop trigger if exists trg_ah_paper_exit_minute_path_audit_append_only_v01
  on public.alpha_hunter_paper_exit_minute_path_audit_v01;
create trigger trg_ah_paper_exit_minute_path_audit_append_only_v01
before update or delete on public.alpha_hunter_paper_exit_minute_path_audit_v01
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

drop trigger if exists trg_ah_paper_exit_minute_path_failures_append_only_v01
  on public.alpha_hunter_paper_exit_minute_path_failures_v01;
create trigger trg_ah_paper_exit_minute_path_failures_append_only_v01
before update or delete on public.alpha_hunter_paper_exit_minute_path_failures_v01
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

create index if not exists idx_ah_paper_exit_minute_path_symbol_time_v01
  on public.alpha_hunter_paper_exit_minute_path_audit_v01(
    symbol,entry_completed_at_utc
  );

create or replace function private.alpha_hunter_collect_paper_exit_minute_path_v01(
  p_limit integer default 10
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $function$
declare
  t record;
  v_cursor timestamptz;
  v_next timestamptz;
  v_entry_minute timestamptz;
  v_final_minute timestamptz;
  v_request_start timestamptz;
  v_status integer;
  v_content text;
  v_body jsonb;
  v_bar jsonb;
  v_bar_at timestamptz;
  v_open numeric;
  v_high numeric;
  v_low numeric;
  v_close numeric;
  v_stop_hit boolean;
  v_target_hit boolean;
  v_entry_minute_ambiguous boolean;
  v_entry_ambiguous_open numeric;
  v_entry_ambiguous_high numeric;
  v_entry_ambiguous_low numeric;
  v_entry_ambiguous_close numeric;
  v_first_stop_at timestamptz;
  v_first_stop_open numeric;
  v_first_stop_high numeric;
  v_first_stop_low numeric;
  v_first_stop_close numeric;
  v_first_target_at timestamptz;
  v_first_target_open numeric;
  v_first_target_high numeric;
  v_first_target_low numeric;
  v_first_target_close numeric;
  v_touch_type text;
  v_first_touch_at timestamptz;
  v_first_touch_open numeric;
  v_first_touch_high numeric;
  v_first_touch_low numeric;
  v_first_touch_close numeric;
  v_matches boolean;
  v_candles integer;
  v_expected integer;
  v_chunks integer;
  v_processed integer := 0;
  v_inserted integer := 0;
  v_ambiguous integer := 0;
  v_unambiguous integer := 0;
  v_no_touch integer := 0;
  v_failures integer := 0;
  v_error text;
begin
  if p_limit is null or p_limit<1 or p_limit>20 then
    raise exception 'p_limit must be between 1 and 20';
  end if;

  for t in
    with entry_fill as (
      select
        f.order_id,
        max(f.filled_at_utc) as entry_completed_at_utc
      from public.alpha_hunter_paper_fills_v02 f
      group by f.order_id
    ),
    protection as (
      select
        p.entry_order_id,
        max(p.trigger_price) filter(where p.protection_type='STOP_LOSS')
          as stop_trigger_price,
        max(p.trigger_price) filter(where p.protection_type='TAKE_PROFIT')
          as target_trigger_price
      from public.alpha_hunter_paper_protective_orders_v03 p
      group by p.entry_order_id
    )
    select
      c.exit_fill_id,
      c.entry_order_id,
      c.decision_id,
      c.symbol,
      c.direction,
      c.exit_reason,
      c.closed_at_utc,
      e.entry_completed_at_utc,
      p.stop_trigger_price,
      p.target_trigger_price
    from public.alpha_hunter_paper_completed_trades_valid_v05 c
    join entry_fill e on e.order_id=c.entry_order_id
    join protection p on p.entry_order_id=c.entry_order_id
    where c.exit_reason in ('STOP_LOSS','TAKE_PROFIT')
      and not exists (
        select 1
        from public.alpha_hunter_paper_exit_minute_path_audit_v01 a
        where a.exit_fill_id=c.exit_fill_id
      )
    order by c.closed_at_utc,c.exit_fill_id
    limit p_limit
  loop
    v_processed := v_processed+1;

    begin
      if t.entry_completed_at_utc is null
         or t.closed_at_utc is null
         or t.closed_at_utc<t.entry_completed_at_utc
         or t.stop_trigger_price is null
         or t.target_trigger_price is null
      then
        raise exception 'INVALID_PATH_BOUNDS_OR_PROTECTION';
      end if;

      if extract(epoch from (t.closed_at_utc-t.entry_completed_at_utc))/60.0
           > 1440.0
      then
        raise exception 'PATH_WINDOW_EXCEEDS_24H';
      end if;

      v_entry_minute := date_trunc('minute',t.entry_completed_at_utc);
      v_final_minute := date_trunc('minute',t.closed_at_utc);
      v_cursor := v_entry_minute;
      v_entry_minute_ambiguous := false;
      v_entry_ambiguous_open := null;
      v_entry_ambiguous_high := null;
      v_entry_ambiguous_low := null;
      v_entry_ambiguous_close := null;
      v_first_stop_at := null;
      v_first_stop_open := null;
      v_first_stop_high := null;
      v_first_stop_low := null;
      v_first_stop_close := null;
      v_first_target_at := null;
      v_first_target_open := null;
      v_first_target_high := null;
      v_first_target_low := null;
      v_first_target_close := null;
      v_candles := 0;
      v_chunks := 0;
      v_expected := (
        extract(
          epoch from (
            (v_final_minute+interval '1 minute')-v_entry_minute
          )
        )/60.0
      )::integer;

      while v_cursor < v_final_minute+interval '1 minute' loop
        v_next := least(
          v_cursor+interval '90 minutes',
          v_final_minute+interval '1 minute'
        );
        v_request_start := v_cursor-interval '1 minute';
        v_chunks := v_chunks+1;

        select (r).status,(r).content
          into v_status,v_content
        from (
          select extensions.http_get(
            pg_catalog.format(
              'https://api.bitget.com/api/v3/market/history-candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=100',
              t.symbol,
              floor(extract(epoch from v_request_start)*1000)::bigint,
              floor(extract(epoch from v_next)*1000)::bigint
            )
          ) r
        ) q;

        if v_status<>200 then
          raise exception 'BITGET_HTTP_STATUS:%',v_status;
        end if;

        v_body := v_content::jsonb;
        if coalesce(v_body->>'code','')<>'00000' then
          raise exception 'BITGET_PAYLOAD_CODE:%',v_body->>'code';
        end if;
        if jsonb_typeof(v_body->'data')<>'array' then
          raise exception 'BITGET_CANDLE_DATA_NOT_ARRAY';
        end if;

        for v_bar in
          select value
          from jsonb_array_elements(v_body->'data')
        loop
          if jsonb_typeof(v_bar)<>'array'
             or jsonb_array_length(v_bar)<5
             or not ((v_bar->>0) ~ '^[0-9]+$')
             or not ((v_bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$')
             or not ((v_bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$')
             or not ((v_bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$')
             or not ((v_bar->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$')
          then
            continue;
          end if;

          v_bar_at := pg_catalog.to_timestamp(
            (v_bar->>0)::double precision/1000.0
          );
          if v_bar_at<v_cursor or v_bar_at>=v_next then
            continue;
          end if;

          v_open := (v_bar->>1)::numeric;
          v_high := (v_bar->>2)::numeric;
          v_low := (v_bar->>3)::numeric;
          v_close := (v_bar->>4)::numeric;
          if v_open<=0 or v_high<=0 or v_low<=0 or v_close<=0
             or v_high<v_low
          then
            continue;
          end if;

          v_candles := v_candles+1;
          v_stop_hit := case
            when t.direction='LONG' then v_low<=t.stop_trigger_price
            when t.direction='SHORT' then v_high>=t.stop_trigger_price
            else false
          end;
          v_target_hit := case
            when t.direction='LONG' then v_high>=t.target_trigger_price
            when t.direction='SHORT' then v_low<=t.target_trigger_price
            else false
          end;

          if v_bar_at=v_entry_minute
             and t.entry_completed_at_utc>v_entry_minute
             and (v_stop_hit or v_target_hit)
          then
            v_entry_minute_ambiguous := true;
            v_entry_ambiguous_open := v_open;
            v_entry_ambiguous_high := v_high;
            v_entry_ambiguous_low := v_low;
            v_entry_ambiguous_close := v_close;
            continue;
          end if;

          if v_stop_hit
             and (v_first_stop_at is null or v_bar_at<v_first_stop_at)
          then
            v_first_stop_at := v_bar_at;
            v_first_stop_open := v_open;
            v_first_stop_high := v_high;
            v_first_stop_low := v_low;
            v_first_stop_close := v_close;
          end if;

          if v_target_hit
             and (v_first_target_at is null or v_bar_at<v_first_target_at)
          then
            v_first_target_at := v_bar_at;
            v_first_target_open := v_open;
            v_first_target_high := v_high;
            v_first_target_low := v_low;
            v_first_target_close := v_close;
          end if;
        end loop;

        v_cursor := v_next;
      end loop;

      v_matches := null;
      if v_candles=0 then
        v_touch_type := 'DATA_INSUFFICIENT';
        v_first_touch_at := null;
        v_first_touch_open := null;
        v_first_touch_high := null;
        v_first_touch_low := null;
        v_first_touch_close := null;
      elsif v_entry_minute_ambiguous then
        v_touch_type := 'ENTRY_MINUTE_ORDERING_AMBIGUOUS';
        v_first_touch_at := v_entry_minute;
        v_first_touch_open := v_entry_ambiguous_open;
        v_first_touch_high := v_entry_ambiguous_high;
        v_first_touch_low := v_entry_ambiguous_low;
        v_first_touch_close := v_entry_ambiguous_close;
      elsif v_first_stop_at is null and v_first_target_at is null then
        v_touch_type := 'NO_MINUTE_TOUCH_FOUND';
        v_first_touch_at := null;
        v_first_touch_open := null;
        v_first_touch_high := null;
        v_first_touch_low := null;
        v_first_touch_close := null;
      elsif v_first_stop_at is not null
         and v_first_target_at is not null
         and v_first_stop_at=v_first_target_at
      then
        v_touch_type := 'AMBIGUOUS_SAME_MINUTE';
        v_first_touch_at := v_first_stop_at;
        v_first_touch_open := v_first_stop_open;
        v_first_touch_high := v_first_stop_high;
        v_first_touch_low := v_first_stop_low;
        v_first_touch_close := v_first_stop_close;
      elsif v_first_target_at is null
         or (
           v_first_stop_at is not null
           and v_first_stop_at<v_first_target_at
         )
      then
        v_touch_type := 'STOP_LOSS';
        v_first_touch_at := v_first_stop_at;
        v_first_touch_open := v_first_stop_open;
        v_first_touch_high := v_first_stop_high;
        v_first_touch_low := v_first_stop_low;
        v_first_touch_close := v_first_stop_close;
        v_matches := t.exit_reason='STOP_LOSS';
      else
        v_touch_type := 'TAKE_PROFIT';
        v_first_touch_at := v_first_target_at;
        v_first_touch_open := v_first_target_open;
        v_first_touch_high := v_first_target_high;
        v_first_touch_low := v_first_target_low;
        v_first_touch_close := v_first_target_close;
        v_matches := t.exit_reason='TAKE_PROFIT';
      end if;

      insert into public.alpha_hunter_paper_exit_minute_path_audit_v01(
        audit_id,exit_fill_id,entry_order_id,decision_id,symbol,direction,
        recorded_exit_reason,entry_completed_at_utc,observed_exit_at_utc,
        stop_trigger_price,target_trigger_price,
        first_stop_touch_minute_utc,first_target_touch_minute_utc,
        inferred_first_touch_type,inferred_first_touch_minute_utc,
        first_touch_open,first_touch_high,first_touch_low,first_touch_close,
        minutes_entry_to_first_touch,minutes_first_touch_to_observed_exit,
        candle_count_checked,expected_candle_count,request_chunks,
        observed_exit_reason_matches,measurement_source,source_endpoint,evidence,
        counterfactual_only,exit_model_change_permitted,
        profitability_claim_permitted,paper_only,exchange_authority,
        trade_permission,production_promotion_permitted,order_path
      ) values (
        pg_catalog.md5(
          'paper-exit-minute-path-v0.1|'||t.exit_fill_id
        ),
        t.exit_fill_id,t.entry_order_id,t.decision_id,t.symbol,t.direction,
        t.exit_reason,t.entry_completed_at_utc,t.closed_at_utc,
        t.stop_trigger_price,t.target_trigger_price,
        v_first_stop_at,v_first_target_at,
        v_touch_type,v_first_touch_at,
        v_first_touch_open,v_first_touch_high,v_first_touch_low,v_first_touch_close,
        case
          when v_first_touch_at is null then null
          else extract(
            epoch from (v_first_touch_at-t.entry_completed_at_utc)
          )/60.0
        end,
        case
          when v_first_touch_at is null then null
          else extract(
            epoch from (t.closed_at_utc-v_first_touch_at)
          )/60.0
        end,
        v_candles,v_expected,v_chunks,v_matches,
        'BITGET_PUBLIC_V3_1M_HISTORY_CANDLES',
        '/api/v3/market/history-candles',
        jsonb_build_object(
          'model_version','paper-exit-minute-path-audit-v0.1',
          'chunk_minutes',90,
          'request_limit',100,
          'request_start_bracket_minutes',1,
          'max_path_minutes',1440,
          'entry_minute_ordering_ambiguous',v_entry_minute_ambiguous,
          'recorded_exit_is_not_rewritten',true,
          'minute_path_is_shadow_evidence',true,
          'same_minute_stop_target_is_ambiguous',true,
          'public_market_data_only',true
        ),
        true,false,false,true,false,false,false,'NONE'
      )
      on conflict(exit_fill_id) do nothing;

      if found then
        v_inserted := v_inserted+1;
        if v_touch_type in (
          'ENTRY_MINUTE_ORDERING_AMBIGUOUS',
          'AMBIGUOUS_SAME_MINUTE'
        ) then
          v_ambiguous := v_ambiguous+1;
        elsif v_touch_type in ('STOP_LOSS','TAKE_PROFIT') then
          v_unambiguous := v_unambiguous+1;
        elsif v_touch_type='NO_MINUTE_TOUCH_FOUND' then
          v_no_touch := v_no_touch+1;
        end if;
      end if;

    exception when others then
      v_error := left(sqlerrm,1000);
      v_failures := v_failures+1;

      insert into public.alpha_hunter_paper_exit_minute_path_failures_v01(
        failure_id,exit_fill_id,entry_order_id,symbol,
        error_class,error_message,evidence,
        paper_only,exchange_authority,trade_permission,order_path
      ) values (
        pg_catalog.md5(
          'paper-exit-minute-path-failure-v0.1|'
          ||coalesce(t.exit_fill_id,'NONE')
          ||'|'||clock_timestamp()::text
        ),
        t.exit_fill_id,t.entry_order_id,t.symbol,
        case
          when v_error like 'BITGET_HTTP_STATUS:%' then 'BITGET_HTTP_ERROR'
          when v_error like 'BITGET_PAYLOAD_CODE:%' then 'BITGET_PAYLOAD_ERROR'
          when v_error='PATH_WINDOW_EXCEEDS_24H' then 'PATH_WINDOW_EXCEEDS_24H'
          else 'MINUTE_PATH_AUDIT_ERROR'
        end,
        v_error,
        jsonb_build_object(
          'model_version','paper-exit-minute-path-audit-v0.1',
          'public_market_data_only',true,
          'recorded_exit_is_not_rewritten',true
        ),
        true,false,false,'NONE'
      );
    end;
  end loop;

  return jsonb_build_object(
    'model_version','paper-exit-minute-path-audit-v0.1',
    'completed_trades_processed',v_processed,
    'audit_rows_inserted',v_inserted,
    'unambiguous_first_touch_rows',v_unambiguous,
    'ambiguous_rows',v_ambiguous,
    'no_touch_rows',v_no_touch,
    'failure_events',v_failures,
    'recorded_exits_rewritten',false,
    'exit_model_changed',false,
    'profitability_claimed',false,
    'public_market_data_only',true,
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_collect_paper_exit_minute_path_v01(integer)
  from public,anon,authenticated,service_role;

create or replace view public.alpha_hunter_paper_exit_minute_path_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::integer as audited_trades,
  count(*) filter(
    where inferred_first_touch_type in ('STOP_LOSS','TAKE_PROFIT')
  )::integer as unambiguous_first_touch_trades,
  count(*) filter(
    where inferred_first_touch_type in (
      'ENTRY_MINUTE_ORDERING_AMBIGUOUS',
      'AMBIGUOUS_SAME_MINUTE'
    )
  )::integer as ambiguous_trades,
  count(*) filter(
    where inferred_first_touch_type='NO_MINUTE_TOUCH_FOUND'
  )::integer as no_touch_found_trades,
  count(*) filter(
    where inferred_first_touch_type='DATA_INSUFFICIENT'
  )::integer as data_insufficient_trades,
  count(*) filter(
    where observed_exit_reason_matches is true
  )::integer as recorded_reason_matches,
  count(*) filter(
    where observed_exit_reason_matches is false
  )::integer as recorded_reason_mismatches,
  avg(minutes_first_touch_to_observed_exit)
    filter(
      where inferred_first_touch_type in ('STOP_LOSS','TAKE_PROFIT')
    ) as average_minutes_first_touch_to_observed_exit,
  max(minutes_first_touch_to_observed_exit)
    filter(
      where inferred_first_touch_type in ('STOP_LOSS','TAKE_PROFIT')
    ) as maximum_minutes_first_touch_to_observed_exit,
  false as exit_model_change_permitted,
  false as profitability_claim_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_paper_exit_minute_path_audit_v01;

revoke all on public.alpha_hunter_paper_exit_minute_path_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_exit_minute_path_status_v01
  to service_role;

commit;
