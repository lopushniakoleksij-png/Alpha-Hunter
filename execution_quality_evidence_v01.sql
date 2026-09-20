-- Alpha Hunter execution-quality evidence v0.1
--
-- Two evidence paths with deliberately different claim ceilings:
--
-- 1) Private GET-only order detail (persisted later by the Mac collector)
--    may expose an explicit limit-order price benchmark. Only then may we
--    calculate fill-vs-limit execution delta. Market orders have no verified
--    pre-trade benchmark in this layer, so slippage remains withheld.
--
-- 2) Public Bitget 1m candles produce deterministic post-fill markouts at
--    1m / 5m / 15m / 60m. Markouts describe subsequent market movement;
--    they are NOT relabeled as slippage or realistic net-R.
--
-- No cost-model activation, risk/leverage mutation, order path, or trade
-- permission is introduced.

create table if not exists public.alpha_hunter_execution_order_evidence_v01 (
  order_evidence_id text primary key,
  fill_evidence_id text not null unique
    references public.alpha_hunter_fill_evidence(fill_evidence_id),

  observed_at_utc timestamptz not null,
  fill_time_utc timestamptz not null,
  symbol text not null,
  fill_side text not null check (fill_side in ('BUY','SELL')),
  fill_price double precision not null check (fill_price>0),

  fill_origin_class text not null,
  order_enter_point_source text,
  origin_consistent boolean,

  order_type text,
  order_state text,
  order_force text,
  order_source text,
  order_trade_side text,
  reduce_only text,

  order_price double precision,
  order_average_price double precision,
  order_created_at_utc timestamptz,
  order_updated_at_utc timestamptz,

  client_oid_present boolean not null default false,
  client_oid_sha256 text,
  order_identity_sha256 text not null
    check (order_identity_sha256 ~ '^[0-9a-f]{64}$'),

  benchmark_class text not null check (
    benchmark_class in (
      'LIMIT_ORDER_PRICE',
      'MARKET_NO_VERIFIED_PRETRADE_BENCHMARK',
      'ORDER_TYPE_UNKNOWN',
      'LIMIT_PRICE_UNAVAILABLE'
    )
  ),

  fill_vs_limit_delta_bps double precision,
  order_average_vs_limit_delta_bps double precision,
  limit_price_delta_claim_permitted boolean not null default false,

  source_endpoint text not null
    check (source_endpoint='/api/v2/mix/order/detail'),
  read_only_get boolean not null default true check (read_only_get=true),
  raw_order_id_persisted_here boolean not null default false
    check (raw_order_id_persisted_here=false),
  raw_client_oid_persisted_here boolean not null default false
    check (raw_client_oid_persisted_here=false),

  scientific_role text not null default
    'DESCRIPTIVE_ORDER_EXECUTION_EVIDENCE',
  slippage_claim_permitted boolean not null default false
    check (slippage_claim_permitted=false),
  alpha_hunter_execution_claim_permitted boolean not null default false
    check (alpha_hunter_execution_claim_permitted=false),
  cost_model_activation_permitted boolean not null default false
    check (cost_model_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check (realistic_net_r_claim_permitted=false),

  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'execution-quality-order-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);


create table if not exists public.alpha_hunter_execution_order_failures_v01 (
  failure_id text primary key,
  fill_evidence_id text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  error_class text not null,
  error_message text not null,
  source_endpoint text not null
    check (source_endpoint='/api/v2/mix/order/detail'),
  read_only_get boolean not null default true check (read_only_get=true),
  raw_order_id_printed boolean not null default false
    check (raw_order_id_printed=false),
  model_version text not null default 'execution-quality-order-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false)
);


create table if not exists public.alpha_hunter_execution_markout_evidence_v01 (
  markout_evidence_id text primary key,
  fill_evidence_id text not null
    references public.alpha_hunter_fill_evidence(fill_evidence_id),

  fill_time_utc timestamptz not null,
  symbol text not null,
  fill_side text not null check (fill_side in ('BUY','SELL')),
  fill_price double precision not null check (fill_price>0),
  fill_base_volume double precision,
  fill_quote_volume double precision,
  fill_origin_class text not null,
  order_identity_sha256 text not null
    check (order_identity_sha256 ~ '^[0-9a-f]{64}$'),

  horizon_minutes integer not null check (horizon_minutes in (1,5,15,60)),
  target_at_utc timestamptz not null,
  reference_expected_at_utc timestamptz not null,
  reference_candle_at_utc timestamptz,
  reference_open double precision,

  signed_post_fill_markout_bps double precision,
  markout_class text not null check (
    markout_class in (
      'FAVORABLE_TO_FILL_SIDE',
      'ADVERSE_TO_FILL_SIDE',
      'FLAT',
      'DATA_INSUFFICIENT'
    )
  ),
  evaluation_status text not null check (
    evaluation_status in ('EVALUATED','DATA_INSUFFICIENT')
  ),

  measurement_source text not null
    check (measurement_source='BITGET_PUBLIC_V3_1M_CANDLES'),
  source_endpoint text not null
    check (source_endpoint='/api/v3/market/candles'),

  post_fill_markout_claim_permitted boolean not null default true
    check (post_fill_markout_claim_permitted=true),
  slippage_claim_permitted boolean not null default false
    check (slippage_claim_permitted=false),
  alpha_hunter_execution_claim_permitted boolean not null default false
    check (alpha_hunter_execution_claim_permitted=false),
  cost_model_activation_permitted boolean not null default false
    check (cost_model_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check (realistic_net_r_claim_permitted=false),

  scientific_role text not null default
    'DESCRIPTIVE_POST_FILL_MARKOUT_NOT_SLIPPAGE',
  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'execution-quality-markout-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),

  unique(fill_evidence_id,horizon_minutes)
);


create table if not exists public.alpha_hunter_execution_markout_failures_v01 (
  failure_id text primary key,
  fill_evidence_id text,
  failed_at_utc timestamptz not null default clock_timestamp(),
  error_class text not null,
  error_message text not null,
  model_version text not null default 'execution-quality-markout-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false)
);


alter table public.alpha_hunter_execution_order_evidence_v01 enable row level security;
alter table public.alpha_hunter_execution_order_failures_v01 enable row level security;
alter table public.alpha_hunter_execution_markout_evidence_v01 enable row level security;
alter table public.alpha_hunter_execution_markout_failures_v01 enable row level security;

revoke all on table public.alpha_hunter_execution_order_evidence_v01
  from public,anon,authenticated;
revoke all on table public.alpha_hunter_execution_order_failures_v01
  from public,anon,authenticated;
revoke all on table public.alpha_hunter_execution_markout_evidence_v01
  from public,anon,authenticated;
revoke all on table public.alpha_hunter_execution_markout_failures_v01
  from public,anon,authenticated;

grant select,insert on table public.alpha_hunter_execution_order_evidence_v01
  to service_role;
grant select,insert on table public.alpha_hunter_execution_order_failures_v01
  to service_role;
grant select on table public.alpha_hunter_execution_markout_evidence_v01
  to service_role;
grant select on table public.alpha_hunter_execution_markout_failures_v01
  to service_role;


drop trigger if exists trg_ah_execution_order_evidence_append_only
  on public.alpha_hunter_execution_order_evidence_v01;
create trigger trg_ah_execution_order_evidence_append_only
before update or delete on public.alpha_hunter_execution_order_evidence_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_execution_order_failures_append_only
  on public.alpha_hunter_execution_order_failures_v01;
create trigger trg_ah_execution_order_failures_append_only
before update or delete on public.alpha_hunter_execution_order_failures_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_execution_markout_evidence_append_only
  on public.alpha_hunter_execution_markout_evidence_v01;
create trigger trg_ah_execution_markout_evidence_append_only
before update or delete on public.alpha_hunter_execution_markout_evidence_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_execution_markout_failures_append_only
  on public.alpha_hunter_execution_markout_failures_v01;
create trigger trg_ah_execution_markout_failures_append_only
before update or delete on public.alpha_hunter_execution_markout_failures_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create index if not exists idx_ah_execution_markout_fill_horizon
  on public.alpha_hunter_execution_markout_evidence_v01(
    fill_evidence_id,horizon_minutes
  );

create index if not exists idx_ah_execution_markout_symbol_time
  on public.alpha_hunter_execution_markout_evidence_v01(
    symbol,fill_time_utc
  );


create or replace function private.alpha_hunter_collect_execution_markouts_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  f record;
  h integer;
  v_url text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_target timestamptz;
  v_expected timestamptz;
  v_reference timestamptz;
  v_reference_open double precision;
  v_markout double precision;
  v_class text;
  v_origin_class text;
  v_inserted integer := 0;
  v_data_insufficient integer := 0;
  v_failures integer := 0;
  v_processed_fills integer := 0;
  v_error text;
begin
  for f in
    select
      x.fill_evidence_id,
      x.fill_time_utc,
      x.symbol,
      x.side,
      x.price,
      x.base_volume,
      x.quote_volume,
      x.order_id,
      x.enter_point_source
    from public.alpha_hunter_fill_evidence x
    where x.fill_time_utc <= clock_timestamp()-interval '62 minutes'
      and x.price>0
      and x.side in ('BUY','SELL')
      and x.symbol ~ '^[A-Z0-9]+USDT$'
      and exists (
        select 1
        from (values(1),(5),(15),(60)) h(horizon_minutes)
        where not exists (
          select 1
          from public.alpha_hunter_execution_markout_evidence_v01 m
          where m.fill_evidence_id=x.fill_evidence_id
            and m.horizon_minutes=h.horizon_minutes
        )
      )
    order by x.fill_time_utc,x.fill_evidence_id
    limit 20
  loop
    v_processed_fills := v_processed_fills+1;

    v_origin_class := case
      when upper(coalesce(f.enter_point_source,''))='API'
        then 'API_ORIGIN_UNVERIFIED'
      when upper(coalesce(f.enter_point_source,'')) in (
        'IOS','ANDROID','WEB','APP','MOBILE'
      )
        then 'HUMAN_UI_EXTERNAL'
      when nullif(trim(coalesce(f.enter_point_source,'')),'') is null
        then 'UNKNOWN_ORIGIN'
      else 'NON_API_EXTERNAL'
    end;

    begin
      v_url := pg_catalog.format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=1m&startTime=%s&endTime=%s&limit=100',
        f.symbol,
        floor(extract(epoch from date_trunc('minute',f.fill_time_utc))*1000)::bigint,
        floor(extract(epoch from (f.fill_time_utc+interval '63 minutes'))*1000)::bigint
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

      foreach h in array array[1,5,15,60]
      loop
        if exists (
          select 1
          from public.alpha_hunter_execution_markout_evidence_v01 m
          where m.fill_evidence_id=f.fill_evidence_id
            and m.horizon_minutes=h
        ) then
          continue;
        end if;

        v_target := f.fill_time_utc + make_interval(mins=>h);
        v_expected := pg_catalog.to_timestamp(
          ceil(extract(epoch from v_target)/60.0)*60.0
        );

        select
          pg_catalog.to_timestamp((bar->>0)::double precision/1000.0),
          (bar->>1)::double precision
        into v_reference,v_reference_open
        from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb)) bar
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and pg_catalog.to_timestamp((bar->>0)::double precision/1000.0)
                = v_expected
        limit 1;

        if v_reference is null or v_reference_open is null or v_reference_open<=0 then
          insert into public.alpha_hunter_execution_markout_evidence_v01(
            markout_evidence_id,fill_evidence_id,fill_time_utc,symbol,
            fill_side,fill_price,fill_base_volume,fill_quote_volume,
            fill_origin_class,order_identity_sha256,
            horizon_minutes,target_at_utc,
            reference_expected_at_utc,reference_candle_at_utc,reference_open,
            signed_post_fill_markout_bps,markout_class,evaluation_status,
            measurement_source,source_endpoint,evidence,
            shadow_only,trade_permission
          ) values (
            pg_catalog.md5(
              'execution-quality-markout-v0.1|'||f.fill_evidence_id||'|'||h::text
            ),
            f.fill_evidence_id,f.fill_time_utc,f.symbol,f.side,f.price,
            f.base_volume,f.quote_volume,v_origin_class,
            pg_catalog.encode(
              extensions.digest(f.order_id,'sha256'),
              'hex'
            ),
            h,v_target,v_expected,null,null,null,
            'DATA_INSUFFICIENT','DATA_INSUFFICIENT',
            'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
            jsonb_build_object(
              'exact_expected_minute_required',true,
              'public_market_data_only',true,
              'markout_is_not_slippage',true,
              'markout_is_not_realistic_net_r',true
            ),
            true,false
          )
          on conflict(fill_evidence_id,horizon_minutes) do nothing;

          if found then
            v_data_insufficient := v_data_insufficient+1;
          end if;
          continue;
        end if;

        v_markout := case
          when f.side='BUY'
            then (v_reference_open-f.price)/f.price*10000.0
          when f.side='SELL'
            then (f.price-v_reference_open)/f.price*10000.0
        end;

        v_class := case
          when abs(v_markout)<1e-9 then 'FLAT'
          when v_markout>0 then 'FAVORABLE_TO_FILL_SIDE'
          else 'ADVERSE_TO_FILL_SIDE'
        end;

        insert into public.alpha_hunter_execution_markout_evidence_v01(
          markout_evidence_id,fill_evidence_id,fill_time_utc,symbol,
          fill_side,fill_price,fill_base_volume,fill_quote_volume,
          fill_origin_class,order_identity_sha256,
          horizon_minutes,target_at_utc,
          reference_expected_at_utc,reference_candle_at_utc,reference_open,
          signed_post_fill_markout_bps,markout_class,evaluation_status,
          measurement_source,source_endpoint,evidence,
          shadow_only,trade_permission
        ) values (
          pg_catalog.md5(
            'execution-quality-markout-v0.1|'||f.fill_evidence_id||'|'||h::text
          ),
          f.fill_evidence_id,f.fill_time_utc,f.symbol,f.side,f.price,
          f.base_volume,f.quote_volume,v_origin_class,
          pg_catalog.encode(
            extensions.digest(f.order_id,'sha256'),
            'hex'
          ),
          h,v_target,v_expected,v_reference,v_reference_open,
          v_markout,v_class,'EVALUATED',
          'BITGET_PUBLIC_V3_1M_CANDLES','/api/v3/market/candles',
          jsonb_build_object(
            'reference_rule','FIRST_EXACT_1M_OPEN_AT_OR_AFTER_HORIZON',
            'exact_expected_minute_required',true,
            'public_market_data_only',true,
            'markout_is_not_slippage',true,
            'markout_is_not_realistic_net_r',true,
            'fill_origin_class',v_origin_class
          ),
          true,false
        )
        on conflict(fill_evidence_id,horizon_minutes) do nothing;

        if found then
          v_inserted := v_inserted+1;
        end if;
      end loop;

    exception when others then
      v_error := left(sqlerrm,1000);
      v_failures := v_failures+1;

      insert into public.alpha_hunter_execution_markout_failures_v01(
        failure_id,fill_evidence_id,error_class,error_message,
        shadow_only,trade_permission
      ) values (
        pg_catalog.md5(
          'execution-quality-markout-failure-v0.1|'||f.fill_evidence_id
          ||'|'||clock_timestamp()::text
        ),
        f.fill_evidence_id,
        case
          when v_error like 'BITGET_HTTP_STATUS:%' then 'BITGET_HTTP_ERROR'
          when v_error like 'BITGET_PAYLOAD_CODE:%' then 'BITGET_PAYLOAD_ERROR'
          else 'MARKOUT_COLLECTOR_ERROR'
        end,
        v_error,true,false
      );
    end;
  end loop;

  return jsonb_build_object(
    'mode','PUBLIC_POST_FILL_MARKOUT_COLLECTION',
    'fills_processed',v_processed_fills,
    'evaluated_rows_inserted',v_inserted,
    'data_insufficient_rows_inserted',v_data_insufficient,
    'failure_events',v_failures,
    'slippage_inferred',false,
    'cost_model_activated',false,
    'realistic_net_r_claimed',false,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_collect_execution_markouts_v01()
  from public,anon,authenticated,service_role;


create or replace view public.alpha_hunter_execution_order_markouts_v01
with (security_invoker=true,security_barrier=true)
as
select
  order_identity_sha256,
  fill_origin_class,
  horizon_minutes,
  count(*)::bigint as constituent_fill_count,
  sum(coalesce(fill_quote_volume,0)) as constituent_quote_volume,
  case
    when bool_and(evaluation_status='EVALUATED') and count(*)>0
      then 'EVALUATED'
    else 'DATA_INSUFFICIENT'
  end as evaluation_status,
  case
    when bool_and(evaluation_status='EVALUATED')
      and sum(coalesce(fill_quote_volume,0))>0
    then sum(
      signed_post_fill_markout_bps*fill_quote_volume
    )/sum(fill_quote_volume)
    when bool_and(evaluation_status='EVALUATED')
    then avg(signed_post_fill_markout_bps)
  end as order_weighted_signed_markout_bps,
  false as slippage_claim_permitted,
  false as alpha_hunter_execution_claim_permitted,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_execution_markout_evidence_v01
group by order_identity_sha256,fill_origin_class,horizon_minutes;

revoke all on public.alpha_hunter_execution_order_markouts_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_order_markouts_v01
  to service_role;


create or replace view public.alpha_hunter_execution_quality_status_v01
with (security_invoker=true,security_barrier=true)
as
with markouts as (
  select
    fill_origin_class,
    horizon_minutes,
    count(*)::bigint as rows,
    count(*) filter(where evaluation_status='EVALUATED')::bigint as evaluated_rows,
    count(*) filter(where evaluation_status='DATA_INSUFFICIENT')::bigint
      as data_insufficient_rows,
    sum(constituent_fill_count)::bigint as constituent_fill_rows,
    percentile_cont(0.5) within group(
      order by order_weighted_signed_markout_bps
    ) filter(where evaluation_status='EVALUATED')
      as median_signed_markout_bps,
    avg(order_weighted_signed_markout_bps)
      filter(where evaluation_status='EVALUATED')
      as mean_signed_markout_bps,
    count(*) filter(
      where evaluation_status='EVALUATED'
        and order_weighted_signed_markout_bps<0
    )::bigint as adverse_markout_rows
  from public.alpha_hunter_execution_order_markouts_v01
  group by fill_origin_class,horizon_minutes
)
select
  m.fill_origin_class,
  m.horizon_minutes,
  m.rows,
  m.evaluated_rows,
  m.data_insufficient_rows,
  m.constituent_fill_rows,
  m.median_signed_markout_bps,
  m.mean_signed_markout_bps,
  m.adverse_markout_rows,
  case
    when m.evaluated_rows>0
    then round(100.0*m.adverse_markout_rows/m.evaluated_rows,2)
  end as adverse_markout_pct,
  (
    select count(*)::bigint
    from public.alpha_hunter_execution_order_evidence_v01 o
    where o.fill_origin_class=m.fill_origin_class
  ) as private_order_detail_rows,
  (
    select count(*)::bigint
    from public.alpha_hunter_execution_order_evidence_v01 o
    where o.fill_origin_class=m.fill_origin_class
      and o.limit_price_delta_claim_permitted=true
  ) as explicit_limit_benchmark_rows,
  'DESCRIPTIVE_EXECUTION_QUALITY_ONLY'::text as scientific_status,
  'NO_SLIPPAGE_OR_NET_R_MODEL_ACTIVATION'::text as claim_ceiling,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  true as shadow_only,
  false as trade_permission
from markouts m
order by m.fill_origin_class,m.horizon_minutes;

revoke all on public.alpha_hunter_execution_quality_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_quality_status_v01
  to service_role;


do $$
begin
  if not exists(
    select 1
    from cron.job
    where jobname='alpha-hunter-execution-markouts-hourly'
  ) then
    perform cron.schedule(
      'alpha-hunter-execution-markouts-hourly',
      '47 * * * *',
      'select private.alpha_hunter_collect_execution_markouts_v01();'
    );
  end if;
end;
$$;
