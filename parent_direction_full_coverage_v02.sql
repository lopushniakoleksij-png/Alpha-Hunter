-- Alpha Hunter parent-direction full-coverage collector v0.2
-- Forward-only function replacement. Public market data only.
-- Fetch each eligible symbol once per timeframe, then fan the result out to every
-- LONG/SHORT hypothesis for that symbol. No threshold/risk/trade-permission change.

create or replace function private.alpha_hunter_collect_big_mover_parent_direction()
returns jsonb
language plpgsql
security definer
set search_path to ''
as $$
declare
  v_run_id text;
  v_symbol record;
  v_hypothesis record;
  v_tf text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_trend jsonb;
  v_endpoint text;
  v_unique_symbols integer := 0;
  v_hypotheses integer := 0;
  v_http_requests integer := 0;
  v_rows_written integer := 0;
  v_failed integer := 0;
begin
  select b.run_id into v_run_id
  from public.alpha_hunter_big_mover_shadow b
  order by b.captured_at_utc desc,b.created_at desc
  limit 1;

  if v_run_id is null then
    raise exception 'no big-mover shadow run available';
  end if;

  with latest_shadow as (
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_shadow b
    where b.run_id=v_run_id
    order by b.symbol,b.direction,b.created_at desc,b.model_version desc
  ), eligible as (
    select *
    from latest_shadow
    where research_status='SHADOW_QUEUE'
      and lifecycle in('PRE_MOVER','IGNITION','EXPANSION')
      and symbol ~ '^[A-Z0-9]+USDT$'
  )
  select count(*),count(distinct symbol)
    into v_hypotheses,v_unique_symbols
  from eligible;

  for v_symbol in
    with latest_shadow as (
      select distinct on (b.symbol,b.direction) b.*
      from public.alpha_hunter_big_mover_shadow b
      where b.run_id=v_run_id
      order by b.symbol,b.direction,b.created_at desc,b.model_version desc
    ), eligible as (
      select *
      from latest_shadow
      where research_status='SHADOW_QUEUE'
        and lifecycle in('PRE_MOVER','IGNITION','EXPANSION')
        and symbol ~ '^[A-Z0-9]+USDT$'
    )
    select symbol,max(captured_at_utc) as captured_at_utc
    from eligible
    group by symbol
    order by symbol
  loop
    foreach v_tf in array array['12H','1D'] loop
      -- Bitget v3 market/candles is documented at 20 req/sec/IP.
      -- 60ms pacing keeps this collector below that rate even if responses are very fast.
      perform pg_catalog.pg_sleep(0.06);
      v_endpoint := 'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol='||v_symbol.symbol||'&interval='||v_tf||'&limit=60';
      v_http_requests := v_http_requests+1;

      begin
        select (r).status,(r).content into v_status,v_content
        from (select extensions.http_get(v_endpoint) as r) q;

        if v_status<>200 then
          v_trend := jsonb_build_object('trend','DATA_UNAVAILABLE','candle_count',0,'latest_close',null,'error','HTTP_'||v_status::text);
          v_failed := v_failed+1;
        else
          v_payload := v_content::jsonb;
          v_trend := private.alpha_hunter_parent_trend_from_payload(v_payload);
          if coalesce(v_trend->>'trend','DATA_UNAVAILABLE')='DATA_UNAVAILABLE' then
            v_failed := v_failed+1;
          end if;
        end if;
      exception when others then
        v_trend := jsonb_build_object('trend','DATA_UNAVAILABLE','candle_count',0,'latest_close',null,'error',sqlerrm);
        v_failed := v_failed+1;
      end;

      for v_hypothesis in
        with latest_shadow as (
          select distinct on (b.symbol,b.direction) b.*
          from public.alpha_hunter_big_mover_shadow b
          where b.run_id=v_run_id
          order by b.symbol,b.direction,b.created_at desc,b.model_version desc
        )
        select symbol,direction,captured_at_utc
        from latest_shadow
        where symbol=v_symbol.symbol
          and research_status='SHADOW_QUEUE'
          and lifecycle in('PRE_MOVER','IGNITION','EXPANSION')
          and symbol ~ '^[A-Z0-9]+USDT$'
        order by direction
      loop
        insert into public.alpha_hunter_big_mover_parent_direction_shadow(
          snapshot_id,run_id,captured_at_utc,symbol,direction,timeframe,trend,candle_count,latest_close,
          source_endpoint,collection_status,error,model_version,shadow_only,trade_permission,updated_at
        ) values (
          -- Preserve logical identity used by v0.1 so repeated same-run collection updates rather than duplicates.
          md5('big-mover-parent-direction-shadow-v0.1|'||v_run_id||'|'||v_hypothesis.symbol||'|'||v_hypothesis.direction||'|'||v_tf),
          v_run_id,v_hypothesis.captured_at_utc,v_hypothesis.symbol,v_hypothesis.direction,v_tf,
          coalesce(v_trend->>'trend','DATA_UNAVAILABLE'),coalesce((v_trend->>'candle_count')::integer,0),
          case when (v_trend->>'latest_close') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
            then (v_trend->>'latest_close')::double precision end,
          v_endpoint,
          case when coalesce(v_trend->>'trend','DATA_UNAVAILABLE')='DATA_UNAVAILABLE' then 'FAILED' else 'PASS' end,
          nullif(v_trend->>'error','null'),
          'big-mover-parent-direction-shadow-v0.2-full-money-entry-coverage',true,false,now()
        )
        on conflict(snapshot_id) do update set
          captured_at_utc=excluded.captured_at_utc,
          trend=excluded.trend,
          candle_count=excluded.candle_count,
          latest_close=excluded.latest_close,
          source_endpoint=excluded.source_endpoint,
          collection_status=excluded.collection_status,
          error=excluded.error,
          model_version=excluded.model_version,
          shadow_only=true,
          trade_permission=false,
          updated_at=now();
        v_rows_written := v_rows_written+1;
      end loop;
    end loop;
  end loop;

  return jsonb_build_object(
    'mode','BIG_MOVER_PARENT_DIRECTION_SHADOW',
    'run_id',v_run_id,
    'coverage_contract','ALL_SHADOW_QUEUE_PRE_MOVER_IGNITION_EXPANSION',
    'hypotheses_covered',v_hypotheses,
    'unique_symbols',v_unique_symbols,
    'timeframes',jsonb_build_array('12H','1D'),
    'http_requests',v_http_requests,
    'rows_processed',v_rows_written,
    'failed_rows',v_failed,
    'symbol_request_deduplication',true,
    'rate_limit_guard_ms',60,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_collect_big_mover_parent_direction() from public,anon,authenticated;
grant execute on function private.alpha_hunter_collect_big_mover_parent_direction() to service_role;
