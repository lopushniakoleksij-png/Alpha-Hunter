-- Alpha Hunter Big-Mover -> Money Entry bridge.
-- Research/evidence only. No order path and no trade permission.
-- Requires big_mover_parent_direction_shadow.sql for 12H/1D enrichment.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

alter table public.alpha_hunter_big_mover_shadow
  add column if not exists raw_change_24h_pct double precision,
  add column if not exists direction_normalized_move_pct double precision;

comment on column public.alpha_hunter_big_mover_shadow.current_move_pct is
  'Legacy direction-normalized 24h move. Use raw_change_24h_pct for signed market move and direction_normalized_move_pct for signature-relative move.';

update public.alpha_hunter_big_mover_shadow
set direction_normalized_move_pct=current_move_pct
where direction_normalized_move_pct is null;

update public.alpha_hunter_big_mover_shadow b
set raw_change_24h_pct=x.raw_move
from (
  select distinct on (sf.run_id,sf.symbol)
    sf.run_id,
    sf.symbol,
    case when (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload->>'change_24h_pct')::double precision end as raw_move
  from public.alpha_hunter_signal_features sf
  order by sf.run_id,sf.symbol,sf.captured_at_utc desc
) x
where b.run_id=x.run_id and b.symbol=x.symbol and b.raw_change_24h_pct is null;

-- Persist the Python parity blocker explicitly instead of leaving it implicit in WATCH status.
update public.alpha_hunter_big_mover_shadow
set blockers=coalesce(blockers,'[]'::jsonb)||'["CURRENT_MOVE_OPPOSES_DIRECTION"]'::jsonb,
    research_status=case when research_status='SHADOW_QUEUE' then 'WATCH' else research_status end
where coalesce(direction_normalized_move_pct,current_move_pct)<-3
  and not coalesce(blockers,'[]'::jsonb) ? 'CURRENT_MOVE_OPPOSES_DIRECTION';

