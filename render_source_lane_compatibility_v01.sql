-- Alpha Hunter Render source-lane compatibility v0.1
--
-- Canonical production scanner writes RENDER_CRON.
-- Manual dashboard scans write RENDER_WEB and are excluded from canonical
-- sealed evidence and decision-support source selection.
-- Legacy RENDER remains accepted temporarily for read continuity.
--
-- Safety: no order authority, no threshold changes, no trade permission.

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

  select sf.run_id, sf.captured_at_utc
    into v_latest_run, v_latest_feature_at
  from public.alpha_hunter_signal_features sf
  join public.alpha_hunter_snapshots p
    on p.run_id=sf.run_id
  where p.payload->'validation_identity'->>'run_source'
    in ('RENDER_CRON','RENDER')
  order by
    case
      when p.payload->'validation_identity'->>'run_source'='RENDER_CRON'
        then 0
      else 1
    end,
    sf.captured_at_utc desc
  limit 1;

  if v_latest_run is null then
    raise exception 'no canonical RENDER_CRON/legacy RENDER feature run available';
  end if;

  if clock_timestamp()-v_latest_feature_at > interval '90 minutes' then
    raise exception
      'canonical RENDER_CRON feature run is stale: run_id=%, captured_at=%',
      v_latest_run,
      v_latest_feature_at;
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
    'rows_upserted',v_inserted,
    'feature_source','CANONICAL_RENDER_CRON_SIGNAL_FEATURES',
    'feature_source_max_age_minutes',90,
    'top_pre_mover_long',v_top_long,'top_pre_mover_short',v_top_short
  );
end;
$$;

revoke all on function public.alpha_hunter_run_big_mover_shadow() from public, anon, authenticated;
grant execute on function public.alpha_hunter_run_big_mover_shadow() to service_role;

-- Alpha Hunter canonical S1-S10 ready-setup view v0.1
--
-- Purpose:
-- Expose strategy candidates that have already passed the S1-S10 candidate
-- contract as a canonical decision-support queue. This closes the gap between
-- strategy discovery and the operator-facing Money Action layer.
--
-- IMPORTANT:
-- READY_SETUP means "all strategy/safety/geometry/5R gates passed for paper
-- decision support". It does NOT grant exchange/order authority.
--
-- Sources:
-- - RENDER_CRON: canonical Render production scanner
-- - RENDER: legacy canonical Render scanner during migration
-- - GITHUB_FAST_DISCOVERY: isolated 20-minute early-discovery scanner
-- - RENDER_WEB is intentionally excluded from the canonical ready queue
--
-- Staleness:
-- - only the latest run from each source
-- - source run must be <= 90 minutes old

create or replace view public.alpha_hunter_strategy_ready_setups_v01
with (security_invoker=true,security_barrier=true)
as
with source_latest as (
  select distinct on (
    p.payload->'validation_identity'->>'run_source'
  )
    p.run_id,
    p.collected_at_utc,
    p.payload->'validation_identity'->>'run_source' as run_source,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256
  from public.alpha_hunter_snapshots p
  where p.payload->'validation_identity'->>'run_source'
      in ('RENDER_CRON','RENDER','GITHUB_FAST_DISCOVERY')
    and p.collected_at_utc >= clock_timestamp()-interval '90 minutes'
  order by
    p.payload->'validation_identity'->>'run_source',
    p.collected_at_utc desc
),
eligible as (
  select
    l.run_source,
    l.run_id,
    l.collected_at_utc as scan_at_utc,
    l.git_commit,
    l.config_sha256,
    extract(
      epoch from (clock_timestamp()-l.collected_at_utc)
    ) as scan_age_seconds,

    o.observation_id,
    o.strategy_instance_id,
    o.symbol,
    o.strategy_id,
    o.strategy_name,
    o.direction,
    o.status as strategy_status,
    o.action as strategy_action,
    coalesce(
      o.strategy_payload->>'proposed_action',
      o.action
    ) as proposed_action,
    o.signal_score,
    o.score_is_calibrated,
    o.reference_price,
    o.entry_price,
    o.stop_price,
    o.target_price,
    o.reward_risk,
    o.distance_to_entry_pct,
    o.geometry_valid,
    o.persistence_state,
    o.consecutive_scans,
    o.first_seen_at_utc,
    o.observed_at_utc,
    o.checks,
    o.reasons,
    o.evidence,

    case
      when o.action='EXECUTE_NOW'
        then 'READY_SETUP_NOW'
      when o.action='PLACE_LIMIT'
        then 'READY_LIMIT_SETUP'
      else 'NOT_READY'
    end as ready_status,

    case
      when o.action='EXECUTE_NOW' then 2
      when o.action='PLACE_LIMIT' then 1
      else 0
    end as action_priority

  from source_latest l
  join public.alpha_hunter_strategy_observations_v01 o
    on o.run_id=l.run_id

  where o.status='SHADOW_CANDIDATE'
    and o.action in ('EXECUTE_NOW','PLACE_LIMIT')
    and o.direction in ('LONG','SHORT')
    and coalesce(o.geometry_valid,false)
    and o.reward_risk>=5.0
    and o.entry_price is not null
    and o.stop_price is not null
    and o.target_price is not null
    and coalesce(o.shadow_only,false)
    and coalesce(o.trade_permission,false)=false
    and coalesce(o.production_permission,false)=false

    and (
      (
        o.direction='LONG'
        and o.stop_price<o.entry_price
        and o.entry_price<o.target_price
      )
      or
      (
        o.direction='SHORT'
        and o.target_price<o.entry_price
        and o.entry_price<o.stop_price
      )
    )
),
ranked as (
  select
    e.*,
    row_number() over (
      partition by e.run_source
      order by
        e.action_priority desc,
        e.signal_score desc,
        e.reward_risk desc,
        coalesce(e.distance_to_entry_pct,0) asc,
        e.symbol,
        e.strategy_id
    ) as source_rank,
    row_number() over (
      partition by e.run_source,e.symbol
      order by
        e.action_priority desc,
        e.signal_score desc,
        e.reward_risk desc,
        coalesce(e.distance_to_entry_pct,0) asc,
        e.strategy_id
    ) as symbol_rank
  from eligible e
)
select
  r.run_source,
  r.run_id,
  r.scan_at_utc,
  r.scan_age_seconds,
  r.git_commit,
  r.config_sha256,
  r.source_rank,
  r.symbol_rank,

  r.symbol,
  r.strategy_id,
  r.strategy_name,
  r.direction,
  r.ready_status,
  r.strategy_action,
  r.signal_score,
  r.score_is_calibrated,

  r.reference_price,
  r.entry_price,
  r.stop_price,
  r.target_price,
  r.reward_risk,
  r.distance_to_entry_pct,

  r.persistence_state,
  r.consecutive_scans,
  r.first_seen_at_utc,
  r.observed_at_utc,

  r.checks,
  r.reasons,
  r.evidence,

  'S1_S10_SHADOW_CANDIDATE_5R'::text as readiness_contract,
  true as decision_support_only,
  true as shadow_only,
  false as live_money_claim_permitted,
  false as execution_authority,
  false as trade_permission,
  false as production_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from ranked r;

revoke all on public.alpha_hunter_strategy_ready_setups_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_strategy_ready_setups_v01
  to service_role;

