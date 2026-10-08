-- Alpha Hunter participation forward endpoint ledger v0.1
--
-- Problem:
--   public.alpha_hunter_participation_forward_* joins to the legacy
--   alpha_hunter_signal_outcomes stream. That evaluator processes the oldest
--   500 pending signals per horizon, leaving ~50k pending rows and starving
--   current participation diagnostics.
--
-- Scientific repair:
--   * forward-only preregistration boundary;
--   * candidate captured from participation diagnostics after registration;
--   * explicit source-signal direction conflicts excluded;
--   * endpoint price = first canonical alpha_hunter_symbol_snapshots row at or
--     after the exact due horizon, within a bounded 30-minute lag;
--   * evaluate 1H/4H/12H/24H direction-adjusted endpoint return;
--   * no stop/target path claim;
--   * no participation threshold derivation or production promotion.
--
-- No historical backfill.

create table if not exists private.alpha_hunter_participation_endpoint_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  endpoint_max_lag_minutes integer not null check(endpoint_max_lag_minutes between 1 and 60),
  horizons_hours integer[] not null,
  status text not null check(status in ('COLLECTING','PAUSED','COMPLETE')),
  scientific_role text not null,
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into private.alpha_hunter_participation_endpoint_specs_v01(
  spec_id,registered_at_utc,endpoint_max_lag_minutes,horizons_hours,status,
  scientific_role,confirmatory_claim_permitted,threshold_derivation_permitted,
  production_promotion_permitted,shadow_only,trade_permission,order_path
) values (
  'PARTICIPATION-ENDPOINT-FORWARD-V01',
  clock_timestamp(),
  30,
  array[1,4,12,24],
  'COLLECTING',
  'FORWARD_PARTICIPATION_ENDPOINT_MEASUREMENT',
  false,false,false,true,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_participation_endpoint_candidates_v01 (
  candidate_id text primary key,
  spec_id text not null references private.alpha_hunter_participation_endpoint_specs_v01(spec_id),
  diagnostic_id text not null unique,
  source_signal_id text not null,
  run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  candidate_direction text not null check(candidate_direction in ('LONG','SHORT')),
  source_signal_direction text,
  reference_price double precision not null check(reference_price>0),
  classification text not null,
  scanner_participation_confirmed boolean,
  scanner_participation_emerging boolean,
  volume_state_15m text,
  volume_ratio_15m double precision,
  volume_state_1h text,
  volume_ratio_1h double precision,
  volume_state_4h text,
  volume_ratio_4h double precision,
  behaviour_volume_ratio double precision,
  market_phase text,
  opportunity_timing text,
  liquidity_pass boolean,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_PARTICIPATION_ENDPOINT_CANDIDATE',
  confirmatory_claim_permitted boolean not null default false
    check(confirmatory_claim_permitted=false),
  threshold_derivation_permitted boolean not null default false
    check(threshold_derivation_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_part_endpoint_candidate_time_v01
  on private.alpha_hunter_participation_endpoint_candidates_v01(
    spec_id,captured_at_utc
  );

create index if not exists idx_ah_part_endpoint_candidate_symbol_v01
  on private.alpha_hunter_participation_endpoint_candidates_v01(
    symbol,captured_at_utc
  );

create table if not exists private.alpha_hunter_participation_endpoint_outcomes_v01 (
  outcome_id text primary key,
  candidate_id text not null
    references private.alpha_hunter_participation_endpoint_candidates_v01(candidate_id),
  spec_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  due_at_utc timestamptz not null,
  endpoint_run_id text not null,
  endpoint_collected_at_utc timestamptz not null,
  endpoint_lag_seconds double precision not null check(endpoint_lag_seconds>=0),
  endpoint_price double precision not null check(endpoint_price>0),
  raw_return_pct double precision not null,
  direction_adjusted_return_pct double precision not null,
  positive_directional_return boolean not null,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_PARTICIPATION_ENDPOINT_OUTCOME',
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

create index if not exists idx_ah_part_endpoint_outcome_horizon_v01
  on private.alpha_hunter_participation_endpoint_outcomes_v01(
    spec_id,horizon_hours,endpoint_collected_at_utc
  );

create table if not exists private.alpha_hunter_participation_endpoint_runs_v01 (
  run_id text primary key,
  spec_id text not null,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  outcomes_inserted integer not null,
  candidate_rows_total integer not null,
  outcome_rows_total integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_participation_endpoint_forward_v01()
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
  v_candidate_total integer:=0;
  v_outcome_total integer:=0;
  v_run_id text;
begin
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
        'direction_contract','CANDIDATE_DIRECTION_USED_EXCEPT_EXPLICIT_SIGNAL_CONFLICT_EXCLUDED',
        'legacy_signal_outcome_dependency',false,
        'historical_backfill_permitted',false
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
    order by due_at_utc,c.candidate_id,h.horizon_hours
    limit 2000
  ), resolved as (
    select
      d.*,
      s.run_id as endpoint_run_id,
      s.collected_at_utc as endpoint_collected_at_utc,
      s.last_price as endpoint_price
    from due d
    join lateral (
      select ss.run_id,ss.collected_at_utc,ss.last_price
      from public.alpha_hunter_symbol_snapshots ss
      where ss.symbol=d.symbol
        and ss.collected_at_utc>=d.due_at_utc
        and ss.collected_at_utc<=d.due_at_utc
          + make_interval(mins=>v_spec.endpoint_max_lag_minutes)
        and ss.last_price is not null
        and ss.last_price>0
      order by ss.collected_at_utc
      limit 1
    ) s on true
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
        'stop_target_path_claim_permitted',false,
        'legacy_signal_outcome_dependency',false
      ),
      false,false,false,true,false,'NONE'
    from resolved r
    on conflict(candidate_id,horizon_hours) do nothing
    returning 1
  )
  select count(*) into v_outcomes_inserted from inserted;

  select count(*) into v_candidate_total
  from private.alpha_hunter_participation_endpoint_candidates_v01
  where spec_id=v_spec.spec_id;

  select count(*) into v_outcome_total
  from private.alpha_hunter_participation_endpoint_outcomes_v01
  where spec_id=v_spec.spec_id;

  v_run_id:='part-endpoint-run-'||md5(v_now::text);

  insert into private.alpha_hunter_participation_endpoint_runs_v01(
    run_id,spec_id,checked_at_utc,candidates_inserted,outcomes_inserted,
    candidate_rows_total,outcome_rows_total,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_candidates_inserted,v_outcomes_inserted,
    v_candidate_total,v_outcome_total,
    jsonb_build_object(
      'model_version','participation-endpoint-forward-v0.1',
      'endpoint_contract','FIRST_CANONICAL_SYMBOL_SNAPSHOT_AT_OR_AFTER_DUE',
      'historical_backfill_permitted',false,
      'threshold_derivation_permitted',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'run_id',v_run_id,
    'candidates_inserted',v_candidates_inserted,
    'outcomes_inserted',v_outcomes_inserted,
    'candidate_rows_total',v_candidate_total,
    'outcome_rows_total',v_outcome_total,
    'shadow_only',true,
    'trade_permission',false,
    'threshold_derivation_permitted',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_participation_endpoint_forward_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_participation_endpoint_forward_v01()
to postgres;

create or replace view private.alpha_hunter_participation_endpoint_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  c.classification,
  o.horizon_hours,
  count(*) as evaluated_rows,
  count(distinct c.symbol) as symbols,
  avg(o.direction_adjusted_return_pct) as avg_direction_adjusted_return_pct,
  percentile_cont(0.5) within group(order by o.direction_adjusted_return_pct)
    as median_direction_adjusted_return_pct,
  100.0*count(*) filter(where o.positive_directional_return)
    /nullif(count(*),0) as positive_directional_pct,
  avg(o.endpoint_lag_seconds) as avg_endpoint_lag_seconds,
  max(o.endpoint_lag_seconds) as max_endpoint_lag_seconds,
  min(c.captured_at_utc) as first_candidate_at_utc,
  max(c.captured_at_utc) as latest_candidate_at_utc,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'FORWARD_ENDPOINT_MEASUREMENT_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from private.alpha_hunter_participation_endpoint_candidates_v01 c
join private.alpha_hunter_participation_endpoint_outcomes_v01 o
  on o.candidate_id=c.candidate_id
group by c.classification,o.horizon_hours;

revoke all on private.alpha_hunter_participation_endpoint_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_endpoint_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_endpoint_outcomes_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_endpoint_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_participation_endpoint_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_participation_endpoint_specs_v01
to service_role;
grant select on private.alpha_hunter_participation_endpoint_candidates_v01
to service_role;
grant select on private.alpha_hunter_participation_endpoint_outcomes_v01
to service_role;
grant select on private.alpha_hunter_participation_endpoint_runs_v01
to service_role;
grant select on private.alpha_hunter_participation_endpoint_scorecard_v01
to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-participation-endpoint-forward-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-participation-endpoint-forward-v01',
  '14 * * * *',
  $cmd$
    select private.alpha_hunter_run_participation_endpoint_forward_v01();
  $cmd$
);

-- No participation diagnostic observed before registered_at_utc is admitted.
