-- Alpha Hunter Big-Mover-First database-native shadow runtime
--
-- Prerequisites:
--   big_mover_answer_key_schema.sql
--   big_mover_shadow_schema.sql
--
-- Safety boundary:
--   shadow_only=true
--   trade_permission=false
--
-- GitHub is CI/source control only. Supabase pg_cron owns hourly shadow execution.

create extension if not exists pg_cron with schema extensions;
create extension if not exists http with schema extensions;

create or replace function public.alpha_hunter_big_mover_training_evidence()
returns table (
  signal_id text,
  run_id text,
  symbol text,
  captured_at_utc timestamptz,
  scanner_direction text,
  scanner_state text,
  model_direction text,
  label text,
  feature_obj jsonb,
  evidence_source text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_latest_audit timestamptz;
  v_historical_end timestamptz;
  v_historical_start timestamptz;
  v_first_answer_key timestamptz;
  v_latest_answer_key timestamptz;
  v_forward_end timestamptz;
begin
  select max(audited_at_utc) into v_latest_audit
  from public.alpha_hunter_missed_mover_audit;
  if v_latest_audit is null then
    raise exception 'no historical mover audit evidence available';
  end if;

  v_historical_end := v_latest_audit - interval '24 hours';
  v_historical_start := v_historical_end - interval '21 days';

  select min(observed_at_utc), max(observed_at_utc)
    into v_first_answer_key, v_latest_answer_key
  from public.alpha_hunter_big_mover_answer_key;
  if v_latest_answer_key is not null then
    v_forward_end := v_latest_answer_key - interval '24 hours';
  end if;

  return query
  with historical_base as (
    select
      sf.signal_id,
      sf.run_id,
      sf.symbol,
      sf.captured_at_utc,
      sf.direction as scanner_direction,
      sf.state as scanner_state,
      coalesce(sf.features, '{}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
        'volume_ratio', sf.volume_ratio,
        'volatility_pct', sf.volatility_pct,
        'compression_score', sf.compression_score,
        'funding_rate', sf.funding_rate,
        'open_interest_change_pct', sf.open_interest_change_pct,
        'relative_strength_btc', sf.relative_strength_btc,
        'rsi_15m', sf.rsi_15m,
        'rsi_1h', sf.rsi_1h,
        'rsi_4h', sf.rsi_4h,
        'distance_to_support_pct', sf.distance_to_support_pct,
        'distance_to_resistance_pct', sf.distance_to_resistance_pct,
        'behaviour_score', sf.source_payload->'behaviour'->'score',
        'spread_pct', sf.source_payload->'behaviour'->'spread_pct',
        'funding_change_pct', sf.source_payload->'behaviour'->'funding_change_pct',
        'relative_strength_acceleration', sf.source_payload->'behaviour'->'relative_strength_acceleration',
        'volume_acceleration_component', sf.source_payload->'behaviour'->'components'->'volume_acceleration',
        'trend_acceleration_component', sf.source_payload->'behaviour'->'components'->'trend_acceleration',
        'volatility_transition_component', sf.source_payload->'behaviour'->'components'->'volatility_transition',
        'liquidity_component', sf.source_payload->'behaviour'->'components'->'liquidity'
      )) as feature_obj
    from public.alpha_hunter_signal_features sf
    where sf.captured_at_utc >= v_historical_start
      and sf.captured_at_utc <= v_historical_end
      and (v_first_answer_key is null or sf.captured_at_utc < v_first_answer_key)
      and sf.source_payload ? 'change_24h_pct'
      and (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      and abs((sf.source_payload->>'change_24h_pct')::double precision) < 5.0
  ), historical_directional as (
    select hb.*, d.model_direction, d.audit_direction
    from historical_base hb
    cross join (values ('LONG','UP'),('SHORT','DOWN')) d(model_direction,audit_direction)
  ), historical_labeled as (
    select
      hd.signal_id,
      hd.run_id,
      hd.symbol,
      hd.captured_at_utc,
      hd.scanner_direction,
      hd.scanner_state,
      hd.model_direction,
      case
        when exists (
          select 1 from public.alpha_hunter_missed_mover_audit a
          where a.symbol=hd.symbol
            and a.mover_direction=hd.audit_direction
            and a.audited_at_utc > hd.captured_at_utc
            and a.audited_at_utc <= hd.captured_at_utc + interval '24 hours'
            and a.mover_threshold_pct >= 10
        ) then 'MOVER'
        when not exists (
          select 1 from public.alpha_hunter_missed_mover_audit a
          where a.symbol=hd.symbol
            and a.mover_direction=hd.audit_direction
            and a.audited_at_utc > hd.captured_at_utc
            and a.audited_at_utc <= hd.captured_at_utc + interval '24 hours'
            and a.mover_threshold_pct >= 5
        ) then 'CONTROL'
        else null
      end as label,
      hd.feature_obj,
      'HISTORICAL_MISSED_MOVER_AUDIT'::text as evidence_source
    from historical_directional hd
  ), forward_base as (
    select
      sf.signal_id,
      sf.run_id,
      sf.symbol,
      sf.captured_at_utc,
      sf.direction as scanner_direction,
      sf.state as scanner_state,
      coalesce(sf.features, '{}'::jsonb) || jsonb_strip_nulls(jsonb_build_object(
        'volume_ratio', sf.volume_ratio,
        'volatility_pct', sf.volatility_pct,
        'compression_score', sf.compression_score,
        'funding_rate', sf.funding_rate,
        'open_interest_change_pct', sf.open_interest_change_pct,
        'relative_strength_btc', sf.relative_strength_btc,
        'rsi_15m', sf.rsi_15m,
        'rsi_1h', sf.rsi_1h,
        'rsi_4h', sf.rsi_4h,
        'distance_to_support_pct', sf.distance_to_support_pct,
        'distance_to_resistance_pct', sf.distance_to_resistance_pct,
        'behaviour_score', sf.source_payload->'behaviour'->'score',
        'spread_pct', sf.source_payload->'behaviour'->'spread_pct',
        'funding_change_pct', sf.source_payload->'behaviour'->'funding_change_pct',
        'relative_strength_acceleration', sf.source_payload->'behaviour'->'relative_strength_acceleration',
        'volume_acceleration_component', sf.source_payload->'behaviour'->'components'->'volume_acceleration',
        'trend_acceleration_component', sf.source_payload->'behaviour'->'components'->'trend_acceleration',
        'volatility_transition_component', sf.source_payload->'behaviour'->'components'->'volatility_transition',
        'liquidity_component', sf.source_payload->'behaviour'->'components'->'liquidity'
      )) as feature_obj
    from public.alpha_hunter_signal_features sf
    where v_first_answer_key is not null
      and v_forward_end is not null
      and v_forward_end >= v_first_answer_key
      and sf.captured_at_utc >= v_first_answer_key
      and sf.captured_at_utc <= v_forward_end
      and sf.source_payload ? 'change_24h_pct'
      and (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      and abs((sf.source_payload->>'change_24h_pct')::double precision) < 5.0
  ), forward_directional as (
    select fb.*, d.model_direction, d.answer_direction
    from forward_base fb
    cross join (values ('LONG','UP'),('SHORT','DOWN')) d(model_direction,answer_direction)
  ), forward_labeled as (
    select
      fd.signal_id,
      fd.run_id,
      fd.symbol,
      fd.captured_at_utc,
      fd.scanner_direction,
      fd.scanner_state,
      fd.model_direction,
      case
        when exists (
          select 1 from public.alpha_hunter_big_mover_answer_key a
          where a.symbol=fd.symbol
            and a.direction=fd.answer_direction
            and a.observed_at_utc > fd.captured_at_utc
            and a.observed_at_utc <= fd.captured_at_utc + interval '24 hours'
            and a.threshold_pct >= 10
        ) then 'MOVER'
        when not exists (
          select 1 from public.alpha_hunter_big_mover_answer_key a
          where a.symbol=fd.symbol
            and a.direction=fd.answer_direction
            and a.observed_at_utc > fd.captured_at_utc
            and a.observed_at_utc <= fd.captured_at_utc + interval '24 hours'
            and a.threshold_pct >= 5
        ) then 'CONTROL'
        else null
      end as label,
      fd.feature_obj,
      'BITGET_FORWARD_ANSWER_KEY'::text as evidence_source
    from forward_directional fd
  )
  select * from historical_labeled where historical_labeled.label is not null
  union all
  select * from forward_labeled where forward_labeled.label is not null;
end;
$$;

revoke all on function public.alpha_hunter_big_mover_training_evidence() from public, anon, authenticated;
grant execute on function public.alpha_hunter_big_mover_training_evidence() to service_role;

create or replace function public.alpha_hunter_run_big_mover_shadow()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_latest_audit timestamptz;
  v_first_answer_key timestamptz;
  v_latest_answer_key timestamptz;
  v_training_end timestamptz;
  v_outcome_latest timestamptz;
  v_evidence_mode text;
  v_latest_run text;
  v_latest_feature_at timestamptz;
  v_inserted integer := 0;
  v_top_long jsonb;
  v_top_short jsonb;
  v_model_version text := 'big-mover-signature-shadow-v0.2-db-forward';
begin
  select max(audited_at_utc) into v_latest_audit
  from public.alpha_hunter_missed_mover_audit;
  select min(observed_at_utc), max(observed_at_utc)
    into v_first_answer_key, v_latest_answer_key
  from public.alpha_hunter_big_mover_answer_key;

  if v_latest_answer_key is not null
     and v_first_answer_key is not null
     and v_latest_answer_key - interval '24 hours' >= v_first_answer_key then
    v_training_end := v_latest_answer_key - interval '24 hours';
    v_outcome_latest := v_latest_answer_key;
    v_evidence_mode := 'HISTORICAL_BOOTSTRAP_PLUS_FORWARD_ANSWER_KEY';
  else
    v_training_end := v_latest_audit - interval '24 hours';
    v_outcome_latest := v_latest_audit;
    v_evidence_mode := 'HISTORICAL_BOOTSTRAP_COLLECTING_FORWARD_HORIZON';
  end if;

  if v_outcome_latest is null then
    raise exception 'no mover outcome evidence available';
  end if;

  select run_id, captured_at_utc into v_latest_run, v_latest_feature_at
  from public.alpha_hunter_signal_features
  order by captured_at_utc desc limit 1;
  if v_latest_run is null then
    raise exception 'no live feature run available';
  end if;

  with labeled as (
    select * from public.alpha_hunter_big_mover_training_evidence()
  ), example_counts as (
    select model_direction,
      count(*) filter (where label='MOVER')::integer as mover_examples,
      count(*) filter (where label='CONTROL')::integer as control_examples,
      count(*)::integer as total_examples
    from labeled group by model_direction
  ), train_long as (
    select l.model_direction,l.label,l.symbol,l.captured_at_utc,
           e.key as feature,e.value::double precision as value
    from labeled l cross join lateral jsonb_each_text(l.feature_obj) e
    where e.value ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
  ), medians as (
    select model_direction,feature,
      percentile_cont(0.5) within group(order by value) filter(where label='MOVER') as mover_median,
      percentile_cont(0.5) within group(order by value) filter(where label='CONTROL') as control_median,
      count(*) filter(where label='MOVER') as mover_values,
      count(*) filter(where label='CONTROL') as control_values
    from train_long group by model_direction,feature
    having count(*) filter(where label='MOVER')>0 and count(*) filter(where label='CONTROL')>0
  ), deviations as (
    select t.model_direction,t.feature,t.label,
      abs(t.value-case when t.label='MOVER' then m.mover_median else m.control_median end) as deviation
    from train_long t join medians m using(model_direction,feature)
  ), mads as (
    select model_direction,feature,
      percentile_cont(0.5) within group(order by deviation) filter(where label='MOVER') as mover_mad,
      percentile_cont(0.5) within group(order by deviation) filter(where label='CONTROL') as control_mad
    from deviations group by model_direction,feature
  ), raw_profiles as (
    select m.model_direction,m.feature,m.mover_median,m.control_median,
      coalesce(md.mover_mad,0) as mover_mad,
      coalesce(md.control_mad,0) as control_mad,
      abs(m.mover_median-m.control_median) as centre_gap,
      (m.mover_values+m.control_values)::double precision/nullif(ec.total_examples,0) as coverage,
      ec.mover_examples,ec.control_examples
    from medians m join mads md using(model_direction,feature)
    join example_counts ec using(model_direction)
  ), profiles as (
    select r.*,ps.pooled_scale,
      case when ps.pooled_scale>0 then r.centre_gap/ps.pooled_scale else 0 end as separation,
      case when r.mover_mad>0 then r.mover_mad else ps.pooled_scale end as mover_scale,
      (case when ps.pooled_scale>0 then r.centre_gap/ps.pooled_scale else 0 end)*r.coverage as weight
    from raw_profiles r
    cross join lateral (
      select percentile_cont(0.5) within group(order by x) as pooled_scale
      from (values(nullif(r.mover_mad,0)),(nullif(r.control_mad,0)),(nullif(r.centre_gap,0))) v(x)
      where x is not null
    ) ps where ps.pooled_scale>0
  ), profile_totals as (
    select model_direction,sum(weight) as total_weight,
      max(mover_examples)::integer as mover_examples,
      max(control_examples)::integer as control_examples
    from profiles where weight>0 group by model_direction
  ), live_base as (
    select sf.symbol,sf.run_id,sf.captured_at_utc,
      (sf.source_payload->>'change_24h_pct')::double precision as raw_move,
      coalesce(sf.features,'{}'::jsonb)||jsonb_strip_nulls(jsonb_build_object(
        'volume_ratio',sf.volume_ratio,'volatility_pct',sf.volatility_pct,
        'compression_score',sf.compression_score,'funding_rate',sf.funding_rate,
        'open_interest_change_pct',sf.open_interest_change_pct,'relative_strength_btc',sf.relative_strength_btc,
        'rsi_15m',sf.rsi_15m,'rsi_1h',sf.rsi_1h,'rsi_4h',sf.rsi_4h,
        'distance_to_support_pct',sf.distance_to_support_pct,'distance_to_resistance_pct',sf.distance_to_resistance_pct,
        'behaviour_score',sf.source_payload->'behaviour'->'score','spread_pct',sf.source_payload->'behaviour'->'spread_pct',
        'funding_change_pct',sf.source_payload->'behaviour'->'funding_change_pct',
        'relative_strength_acceleration',sf.source_payload->'behaviour'->'relative_strength_acceleration',
        'volume_acceleration_component',sf.source_payload->'behaviour'->'components'->'volume_acceleration',
        'trend_acceleration_component',sf.source_payload->'behaviour'->'components'->'trend_acceleration',
        'volatility_transition_component',sf.source_payload->'behaviour'->'components'->'volatility_transition',
        'liquidity_component',sf.source_payload->'behaviour'->'components'->'liquidity'
      )) as feature_obj
    from public.alpha_hunter_signal_features sf
    where sf.run_id=v_latest_run and sf.source_payload?'change_24h_pct'
      and (sf.source_payload->>'change_24h_pct') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
  ), live_directional as (
    select lb.*,d.model_direction,
      case when d.model_direction='LONG' then lb.raw_move else -lb.raw_move end as directional_move
    from live_base lb cross join(values('LONG'),('SHORT')) d(model_direction)
  ), live_long as (
    select ld.symbol,ld.run_id,ld.captured_at_utc,ld.model_direction,ld.raw_move,ld.directional_move,
      e.key as feature,e.value::double precision as value
    from live_directional ld cross join lateral jsonb_each_text(ld.feature_obj) e
    where e.value ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
  ), scored_features as (
    select ll.*,p.mover_median,p.mover_scale,p.weight,p.mover_examples,p.control_examples,
      p.weight*(1.0/(1.0+abs(ll.value-p.mover_median)/p.mover_scale)) as weighted_similarity
    from live_long ll join profiles p using(model_direction,feature)
    where p.weight>0 and p.mover_scale>0
  ), scores as (
    select sf.symbol,sf.run_id,max(sf.captured_at_utc) as captured_at_utc,sf.model_direction,
      max(sf.raw_move) as raw_move,max(sf.directional_move) as directional_move,
      100.0*sum(sf.weighted_similarity)/nullif(sum(sf.weight),0) as similarity_score,
      sum(sf.weight)/nullif(pt.total_weight,0) as feature_coverage,
      pt.mover_examples,pt.control_examples
    from scored_features sf join profile_totals pt using(model_direction)
    group by sf.symbol,sf.run_id,sf.model_direction,pt.total_weight,pt.mover_examples,pt.control_examples
  ), classified as (
    select s.*,
      case when directional_move<1 then 'PRE_MOVER' when directional_move<=15 then 'IGNITION'
           when directional_move<=25 then 'EXPANSION' else 'EXTENDED' end as lifecycle,
      case when directional_move>25 then 'RESEARCH_ONLY' when directional_move>15 then 'RETEST_ONLY'
           when directional_move< -3 then 'WATCH' else 'SHADOW_QUEUE' end as research_status
    from scores s
  ), upserted as (
    insert into public.alpha_hunter_big_mover_shadow(
      observation_id,run_id,captured_at_utc,symbol,direction,similarity_score,feature_coverage,
      lifecycle,research_status,current_move_pct,model_version,mover_examples,control_examples,
      training_end_utc,latest_audit_utc,audit_staleness_hours,blockers,contributions,shadow_only,trade_permission
    )
    select md5(v_model_version||'|'||c.run_id||'|'||c.symbol||'|'||c.model_direction),
      c.run_id,c.captured_at_utc,c.symbol,c.model_direction,
      round(c.similarity_score::numeric,4)::double precision,round(c.feature_coverage::numeric,6)::double precision,
      c.lifecycle,c.research_status,c.directional_move,v_model_version,c.mover_examples,c.control_examples,
      v_training_end,v_outcome_latest,greatest(0,extract(epoch from(now()-v_outcome_latest))/3600.0),
      case when c.feature_coverage<0.5 then '["LOW_FEATURE_COVERAGE"]'::jsonb else '[]'::jsonb end,
      '[]'::jsonb,true,false
    from classified c
    on conflict(observation_id) do update set
      captured_at_utc=excluded.captured_at_utc,similarity_score=excluded.similarity_score,
      feature_coverage=excluded.feature_coverage,lifecycle=excluded.lifecycle,research_status=excluded.research_status,
      current_move_pct=excluded.current_move_pct,mover_examples=excluded.mover_examples,control_examples=excluded.control_examples,
      training_end_utc=excluded.training_end_utc,latest_audit_utc=excluded.latest_audit_utc,
      audit_staleness_hours=excluded.audit_staleness_hours,blockers=excluded.blockers,contributions=excluded.contributions,
      shadow_only=true,trade_permission=false
    returning 1
  ) select count(*) into v_inserted from upserted;

  select to_jsonb(x) into v_top_long from(
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,current_move_pct
    from public.alpha_hunter_big_mover_shadow
    where run_id=v_latest_run and model_version=v_model_version and direction='LONG'
      and research_status='SHADOW_QUEUE' and current_move_pct<5 and lifecycle in('PRE_MOVER','IGNITION')
    order by case when current_move_pct>=1 and current_move_pct<5 then 0 else 1 end,
      similarity_score desc nulls last,feature_coverage desc limit 1
  )x;
  select to_jsonb(x) into v_top_short from(
    select symbol,direction,similarity_score,feature_coverage,lifecycle,research_status,current_move_pct
    from public.alpha_hunter_big_mover_shadow
    where run_id=v_latest_run and model_version=v_model_version and direction='SHORT'
      and research_status='SHADOW_QUEUE' and current_move_pct<5 and lifecycle in('PRE_MOVER','IGNITION')
    order by case when current_move_pct>=1 and current_move_pct<5 then 0 else 1 end,
      similarity_score desc nulls last,feature_coverage desc limit 1
  )x;

  return jsonb_build_object(
    'mode','SUPABASE_PRODUCTION_EVIDENCE_SHADOW_ONLY','evidence_mode',v_evidence_mode,
    'shadow_only',true,'trade_permission',false,'model_version',v_model_version,
    'latest_feature_run_id',v_latest_run,'latest_feature_at_utc',v_latest_feature_at,
    'latest_outcome_evidence_utc',v_outcome_latest,'training_end_utc',v_training_end,
    'rows_upserted',v_inserted,'top_pre_mover_long',v_top_long,'top_pre_mover_short',v_top_short
  );
end;
$$;

revoke all on function public.alpha_hunter_run_big_mover_shadow() from public, anon, authenticated;
grant execute on function public.alpha_hunter_run_big_mover_shadow() to service_role;

create or replace function public.alpha_hunter_collect_big_mover_answer_key()
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_observed_at timestamptz := clock_timestamp();
  v_bucket timestamptz := date_trunc('hour',clock_timestamp());
  v_inserted integer := 0;
  v_scoring jsonb;
begin
  select (r).status,(r).content into v_status,v_content
  from(select extensions.http_get('https://api.bitget.com/api/v2/mix/market/tickers?productType=usdt-futures') as r)q;
  if v_status<>200 then raise exception 'Bitget ticker HTTP status %',v_status; end if;
  v_payload:=v_content::jsonb;
  if coalesce(v_payload->>'code','')<>'00000' then
    raise exception 'Bitget ticker payload code %',v_payload->>'code';
  end if;

  with raw as(
    select value as ticker from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb))
  ), normalized as(
    select upper(ticker->>'symbol') as symbol,
      case when(ticker->>'lastPr')~'^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then(ticker->>'lastPr')::double precision end as last_price,
      case when(ticker->>'change24h')~'^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then(ticker->>'change24h')::double precision*100.0 end as change_pct,
      case when coalesce(ticker->>'quoteVolume',ticker->>'usdtVolume','')~'^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
        then coalesce(ticker->>'quoteVolume',ticker->>'usdtVolume')::double precision else 0.0 end as quote_volume
    from raw
  ), expanded as(
    select n.*,case when n.change_pct>=0 then 'UP' else 'DOWN' end as direction,
      threshold::double precision as threshold_pct
    from normalized n cross join unnest(array[5.0,10.0,20.0]) as threshold
    where n.symbol is not null and n.last_price is not null and n.last_price>0
      and n.change_pct is not null and abs(n.change_pct)>=threshold
  ), inserted as(
    insert into public.alpha_hunter_big_mover_answer_key(
      event_id,observed_at_utc,hour_bucket_utc,symbol,product_type,direction,threshold_pct,
      current_24h_move_pct,last_price,quote_volume_24h,strategy_eligible,liquidity_pass,
      source,model_version,shadow_only,trade_permission
    )
    select md5('big-mover-answer-key-v0.1|'||symbol||'|'||v_bucket::text||'|'||direction||'|'||to_char(threshold_pct,'FM999990.00')),
      v_observed_at,v_bucket,symbol,'usdt-futures',direction,threshold_pct,change_pct,last_price,quote_volume,
      true,quote_volume>=100000.0,'BITGET_PUBLIC_ALL_TICKERS_DB_HTTP','big-mover-answer-key-v0.1-db',true,false
    from expanded on conflict(event_id)do nothing returning 1
  ) select count(*) into v_inserted from inserted;

  v_scoring:=public.alpha_hunter_run_big_mover_shadow();
  return jsonb_build_object(
    'mode','BITGET_BIG_MOVER_DB_NATIVE_HOURLY','shadow_only',true,'trade_permission',false,
    'observed_at_utc',v_observed_at,'answer_key_rows_inserted',v_inserted,
    'ticker_count',jsonb_array_length(coalesce(v_payload->'data','[]'::jsonb)),'scoring',v_scoring
  );
end;
$$;

revoke all on function public.alpha_hunter_collect_big_mover_answer_key() from public, anon, authenticated;
grant execute on function public.alpha_hunter_collect_big_mover_answer_key() to service_role;

-- Keep exactly one database-native hourly job. If already installed, do not duplicate it.
do $$
begin
  if not exists(select 1 from cron.job where jobname='alpha-hunter-big-mover-shadow-hourly') then
    perform cron.schedule(
      'alpha-hunter-big-mover-shadow-hourly',
      '10 * * * *',
      'select public.alpha_hunter_collect_big_mover_answer_key();'
    );
  end if;
end;
$$;
