-- Alpha Hunter automatic prospective decision freeze v0.2
--
-- Purpose:
--   Persist Alpha Hunter's own execution decision immediately when a complete
--   prospective decision quote is captured, so later exact Bitget fills can be
--   scientifically attributed without relying on a heavyweight profitability
--   monitor view.
--
-- Critical boundary:
--   This freezes decision evidence only. It never binds a fill, never infers
--   attribution from symbol/time proximity, never submits an exchange order,
--   and never grants trade or production permission.

create or replace function private.alpha_hunter_auto_freeze_execution_decision_v02()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  s public.alpha_hunter_strategy_observations_v01%rowtype;
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  a public.alpha_hunter_profitability_test_activations_v01%rowtype;
  p public.alpha_hunter_snapshots%rowtype;
  v_execution_event_id text;
begin
  if new.quote_complete is not true
     or new.prospective_capture is not true
     or new.action not in ('EXECUTE_NOW','PLACE_LIMIT')
     or coalesce(new.run_source,'')<>'RENDER_CRON'
  then
    return new;
  end if;

  select x.* into s
  from public.alpha_hunter_strategy_observations_v01 x
  where x.observation_id=new.observation_id
  limit 1;

  if s.observation_id is null
     or s.geometry_valid is not true
     or s.direction<>new.direction
     or s.action<>new.action
  then
    return new;
  end if;

  select x.* into p
  from public.alpha_hunter_snapshots x
  where x.run_id=new.run_id
  limit 1;

  if p.run_id is null then
    return new;
  end if;

  select spec.*,act.* into sp,a
  from public.alpha_hunter_profitability_test_specs_v01 spec
  join public.alpha_hunter_profitability_test_activations_v01 act
    on act.spec_id=spec.spec_id
  where spec.required_run_source=new.run_source
    and act.started_at_utc<=new.observed_at_utc
    and (
      (
        spec.frozen_scientific_fingerprint_sha256 is not null
        and coalesce(
          p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
          ''
        )=spec.frozen_scientific_fingerprint_sha256
      )
      or
      (
        spec.frozen_scientific_fingerprint_sha256 is null
        and coalesce(p.payload->'validation_identity'->>'git_commit','')
            =act.baseline_git_commit
        and coalesce(p.payload->'validation_identity'->>'config_sha256','')
            =act.baseline_config_sha256
      )
    )
  order by act.activated_at_utc desc
  limit 1;

  if sp.spec_id is null then
    return new;
  end if;

  v_execution_event_id:='exec-auto-'||md5(new.observation_id);

  insert into public.alpha_hunter_execution_decision_freezes_v01(
    execution_event_id,
    spec_id,
    decision_observation_id,
    strategy_instance_id,
    decision_run_id,
    symbol,
    strategy_id,
    direction,
    action,
    decision_observed_at_utc,
    decision_captured_at_utc,
    frozen_at_utc,
    reference_price,
    planned_entry_price,
    stop_price,
    target_price,
    reward_risk,
    best_bid,
    best_ask,
    midpoint,
    entry_cross_price,
    entry_cross_half_spread_bps,
    quote_complete,
    prospective_capture,
    evidence,
    scientific_role,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_execution_event_id,
    sp.spec_id,
    new.observation_id,
    new.strategy_instance_id,
    new.run_id,
    new.symbol,
    new.strategy_id,
    new.direction,
    new.action,
    new.observed_at_utc,
    new.captured_at_utc,
    greatest(clock_timestamp(),new.captured_at_utc),
    new.reference_price,
    new.planned_entry_price,
    s.stop_price,
    s.target_price,
    s.reward_risk,
    new.best_bid,
    new.best_ask,
    new.midpoint,
    new.entry_cross_price,
    new.entry_cross_half_spread_bps,
    true,
    true,
    jsonb_build_object(
      'source','SEALED_PROSPECTIVE_DECISION_QUOTE',
      'capture_mode','AUTO_FREEZE_AT_DECISION_QUOTE_INSERT',
      'run_source',new.run_source,
      'git_commit',new.git_commit,
      'config_sha256',new.config_sha256,
      'scientific_fingerprint_sha256',
        p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
      'automatic_decision_freeze',true,
      'automatic_fill_binding_permitted',false,
      'symbol_time_proximity_attribution_permitted',false,
      'explicit_exact_fill_binding_required',true
    ),
    'PROSPECTIVE_EXECUTION_ATTRIBUTION_AUTO_FREEZE',
    true,
    false,
    false,
    'NONE'
  )
  on conflict(decision_observation_id) do nothing;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_auto_freeze_execution_decision_v02()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_auto_freeze_execution_decision_v02
on public.alpha_hunter_shadow_decision_quotes_v01;

