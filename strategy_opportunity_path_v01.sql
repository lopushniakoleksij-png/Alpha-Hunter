-- Alpha Hunter strategy opportunity-path ledger v0.1
--
-- Purpose:
--   Measure what happened after the FIRST objectively observed S1-S10 strategy
--   episode, even when the setup never became a SHADOW_CANDIDATE.
--
-- This answers a different question from the execution-forward ledger:
--   "Did Alpha Hunter see the move early enough?"
--
-- It does NOT answer:
--   "Was the setup executable?" or "Does the strategy have proven edge?"
--
-- Scientific boundaries:
--   * source = canonical persisted strategy episodes + canonical symbol snapshots
--   * no second exchange/universe scan
--   * path starts at the next fully closed 1H candle after first observation
--   * partial signal hour is excluded
--   * missing path evidence stays explicit
--   * descriptive only; no ranking, threshold change, trade permission or promotion

create table if not exists public.alpha_hunter_strategy_opportunity_paths_v01 (
  episode_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  evaluated_at_utc timestamptz not null default clock_timestamp(),
  horizon_end_utc timestamptz not null,

  symbol text not null,
  strategy_id text not null,
  strategy_name text,
  strategy_engine_version text,
  direction text not null check(direction in ('LONG','SHORT')),

  first_observed_at_utc timestamptz not null,
  first_status text not null,
  first_gate_action text not null,
  first_proposed_action text,
  first_signal_score double precision,
  first_reference_price double precision,
  first_entry_price double precision,
  first_stop_price double precision,
  first_target_price double precision,
  first_risk_amount double precision,
  first_reward_amount double precision,
  first_reward_risk double precision,
  first_geometry_valid boolean not null default false,
  first_rr_minimum_met boolean not null default false,

  first_candidate_at_utc timestamptz,
  first_candidate_reference_price double precision,
  first_candidate_entry_price double precision,
  first_candidate_reward_risk double precision,
  time_to_candidate_minutes double precision,
  confirmation_tax_reference_pct double precision,
  confirmation_tax_r double precision,

  measurement_start_candle_open_utc timestamptz,
  expected_path_candle_count integer not null default 0,
  observed_path_candle_count integer not null default 0,
  path_coverage_pct double precision,
  path_measurement_quality text not null,
  partial_signal_hour_excluded boolean not null default true
    check(partial_signal_hour_excluded=true),

  opportunity_max_favorable_excursion_pct double precision,
  opportunity_max_adverse_excursion_pct double precision,
  opportunity_endpoint_close_price double precision,
  opportunity_direction_adjusted_endpoint_return_pct double precision,
  opportunity_max_favorable_excursion_r_from_reference double precision,
  opportunity_max_adverse_excursion_r_from_reference double precision,

  first_planned_entry_touch_candle_open_utc timestamptz,
  planned_entry_touch_status text not null,
  time_to_planned_entry_touch_minutes double precision,

  descriptive_only boolean not null default true check(descriptive_only=true),
  scientific_role text not null default 'FIRST_OBSERVATION_OPPORTUNITY_PATH',
  model_version text not null default 'strategy-opportunity-path-v0.1',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),

  primary key(episode_id,horizon_hours)
);

create index if not exists idx_ah_strategy_opportunity_strategy_v01
  on public.alpha_hunter_strategy_opportunity_paths_v01(
    strategy_id,horizon_hours,evaluated_at_utc
  );

create index if not exists idx_ah_strategy_opportunity_symbol_v01
  on public.alpha_hunter_strategy_opportunity_paths_v01(
    symbol,first_observed_at_utc
  );

alter table public.alpha_hunter_strategy_opportunity_paths_v01
  enable row level security;

revoke all on table public.alpha_hunter_strategy_opportunity_paths_v01
  from public,anon,authenticated,service_role;

grant select on table public.alpha_hunter_strategy_opportunity_paths_v01
  to service_role;

drop trigger if exists trg_ah_strategy_opportunity_append_only_v01
  on public.alpha_hunter_strategy_opportunity_paths_v01;

