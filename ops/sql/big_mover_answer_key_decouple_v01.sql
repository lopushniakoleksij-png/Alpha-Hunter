-- Alpha Hunter Big-Mover answer-key / shadow-scoring decoupling v0.1
--
-- Operational isolation only.
-- Current Bitget answer-key evidence must not roll back merely because the
-- research-only robust shadow scorer is expensive.
--
-- Schedule:
--   :46  heavy shadow scoring, isolated from the core control-plane chain
--   :10  lightweight answer-key capture
--   :16  parent direction, guarded against stale shadow evidence
--
-- No trading threshold, strategy, direction, risk, READY or order authority
-- changes are introduced.

create or replace function public.alpha_hunter_collect_big_mover_answer_key()
returns jsonb
language plpgsql
security definer
set search_path = 'public','extensions'
as $function$
declare
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_observed_at timestamptz:=clock_timestamp();
  v_bucket timestamptz:=date_trunc('hour',clock_timestamp());
  v_inserted integer:=0;
  v_latest_feature_run_id text;
  v_latest_feature_at timestamptz;
  v_latest_shadow_run_id text;
  v_latest_shadow_at timestamptz;
  v_shadow_fresh boolean:=false;
begin
  select (r).status,(r).content
    into v_status,v_content
  from (
    select extensions.http_get(
      'https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures'
    ) as r
  ) q;

  if v_status<>200 then
    raise exception 'Bitget ticker HTTP status %',v_status;
  end if;

  v_payload:=v_content::jsonb;

  if coalesce(v_payload->>'code','')<>'00000' then
    raise exception 'Bitget ticker payload code %',v_payload->>'code';
  end if;

  with raw as (
    select value as ticker
    from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb))
  ), normalized as (
    select
      upper(ticker->>'symbol') as symbol,
      case
        when (ticker->>'lastPr')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ticker->>'lastPr')::double precision
      end as last_price,
      case
        when (ticker->>'change24h')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (ticker->>'change24h')::double precision*100.0
      end as change_pct,
      case
        when coalesce(ticker->>'quoteVolume',ticker->>'usdtVolume','')
          ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then coalesce(
          ticker->>'quoteVolume',
          ticker->>'usdtVolume'
        )::double precision
        else 0.0
      end as quote_volume
    from raw
  ), expanded as (
    select
      n.*,
      case when n.change_pct>=0 then 'UP' else 'DOWN' end as direction,
      threshold::double precision as threshold_pct
    from normalized n
    cross join unnest(array[5.0,10.0,20.0]) as threshold
    where n.symbol is not null
      and n.last_price is not null
      and n.last_price>0
      and n.change_pct is not null
      and abs(n.change_pct)>=threshold
  ), inserted as (
    insert into public.alpha_hunter_big_mover_answer_key(
      event_id,observed_at_utc,hour_bucket_utc,symbol,product_type,
      direction,threshold_pct,current_24h_move_pct,last_price,
      quote_volume_24h,strategy_eligible,liquidity_pass,source,model_version,
      shadow_only,trade_permission
    )
    select
      md5(
        'big-mover-answer-key-v0.1|'||symbol||'|'||v_bucket::text||'|'||
        direction||'|'||to_char(threshold_pct,'FM999990.00')
      ),
      v_observed_at,v_bucket,symbol,'usdt-futures',direction,threshold_pct,
      change_pct,last_price,quote_volume,true,quote_volume>=100000.0,
      'BITGET_PUBLIC_ALL_TICKERS_DB_HTTP',
      'big-mover-answer-key-v0.2-decoupled',
      true,false
    from expanded
    on conflict(event_id) do nothing
    returning 1
  )
  select count(*) into v_inserted from inserted;

  select sf.run_id,max(sf.captured_at_utc)
    into v_latest_feature_run_id,v_latest_feature_at
  from public.alpha_hunter_signal_features sf
  join public.alpha_hunter_snapshots p
    on p.run_id=sf.run_id
  where p.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  group by sf.run_id
  order by max(sf.captured_at_utc) desc
  limit 1;

  select b.run_id,b.captured_at_utc
    into v_latest_shadow_run_id,v_latest_shadow_at
  from public.alpha_hunter_big_mover_shadow b
  order by b.captured_at_utc desc,b.created_at desc
  limit 1;

  v_shadow_fresh:=(
    v_latest_shadow_at is not null
    and clock_timestamp()-v_latest_shadow_at<=interval '90 minutes'
  );

  return jsonb_build_object(
    'mode','BITGET_BIG_MOVER_DB_NATIVE_HOURLY',
    'shadow_only',true,
    'trade_permission',false,
    'observed_at_utc',v_observed_at,
    'answer_key_rows_inserted',v_inserted,
    'ticker_count',jsonb_array_length(coalesce(v_payload->'data','[]'::jsonb)),
    'scoring',jsonb_build_object(
      'status','DECOUPLED_RESEARCH_SCORER',
      'latest_feature_run_id',v_latest_feature_run_id,
      'latest_feature_at_utc',v_latest_feature_at,
      'latest_shadow_run_id',v_latest_shadow_run_id,
      'latest_shadow_at_utc',v_latest_shadow_at,
      'shadow_scoring_fresh',v_shadow_fresh,
      'heavy_scoring_inline',false,
      'heavy_scoring_schedule','11 * * * *'
    )
  );
end;
$function$;

revoke execute on function public.alpha_hunter_collect_big_mover_answer_key()
from public,anon,authenticated;
grant execute on function public.alpha_hunter_collect_big_mover_answer_key()
to service_role;

-- Preserve the existing full-coverage parent-direction implementation as the
-- core, then put a freshness firewall in front of it.
do $rename$
begin
  if to_regprocedure(
       'private.alpha_hunter_collect_big_mover_parent_direction_core_v03()'
     ) is null
  then
    alter function private.alpha_hunter_collect_big_mover_parent_direction()
      rename to alpha_hunter_collect_big_mover_parent_direction_core_v03;
  end if;
end;
$rename$;

create or replace function private.alpha_hunter_collect_big_mover_parent_direction()
returns jsonb
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_shadow_run_id text;
  v_shadow_at timestamptz;
  v_result jsonb;
begin
  select b.run_id,b.captured_at_utc
    into v_shadow_run_id,v_shadow_at
  from public.alpha_hunter_big_mover_shadow b
  order by b.captured_at_utc desc,b.created_at desc
  limit 1;

  if v_shadow_run_id is null or v_shadow_at is null then
    raise exception 'no big-mover shadow run available';
  end if;

  if clock_timestamp()-v_shadow_at>interval '90 minutes' then
    raise exception
      'big-mover shadow is stale: run_id=%, captured_at=%',
      v_shadow_run_id,v_shadow_at;
  end if;

  v_result:=private.alpha_hunter_collect_big_mover_parent_direction_core_v03();

  return v_result||jsonb_build_object(
    'shadow_freshness_guard',true,
    'shadow_run_id',v_shadow_run_id,
    'shadow_captured_at_utc',v_shadow_at,
    'shadow_max_age_minutes',90,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$function$;

revoke all on function private.alpha_hunter_collect_big_mover_parent_direction()
from public,anon,authenticated;
grant execute on function private.alpha_hunter_collect_big_mover_parent_direction()
to service_role;

-- Heavy training/scoring is research-only and runs after the core chain.
do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-big-mover-shadow-model-research-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-big-mover-shadow-model-research-v01',
  '11 * * * *',
  $cmd$
    set statement_timeout='240s';
    select public.alpha_hunter_run_big_mover_shadow();
  $cmd$
);
