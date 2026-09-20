-- Alpha Hunter execution order-minute benchmark v0.1
--
-- Purpose:
--   Add a coarse historical pre-fill benchmark for recovered MARKET orders
--   using the public Bitget 1m candle OPEN for the minute containing the
--   private order creation timestamp (cTime).
--
-- Claim ceiling:
--   This is NOT slippage. It combines market movement since the minute open
--   with execution effects and uses a reference that may be up to <60 seconds
--   old at order creation. It is descriptive transaction-cost evidence only.
--   It cannot support Alpha Hunter execution attribution, cost-model
--   activation, or realistic net-R claims.
--
-- Safety:
--   public GET market data only; no exchange write path; append-only evidence;
--   shadow_only=true; trade_permission=false.

create table if not exists public.alpha_hunter_execution_order_minute_benchmark_v01 (
  benchmark_evidence_id text primary key,
  order_evidence_id text not null,
  fill_evidence_id text not null unique,
  captured_at_utc timestamptz not null default clock_timestamp(),
  fill_time_utc timestamptz not null,
  order_created_at_utc timestamptz not null,
  symbol text not null,
  fill_side text not null check(fill_side in ('BUY','SELL')),
  fill_price double precision not null check(fill_price>0),
  fill_origin_class text,
  order_identity_sha256 text,
  reference_expected_at_utc timestamptz not null,
  reference_candle_at_utc timestamptz,
  reference_open double precision,
  reference_age_seconds double precision,
  order_to_fill_seconds double precision,
  signed_adverse_fill_vs_order_minute_open_bps double precision,
  benchmark_class text not null
    check(benchmark_class in (
      'COARSE_ORDER_MINUTE_OPEN_NOT_SLIPPAGE',
      'DATA_INSUFFICIENT'
    )),
  evaluation_status text not null
    check(evaluation_status in (
      'EVALUATED',
      'DATA_INSUFFICIENT',
      'DATA_INTEGRITY_ERROR'
    )),
  measurement_source text not null,
  source_endpoint text not null,
  evidence jsonb not null default '{}'::jsonb
    check(jsonb_typeof(evidence)='object'),
  slippage_claim_permitted boolean not null default false
    check(slippage_claim_permitted=false),
  alpha_hunter_execution_claim_permitted boolean not null default false
    check(alpha_hunter_execution_claim_permitted=false),
  cost_model_activation_permitted boolean not null default false
    check(cost_model_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  model_version text not null default 'execution-order-minute-benchmark-v0.1'
);

create table if not exists public.alpha_hunter_execution_order_minute_benchmark_failures_v01 (
  failure_id text primary key,
  order_evidence_id text,
  fill_evidence_id text,
  symbol text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  error_class text not null,
  error_message text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false)
);

alter table public.alpha_hunter_execution_order_minute_benchmark_v01 enable row level security;
alter table public.alpha_hunter_execution_order_minute_benchmark_failures_v01 enable row level security;

revoke all on public.alpha_hunter_execution_order_minute_benchmark_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_execution_order_minute_benchmark_failures_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_order_minute_benchmark_v01 to service_role;
grant select on public.alpha_hunter_execution_order_minute_benchmark_failures_v01 to service_role;

drop trigger if exists trg_ah_execution_order_minute_benchmark_append_only
  on public.alpha_hunter_execution_order_minute_benchmark_v01;
create trigger trg_ah_execution_order_minute_benchmark_append_only
before update or delete on public.alpha_hunter_execution_order_minute_benchmark_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_execution_order_minute_benchmark_failures_append_only
  on public.alpha_hunter_execution_order_minute_benchmark_failures_v01;
create trigger trg_ah_execution_order_minute_benchmark_failures_append_only
before update or delete on public.alpha_hunter_execution_order_minute_benchmark_failures_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create index if not exists idx_ah_order_minute_benchmark_symbol_time
  on public.alpha_hunter_execution_order_minute_benchmark_v01(symbol,order_created_at_utc);

