-- Alpha Hunter volume-growth forward ranking scorecard v0.1
--
-- Purpose:
--   Evaluate the V15 volume-growth top-30 ranking challenger prospectively.
--
-- Experimental law:
--   * capture only candidates observed AFTER deployment;
--   * candidate must still be below the +/-5% mover threshold at capture;
--   * selection uses only contemporaneous universe evidence;
--   * wait 24H before labeling whether a new +5% mover event occurred;
--   * compare shadow top-30 against production deep-scan selection;
--   * no trading, threshold, selector, or production mutation is permitted.

create table if not exists private.alpha_hunter_volume_growth_forward_candidates_v01 (
  candidate_id text primary key,
  observation_id text not null unique,
  captured_at_utc timestamptz not null default clock_timestamp(),
  observed_at_utc timestamptz not null,
  maturity_at_utc timestamptz not null,
  selection_run_id text not null,
  symbol text not null,
  start_change_24h_pct double precision not null,
  quote_volume_24h double precision,
  previous_observed_at_utc timestamptz,
  previous_quote_volume_24h double precision,
  previous_gap_seconds double precision,
  volume_log_growth double precision,
  volume_growth_rank bigint,
  shadow_top30_selected boolean not null,
  production_deep_scan_selected boolean not null,
  evaluation_status text not null default 'PENDING'
    check(evaluation_status in ('PENDING','EVALUATED')),
  mover_within_24h boolean,
  mover_event_id text,
  mover_observed_at_utc timestamptz,
  mover_direction text,
  mover_threshold_pct double precision,
  mover_move_pct double precision,
  minutes_to_mover double precision,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_RANKING_CHALLENGER_SCORECARD',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(abs(start_change_24h_pct)<5.0),
  check(shadow_top30_selected or production_deep_scan_selected)
);

create index if not exists idx_ah_vg_forward_pending_v01
  on private.alpha_hunter_volume_growth_forward_candidates_v01(
    evaluation_status,maturity_at_utc
  );

create index if not exists idx_ah_vg_forward_symbol_time_v01
  on private.alpha_hunter_volume_growth_forward_candidates_v01(
    symbol,observed_at_utc
  );

