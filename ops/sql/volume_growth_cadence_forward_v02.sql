-- Alpha Hunter volume-growth cadence-aware forward scorecard v0.2
--
-- Problem:
--   v0.1 used LAG() on universe rows and required a 50-70 minute gap.
--   Production now scans roughly every 20 minutes, so the immediate LAG()
--   predecessor is ~20 minutes old and current rows become ineligible.
--
-- Fix:
--   For each current universe row, explicitly select the nearest observation
--   50-70 minutes earlier for the same symbol, targeting ~60 minutes.
--
-- Scientific boundary:
--   * supersedes the empty v0.1 forward experiment;
--   * new preregistration start boundary is created at deployment;
--   * no historical candidate backfill;
--   * no production selector mutation;
--   * no trade / threshold / promotion authority.

create table if not exists private.alpha_hunter_volume_growth_forward_specs_v02 (
  spec_id text primary key,
  experiment_started_at_utc timestamptz not null,
  prior_min_minutes integer not null,
  prior_max_minutes integer not null,
  prior_target_minutes integer not null,
  outcome_horizon_hours integer not null,
  mover_threshold_pct double precision not null,
  capture_abs_change_lt_pct double precision not null,
  scientific_role text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(prior_min_minutes>0),
  check(prior_max_minutes>prior_min_minutes),
  check(prior_target_minutes between prior_min_minutes and prior_max_minutes),
  check(outcome_horizon_hours>0),
  check(mover_threshold_pct>0),
  check(capture_abs_change_lt_pct>0)
);

