-- Alpha Hunter Big-Mover parent-direction shadow collector.
-- This is deliberately isolated from the legacy 15m/1H/4H scanner state machine.
-- It uses public Bitget candles only and can never grant trade permission.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_big_mover_parent_direction_shadow (
  snapshot_id text primary key,
  run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  timeframe text not null check (timeframe in ('12H','1D')),
  trend text not null check (trend in ('BULLISH','BEARISH','NEUTRAL','DATA_UNAVAILABLE')),
  candle_count integer not null default 0,
  latest_close double precision,
  source_endpoint text not null,
  collection_status text not null,
  error text,
  model_version text not null default 'big-mover-parent-direction-shadow-v0.1',
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_ah_big_mover_parent_run_symbol
  on public.alpha_hunter_big_mover_parent_direction_shadow(run_id,symbol,direction,timeframe);

alter table public.alpha_hunter_big_mover_parent_direction_shadow enable row level security;
revoke all on table public.alpha_hunter_big_mover_parent_direction_shadow from public, anon, authenticated;
grant select, insert, update on table public.alpha_hunter_big_mover_parent_direction_shadow to service_role;

-- Reproduce the existing Python EMA calculation without changing production scanner logic.
create or replace function private.alpha_hunter_ema(
  p_values double precision[],
  p_period integer
)
returns double precision
language plpgsql
immutable
set search_path = ''
as $$
declare
  v_n integer;
  v_ema double precision;
  v_alpha double precision;
  i integer;
begin
  v_n := coalesce(array_length(p_values,1),0);
  if p_period <= 0 or v_n < p_period then
    return null;
  end if;
  select avg(x) into v_ema from unnest(p_values[1:p_period]) as u(x);
  v_alpha := 2.0/(p_period+1.0);
  if v_n > p_period then
    for i in p_period+1..v_n loop
      v_ema := (p_values[i]-v_ema)*v_alpha+v_ema;
    end loop;
  end if;
  return v_ema;
end;
$$;

revoke execute on function private.alpha_hunter_ema(double precision[],integer) from public, anon, authenticated;
grant execute on function private.alpha_hunter_ema(double precision[],integer) to service_role;

-- Reproduce analysis.py::trend_state: EMA9 vs EMA21 plus latest close vs close five candles ago.
create or replace function private.alpha_hunter_parent_trend_from_payload(p_payload jsonb)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
declare
  v_values double precision[];
  v_n integer;
  v_fast double precision;
  v_slow double precision;
  v_recent double precision;
  v_prior double precision;
  v_trend text;
begin
  if coalesce(p_payload->>'code','') <> '00000' then
    return jsonb_build_object(
      'trend','DATA_UNAVAILABLE','candle_count',0,'latest_close',null,
      'error','BITGET_CODE_'||coalesce(p_payload->>'code','MISSING')
    );
  end if;

  select array_agg(close_value order by ts_value)
    into v_values
  from (
    select
      case when (row_value->>0) ~ '^[0-9]+$' then (row_value->>0)::bigint end as ts_value,
      case when (row_value->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (row_value->>4)::double precision end as close_value
    from jsonb_array_elements(coalesce(p_payload->'data','[]'::jsonb)) as r(row_value)
    where jsonb_typeof(row_value)='array' and jsonb_array_length(row_value)>=5
  ) q
  where ts_value is not null and close_value is not null;

  v_n := coalesce(array_length(v_values,1),0);
  if v_n < 30 then
    return jsonb_build_object(
      'trend','DATA_UNAVAILABLE','candle_count',v_n,
      'latest_close',case when v_n>0 then v_values[v_n] else null end,
      'error','INSUFFICIENT_CANDLES'
    );
  end if;

  v_fast := private.alpha_hunter_ema(v_values,9);
  v_slow := private.alpha_hunter_ema(v_values,21);
  v_recent := v_values[v_n];
  v_prior := v_values[v_n-4];

  if v_fast is not null and v_slow is not null and v_fast>v_slow and v_recent>v_prior then
    v_trend := 'BULLISH';
  elsif v_fast is not null and v_slow is not null and v_fast<v_slow and v_recent<v_prior then
    v_trend := 'BEARISH';
  else
    v_trend := 'NEUTRAL';
  end if;

  return jsonb_build_object(
    'trend',v_trend,'candle_count',v_n,'latest_close',v_recent,
    'ema9',v_fast,'ema21',v_slow,'prior_close_5',v_prior,'error',null
  );
end;
$$;

revoke execute on function private.alpha_hunter_parent_trend_from_payload(jsonb) from public, anon, authenticated;
grant execute on function private.alpha_hunter_parent_trend_from_payload(jsonb) to service_role;

-- Collect only the top five early candidates per side: at most twenty public candle requests/hour.
create or replace function private.alpha_hunter_collect_big_mover_parent_direction()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_run_id text;
  v_row record;
  v_tf text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_trend jsonb;
  v_count integer := 0;
  v_failed integer := 0;
  v_endpoint text;
begin
  select b.run_id into v_run_id
  from public.alpha_hunter_big_mover_shadow b
  order by b.captured_at_utc desc,b.created_at desc limit 1;
  if v_run_id is null then
    raise exception 'no big-mover shadow run available';
  end if;

  for v_row in
    with latest_shadow as (
      select distinct on (b.symbol,b.direction) b.*
      from public.alpha_hunter_big_mover_shadow b
      where b.run_id=v_run_id
      order by b.symbol,b.direction,b.created_at desc,b.model_version desc
    ), ranked as (
      select b.*,
        row_number() over(
          partition by b.direction
          order by b.similarity_score desc nulls last,b.feature_coverage desc,b.symbol
        ) as rn
      from latest_shadow b
      where b.research_status='SHADOW_QUEUE'
        and b.lifecycle in('PRE_MOVER','IGNITION')
        and coalesce(b.direction_normalized_move_pct,b.current_move_pct)>=-3
    )
    select symbol,direction,captured_at_utc
    from ranked
    where rn<=5 and symbol ~ '^[A-Z0-9]+USDT$'
  loop
    foreach v_tf in array array['12H','1D'] loop
      begin
        v_endpoint := 'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol='||v_row.symbol||'&interval='||v_tf||'&limit=60';
        select (r).status,(r).content into v_status,v_content
        from (select extensions.http_get(v_endpoint) as r) q;

        if v_status<>200 then
          v_trend := jsonb_build_object(
            'trend','DATA_UNAVAILABLE','candle_count',0,'latest_close',null,
            'error','HTTP_'||v_status::text
          );
          v_failed := v_failed+1;
        else
          v_payload := v_content::jsonb;
          v_trend := private.alpha_hunter_parent_trend_from_payload(v_payload);
          if coalesce(v_trend->>'trend','DATA_UNAVAILABLE')='DATA_UNAVAILABLE' then
            v_failed := v_failed+1;
          end if;
        end if;
      exception when others then
        v_trend := jsonb_build_object(
          'trend','DATA_UNAVAILABLE','candle_count',0,'latest_close',null,'error',sqlerrm
        );
        v_failed := v_failed+1;
      end;

      insert into public.alpha_hunter_big_mover_parent_direction_shadow(
        snapshot_id,run_id,captured_at_utc,symbol,direction,timeframe,trend,candle_count,latest_close,
        source_endpoint,collection_status,error,model_version,shadow_only,trade_permission,updated_at
      ) values (
        md5('big-mover-parent-direction-shadow-v0.1|'||v_run_id||'|'||v_row.symbol||'|'||v_row.direction||'|'||v_tf),
        v_run_id,v_row.captured_at_utc,v_row.symbol,v_row.direction,v_tf,
        coalesce(v_trend->>'trend','DATA_UNAVAILABLE'),coalesce((v_trend->>'candle_count')::integer,0),
        case when (v_trend->>'latest_close') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          then (v_trend->>'latest_close')::double precision end,
        v_endpoint,
        case when coalesce(v_trend->>'trend','DATA_UNAVAILABLE')='DATA_UNAVAILABLE' then 'FAILED' else 'PASS' end,
        nullif(v_trend->>'error','null'),'big-mover-parent-direction-shadow-v0.1',true,false,now()
      )
      on conflict(snapshot_id) do update set
        captured_at_utc=excluded.captured_at_utc,
        trend=excluded.trend,
        candle_count=excluded.candle_count,
        latest_close=excluded.latest_close,
        source_endpoint=excluded.source_endpoint,
        collection_status=excluded.collection_status,
        error=excluded.error,
        shadow_only=true,
        trade_permission=false,
        updated_at=now();

      v_count := v_count+1;
    end loop;
  end loop;

  return jsonb_build_object(
    'mode','BIG_MOVER_PARENT_DIRECTION_SHADOW',
    'run_id',v_run_id,
    'rows_processed',v_count,
    'failed_rows',v_failed,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke execute on function private.alpha_hunter_collect_big_mover_parent_direction() from public, anon, authenticated;
grant execute on function private.alpha_hunter_collect_big_mover_parent_direction() to service_role;

-- Big-Mover scoring is at :10; parent direction follows at :11.
do $$
begin
  if exists(select 1 from cron.job where jobname='alpha-hunter-big-mover-parent-direction-hourly') then
    perform cron.unschedule(jobid)
    from cron.job
    where jobname='alpha-hunter-big-mover-parent-direction-hourly';
  end if;
  perform cron.schedule(
    'alpha-hunter-big-mover-parent-direction-hourly',
    '11 * * * *',
    'select private.alpha_hunter_collect_big_mover_parent_direction();'
  );
end;
$$;