create table if not exists private.alpha_hunter_volume_growth_forward_runs_v01 (
  scorecard_run_id text primary key,
  checked_at_utc timestamptz not null,
  selection_run_id text,
  candidates_inserted integer not null,
  candidates_evaluated integer not null,
  pending_after_run integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_volume_growth_forward_scorecard_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_now timestamptz:=clock_timestamp();
  v_selection_run_id text;
  v_inserted integer:=0;
  v_evaluated integer:=0;
  v_pending integer:=0;
  v_scorecard_run_id text;
  r private.alpha_hunter_volume_growth_forward_candidates_v01%rowtype;
  m public.alpha_hunter_big_mover_answer_key%rowtype;
begin
  select s.selection_run_id
    into v_selection_run_id
  from public.alpha_hunter_volume_growth_ranking_shadow_v01 s
  where s.selection_run_id is not null
  order by s.observed_at_utc desc
  limit 1;

  if v_selection_run_id is not null then
    with inserted as (
      insert into private.alpha_hunter_volume_growth_forward_candidates_v01(
        candidate_id,observation_id,captured_at_utc,observed_at_utc,maturity_at_utc,
        selection_run_id,symbol,start_change_24h_pct,quote_volume_24h,
        previous_observed_at_utc,previous_quote_volume_24h,previous_gap_seconds,
        volume_log_growth,volume_growth_rank,shadow_top30_selected,
        production_deep_scan_selected,evidence,
        scientific_role,shadow_only,trade_permission,
        threshold_change_permitted,production_promotion_permitted,order_path
      )
      select
        'vg-forward-'||md5(s.observation_id),
        s.observation_id,
        v_now,
        s.observed_at_utc,
        s.observed_at_utc+interval '24 hours',
        s.selection_run_id,
        s.symbol,
        s.change_24h_pct,
        s.quote_volume_24h,
        s.previous_observed_at_utc,
        s.previous_quote_volume_24h,
        s.previous_gap_seconds::double precision,
        s.volume_log_growth,
        s.volume_growth_rank,
        s.shadow_top30_selected,
        s.production_deep_scan_selected,
        jsonb_build_object(
          'challenger_rule',s.challenger_rule,
          'measurement_quality',s.measurement_quality,
          'ranking_eligible',s.ranking_eligible,
          'capture_rule','LATEST_SELECTION_RUN_ONLY_BELOW_5PCT',
          'future_outcome_used_for_selection',false,
          'production_selector_changed',false
        ),
        'FORWARD_RANKING_CHALLENGER_SCORECARD',
        true,false,false,false,'NONE'
      from public.alpha_hunter_volume_growth_ranking_shadow_v01 s
      where s.selection_run_id=v_selection_run_id
        and s.ranking_eligible
        and abs(s.change_24h_pct)<5.0
        and (s.shadow_top30_selected or s.production_deep_scan_selected)
      on conflict(observation_id) do nothing
      returning 1
    )
    select count(*) into v_inserted from inserted;
  end if;

  for r in
    select *
    from private.alpha_hunter_volume_growth_forward_candidates_v01
    where evaluation_status='PENDING'
      and maturity_at_utc<=v_now
    order by maturity_at_utc
    limit 500
  loop
    select a.* into m
    from public.alpha_hunter_big_mover_answer_key a
    where a.symbol=r.symbol
      and a.threshold_pct=5.0
      and a.observed_at_utc>r.observed_at_utc
      and a.observed_at_utc<=r.maturity_at_utc
    order by a.observed_at_utc
    limit 1;

    update private.alpha_hunter_volume_growth_forward_candidates_v01
    set evaluation_status='EVALUATED',
        mover_within_24h=(m.event_id is not null),
        mover_event_id=m.event_id,
        mover_observed_at_utc=m.observed_at_utc,
        mover_direction=m.direction,
        mover_threshold_pct=m.threshold_pct,
        mover_move_pct=m.current_24h_move_pct,
        minutes_to_mover=case
          when m.event_id is null then null
          else extract(epoch from(m.observed_at_utc-r.observed_at_utc))/60.0
        end,
        evidence=evidence||jsonb_build_object(
          'outcome_window_hours',24,
          'outcome_definition','FIRST_NEW_5PCT_ANSWER_KEY_EVENT_AFTER_SUB5_CAPTURE',
          'evaluated_at_utc',v_now,
          'mover_within_24h',(m.event_id is not null)
        )
    where candidate_id=r.candidate_id;

    v_evaluated:=v_evaluated+1;
  end loop;

  select count(*) into v_pending
  from private.alpha_hunter_volume_growth_forward_candidates_v01
  where evaluation_status='PENDING';

  v_scorecard_run_id:='vg-scorecard-'||md5(
    v_now::text||'|'||coalesce(v_selection_run_id,'NONE')
  );

  insert into private.alpha_hunter_volume_growth_forward_runs_v01(
    scorecard_run_id,checked_at_utc,selection_run_id,candidates_inserted,
    candidates_evaluated,pending_after_run,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_scorecard_run_id,v_now,v_selection_run_id,v_inserted,
    v_evaluated,v_pending,
    jsonb_build_object(
      'model_version','volume-growth-forward-scorecard-v0.1',
      'capture_threshold_abs_change_pct_lt',5.0,
      'outcome_horizon_hours',24,
      'outcome_threshold_pct',5.0,
      'production_selector_changed',false,
      'trade_permission',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'scorecard_run_id',v_scorecard_run_id,
    'selection_run_id',v_selection_run_id,
    'candidates_inserted',v_inserted,
    'candidates_evaluated',v_evaluated,
    'pending_after_run',v_pending,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_volume_growth_forward_scorecard_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_volume_growth_forward_scorecard_v01()
to postgres;

create or replace view private.alpha_hunter_volume_growth_forward_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
with e as (
  select *
  from private.alpha_hunter_volume_growth_forward_candidates_v01
  where evaluation_status='EVALUATED'
)
select
  count(*) as evaluated_candidate_rows,

  count(*) filter(where shadow_top30_selected) as shadow_selected_rows,
  count(*) filter(where shadow_top30_selected and mover_within_24h) as shadow_mover_hits,
  100.0*count(*) filter(where shadow_top30_selected and mover_within_24h)
    /nullif(count(*) filter(where shadow_top30_selected),0) as shadow_precision_pct,

  count(*) filter(where production_deep_scan_selected) as production_selected_rows,
  count(*) filter(where production_deep_scan_selected and mover_within_24h)
    as production_mover_hits,
  100.0*count(*) filter(where production_deep_scan_selected and mover_within_24h)
    /nullif(count(*) filter(where production_deep_scan_selected),0)
    as production_precision_pct,

  count(*) filter(
    where shadow_top30_selected and not production_deep_scan_selected
  ) as shadow_only_rows,
  count(*) filter(
    where shadow_top30_selected
      and not production_deep_scan_selected
      and mover_within_24h
  ) as shadow_only_mover_hits,
  100.0*count(*) filter(
    where shadow_top30_selected
      and not production_deep_scan_selected
      and mover_within_24h
  )/nullif(count(*) filter(
    where shadow_top30_selected and not production_deep_scan_selected
  ),0) as shadow_only_precision_pct,

  count(*) filter(
    where production_deep_scan_selected and not shadow_top30_selected
  ) as production_only_rows,
  count(*) filter(
    where production_deep_scan_selected
      and not shadow_top30_selected
      and mover_within_24h
  ) as production_only_mover_hits,
  100.0*count(*) filter(
    where production_deep_scan_selected
      and not shadow_top30_selected
      and mover_within_24h
  )/nullif(count(*) filter(
    where production_deep_scan_selected and not shadow_top30_selected
  ),0) as production_only_precision_pct,

  count(*) filter(
    where shadow_top30_selected and production_deep_scan_selected
  ) as overlap_rows,
  avg(minutes_to_mover) filter(
    where mover_within_24h and shadow_top30_selected
  ) as shadow_avg_minutes_to_mover,
  avg(minutes_to_mover) filter(
    where mover_within_24h and production_deep_scan_selected
  ) as production_avg_minutes_to_mover,

  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'FORWARD_SELECTION_PRECISION_ONLY_NOT_EXECUTION_EDGE'::text as claim_ceiling
from e;

revoke all on private.alpha_hunter_volume_growth_forward_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_forward_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_forward_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_volume_growth_forward_candidates_v01
to service_role;
grant select on private.alpha_hunter_volume_growth_forward_runs_v01
to service_role;
grant select on private.alpha_hunter_volume_growth_forward_scorecard_v01
to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-volume-growth-forward-scorecard-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-volume-growth-forward-scorecard-v01',
  '6,31,51 * * * *',
  $cmd$
    select private.alpha_hunter_run_volume_growth_forward_scorecard_v01();
  $cmd$
);

-- No historical candidate row is backfilled by this script.
