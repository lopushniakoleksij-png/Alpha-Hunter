-- Alpha Hunter participation forward endpoint collector v0.2
--
-- Purpose:
--   Repair queue starvation in v0.1 without changing the preregistered
--   scientific endpoint contract, R3, thresholds, trade permissions, or orders.
--
-- Confirmed v0.1 defect:
--   v0.1 applies LIMIT 2000 before canonical endpoint resolution. Once the
--   oldest unresolved rows have no snapshot inside the <=30 minute window,
--   they permanently occupy the queue and block later resolvable rows.
--
-- v0.2 repair:
--   1. preserve the original forward registration boundary;
--   2. preserve endpoint_max_lag_minutes = 30;
--   3. resolve only rows that already have a canonical snapshot in-window,
--      then apply the 2000-row processing limit;
--   4. explicitly censor matured rows that have no canonical snapshot inside
--      the frozen endpoint window;
--   5. never mutate/delete legacy or existing forward outcome rows;
--   6. remain shadow-only with no production or trade authority.
--
-- This is forward-cohort recovery, not historical pre-registration backfill.

create table if not exists private.alpha_hunter_participation_endpoint_failures_v02 (
  failure_id text primary key,
  candidate_id text not null
    references private.alpha_hunter_participation_endpoint_candidates_v01(candidate_id),
  spec_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  due_at_utc timestamptz not null,
  window_closed_at_utc timestamptz not null,
  failure_reason text not null
    check(failure_reason='NO_CANONICAL_SNAPSHOT_WITHIN_30M'),
  first_later_snapshot_at_utc timestamptz,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_ENDPOINT_CENSOR_RECORD',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique(candidate_id,horizon_hours)
);

create index if not exists idx_ah_part_endpoint_failure_horizon_v02
  on private.alpha_hunter_participation_endpoint_failures_v02(
    spec_id,horizon_hours,due_at_utc
  );