create table if not exists public.alpha_hunter_big_mover_money_entry_shadow (
  bridge_id text primary key,
  run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  similarity_score double precision,
  feature_coverage double precision not null,
  lifecycle text not null,
  research_status text not null,
  raw_change_24h_pct double precision,
  direction_normalized_move_pct double precision,
  scanner_direction text,
  direction_1h text,
  direction_4h text,
  direction_12h text,
  direction_1d text,
  liquidity_state text,
  opportunity_timing text,
  candidate_quality_status text,
  candidate_entry double precision,
  stop_price double precision,
  target_price double precision,
  execution_rr double precision,
  bridge_status text not null,
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'big-mover-money-entry-bridge-v0.1',
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.alpha_hunter_big_mover_money_entry_shadow enable row level security;
revoke all on table public.alpha_hunter_big_mover_money_entry_shadow from public, anon, authenticated;
grant select, insert, update on table public.alpha_hunter_big_mover_money_entry_shadow to service_role;

create or replace function private.alpha_hunter_run_big_mover_money_entry_bridge()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_run_id text;
  v_captured timestamptz;
  v_upserted integer := 0;
  v_top_long jsonb;
  v_top_short jsonb;
begin
  select b.run_id,max(b.captured_at_utc)
    into v_run_id,v_captured
  from public.alpha_hunter_big_mover_shadow b
  where b.run_id=(
    select b2.run_id
    from public.alpha_hunter_big_mover_shadow b2
    order by b2.captured_at_utc desc,b2.created_at desc limit 1
  )
  group by b.run_id;

  if v_run_id is null then
    raise exception 'no big-mover shadow run available';
  end if;

  with latest_shadow as (
    -- Multiple model versions may coexist for one run; choose one row deterministically.
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_shadow b
    where b.run_id=v_run_id
    order by b.symbol,b.direction,b.created_at desc,b.model_version desc
  ), source_rows as (
    select
      b.run_id,b.captured_at_utc,b.symbol,b.direction,b.similarity_score,b.feature_coverage,
      b.lifecycle,b.research_status,
      coalesce(
        b.raw_change_24h_pct,
        case when (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          then (sf.source_payload->>'change_24h_pct')::double precision end
      ) as raw_change_24h_pct,
      coalesce(b.direction_normalized_move_pct,b.current_move_pct) as direction_normalized_move_pct,
      upper(nullif(sf.direction,'')) as scanner_direction,
      upper(nullif(coalesce(sf.source_payload#>>'{timeframes,1H,trend}',sf.trend_1h),'')) as direction_1h,
      upper(nullif(coalesce(sf.source_payload#>>'{timeframes,4H,trend}',sf.trend_4h),'')) as direction_4h,
      sf.liquidity_state,
      sf.source_payload->>'opportunity_timing' as opportunity_timing,
      sf.source_payload->>'candidate_quality_status' as candidate_quality_status,
      case when (sf.source_payload#>>'{execution_setup,entry}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,entry}')::double precision end as candidate_entry,
      case when (sf.source_payload#>>'{execution_setup,stop}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,stop}')::double precision end as stop_price,
      case when (sf.source_payload#>>'{execution_setup,target}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,target}')::double precision end as target_price,
      case when (sf.source_payload#>>'{execution_setup,rr}') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then (sf.source_payload#>>'{execution_setup,rr}')::double precision end as execution_rr,
      coalesce(b.blockers,'[]'::jsonb) as signature_blockers
    from latest_shadow b
    left join lateral (
      select s.*
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
  ), evaluated as (
    select s.*,
      s.signature_blockers
      || case when s.direction_normalized_move_pct<-3 then '["CURRENT_MOVE_OPPOSES_DIRECTION"]'::jsonb else '[]'::jsonb end
      || case when s.scanner_direction is not null and s.scanner_direction<>s.direction then '["SCANNER_DIRECTION_CONFLICT"]'::jsonb else '[]'::jsonb end
      || case when s.liquidity_state is null then '["LIQUIDITY_STATE_MISSING"]'::jsonb else '[]'::jsonb end
      || case when s.candidate_entry is null or s.stop_price is null or s.execution_rr is null then '["EXECUTION_GEOMETRY_MISSING"]'::jsonb else '[]'::jsonb end
      || case when s.research_status<>'SHADOW_QUEUE' then '["NOT_IN_SHADOW_QUEUE"]'::jsonb else '[]'::jsonb end as all_blockers
    from source_rows s
  ), dedup as (
    select e.*,
      (select coalesce(jsonb_agg(distinct value),'[]'::jsonb) from jsonb_array_elements(e.all_blockers)) as blockers_dedup
    from evaluated e
  ), upserted as (
    insert into public.alpha_hunter_big_mover_money_entry_shadow(
      bridge_id,run_id,captured_at_utc,symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,scanner_direction,direction_1h,direction_4h,direction_12h,direction_1d,
      liquidity_state,opportunity_timing,candidate_quality_status,candidate_entry,stop_price,target_price,execution_rr,
      bridge_status,blockers,evidence,model_version,shadow_only,trade_permission,updated_at
    )
    select
      md5('big-mover-money-entry-bridge-v0.1|'||d.run_id||'|'||d.symbol||'|'||d.direction),
      d.run_id,d.captured_at_utc,d.symbol,d.direction,d.similarity_score,d.feature_coverage,d.lifecycle,d.research_status,
      d.raw_change_24h_pct,d.direction_normalized_move_pct,d.scanner_direction,d.direction_1h,d.direction_4h,null,null,
      d.liquidity_state,d.opportunity_timing,d.candidate_quality_status,d.candidate_entry,d.stop_price,d.target_price,d.execution_rr,
      case
        when d.direction_normalized_move_pct<-3 then 'WATCH'
        when jsonb_array_length(d.blockers_dedup)>0 then 'DATA_INSUFFICIENT'
        else 'READY_FOR_MONEY_ENTRY_EVAL'
      end,
      d.blockers_dedup,
      jsonb_build_object(
        'source','BIG_MOVER_SHADOW_PLUS_LIVE_SCANNER',
        'thresholds_invented',false,
        't0_authorized',false,
        'trade_permission',false,
        'note','Bridge only. Exact T0/T1/T2 decision remains fail-closed until all Money Entry evidence and validated thresholds are present.'
      ),
      'big-mover-money-entry-bridge-v0.1',true,false,now()
    from dedup d
    on conflict(bridge_id) do update set
      captured_at_utc=excluded.captured_at_utc,
      similarity_score=excluded.similarity_score,
      feature_coverage=excluded.feature_coverage,
      lifecycle=excluded.lifecycle,
      research_status=excluded.research_status,
      raw_change_24h_pct=excluded.raw_change_24h_pct,
      direction_normalized_move_pct=excluded.direction_normalized_move_pct,
      scanner_direction=excluded.scanner_direction,
      direction_1h=excluded.direction_1h,
      direction_4h=excluded.direction_4h,
      direction_12h=null,
      direction_1d=null,
      liquidity_state=excluded.liquidity_state,
      opportunity_timing=excluded.opportunity_timing,
      candidate_quality_status=excluded.candidate_quality_status,
      candidate_entry=excluded.candidate_entry,
      stop_price=excluded.stop_price,
      target_price=excluded.target_price,
      execution_rr=excluded.execution_rr,
      bridge_status=excluded.bridge_status,
      blockers=excluded.blockers,
      evidence=excluded.evidence,
      shadow_only=true,
      trade_permission=false,
      updated_at=now()
    returning 1
  )
  select count(*) into v_upserted from upserted;

  select to_jsonb(x) into v_top_long from (
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='LONG'
    order by similarity_score desc nulls last limit 1
  ) x;

  select to_jsonb(x) into v_top_short from (
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,
      raw_change_24h_pct,direction_normalized_move_pct,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='SHORT'
    order by similarity_score desc nulls last limit 1
  ) x;

  return jsonb_build_object(
    'mode','BIG_MOVER_TO_MONEY_ENTRY_SHADOW_BRIDGE',
    'run_id',v_run_id,'captured_at_utc',v_captured,'rows_upserted',v_upserted,
    'shadow_only',true,'trade_permission',false,'top_long',v_top_long,'top_short',v_top_short
  );
end;
$$;

revoke execute on function private.alpha_hunter_run_big_mover_money_entry_bridge() from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_big_mover_money_entry_bridge() to service_role;

-- Enrich the bridge with independently collected 12H/1D parent direction.
create or replace function private.alpha_hunter_run_big_mover_money_entry_pipeline()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_base jsonb;
  v_run_id text;
  v_top_long jsonb;
  v_top_short jsonb;
begin
  v_base := private.alpha_hunter_run_big_mover_money_entry_bridge();
  v_run_id := v_base->>'run_id';

  with parents as (
    select p.run_id,p.symbol,p.direction,
      max(p.trend) filter(where p.timeframe='12H') as trend_12h,
      max(p.trend) filter(where p.timeframe='1D') as trend_1d
    from public.alpha_hunter_big_mover_parent_direction_shadow p
    where p.run_id=v_run_id
    group by p.run_id,p.symbol,p.direction
  ), base as (
    select m.bridge_id,m.direction,m.direction_normalized_move_pct,p.trend_12h,p.trend_1d,
      coalesce((
        select jsonb_agg(value)
        from jsonb_array_elements(m.blockers) e(value)
        where value #>> '{}' not in (
          'PARENT_12H_MISSING','PARENT_1D_MISSING','PARENT_12H_DATA_UNAVAILABLE','PARENT_1D_DATA_UNAVAILABLE',
          'PARENT_12H_NOT_ALIGNED','PARENT_1D_NOT_ALIGNED'
        )
      ),'[]'::jsonb) as retained
    from public.alpha_hunter_big_mover_money_entry_shadow m
    left join parents p on p.run_id=m.run_id and p.symbol=m.symbol and p.direction=m.direction
    where m.run_id=v_run_id
  ), rebuilt as (
    select b.*,
      b.retained
      || case when b.trend_12h is null or b.trend_12h='DATA_UNAVAILABLE' then '["PARENT_12H_DATA_UNAVAILABLE"]'::jsonb else '[]'::jsonb end
      || case when b.trend_1d is null or b.trend_1d='DATA_UNAVAILABLE' then '["PARENT_1D_DATA_UNAVAILABLE"]'::jsonb else '[]'::jsonb end
      || case when b.trend_12h is not null and b.trend_12h<>'DATA_UNAVAILABLE'
          and not ((b.direction='LONG' and b.trend_12h='BULLISH') or (b.direction='SHORT' and b.trend_12h='BEARISH'))
        then '["PARENT_12H_NOT_ALIGNED"]'::jsonb else '[]'::jsonb end
      || case when b.trend_1d is not null and b.trend_1d<>'DATA_UNAVAILABLE'
          and not ((b.direction='LONG' and b.trend_1d='BULLISH') or (b.direction='SHORT' and b.trend_1d='BEARISH'))
        then '["PARENT_1D_NOT_ALIGNED"]'::jsonb else '[]'::jsonb end as all_blockers
    from base b
  ), dedup as (
    select r.*,
      coalesce((select jsonb_agg(distinct value) from jsonb_array_elements(r.all_blockers)),'[]'::jsonb) as blockers_dedup
    from rebuilt r
  )
  update public.alpha_hunter_big_mover_money_entry_shadow m
  set direction_12h=d.trend_12h,
      direction_1d=d.trend_1d,
      blockers=d.blockers_dedup,
      bridge_status=case
        when coalesce(m.direction_normalized_move_pct,0)<-3 then 'WATCH'
        when (d.trend_12h is not null and d.trend_12h<>'DATA_UNAVAILABLE'
              and not ((m.direction='LONG' and d.trend_12h='BULLISH') or (m.direction='SHORT' and d.trend_12h='BEARISH')))
          or (d.trend_1d is not null and d.trend_1d<>'DATA_UNAVAILABLE'
              and not ((m.direction='LONG' and d.trend_1d='BULLISH') or (m.direction='SHORT' and d.trend_1d='BEARISH')))
          then 'BLOCKED'
        when jsonb_array_length(d.blockers_dedup)>0 then 'DATA_INSUFFICIENT'
        else 'READY_FOR_MONEY_ENTRY_EVAL'
      end,
      evidence=m.evidence||jsonb_build_object(
        'parent_direction_source','BITGET_PUBLIC_12H_1D_SHADOW',
        'parent_direction_enriched',true
      ),
      shadow_only=true,
      trade_permission=false,
      updated_at=now()
  from dedup d
  where m.bridge_id=d.bridge_id;

  select to_jsonb(x) into v_top_long from (
    select symbol,direction,similarity_score,lifecycle,research_status,raw_change_24h_pct,direction_normalized_move_pct,
      direction_12h,direction_1d,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='LONG'
    order by case bridge_status when 'READY_FOR_MONEY_ENTRY_EVAL' then 0 when 'DATA_INSUFFICIENT' then 1 when 'WATCH' then 2 else 3 end,
      similarity_score desc nulls last limit 1
  ) x;

  select to_jsonb(x) into v_top_short from (
    select symbol,direction,similarity_score,lifecycle,research_status,raw_change_24h_pct,direction_normalized_move_pct,
      direction_12h,direction_1d,bridge_status,blockers,candidate_entry,stop_price,target_price,execution_rr
    from public.alpha_hunter_big_mover_money_entry_shadow
    where run_id=v_run_id and direction='SHORT'
    order by case bridge_status when 'READY_FOR_MONEY_ENTRY_EVAL' then 0 when 'DATA_INSUFFICIENT' then 1 when 'WATCH' then 2 else 3 end,
      similarity_score desc nulls last limit 1
  ) x;

  return jsonb_build_object(
    'mode','BIG_MOVER_TO_MONEY_ENTRY_SHADOW_PIPELINE',
    'run_id',v_run_id,'shadow_only',true,'trade_permission',false,
    'top_long',v_top_long,'top_short',v_top_short
  );
end;
$$;

revoke execute on function private.alpha_hunter_run_big_mover_money_entry_pipeline() from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_big_mover_money_entry_pipeline() to service_role;

-- Parent direction is collected at :11; the bridge is evaluated at :12.
do $$
begin
  if exists(select 1 from cron.job where jobname='alpha-hunter-big-mover-money-entry-bridge-hourly') then
    perform cron.unschedule(jobid)
    from cron.job
    where jobname='alpha-hunter-big-mover-money-entry-bridge-hourly';
  end if;
  perform cron.schedule(
    'alpha-hunter-big-mover-money-entry-bridge-hourly',
    '12 * * * *',
    'select private.alpha_hunter_run_big_mover_money_entry_pipeline();'
  );
end;
$$;