create or replace function private.alpha_hunter_collect_order_minute_benchmark_v01(
  p_limit integer default 25
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  o record;
  v_url text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_expected timestamptz;
  v_reference timestamptz;
  v_open double precision;
  v_age_seconds double precision;
  v_order_to_fill_seconds double precision;
  v_delta double precision;
  v_inserted integer := 0;
  v_data_insufficient integer := 0;
  v_integrity_errors integer := 0;
  v_failures integer := 0;
  v_processed integer := 0;
  v_error text;
begin
  if p_limit is null or p_limit<1 or p_limit>100 then
    raise exception 'p_limit must be between 1 and 100';
  end if;

  for o in
    select
      e.order_evidence_id,
      e.fill_evidence_id,
      e.fill_time_utc,
      e.order_created_at_utc,
      e.symbol,
      e.fill_side,
      e.fill_price,
      e.fill_origin_class,
      e.order_identity_sha256
    from public.alpha_hunter_execution_order_evidence_v01 e
    where e.order_type='MARKET'
      and e.order_created_at_utc is not null
      and e.fill_time_utc is not null
      and e.fill_price>0
      and e.fill_side in ('BUY','SELL')
      and e.symbol ~ '^[A-Z0-9]+USDT$'
      and not exists (
        select 1
        from public.alpha_hunter_execution_order_minute_benchmark_v01 b
        where b.fill_evidence_id=e.fill_evidence_id
      )
    order by e.order_created_at_utc,e.fill_evidence_id
    limit p_limit
  loop
    v_processed := v_processed+1;
    v_expected := date_trunc('minute',o.order_created_at_utc);
    v_reference := null;
    v_open := null;
    v_age_seconds := extract(epoch from (o.order_created_at_utc-v_expected));
    v_order_to_fill_seconds := extract(epoch from (o.fill_time_utc-o.order_created_at_utc));

    begin
      v_url := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=5',
        o.symbol,
        floor(extract(epoch from v_expected)*1000)::bigint,
        floor(extract(epoch from (v_expected+interval '2 minutes'))*1000)::bigint
      );

      select (r).status,(r).content
      into v_status,v_content
      from (select extensions.http_get(v_url) r) q;

      if v_status<>200 then
        raise exception 'BITGET_HTTP_STATUS:%',v_status;
      end if;

      v_payload := v_content::jsonb;
      if coalesce(v_payload->>'code','')<>'00000' then
        raise exception 'BITGET_PAYLOAD_CODE:%',v_payload->>'code';
      end if;

      select
        pg_catalog.to_timestamp((bar->>0)::double precision/1000.0),
        (bar->>1)::double precision
      into v_reference,v_open
      from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb)) bar
      where (bar->>0) ~ '^[0-9]+$'
        and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        and pg_catalog.to_timestamp((bar->>0)::double precision/1000.0)=v_expected
      limit 1;

      if v_reference is null or v_open is null or v_open<=0 then
        insert into public.alpha_hunter_execution_order_minute_benchmark_v01(
          benchmark_evidence_id,order_evidence_id,fill_evidence_id,
          fill_time_utc,order_created_at_utc,symbol,fill_side,fill_price,
          fill_origin_class,order_identity_sha256,
          reference_expected_at_utc,reference_candle_at_utc,reference_open,
          reference_age_seconds,order_to_fill_seconds,
          signed_adverse_fill_vs_order_minute_open_bps,
          benchmark_class,evaluation_status,measurement_source,source_endpoint,evidence,
          slippage_claim_permitted,alpha_hunter_execution_claim_permitted,
          cost_model_activation_permitted,realistic_net_r_claim_permitted,
          shadow_only,trade_permission
        ) values (
          pg_catalog.md5('execution-order-minute-benchmark-v0.1|'||o.fill_evidence_id),
          o.order_evidence_id,o.fill_evidence_id,o.fill_time_utc,o.order_created_at_utc,
          o.symbol,o.fill_side,o.fill_price,o.fill_origin_class,o.order_identity_sha256,
          v_expected,null,null,v_age_seconds,v_order_to_fill_seconds,null,
          'DATA_INSUFFICIENT','DATA_INSUFFICIENT',
          'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
          jsonb_build_object(
            'reference_rule','OPEN_OF_MINUTE_CONTAINING_PRIVATE_ORDER_CTIME',
            'reference_precedes_or_equals_order_creation',true,
            'max_reference_age_seconds',60,
            'public_market_data_only',true,
            'benchmark_is_not_slippage',true,
            'benchmark_mixes_market_movement_and_execution',true,
            'benchmark_is_not_alpha_hunter_performance',true,
            'benchmark_is_not_realistic_net_r',true
          ),
          false,false,false,false,true,false
        )
        on conflict(fill_evidence_id) do nothing;

        if found then
          v_data_insufficient := v_data_insufficient+1;
        end if;
        continue;
      end if;

      if v_order_to_fill_seconds < 0 or v_age_seconds < 0 or v_age_seconds >= 60 then
        v_delta := null;
        insert into public.alpha_hunter_execution_order_minute_benchmark_v01(
          benchmark_evidence_id,order_evidence_id,fill_evidence_id,
          fill_time_utc,order_created_at_utc,symbol,fill_side,fill_price,
          fill_origin_class,order_identity_sha256,
          reference_expected_at_utc,reference_candle_at_utc,reference_open,
          reference_age_seconds,order_to_fill_seconds,
          signed_adverse_fill_vs_order_minute_open_bps,
          benchmark_class,evaluation_status,measurement_source,source_endpoint,evidence,
          slippage_claim_permitted,alpha_hunter_execution_claim_permitted,
          cost_model_activation_permitted,realistic_net_r_claim_permitted,
          shadow_only,trade_permission
        ) values (
          pg_catalog.md5('execution-order-minute-benchmark-v0.1|'||o.fill_evidence_id),
          o.order_evidence_id,o.fill_evidence_id,o.fill_time_utc,o.order_created_at_utc,
          o.symbol,o.fill_side,o.fill_price,o.fill_origin_class,o.order_identity_sha256,
          v_expected,v_reference,v_open,v_age_seconds,v_order_to_fill_seconds,null,
          'COARSE_ORDER_MINUTE_OPEN_NOT_SLIPPAGE','DATA_INTEGRITY_ERROR',
          'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
          jsonb_build_object(
            'reference_rule','OPEN_OF_MINUTE_CONTAINING_PRIVATE_ORDER_CTIME',
            'benchmark_is_not_slippage',true,
            'benchmark_mixes_market_movement_and_execution',true,
            'integrity_error','NEGATIVE_ORDER_TO_FILL_OR_INVALID_REFERENCE_AGE'
          ),
          false,false,false,false,true,false
        )
        on conflict(fill_evidence_id) do nothing;

        if found then
          v_integrity_errors := v_integrity_errors+1;
        end if;
        continue;
      end if;

      v_delta := case
        when o.fill_side='BUY'
          then (o.fill_price-v_open)/v_open*10000.0
        when o.fill_side='SELL'
          then (v_open-o.fill_price)/v_open*10000.0
      end;

      insert into public.alpha_hunter_execution_order_minute_benchmark_v01(
        benchmark_evidence_id,order_evidence_id,fill_evidence_id,
        fill_time_utc,order_created_at_utc,symbol,fill_side,fill_price,
        fill_origin_class,order_identity_sha256,
        reference_expected_at_utc,reference_candle_at_utc,reference_open,
        reference_age_seconds,order_to_fill_seconds,
        signed_adverse_fill_vs_order_minute_open_bps,
        benchmark_class,evaluation_status,measurement_source,source_endpoint,evidence,
        slippage_claim_permitted,alpha_hunter_execution_claim_permitted,
        cost_model_activation_permitted,realistic_net_r_claim_permitted,
        shadow_only,trade_permission
      ) values (
        pg_catalog.md5('execution-order-minute-benchmark-v0.1|'||o.fill_evidence_id),
        o.order_evidence_id,o.fill_evidence_id,o.fill_time_utc,o.order_created_at_utc,
        o.symbol,o.fill_side,o.fill_price,o.fill_origin_class,o.order_identity_sha256,
        v_expected,v_reference,v_open,v_age_seconds,v_order_to_fill_seconds,v_delta,
        'COARSE_ORDER_MINUTE_OPEN_NOT_SLIPPAGE','EVALUATED',
        'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
        jsonb_build_object(
          'reference_rule','OPEN_OF_MINUTE_CONTAINING_PRIVATE_ORDER_CTIME',
          'reference_precedes_or_equals_order_creation',true,
          'reference_age_seconds',v_age_seconds,
          'public_market_data_only',true,
          'benchmark_is_not_slippage',true,
          'benchmark_mixes_market_movement_and_execution',true,
          'benchmark_is_not_alpha_hunter_performance',true,
          'benchmark_is_not_realistic_net_r',true,
          'positive_delta_means_adverse_to_fill_side',true
        ),
        false,false,false,false,true,false
      )
      on conflict(fill_evidence_id) do nothing;

      if found then
        v_inserted := v_inserted+1;
      end if;

    exception when others then
      v_error := left(sqlerrm,1000);
      v_failures := v_failures+1;

      insert into public.alpha_hunter_execution_order_minute_benchmark_failures_v01(
        failure_id,order_evidence_id,fill_evidence_id,symbol,
        error_class,error_message,shadow_only,trade_permission
      ) values (
        pg_catalog.md5(
          'execution-order-minute-benchmark-failure-v0.1|'||o.fill_evidence_id
          ||'|'||clock_timestamp()::text
        ),
        o.order_evidence_id,o.fill_evidence_id,o.symbol,
        case
          when v_error like 'BITGET_HTTP_STATUS:%' then 'BITGET_HTTP_ERROR'
          when v_error like 'BITGET_PAYLOAD_CODE:%' then 'BITGET_PAYLOAD_ERROR'
          else 'BENCHMARK_COLLECTOR_ERROR'
        end,
        v_error,true,false
      );
    end;
  end loop;

  return jsonb_build_object(
    'mode','COARSE_ORDER_MINUTE_PRE_FILL_BENCHMARK',
    'market_orders_processed',v_processed,
    'evaluated_rows_inserted',v_inserted,
    'data_insufficient_rows_inserted',v_data_insufficient,
    'data_integrity_rows_inserted',v_integrity_errors,
    'failure_events',v_failures,
    'slippage_inferred',false,
    'alpha_hunter_execution_claimed',false,
    'cost_model_activated',false,
    'realistic_net_r_claimed',false,
    'new_cron_created',false,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_collect_order_minute_benchmark_v01(integer)
  from public,anon,authenticated,service_role;