create table if not exists private.alpha_hunter_participation_endpoint_runs_v02 (
  run_id text primary key,
  spec_id text not null,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  outcomes_inserted integer not null,
  failures_inserted integer not null,
  candidate_rows_total integer not null,
  outcome_rows_total integer not null,
  failure_rows_total integer not null,
  resolvable_backlog_rows integer not null,
  expired_uncensored_backlog_rows integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_participation_endpoint_forward_v02()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_participation_endpoint_specs_v01%rowtype;
  v_now timestamptz:=clock_timestamp();
  v_candidates_inserted integer:=0;
  v_outcomes_inserted integer:=0;
  v_failures_inserted integer:=0;
  v_candidate_total integer:=0;
  v_outcome_total integer:=0;
  v_failure_total integer:=0;
  v_resolvable_backlog integer:=0;
  v_expired_uncensored_backlog integer:=0;
  v_run_id text;
begin
  -- Prevent overlapping v0.2 runs from producing cross-table outcome/censor races.
  if not pg_try_advisory_xact_lock(
    hashtextextended('alpha-hunter-participation-endpoint-forward-v02',0)
  ) then
    return jsonb_build_object(
      'status','RUN_ALREADY_ACTIVE',
      'shadow_only',true,
      'trade_permission',false,
      'production_promotion_permitted',false
    );
  end if;

  select * into v_spec
  from private.alpha_hunter_participation_endpoint_specs_v01
  where spec_id='PARTICIPATION-ENDPOINT-FORWARD-V01'
    and status='COLLECTING';

  if v_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false
    );
  end if;

  -- Fail closed if the preregistered endpoint contract has drifted.
  if v_spec.endpoint_max_lag_minutes<>30
     or v_spec.horizons_hours<>array[1,4,12,24] then
    return jsonb_build_object(
      'status','FROZEN_CONTRACT_MISMATCH',
      'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
      'horizons_hours',v_spec.horizons_hours,
      'shadow_only',true,
      'trade_permission',false,
      'production_promotion_permitted',false
    );
  end if;

  -- Preserve the original forward-only candidate admission boundary.
  with inserted as (
    insert into private.alpha_hunter_participation_endpoint_candidates_v01(
      candidate_id,spec_id,diagnostic_id,source_signal_id,run_id,captured_at_utc,
      symbol,candidate_direction,source_signal_direction,reference_price,
      classification,scanner_participation_confirmed,scanner_participation_emerging,
      volume_state_15m,volume_ratio_15m,volume_state_1h,volume_ratio_1h,
      volume_state_4h,volume_ratio_4h,behaviour_volume_ratio,market_phase,
      opportunity_timing,liquidity_pass,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-endpoint-'||md5(v_spec.spec_id||'|'||d.diagnostic_id),
      v_spec.spec_id,
      d.diagnostic_id,
      d.source_signal_id,
      d.run_id,
      d.captured_at_utc,
      d.symbol,
      d.candidate_direction,
      s.direction,
      s.reference_price,
      d.classification,
      d.scanner_participation_confirmed,
      d.scanner_participation_emerging,
      d.volume_state_15m,
      d.volume_ratio_15m,
      d.volume_state_1h,
      d.volume_ratio_1h,
      d.volume_state_4h,
      d.volume_ratio_4h,
      d.behaviour_volume_ratio,
      d.market_phase,
      d.opportunity_timing,
      d.liquidity_pass,
      jsonb_build_object(
        'source_model_version',d.model_version,
        'source_signal_detected_at_utc',s.detected_at_utc,
        'direction_contract',
          'CANDIDATE_DIRECTION_USED_EXCEPT_EXPLICIT_SIGNAL_CONFLICT_EXCLUDED',
        'legacy_signal_outcome_dependency',false,
        'historical_pre_registration_backfill_permitted',false,
        'collector_version','participation-endpoint-forward-v0.2'
      ),
      false,false,false,true,false,'NONE'
    from public.alpha_hunter_participation_diagnostics d
    join public.alpha_hunter_signals s
      on s.signal_id=d.source_signal_id
    where d.captured_at_utc>=v_spec.registered_at_utc
      and d.candidate_direction in ('LONG','SHORT')
      and s.reference_price is not null
      and s.reference_price>0
      and (s.direction is null or s.direction=d.candidate_direction)
      and d.shadow_only=true
      and d.trade_permission=false
    on conflict(diagnostic_id) do nothing
    returning 1
  )
  select count(*) into v_candidates_inserted from inserted;

  -- Critical v0.2 change:
  -- resolve the canonical snapshot first; LIMIT applies only to resolvable rows.
  with due as (
    select
      c.candidate_id,
      c.spec_id,
      c.symbol,
      c.candidate_direction,
      c.reference_price,
      h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_endpoint_candidates_v01 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)<=v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_outcomes_v01 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  ), resolved as (
    select
      d.*,
      ss.run_id as endpoint_run_id,
      ss.collected_at_utc as endpoint_collected_at_utc,
      ss.last_price as endpoint_price
    from due d
    join lateral (
      select s.run_id,s.collected_at_utc,s.last_price
      from public.alpha_hunter_symbol_snapshots s
      where s.symbol=d.symbol
        and s.collected_at_utc>=d.due_at_utc
        and s.collected_at_utc<=d.due_at_utc
          +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
        and s.last_price is not null
        and s.last_price>0
      order by s.collected_at_utc
      limit 1
    ) ss on true
    order by d.due_at_utc,d.candidate_id,d.horizon_hours
    limit 2000
  ), inserted as (
    insert into private.alpha_hunter_participation_endpoint_outcomes_v01(
      outcome_id,candidate_id,spec_id,horizon_hours,due_at_utc,
      endpoint_run_id,endpoint_collected_at_utc,endpoint_lag_seconds,
      endpoint_price,raw_return_pct,direction_adjusted_return_pct,
      positive_directional_return,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-endpoint-outcome-'||md5(
        r.candidate_id||'|'||r.horizon_hours::text
      ),
      r.candidate_id,
      r.spec_id,
      r.horizon_hours,
      r.due_at_utc,
      r.endpoint_run_id,
      r.endpoint_collected_at_utc,
      extract(epoch from(r.endpoint_collected_at_utc-r.due_at_utc)),
      r.endpoint_price,
      100.0*(r.endpoint_price/r.reference_price-1.0),
      case
        when r.candidate_direction='SHORT'
          then -100.0*(r.endpoint_price/r.reference_price-1.0)
        else 100.0*(r.endpoint_price/r.reference_price-1.0)
      end,
      case
        when r.candidate_direction='SHORT'
          then -100.0*(r.endpoint_price/r.reference_price-1.0)>0
        else 100.0*(r.endpoint_price/r.reference_price-1.0)>0
      end,
      jsonb_build_object(
        'endpoint_contract','FIRST_CANONICAL_SYMBOL_SNAPSHOT_AT_OR_AFTER_DUE',
        'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
        'collector_version','participation-endpoint-forward-v0.2',
        'stop_target_path_claim_permitted',false,
        'legacy_signal_outcome_dependency',false
      ),
      false,false,false,true,false,'NONE'
    from resolved r
    on conflict(candidate_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_outcomes_inserted from inserted;

  -- Explicitly censor matured endpoint windows that never received an
  -- admissible canonical snapshot. Later snapshots do not change the outcome:
  -- the scientific endpoint window remains frozen at <=30 minutes.
  with due_expired as (
    select
      c.candidate_id,
      c.spec_id,
      c.symbol,
      h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
          as window_closed_at_utc
    from private.alpha_hunter_participation_endpoint_candidates_v01 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)<v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_outcomes_v01 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from public.alpha_hunter_symbol_snapshots s
        where s.symbol=c.symbol
          and s.collected_at_utc>=
            c.captured_at_utc+make_interval(hours=>h.horizon_hours)
          and s.collected_at_utc<=
            c.captured_at_utc+make_interval(hours=>h.horizon_hours)
              +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
          and s.last_price is not null
          and s.last_price>0
      )
    order by due_at_utc,c.candidate_id,h.horizon_hours
    limit 2000
  ), censored as (
    select
      d.*,
      (
        select min(s.collected_at_utc)
        from public.alpha_hunter_symbol_snapshots s
        where s.symbol=d.symbol
          and s.collected_at_utc>d.window_closed_at_utc
          and s.last_price is not null
          and s.last_price>0
      ) as first_later_snapshot_at_utc
    from due_expired d
  ), inserted as (
    insert into private.alpha_hunter_participation_endpoint_failures_v02(
      failure_id,candidate_id,spec_id,horizon_hours,due_at_utc,
      window_closed_at_utc,failure_reason,first_later_snapshot_at_utc,evidence,
      confirmatory_claim_permitted,threshold_derivation_permitted,
      production_promotion_permitted,shadow_only,trade_permission,order_path
    )
    select
      'part-endpoint-failure-'||md5(
        x.candidate_id||'|'||x.horizon_hours::text
      ),
      x.candidate_id,
      x.spec_id,
      x.horizon_hours,
      x.due_at_utc,
      x.window_closed_at_utc,
      'NO_CANONICAL_SNAPSHOT_WITHIN_30M',
      x.first_later_snapshot_at_utc,
      jsonb_build_object(
        'endpoint_contract','FIRST_CANONICAL_SYMBOL_SNAPSHOT_AT_OR_AFTER_DUE',
        'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
        'collector_version','participation-endpoint-forward-v0.2',
        'censored',true,
        'endpoint_return_claim_permitted',false,
        'stop_target_path_claim_permitted',false,
        'threshold_derivation_permitted',false
      ),
      false,false,false,true,false,'NONE'
    from censored x
    on conflict(candidate_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_failures_inserted from inserted;

  select count(*) into v_candidate_total
  from private.alpha_hunter_participation_endpoint_candidates_v01
  where spec_id=v_spec.spec_id;

  select count(*) into v_outcome_total
  from private.alpha_hunter_participation_endpoint_outcomes_v01
  where spec_id=v_spec.spec_id;

  select count(*) into v_failure_total
  from private.alpha_hunter_participation_endpoint_failures_v02
  where spec_id=v_spec.spec_id;

  -- Remaining valid evidence that is ready but not yet materialized.
  with due as (
    select
      c.candidate_id,c.symbol,h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_endpoint_candidates_v01 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)<=v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_outcomes_v01 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  )
  select count(*) into v_resolvable_backlog
  from due d
  where exists (
    select 1
    from public.alpha_hunter_symbol_snapshots s
    where s.symbol=d.symbol
      and s.collected_at_utc>=d.due_at_utc
      and s.collected_at_utc<=d.due_at_utc
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
      and s.last_price is not null
      and s.last_price>0
  );

  -- Matured missing-window rows still awaiting explicit censor materialization.
  with due as (
    select
      c.candidate_id,c.symbol,h.horizon_hours,
      c.captured_at_utc+make_interval(hours=>h.horizon_hours) as due_at_utc
    from private.alpha_hunter_participation_endpoint_candidates_v01 c
    cross join lateral unnest(v_spec.horizons_hours) as h(horizon_hours)
    where c.spec_id=v_spec.spec_id
      and c.captured_at_utc+make_interval(hours=>h.horizon_hours)
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)<v_now
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_outcomes_v01 o
        where o.candidate_id=c.candidate_id
          and o.horizon_hours=h.horizon_hours
      )
      and not exists (
        select 1
        from private.alpha_hunter_participation_endpoint_failures_v02 f
        where f.candidate_id=c.candidate_id
          and f.horizon_hours=h.horizon_hours
      )
  )
  select count(*) into v_expired_uncensored_backlog
  from due d
  where not exists (
    select 1
    from public.alpha_hunter_symbol_snapshots s
    where s.symbol=d.symbol
      and s.collected_at_utc>=d.due_at_utc
      and s.collected_at_utc<=d.due_at_utc
        +make_interval(mins=>v_spec.endpoint_max_lag_minutes)
      and s.last_price is not null
      and s.last_price>0
  );

  v_run_id:='part-endpoint-v02-run-'||md5(v_now::text);

  insert into private.alpha_hunter_participation_endpoint_runs_v02(
    run_id,spec_id,checked_at_utc,candidates_inserted,outcomes_inserted,
    failures_inserted,candidate_rows_total,outcome_rows_total,failure_rows_total,
    resolvable_backlog_rows,expired_uncensored_backlog_rows,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_candidates_inserted,v_outcomes_inserted,
    v_failures_inserted,v_candidate_total,v_outcome_total,v_failure_total,
    v_resolvable_backlog,v_expired_uncensored_backlog,
    jsonb_build_object(
      'model_version','participation-endpoint-forward-v0.2',
      'endpoint_contract','FIRST_CANONICAL_SYMBOL_SNAPSHOT_AT_OR_AFTER_DUE',
      'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
      'queue_limit_applied_after_resolution',true,
      'explicit_endpoint_censoring',true,
      'historical_pre_registration_backfill_permitted',false,
      'threshold_derivation_permitted',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','OK',
    'run_id',v_run_id,
    'candidates_inserted',v_candidates_inserted,
    'outcomes_inserted',v_outcomes_inserted,
    'failures_inserted',v_failures_inserted,
    'candidate_rows_total',v_candidate_total,
    'outcome_rows_total',v_outcome_total,
    'failure_rows_total',v_failure_total,
    'resolvable_backlog_rows',v_resolvable_backlog,
    'expired_uncensored_backlog_rows',v_expired_uncensored_backlog,
    'endpoint_max_lag_minutes',v_spec.endpoint_max_lag_minutes,
    'shadow_only',true,
    'trade_permission',false,
    'threshold_derivation_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on private.alpha_hunter_participation_endpoint_failures_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_endpoint_runs_v02
from public,anon,authenticated,service_role;
revoke all on function private.alpha_hunter_run_participation_endpoint_forward_v02()
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_participation_endpoint_failures_v02
to service_role;
grant select on private.alpha_hunter_participation_endpoint_runs_v02
to service_role;
grant execute on function private.alpha_hunter_run_participation_endpoint_forward_v02()
to postgres;

-- Deployment intent: replace the starved v0.1 cron, never run both collectors.
do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname in (
      'alpha-hunter-participation-endpoint-forward-v01',
      'alpha-hunter-participation-endpoint-forward-v02'
    )
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-participation-endpoint-forward-v02',
  '14 * * * *',
  $cmd$
    select private.alpha_hunter_run_participation_endpoint_forward_v02();
  $cmd$
);

-- No legacy outcome row is updated/deleted.
-- No existing forward outcome row is updated/deleted.
-- No diagnostic captured before the original registered_at_utc is admitted.
