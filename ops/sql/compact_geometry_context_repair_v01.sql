-- Alpha Hunter compact geometry-context forward repair v0.1
--
-- Root cause:
--   signal-source-v0.2 compact storage removed source_payload.timeframes.
--   The prospective geometry holdout depends on compact 15m/1H/4H
--   support/resistance plus 15m/1H ATR and 1H volume-anomaly state.
--
-- Production-safe bridge:
--   Enrich ONLY future alpha_hunter_signal_features inserts from the canonical
--   alpha_hunter_symbol_snapshots row with the exact same run_id + symbol.
--
-- No historical backfill.
-- No trade/threshold/risk/selector/order authority.
-- Fail-open for the production feature insert: an enrichment error records a
-- private failure event and returns NEW unchanged rather than breaking scanner.

create table if not exists private.alpha_hunter_geometry_context_enrichment_events_v01 (
  event_id text primary key,
  occurred_at_utc timestamptz not null default clock_timestamp(),
  event_type text not null check(event_type in ('ENRICHED','SOURCE_MISSING','ERROR')),
  run_id text,
  signal_id text,
  symbol text,
  source_snapshot_created_at timestamptz,
  timeframes_restored boolean not null default false,
  error_sqlstate text,
  error_message text,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'GEOMETRY_CONTEXT_SOURCE_REPAIR',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

create index if not exists idx_ah_geometry_context_enrich_event_time_v01
  on private.alpha_hunter_geometry_context_enrichment_events_v01(
    event_type,occurred_at_utc desc
  );

create or replace function private.alpha_hunter_enrich_signal_feature_geometry_context_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_payload jsonb;
  v_snapshot_created_at timestamptz;
  v_timeframes jsonb;
  v_event_id text;
begin
  if jsonb_typeof(new.source_payload->'timeframes')='object'
     and coalesce(new.source_payload->'timeframes','{}'::jsonb)<>'{}'::jsonb
  then
    return new;
  end if;

  select s.payload,s.created_at
    into v_payload,v_snapshot_created_at
  from public.alpha_hunter_symbol_snapshots s
  where s.run_id=new.run_id
    and s.symbol=new.symbol
  order by s.created_at desc
  limit 1;

  if v_payload is null then
    v_event_id:='geometry-context-source-missing-'||
      md5(coalesce(new.signal_id,'')||'|'||coalesce(new.run_id,'')||'|'||
          coalesce(new.symbol,'')||'|'||clock_timestamp()::text);

    insert into private.alpha_hunter_geometry_context_enrichment_events_v01(
      event_id,event_type,run_id,signal_id,symbol,timeframes_restored,evidence,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      v_event_id,'SOURCE_MISSING',new.run_id,new.signal_id,new.symbol,false,
      jsonb_build_object(
        'join_contract','EXACT_RUN_ID_PLUS_SYMBOL',
        'historical_backfill_permitted',false
      ),
      true,false,false,'NONE'
    );

    return new;
  end if;

  v_timeframes:=jsonb_build_object(
    '15m',jsonb_build_object(
      'trend',v_payload#>'{timeframes,15m,trend}',
      'support',v_payload#>'{timeframes,15m,support}',
      'resistance',v_payload#>'{timeframes,15m,resistance}',
      'indicators',jsonb_build_object(
        'atr_pct',v_payload#>'{timeframes,15m,indicators,atr_pct}',
        'volume_anomaly',jsonb_build_object(
          'state',v_payload#>'{timeframes,15m,indicators,volume_anomaly,state}',
          'ratio',v_payload#>'{timeframes,15m,indicators,volume_anomaly,ratio}',
          'z_score',v_payload#>'{timeframes,15m,indicators,volume_anomaly,z_score}',
          'source',v_payload#>'{timeframes,15m,indicators,volume_anomaly,source}',
          'candle_interval_ms',v_payload#>'{timeframes,15m,indicators,volume_anomaly,candle_interval_ms}',
          'ignored_incomplete_candle',v_payload#>'{timeframes,15m,indicators,volume_anomaly,ignored_incomplete_candle}'
        )
      )
    ),
    '1H',jsonb_build_object(
      'trend',v_payload#>'{timeframes,1H,trend}',
      'support',v_payload#>'{timeframes,1H,support}',
      'resistance',v_payload#>'{timeframes,1H,resistance}',
      'indicators',jsonb_build_object(
        'atr_pct',v_payload#>'{timeframes,1H,indicators,atr_pct}',
        'volume_anomaly',jsonb_build_object(
          'state',v_payload#>'{timeframes,1H,indicators,volume_anomaly,state}',
          'ratio',v_payload#>'{timeframes,1H,indicators,volume_anomaly,ratio}',
          'z_score',v_payload#>'{timeframes,1H,indicators,volume_anomaly,z_score}',
          'source',v_payload#>'{timeframes,1H,indicators,volume_anomaly,source}',
          'candle_interval_ms',v_payload#>'{timeframes,1H,indicators,volume_anomaly,candle_interval_ms}',
          'ignored_incomplete_candle',v_payload#>'{timeframes,1H,indicators,volume_anomaly,ignored_incomplete_candle}'
        )
      )
    ),
    '4H',jsonb_build_object(
      'trend',v_payload#>'{timeframes,4H,trend}',
      'support',v_payload#>'{timeframes,4H,support}',
      'resistance',v_payload#>'{timeframes,4H,resistance}',
      'indicators',jsonb_build_object(
        'atr_pct',v_payload#>'{timeframes,4H,indicators,atr_pct}',
        'volume_anomaly',jsonb_build_object(
          'state',v_payload#>'{timeframes,4H,indicators,volume_anomaly,state}',
          'ratio',v_payload#>'{timeframes,4H,indicators,volume_anomaly,ratio}',
          'z_score',v_payload#>'{timeframes,4H,indicators,volume_anomaly,z_score}',
          'source',v_payload#>'{timeframes,4H,indicators,volume_anomaly,source}',
          'candle_interval_ms',v_payload#>'{timeframes,4H,indicators,volume_anomaly,candle_interval_ms}',
          'ignored_incomplete_candle',v_payload#>'{timeframes,4H,indicators,volume_anomaly,ignored_incomplete_candle}'
        )
      )
    )
  );

  new.source_payload:=
    coalesce(new.source_payload,'{}'::jsonb)
    || jsonb_build_object(
      'timeframes',v_timeframes,
      '_geometry_context_version','geometry-context-v0.1',
      '_geometry_context_source','CANONICAL_SYMBOL_SNAPSHOT_EXACT_RUN_SYMBOL'
    );

  v_event_id:='geometry-context-enriched-'||
    md5(coalesce(new.signal_id,'')||'|'||coalesce(new.run_id,'')||'|'||
        coalesce(new.symbol,''));

  insert into private.alpha_hunter_geometry_context_enrichment_events_v01(
    event_id,event_type,run_id,signal_id,symbol,source_snapshot_created_at,
    timeframes_restored,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_event_id,'ENRICHED',new.run_id,new.signal_id,new.symbol,v_snapshot_created_at,
    true,
    jsonb_build_object(
      'join_contract','EXACT_RUN_ID_PLUS_SYMBOL',
      'geometry_context_version','geometry-context-v0.1',
      'storage_contract_preserved',new.source_payload->>'_storage_contract',
      'historical_backfill_permitted',false,
      'full_raw_timeframes_duplicated',false
    ),
    true,false,false,'NONE'
  )
  on conflict(event_id) do nothing;

  return new;

exception when others then
  begin
    v_event_id:='geometry-context-error-'||
      md5(coalesce(new.signal_id,'')||'|'||coalesce(new.run_id,'')||'|'||
          coalesce(new.symbol,'')||'|'||clock_timestamp()::text);

    insert into private.alpha_hunter_geometry_context_enrichment_events_v01(
      event_id,event_type,run_id,signal_id,symbol,timeframes_restored,
      error_sqlstate,error_message,evidence,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      v_event_id,'ERROR',new.run_id,new.signal_id,new.symbol,false,
      sqlstate,sqlerrm,
      jsonb_build_object(
        'feature_insert_fail_open',true,
        'historical_backfill_permitted',false
      ),
      true,false,false,'NONE'
    );
  exception when others then
    null;
  end;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_enrich_signal_feature_geometry_context_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_enrich_signal_feature_geometry_context_v01
  on public.alpha_hunter_signal_features;

create trigger trg_ah_enrich_signal_feature_geometry_context_v01
before insert on public.alpha_hunter_signal_features
for each row
execute function private.alpha_hunter_enrich_signal_feature_geometry_context_v01();

revoke all on private.alpha_hunter_geometry_context_enrichment_events_v01
from public,anon,authenticated,service_role;
grant select on private.alpha_hunter_geometry_context_enrichment_events_v01
to service_role;

-- Forward-only repair: no existing alpha_hunter_signal_features row is updated.