create trigger trg_ah_strategy_opportunity_append_only_v01
before update or delete on public.alpha_hunter_strategy_opportunity_paths_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_capture_strategy_opportunity_paths_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_episode public.alpha_hunter_strategy_episodes_v01%rowtype;
  v_candidate public.alpha_hunter_strategy_observations_v01%rowtype;
  v_horizon integer;
  v_horizon_end timestamptz;
  v_measurement_start timestamptz;

  v_expected_count integer;
  v_observed_count integer;
  v_coverage double precision;
  v_quality text;

  v_max_high double precision;
  v_min_low double precision;
  v_endpoint_close double precision;
  v_mfe double precision;
  v_mae double precision;
  v_endpoint_return double precision;
  v_mfe_r double precision;
  v_mae_r double precision;

  v_first_proposed_action text;
  v_first_rr_ok boolean;

  v_candidate_entry double precision;
  v_time_to_candidate double precision;
  v_confirmation_tax_reference double precision;
  v_confirmation_tax_r double precision;

  v_entry_touch timestamptz;
  v_entry_touch_status text;
  v_time_to_entry_touch double precision;

  v_inserted integer := 0;
begin
  for v_episode in
    select e.*
    from public.alpha_hunter_strategy_episodes_v01 e
    where e.first_observed_at_utc <= clock_timestamp() - interval '1 hour'
    order by e.first_observed_at_utc,e.episode_id
    limit 1000
  loop
    foreach v_horizon in array array[1,4,12,24]
    loop
      v_horizon_end :=
        v_episode.first_observed_at_utc
        + make_interval(hours=>v_horizon);

      if clock_timestamp() < v_horizon_end
         or exists (
           select 1
           from public.alpha_hunter_strategy_opportunity_paths_v01 o
           where o.episode_id=v_episode.episode_id
             and o.horizon_hours=v_horizon
         )
      then
        continue;
      end if;

      v_first_proposed_action := coalesce(
        nullif(v_episode.first_strategy_payload->>'proposed_action',''),
        nullif(v_episode.first_action,''),
        'NO_SAFE_TRADE'
      );

      v_first_rr_ok := coalesce(
        v_episode.first_reward_risk >= 5.0,
        false
      );

      v_candidate := null;
      select o.* into v_candidate
      from public.alpha_hunter_strategy_observations_v01 o
      where o.strategy_instance_id=v_episode.episode_id
        and o.status='SHADOW_CANDIDATE'
        and o.observed_at_utc<=v_horizon_end
      order by o.observed_at_utc,o.observation_id
      limit 1;

      v_candidate_entry := null;
      v_time_to_candidate := null;
      v_confirmation_tax_reference := null;
      v_confirmation_tax_r := null;

      if v_candidate.observation_id is not null then
        v_candidate_entry := coalesce(
          v_candidate.entry_price,
          v_candidate.reference_price
        );

        v_time_to_candidate := extract(
          epoch from (
            v_candidate.observed_at_utc-v_episode.first_observed_at_utc
          )
        )/60.0;

        if v_episode.first_reference_price is not null
           and v_episode.first_reference_price>0
           and v_candidate.reference_price is not null
        then
          v_confirmation_tax_reference :=
            case
              when v_episode.direction='LONG'
                then 100.0*(
                  v_candidate.reference_price-v_episode.first_reference_price
                )/v_episode.first_reference_price
              else 100.0*(
                  v_episode.first_reference_price-v_candidate.reference_price
                )/v_episode.first_reference_price
            end;
        end if;

        if v_episode.first_risk_amount is not null
           and v_episode.first_risk_amount>0
           and v_candidate.reference_price is not null
           and v_episode.first_reference_price is not null
        then
          v_confirmation_tax_r :=
            case
              when v_episode.direction='LONG'
                then (
                  v_candidate.reference_price-v_episode.first_reference_price
                )/v_episode.first_risk_amount
              else (
                  v_episode.first_reference_price-v_candidate.reference_price
                )/v_episode.first_risk_amount
            end;
        end if;
      end if;

      v_measurement_start :=
        date_trunc('hour',v_episode.first_observed_at_utc)
        + interval '1 hour';

      v_expected_count := greatest(
        0,
        floor(
          extract(epoch from (v_horizon_end-v_measurement_start))/3600.0
        )::integer
      );

      v_observed_count := 0;
      v_coverage := null;
      v_quality := 'NOT_MEASURABLE';
      v_max_high := null;
      v_min_low := null;
      v_endpoint_close := null;
      v_mfe := null;
      v_mae := null;
      v_endpoint_return := null;
      v_mfe_r := null;
      v_mae_r := null;
      v_entry_touch := null;
      v_entry_touch_status := 'NO_ENTRY_INTENT';
      v_time_to_entry_touch := null;

      with candles as (
        select distinct on (candle_open)
          candle_open,high_price,low_price,close_price
        from (
          select
            to_timestamp(
              (
                (
                  s.payload->'timeframes'->'1H'->'last_closed_candle'
                  ->>'timestamp'
                )::double precision
              )/1000.0
            ) as candle_open,
            nullif(
              s.payload->'timeframes'->'1H'->'last_closed_candle'
              ->>'high',''
            )::double precision as high_price,
            nullif(
              s.payload->'timeframes'->'1H'->'last_closed_candle'
              ->>'low',''
            )::double precision as low_price,
            nullif(
              s.payload->'timeframes'->'1H'->'last_closed_candle'
              ->>'close',''
            )::double precision as close_price,
            s.collected_at_utc
          from public.alpha_hunter_symbol_snapshots s
          where s.symbol=v_episode.symbol
            and s.collected_at_utc>v_episode.first_observed_at_utc
            and jsonb_typeof(
              s.payload->'timeframes'->'1H'->'last_closed_candle'
            )='object'
            and (
              s.payload->'timeframes'->'1H'->'last_closed_candle'
              ->>'timestamp'
            ) is not null
        ) x
        where candle_open>=v_measurement_start
          and candle_open+interval '1 hour'<=v_horizon_end
        order by candle_open,collected_at_utc desc
      ),
      aggregate_path as (
        select
          count(*)::integer as candle_count,
          max(high_price) as max_high,
          min(low_price) as min_low
        from candles
      ),
      endpoint as (
        select close_price
        from candles
        order by candle_open desc
        limit 1
      ),
      entry_touch as (
        select min(candle_open) as touched_at
        from candles
        where v_episode.earliest_identifiable_entry_price is not null
          and v_episode.earliest_identifiable_entry_price>0
          and (
            (
              v_first_proposed_action='PLACE_LIMIT'
              and low_price<=v_episode.earliest_identifiable_entry_price
              and high_price>=v_episode.earliest_identifiable_entry_price
            )
          )
      )
      select
        a.candle_count,a.max_high,a.min_low,e.close_price,t.touched_at
      into
        v_observed_count,v_max_high,v_min_low,v_endpoint_close,v_entry_touch
      from aggregate_path a
      left join endpoint e on true
      left join entry_touch t on true;

      v_coverage :=
        case
          when v_expected_count>0
            then least(
              100.0,
              100.0*v_observed_count::double precision/v_expected_count
            )
          else 0.0
        end;

      v_quality :=
        case
          when v_expected_count=0 then 'INSUFFICIENT_POST_SIGNAL_WINDOW'
          when v_coverage>=80.0 then 'COMPLETE_ENOUGH'
          else 'INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
        end;

      if v_episode.first_reference_price is not null
         and v_episode.first_reference_price>0
         and v_max_high is not null
         and v_min_low is not null
      then
        if v_episode.direction='LONG' then
          v_mfe := greatest(
            0.0,
            100.0*(
              v_max_high-v_episode.first_reference_price
            )/v_episode.first_reference_price
          );
          v_mae := greatest(
            0.0,
            100.0*(
              v_episode.first_reference_price-v_min_low
            )/v_episode.first_reference_price
          );
        else
          v_mfe := greatest(
            0.0,
            100.0*(
              v_episode.first_reference_price-v_min_low
            )/v_episode.first_reference_price
          );
          v_mae := greatest(
            0.0,
            100.0*(
              v_max_high-v_episode.first_reference_price
            )/v_episode.first_reference_price
          );
        end if;

        if v_episode.first_risk_amount is not null
           and v_episode.first_risk_amount>0
        then
          if v_episode.direction='LONG' then
            v_mfe_r := greatest(
              0.0,
              (v_max_high-v_episode.first_reference_price)
              /v_episode.first_risk_amount
            );
            v_mae_r := greatest(
              0.0,
              (v_episode.first_reference_price-v_min_low)
              /v_episode.first_risk_amount
            );
          else
            v_mfe_r := greatest(
              0.0,
              (v_episode.first_reference_price-v_min_low)
              /v_episode.first_risk_amount
            );
            v_mae_r := greatest(
              0.0,
              (v_max_high-v_episode.first_reference_price)
              /v_episode.first_risk_amount
            );
          end if;
        end if;
      end if;

      if v_episode.first_reference_price is not null
         and v_episode.first_reference_price>0
         and v_endpoint_close is not null
      then
        v_endpoint_return :=
          case
            when v_episode.direction='LONG'
              then 100.0*(
                v_endpoint_close/v_episode.first_reference_price-1.0
              )
            else 100.0*(
              1.0-v_endpoint_close/v_episode.first_reference_price
            )
          end;
      end if;

      if v_first_proposed_action='EXECUTE_NOW' then
        v_entry_touch_status := 'IMMEDIATE_INTENT_AT_FIRST_OBSERVATION';
        v_entry_touch := v_episode.first_observed_at_utc;
        v_time_to_entry_touch := 0.0;
      elsif v_first_proposed_action='PLACE_LIMIT' then
        if v_episode.earliest_identifiable_entry_price is null
           or v_episode.earliest_identifiable_entry_price<=0
        then
          v_entry_touch_status := 'INVALID_PLANNED_ENTRY';
        elsif v_entry_touch is null then
          v_entry_touch_status := 'NOT_TOUCHED_WITHIN_HORIZON';
        else
          v_entry_touch_status := 'TOUCHED_AFTER_FIRST_OBSERVATION';
          v_time_to_entry_touch := extract(
            epoch from (
              (v_entry_touch+interval '1 hour')
              -v_episode.first_observed_at_utc
            )
          )/60.0;
        end if;
      else
        v_entry_touch_status := 'NO_EXECUTABLE_ENTRY_INTENT';
      end if;

      insert into public.alpha_hunter_strategy_opportunity_paths_v01(
        episode_id,horizon_hours,evaluated_at_utc,horizon_end_utc,
        symbol,strategy_id,strategy_name,strategy_engine_version,direction,
        first_observed_at_utc,first_status,first_gate_action,
        first_proposed_action,first_signal_score,first_reference_price,
        first_entry_price,first_stop_price,first_target_price,
        first_risk_amount,first_reward_amount,first_reward_risk,
        first_geometry_valid,first_rr_minimum_met,
        first_candidate_at_utc,first_candidate_reference_price,
        first_candidate_entry_price,first_candidate_reward_risk,
        time_to_candidate_minutes,confirmation_tax_reference_pct,
        confirmation_tax_r,
        measurement_start_candle_open_utc,expected_path_candle_count,
        observed_path_candle_count,path_coverage_pct,path_measurement_quality,
        partial_signal_hour_excluded,
        opportunity_max_favorable_excursion_pct,
        opportunity_max_adverse_excursion_pct,
        opportunity_endpoint_close_price,
        opportunity_direction_adjusted_endpoint_return_pct,
        opportunity_max_favorable_excursion_r_from_reference,
        opportunity_max_adverse_excursion_r_from_reference,
        first_planned_entry_touch_candle_open_utc,
        planned_entry_touch_status,time_to_planned_entry_touch_minutes,
        descriptive_only,scientific_role,model_version,
        shadow_only,trade_permission,threshold_change_permitted,
        production_promotion_permitted,order_path
      ) values (
        v_episode.episode_id,v_horizon,clock_timestamp(),v_horizon_end,
        v_episode.symbol,v_episode.strategy_id,v_episode.strategy_name,
        v_episode.strategy_engine_version,v_episode.direction,
        v_episode.first_observed_at_utc,v_episode.first_status,
        v_episode.first_action,v_first_proposed_action,
        v_episode.first_signal_score,v_episode.first_reference_price,
        v_episode.earliest_identifiable_entry_price,
        v_episode.first_stop_price,v_episode.first_target_price,
        v_episode.first_risk_amount,v_episode.first_reward_amount,
        v_episode.first_reward_risk,v_episode.first_geometry_valid,
        v_first_rr_ok,
        v_candidate.observed_at_utc,v_candidate.reference_price,
        v_candidate_entry,v_candidate.reward_risk,
        v_time_to_candidate,v_confirmation_tax_reference,
        v_confirmation_tax_r,
        v_measurement_start,v_expected_count,v_observed_count,
        v_coverage,v_quality,true,
        v_mfe,v_mae,v_endpoint_close,v_endpoint_return,
        v_mfe_r,v_mae_r,
        v_entry_touch,v_entry_touch_status,v_time_to_entry_touch,
        true,'FIRST_OBSERVATION_OPPORTUNITY_PATH',
        'strategy-opportunity-path-v0.1',
        true,false,false,false,'NONE'
      )
      on conflict(episode_id,horizon_hours) do nothing;

      if found then
        v_inserted := v_inserted+1;
      end if;
    end loop;
  end loop;

  return jsonb_build_object(
    'model_version','strategy-opportunity-path-v0.1',
    'inserted_paths',v_inserted,
    'descriptive_only',true,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_strategy_opportunity_paths_v01()
  from public,anon,authenticated,service_role;


create or replace view public.alpha_hunter_strategy_opportunity_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  strategy_id,
  strategy_engine_version,
  horizon_hours,
  count(*) as evaluated_episodes,
  count(distinct symbol) as distinct_symbols,
  count(*) filter(where first_status='WATCH') as first_watch_episodes,
  count(*) filter(where first_status='SHADOW_CANDIDATE')
    as first_candidate_episodes,
  count(*) filter(where first_candidate_at_utc is not null)
    as candidate_by_horizon,
  count(*) filter(where first_rr_minimum_met)
    as first_rr_gate_pass,
  avg(time_to_candidate_minutes)
    filter(where first_candidate_at_utc is not null)
    as avg_time_to_candidate_minutes,
  avg(confirmation_tax_reference_pct)
    filter(where confirmation_tax_reference_pct is not null)
    as avg_confirmation_tax_reference_pct,
  avg(opportunity_max_favorable_excursion_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_opportunity_mfe_pct,
  avg(opportunity_max_adverse_excursion_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_opportunity_mae_pct,
  avg(opportunity_direction_adjusted_endpoint_return_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_opportunity_endpoint_return_pct,
  avg(opportunity_max_favorable_excursion_r_from_reference)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_opportunity_mfe_r_from_reference,
  count(*) filter(
    where planned_entry_touch_status='TOUCHED_AFTER_FIRST_OBSERVATION'
  ) as planned_limit_touched,
  count(*) filter(
    where planned_entry_touch_status='NOT_TOUCHED_WITHIN_HORIZON'
  ) as planned_limit_not_touched,
  count(*) filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as complete_path_episodes,
  true as descriptive_only,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_strategy_opportunity_paths_v01
group by strategy_id,strategy_engine_version,horizon_hours;

revoke all on public.alpha_hunter_strategy_opportunity_scorecard_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_strategy_opportunity_scorecard_v01
  to service_role;


create or replace view public.alpha_hunter_strategy_opportunity_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  (select count(*) from public.alpha_hunter_strategy_episodes_v01)
    as source_strategy_episodes,
  (select count(*) from public.alpha_hunter_strategy_opportunity_paths_v01)
    as opportunity_path_rows,
  (select count(distinct episode_id)
   from public.alpha_hunter_strategy_opportunity_paths_v01)
    as evaluated_episode_count,
  (select max(evaluated_at_utc)
   from public.alpha_hunter_strategy_opportunity_paths_v01)
    as latest_evaluation_at_utc,
  'DESCRIPTIVE_ONLY_NOT_EDGE_PROOF'::text as evidence_status,
  'CANONICAL_SYMBOL_SNAPSHOTS_ONLY'::text as market_data_source,
  'FIRST_OBSERVATION_NEXT_FULL_1H_CANDLE'::text as path_anchor,
  true as partial_signal_hour_excluded,
  true as descriptive_only,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path;

revoke all on public.alpha_hunter_strategy_opportunity_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_strategy_opportunity_status_v01
  to service_role;


do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname='alpha-hunter-strategy-opportunity-path-v01-hourly'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'alpha-hunter-strategy-opportunity-path-v01-hourly',
  '54 * * * *',
  'select private.alpha_hunter_capture_strategy_opportunity_paths_v01();'
);