insert into private.alpha_hunter_volume_growth_forward_specs_v02(
  spec_id,experiment_started_at_utc,
  prior_min_minutes,prior_max_minutes,prior_target_minutes,
  outcome_horizon_hours,mover_threshold_pct,capture_abs_change_lt_pct,
  scientific_role,shadow_only,trade_permission,threshold_change_permitted,
  production_promotion_permitted,order_path
) values (
  'VG-FORWARD-TOP30-CADENCE-V02',
  clock_timestamp(),
  50,70,60,
  24,5.0,5.0,
  'FORWARD_RANKING_CHALLENGER_PREREGISTRATION_V02',
  true,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_volume_growth_experiment_supersessions_v01 (
  superseded_spec_id text primary key,
  replacement_spec_id text not null,
  superseded_at_utc timestamptz not null default clock_timestamp(),
  supersession_reason text not null,
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'EXPERIMENT_SUPERSESSION',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

insert into private.alpha_hunter_volume_growth_experiment_supersessions_v01(
  superseded_spec_id,replacement_spec_id,supersession_reason,evidence,
  scientific_role,shadow_only,trade_permission,production_promotion_permitted,order_path
) values (
  'VG-FORWARD-TOP30-V01',
  'VG-FORWARD-TOP30-CADENCE-V02',
  'V01_LAG_PREDECESSOR_INCOMPATIBLE_WITH_20_MINUTE_SCANNER_CADENCE',
  jsonb_build_object(
    'diagnosed_run_id','c3f8f68a8c0de4be85109036da3578d3',
    'diagnosed_run_rows',804,
    'v01_ranking_eligible_rows',0,
    'v01_immediate_lag_gap_seconds',1264.911004,
    'counterfactual_50_70m_prefilter_rows',407,
    'counterfactual_50_70m_ranking_eligible_rows',407,
    'counterfactual_shadow_top30_rows',30,
    'counterfactual_prior_gap_seconds',3603.280768,
    'historical_backfill_permitted',false
  ),
  'EXPERIMENT_SUPERSESSION',
  true,false,false,'NONE'
)
on conflict(superseded_spec_id) do nothing;

create table if not exists private.alpha_hunter_volume_growth_ranking_snapshots_v02 (
  ranking_snapshot_id text primary key,
  spec_id text not null references private.alpha_hunter_volume_growth_forward_specs_v02(spec_id),
  observation_id text not null unique,
  captured_at_utc timestamptz not null,
  observed_at_utc timestamptz not null,
  selection_run_id text not null,
  symbol text not null,
  last_price double precision,
  change_24h_pct double precision not null,
  quote_volume_24h double precision,
  production_deep_scan_selected boolean not null,
  previous_observed_at_utc timestamptz not null,
  previous_quote_volume_24h double precision not null,
  previous_gap_seconds double precision not null,
  volume_log_growth double precision not null,
  volume_growth_rank bigint not null,
  shadow_top30_selected boolean not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(previous_gap_seconds between 3000 and 4200)
);

create index if not exists idx_ah_vg_rank_v02_run_rank
  on private.alpha_hunter_volume_growth_ranking_snapshots_v02(
    selection_run_id,volume_growth_rank
  );

create index if not exists idx_ah_vg_rank_v02_symbol_time
  on private.alpha_hunter_volume_growth_ranking_snapshots_v02(
    symbol,observed_at_utc
  );

create table if not exists private.alpha_hunter_volume_growth_forward_candidates_v02 (
  candidate_id text primary key,
  spec_id text not null references private.alpha_hunter_volume_growth_forward_specs_v02(spec_id),
  ranking_snapshot_id text not null references private.alpha_hunter_volume_growth_ranking_snapshots_v02(ranking_snapshot_id),
  observation_id text not null unique,
  captured_at_utc timestamptz not null,
  observed_at_utc timestamptz not null,
  maturity_at_utc timestamptz not null,
  selection_run_id text not null,
  symbol text not null,
  start_change_24h_pct double precision not null,
  quote_volume_24h double precision,
  volume_log_growth double precision not null,
  volume_growth_rank bigint not null,
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

create index if not exists idx_ah_vg_forward_v02_pending
  on private.alpha_hunter_volume_growth_forward_candidates_v02(
    evaluation_status,maturity_at_utc
  );

create index if not exists idx_ah_vg_forward_v02_symbol_time
  on private.alpha_hunter_volume_growth_forward_candidates_v02(
    symbol,observed_at_utc
  );

create table if not exists private.alpha_hunter_volume_growth_forward_runs_v02 (
  scorecard_run_id text primary key,
  spec_id text not null references private.alpha_hunter_volume_growth_forward_specs_v02(spec_id),
  checked_at_utc timestamptz not null,
  selection_run_id text,
  ranking_rows_inserted integer not null,
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

create or replace function private.alpha_hunter_run_volume_growth_forward_scorecard_v02()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_now timestamptz:=clock_timestamp();
  v_spec_id text:='VG-FORWARD-TOP30-CADENCE-V02';
  v_started_at timestamptz;
  v_prior_min integer;
  v_prior_max integer;
  v_prior_target integer;
  v_selection_run_id text;
  v_ranking_inserted integer:=0;
  v_candidates_inserted integer:=0;
  v_evaluated integer:=0;
  v_pending integer:=0;
  v_scorecard_run_id text;
  r private.alpha_hunter_volume_growth_forward_candidates_v02%rowtype;
  m public.alpha_hunter_big_mover_answer_key%rowtype;
begin
  select
    experiment_started_at_utc,
    prior_min_minutes,
    prior_max_minutes,
    prior_target_minutes
  into
    v_started_at,
    v_prior_min,
    v_prior_max,
    v_prior_target
  from private.alpha_hunter_volume_growth_forward_specs_v02
  where spec_id=v_spec_id;

  if v_started_at is null then
    raise exception 'volume-growth v02 forward spec missing';
  end if;

  select u.selection_run_id
    into v_selection_run_id
  from public.alpha_hunter_universe_hourly u
  where u.selection_run_id is not null
    and u.observed_at_utc>=v_started_at
  order by u.observed_at_utc desc
  limit 1;

  if v_selection_run_id is not null then
    with current_run as (
      select
        u.observation_id,u.observed_at_utc,u.selection_run_id,u.symbol,
        u.last_price,u.change_24h_pct,u.quote_volume_24h,
        u.prefilter_eligible,u.deep_scan_selected,
        u.measurement_quality
      from public.alpha_hunter_universe_hourly u
      where u.selection_run_id=v_selection_run_id
        and u.observed_at_utc>=v_started_at
    ), features as (
      select
        c.*,
        p.observed_at_utc as previous_observed_at_utc,
        p.quote_volume_24h as previous_quote_volume_24h,
        extract(epoch from(c.observed_at_utc-p.observed_at_utc))::double precision
          as previous_gap_seconds,
        case
          when c.prefilter_eligible
           and p.observed_at_utc is not null
           and p.quote_volume_24h>0
           and c.quote_volume_24h>0
          then ln(c.quote_volume_24h/p.quote_volume_24h)
        end as volume_log_growth
      from current_run c
      left join lateral (
        select
          u.observed_at_utc,
          u.quote_volume_24h
        from public.alpha_hunter_universe_hourly u
        where u.symbol=c.symbol
          and u.observed_at_utc between
              c.observed_at_utc-make_interval(mins=>v_prior_max)
              and c.observed_at_utc-make_interval(mins=>v_prior_min)
        order by
          abs(extract(epoch from(
            (c.observed_at_utc-u.observed_at_utc)
            - make_interval(mins=>v_prior_target)
          ))),
          u.observed_at_utc desc
        limit 1
      ) p on true
    ), ranked as (
      select
        f.*,
        row_number() over(
          partition by f.selection_run_id
          order by f.volume_log_growth desc,f.symbol
        ) as volume_growth_rank
      from features f
      where f.prefilter_eligible
        and f.volume_log_growth is not null
        and f.volume_log_growth=f.volume_log_growth
    ), inserted as (
      insert into private.alpha_hunter_volume_growth_ranking_snapshots_v02(
        ranking_snapshot_id,spec_id,observation_id,captured_at_utc,
        observed_at_utc,selection_run_id,symbol,last_price,change_24h_pct,
        quote_volume_24h,production_deep_scan_selected,
        previous_observed_at_utc,previous_quote_volume_24h,
        previous_gap_seconds,volume_log_growth,volume_growth_rank,
        shadow_top30_selected,evidence,
        shadow_only,trade_permission,threshold_change_permitted,
        production_promotion_permitted,order_path
      )
      select
        'vg-rank-v02-'||md5(ranked_row.observation_id),
        v_spec_id,
        ranked_row.observation_id,
        v_now,
        ranked_row.observed_at_utc,
        ranked_row.selection_run_id,
        ranked_row.symbol,
        ranked_row.last_price,
        ranked_row.change_24h_pct,
        ranked_row.quote_volume_24h,
        ranked_row.deep_scan_selected,
        ranked_row.previous_observed_at_utc,
        ranked_row.previous_quote_volume_24h,
        ranked_row.previous_gap_seconds,
        ranked_row.volume_log_growth,
        ranked_row.volume_growth_rank,
        ranked_row.volume_growth_rank<=30,
        jsonb_build_object(
          'model_version','volume-growth-ranking-cadence-aware-v0.2',
          'prior_window_minutes',jsonb_build_array(v_prior_min,v_prior_max),
          'prior_target_minutes',v_prior_target,
          'measurement_quality',ranked_row.measurement_quality,
          'production_selector_changed',false
        ),
        true,false,false,false,'NONE'
      from ranked ranked_row
      on conflict(observation_id) do nothing
      returning 1
    )
    select count(*) into v_ranking_inserted from inserted;

    with inserted as (
      insert into private.alpha_hunter_volume_growth_forward_candidates_v02(
        candidate_id,spec_id,ranking_snapshot_id,observation_id,
        captured_at_utc,observed_at_utc,maturity_at_utc,
        selection_run_id,symbol,start_change_24h_pct,quote_volume_24h,
        volume_log_growth,volume_growth_rank,shadow_top30_selected,
        production_deep_scan_selected,evidence,
        shadow_only,trade_permission,threshold_change_permitted,
        production_promotion_permitted,order_path
      )
      select
        'vg-forward-v02-'||md5(s.observation_id),
        v_spec_id,
        s.ranking_snapshot_id,
        s.observation_id,
        v_now,
        s.observed_at_utc,
        s.observed_at_utc+interval '24 hours',
        s.selection_run_id,
        s.symbol,
        s.change_24h_pct,
        s.quote_volume_24h,
        s.volume_log_growth,
        s.volume_growth_rank,
        s.shadow_top30_selected,
        s.production_deep_scan_selected,
        jsonb_build_object(
          'model_version','volume-growth-forward-scorecard-v0.2',
          'capture_rule','POST_PREREGISTRATION_SUB5_ONLY',
          'future_outcome_used_for_selection',false,
          'production_selector_changed',false
        ),
        true,false,false,false,'NONE'
      from private.alpha_hunter_volume_growth_ranking_snapshots_v02 s
      where s.spec_id=v_spec_id
        and s.selection_run_id=v_selection_run_id
        and abs(s.change_24h_pct)<5.0
        and (s.shadow_top30_selected or s.production_deep_scan_selected)
      on conflict(observation_id) do nothing
      returning 1
    )
    select count(*) into v_candidates_inserted from inserted;
  end if;

  for r in
    select *
    from private.alpha_hunter_volume_growth_forward_candidates_v02
    where spec_id=v_spec_id
      and evaluation_status='PENDING'
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

    update private.alpha_hunter_volume_growth_forward_candidates_v02
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
          'evaluated_at_utc',v_now,
          'outcome_window_hours',24,
          'outcome_definition','FIRST_NEW_5PCT_EVENT_AFTER_SUB5_CAPTURE',
          'mover_within_24h',(m.event_id is not null)
        )
    where candidate_id=r.candidate_id;

    v_evaluated:=v_evaluated+1;
  end loop;

  select count(*) into v_pending
  from private.alpha_hunter_volume_growth_forward_candidates_v02
  where spec_id=v_spec_id
    and evaluation_status='PENDING';

  v_scorecard_run_id:='vg-scorecard-v02-'||md5(
    v_now::text||'|'||coalesce(v_selection_run_id,'NONE')
  );

  insert into private.alpha_hunter_volume_growth_forward_runs_v02(
    scorecard_run_id,spec_id,checked_at_utc,selection_run_id,
    ranking_rows_inserted,candidates_inserted,candidates_evaluated,
    pending_after_run,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_scorecard_run_id,v_spec_id,v_now,v_selection_run_id,
    v_ranking_inserted,v_candidates_inserted,v_evaluated,v_pending,
    jsonb_build_object(
      'model_version','volume-growth-forward-scorecard-v0.2',
      'prior_min_minutes',v_prior_min,
      'prior_max_minutes',v_prior_max,
      'prior_target_minutes',v_prior_target,
      'capture_threshold_abs_change_pct_lt',5.0,
      'outcome_horizon_hours',24,
      'outcome_threshold_pct',5.0,
      'production_selector_changed',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'scorecard_run_id',v_scorecard_run_id,
    'selection_run_id',v_selection_run_id,
    'ranking_rows_inserted',v_ranking_inserted,
    'candidates_inserted',v_candidates_inserted,
    'candidates_evaluated',v_evaluated,
    'pending_after_run',v_pending,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_volume_growth_forward_scorecard_v02()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_volume_growth_forward_scorecard_v02()
to postgres;

create or replace view private.alpha_hunter_volume_growth_forward_scorecard_v02
with (security_invoker=true,security_barrier=true)
as
with e as (
  select *
  from private.alpha_hunter_volume_growth_forward_candidates_v02
  where evaluation_status='EVALUATED'
)
select
  count(*) as evaluated_candidate_rows,

  count(*) filter(where shadow_top30_selected) as shadow_selected_rows,
  count(*) filter(where shadow_top30_selected and mover_within_24h)
    as shadow_mover_hits,
  100.0*count(*) filter(where shadow_top30_selected and mover_within_24h)
    /nullif(count(*) filter(where shadow_top30_selected),0)
    as shadow_precision_pct,

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

revoke all on private.alpha_hunter_volume_growth_forward_specs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_experiment_supersessions_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_ranking_snapshots_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_forward_candidates_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_forward_runs_v02
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_volume_growth_forward_scorecard_v02
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_volume_growth_forward_specs_v02
to service_role;
grant select on private.alpha_hunter_volume_growth_experiment_supersessions_v01
to service_role;
grant select on private.alpha_hunter_volume_growth_ranking_snapshots_v02
to service_role;
grant select on private.alpha_hunter_volume_growth_forward_candidates_v02
to service_role;
grant select on private.alpha_hunter_volume_growth_forward_runs_v02
to service_role;
grant select on private.alpha_hunter_volume_growth_forward_scorecard_v02
to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname in (
      'alpha-hunter-volume-growth-forward-scorecard-v01',
      'alpha-hunter-volume-growth-forward-scorecard-v02'
    )
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-volume-growth-forward-scorecard-v02',
  '9,30,52 * * * *',
  $cmd$
    select private.alpha_hunter_run_volume_growth_forward_scorecard_v02();
  $cmd$
);

-- No universe observation before the v02 preregistration boundary is admitted.