create trigger trg_ah_auto_freeze_execution_decision_v02
after insert on public.alpha_hunter_shadow_decision_quotes_v01
for each row execute function private.alpha_hunter_auto_freeze_execution_decision_v02();

-- Seed only the latest currently-live canonical run. These rows become
-- prospective from seed time forward. No historical backfill is performed and
-- any fill/order predating frozen_at_utc remains ineligible for binding.
do $seed$
declare
  q public.alpha_hunter_shadow_decision_quotes_v01%rowtype;
  s public.alpha_hunter_strategy_observations_v01%rowtype;
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  a public.alpha_hunter_profitability_test_activations_v01%rowtype;
  p public.alpha_hunter_snapshots%rowtype;
  v_latest_run_id text;
  v_seed_at timestamptz:=clock_timestamp();
begin
  select x.run_id into v_latest_run_id
  from public.alpha_hunter_snapshots x
  where x.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  order by x.collected_at_utc desc
  limit 1;

  if v_latest_run_id is null then
    return;
  end if;

  select x.* into p
  from public.alpha_hunter_snapshots x
  where x.run_id=v_latest_run_id
  limit 1;

  for q in
    select x.*
    from public.alpha_hunter_shadow_decision_quotes_v01 x
    where x.run_id=v_latest_run_id
      and x.run_source='RENDER_CRON'
      and x.quote_complete=true
      and x.prospective_capture=true
      and x.action in ('EXECUTE_NOW','PLACE_LIMIT')
  loop
    select x.* into s
    from public.alpha_hunter_strategy_observations_v01 x
    where x.observation_id=q.observation_id
    limit 1;

    if s.observation_id is null
       or s.geometry_valid is not true
       or s.direction<>q.direction
       or s.action<>q.action
    then
      continue;
    end if;

    select spec.*,act.* into sp,a
    from public.alpha_hunter_profitability_test_specs_v01 spec
    join public.alpha_hunter_profitability_test_activations_v01 act
      on act.spec_id=spec.spec_id
    where spec.required_run_source=q.run_source
      and act.started_at_utc<=q.observed_at_utc
      and (
        (
          spec.frozen_scientific_fingerprint_sha256 is not null
          and coalesce(
            p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
            ''
          )=spec.frozen_scientific_fingerprint_sha256
        )
        or
        (
          spec.frozen_scientific_fingerprint_sha256 is null
          and coalesce(p.payload->'validation_identity'->>'git_commit','')
              =act.baseline_git_commit
          and coalesce(p.payload->'validation_identity'->>'config_sha256','')
              =act.baseline_config_sha256
        )
      )
    order by act.activated_at_utc desc
    limit 1;

    if sp.spec_id is null then
      continue;
    end if;

    insert into public.alpha_hunter_execution_decision_freezes_v01(
      execution_event_id,spec_id,decision_observation_id,strategy_instance_id,
      decision_run_id,symbol,strategy_id,direction,action,
      decision_observed_at_utc,decision_captured_at_utc,frozen_at_utc,
      reference_price,planned_entry_price,stop_price,target_price,reward_risk,
      best_bid,best_ask,midpoint,entry_cross_price,entry_cross_half_spread_bps,
      quote_complete,prospective_capture,evidence,scientific_role,
      shadow_only,trade_permission,production_promotion_permitted,order_path
    ) values (
      'exec-seed-'||md5(q.observation_id),
      sp.spec_id,q.observation_id,q.strategy_instance_id,q.run_id,q.symbol,
      q.strategy_id,q.direction,q.action,q.observed_at_utc,q.captured_at_utc,
      greatest(v_seed_at,q.captured_at_utc),
      q.reference_price,q.planned_entry_price,s.stop_price,s.target_price,
      s.reward_risk,q.best_bid,q.best_ask,q.midpoint,q.entry_cross_price,
      q.entry_cross_half_spread_bps,true,true,
      jsonb_build_object(
        'source','SEALED_PROSPECTIVE_DECISION_QUOTE',
        'capture_mode','CURRENT_RUN_ACTIVATION_SEED',
        'run_source',q.run_source,
        'git_commit',q.git_commit,
        'config_sha256',q.config_sha256,
        'scientific_fingerprint_sha256',
          p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
        'prospective_from_frozen_at_utc',true,
        'historical_backfill',false,
        'automatic_fill_binding_permitted',false,
        'symbol_time_proximity_attribution_permitted',false,
        'explicit_exact_fill_binding_required',true
      ),
      'PROSPECTIVE_EXECUTION_ATTRIBUTION_AUTO_FREEZE',
      true,false,false,'NONE'
    )
    on conflict(decision_observation_id) do nothing;
  end loop;
end;
$seed$;
