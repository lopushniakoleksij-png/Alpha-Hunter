-- Alpha Hunter strategy forward-outcome runtime optimization v0.2
--
-- Operational-only performance patch. Scientific outcome definitions remain
-- unchanged. The collector still uses canonical fully closed 1H candles,
-- excludes the trigger candle, preserves ambiguous ordering, and grants no
-- trade or production permission.
--
-- Changes:
-- * bound canonical symbol-snapshot reads to collected_at_utc >= the already
--   frozen measurement start so idx_ah_symbol_time can prune old snapshots;
-- * process at most 120 due episodes per run to stay within the DB statement
--   budget. Later runs continue the immutable backlog.

create or replace function private.alpha_hunter_capture_strategy_forward_outcomes_v01()
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

  v_candidate_entry double precision;
  v_candidate_stop double precision;
  v_candidate_target double precision;

  v_confirmation_tax_reference double precision;
  v_confirmation_tax_entry double precision;
  v_confirmation_tax_r double precision;
  v_remaining_r_delta double precision;
  v_time_to_candidate double precision;

  v_entry_status text;
  v_trigger_candle_open timestamptz;
  v_trigger_known_at timestamptz;
  v_fill_price double precision;
  v_time_to_entry double precision;

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

  v_target_hit_at timestamptz;
  v_stop_hit_at timestamptz;
  v_path_class text;
  v_ordering_ambiguous boolean;

  v_inserted integer := 0;
begin
  for v_episode in
    select e.*
    from public.alpha_hunter_strategy_episodes_v01 e
    where e.first_observed_at_utc <= clock_timestamp() - interval '1 hour'
      and exists (
        select 1
        from (values (1),(4),(12),(24)) as h(horizon_hours)
        where e.first_observed_at_utc
                + h.horizon_hours * interval '1 hour'
              <= clock_timestamp()
          and not exists (
            select 1
            from public.alpha_hunter_strategy_forward_outcomes_v01 o
            where o.episode_id=e.episode_id
              and o.horizon_hours=h.horizon_hours
          )
      )
    order by e.first_observed_at_utc
    limit 120
  loop
    foreach v_horizon in array array[1,4,12,24]
    loop
      v_horizon_end := v_episode.first_observed_at_utc
        + make_interval(hours=>v_horizon);

      if clock_timestamp() < v_horizon_end
         or exists (
           select 1
           from public.alpha_hunter_strategy_forward_outcomes_v01 o
           where o.episode_id=v_episode.episode_id
             and o.horizon_hours=v_horizon
         )
      then
        continue;
      end if;

      v_candidate := null;

      select o.* into v_candidate
      from public.alpha_hunter_strategy_observations_v01 o
      where o.strategy_instance_id=v_episode.episode_id
        and o.status='SHADOW_CANDIDATE'
        and o.observed_at_utc<=v_horizon_end
      order by o.observed_at_utc,o.observation_id
      limit 1;

      v_confirmation_tax_reference := null;
      v_confirmation_tax_entry := null;
      v_confirmation_tax_r := null;
      v_remaining_r_delta := null;
      v_time_to_candidate := null;
      v_candidate_entry := null;
      v_candidate_stop := null;
      v_candidate_target := null;

      if v_candidate.observation_id is not null then
        v_candidate_entry := coalesce(
          v_candidate.entry_price,
          v_candidate.reference_price
        );
        v_candidate_stop := v_candidate.stop_price;
        v_candidate_target := v_candidate.target_price;
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

        if v_episode.earliest_identifiable_entry_price is not null
           and v_episode.earliest_identifiable_entry_price>0
           and v_candidate_entry is not null
        then
          v_confirmation_tax_entry :=
            case
              when v_episode.direction='LONG'
                then 100.0*(
                  v_candidate_entry-v_episode.earliest_identifiable_entry_price
                )/v_episode.earliest_identifiable_entry_price
              else 100.0*(
                  v_episode.earliest_identifiable_entry_price-v_candidate_entry
                )/v_episode.earliest_identifiable_entry_price
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

        if v_candidate.reward_risk is not null
           and v_episode.first_reward_risk is not null
        then
          v_remaining_r_delta :=
            v_candidate.reward_risk-v_episode.first_reward_risk;
        end if;
      end if;

      v_entry_status := 'NO_SHADOW_CANDIDATE';
      v_trigger_candle_open := null;
      v_trigger_known_at := null;
      v_fill_price := null;
      v_time_to_entry := null;
      v_measurement_start := null;
      v_expected_count := 0;
      v_observed_count := 0;
      v_coverage := null;
      v_quality := 'NOT_MEASURABLE';
      v_max_high := null;
      v_min_low := null;
      v_endpoint_close := null;
      v_mfe := null;
      v_mae := null;
      v_endpoint_return := null;
      v_target_hit_at := null;
      v_stop_hit_at := null;
      v_path_class := 'NO_SHADOW_CANDIDATE';
      v_ordering_ambiguous := false;

      if v_candidate.observation_id is not null then
        if v_candidate_entry is null or v_candidate_entry<=0 then
          v_entry_status := 'INVALID_ENTRY_GEOMETRY';
          v_path_class := 'INVALID_ENTRY_GEOMETRY';

        elsif v_candidate.action='EXECUTE_NOW' then
          v_entry_status := 'TRIGGERED_EXECUTE_NOW';
          v_fill_price := v_candidate_entry;
          v_trigger_known_at := v_candidate.observed_at_utc;
          v_time_to_entry := extract(
            epoch from (
              v_trigger_known_at-v_episode.first_observed_at_utc
            )
          )/60.0;

          v_measurement_start :=
            date_trunc('hour',v_candidate.observed_at_utc)
            + interval '1 hour';

        elsif v_candidate.action='PLACE_LIMIT' then
          select
            to_timestamp(
              ((s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp')::double precision)/1000.0
            )
          into v_trigger_candle_open
          from public.alpha_hunter_symbol_snapshots s
          where s.symbol=v_episode.symbol
            and s.collected_at_utc>v_candidate.observed_at_utc
            and jsonb_typeof(
              s.payload->'timeframes'->'1H'->'last_closed_candle'
            )='object'
            and (
              s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp'
            ) is not null
            and to_timestamp(
              ((s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp')::double precision)/1000.0
            )
              >= date_trunc('hour',v_candidate.observed_at_utc)+interval '1 hour'
            and to_timestamp(
              ((s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp')::double precision)/1000.0
            ) + interval '1 hour'
              <= v_horizon_end
            and nullif(
              s.payload->'timeframes'->'1H'->'last_closed_candle'->>'low',''
            )::double precision <= v_candidate_entry
            and nullif(
              s.payload->'timeframes'->'1H'->'last_closed_candle'->>'high',''
            )::double precision >= v_candidate_entry
          order by 1
          limit 1;

          if v_trigger_candle_open is null then
            v_entry_status := 'NOT_TRIGGERED_WITHIN_HORIZON';
            v_path_class := 'NOT_TRIGGERED_WITHIN_HORIZON';
          else
            v_entry_status := 'TRIGGERED_LIMIT';
            v_fill_price := v_candidate_entry;
            v_trigger_known_at := v_trigger_candle_open+interval '1 hour';
            v_time_to_entry := extract(
              epoch from (
                v_trigger_known_at-v_episode.first_observed_at_utc
              )
            )/60.0;
            v_measurement_start :=
              v_trigger_candle_open+interval '1 hour';
          end if;

        else
          v_entry_status := 'UNSUPPORTED_CANDIDATE_ACTION';
          v_path_class := 'UNSUPPORTED_CANDIDATE_ACTION';
        end if;
      end if;

      if v_fill_price is not null
         and v_measurement_start is not null
         and v_measurement_start<v_horizon_end
      then
        v_expected_count := greatest(
          0,
          floor(
            extract(epoch from (v_horizon_end-v_measurement_start))/3600.0
          )::integer
        );

        with candles as (
          select distinct on (candle_open)
            candle_open,high_price,low_price,close_price
          from (
            select
              to_timestamp(
                ((s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp')::double precision)/1000.0
              ) as candle_open,
              nullif(
                s.payload->'timeframes'->'1H'->'last_closed_candle'->>'high',''
              )::double precision as high_price,
              nullif(
                s.payload->'timeframes'->'1H'->'last_closed_candle'->>'low',''
              )::double precision as low_price,
              nullif(
                s.payload->'timeframes'->'1H'->'last_closed_candle'->>'close',''
              )::double precision as close_price,
              s.collected_at_utc
            from public.alpha_hunter_symbol_snapshots s
            where s.symbol=v_episode.symbol
              and s.collected_at_utc>=v_measurement_start
              and jsonb_typeof(
                s.payload->'timeframes'->'1H'->'last_closed_candle'
              )='object'
              and (
                s.payload->'timeframes'->'1H'->'last_closed_candle'->>'timestamp'
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
        target_hit as (
          select min(candle_open) as hit_at
          from candles
          where v_candidate_target is not null
            and (
              (v_episode.direction='LONG' and high_price>=v_candidate_target)
              or
              (v_episode.direction='SHORT' and low_price<=v_candidate_target)
            )
        ),
        stop_hit as (
          select min(candle_open) as hit_at
          from candles
          where v_candidate_stop is not null
            and (
              (v_episode.direction='LONG' and low_price<=v_candidate_stop)
              or
              (v_episode.direction='SHORT' and high_price>=v_candidate_stop)
            )
        )
        select
          a.candle_count,a.max_high,a.min_low,e.close_price,
          t.hit_at,st.hit_at
        into
          v_observed_count,v_max_high,v_min_low,v_endpoint_close,
          v_target_hit_at,v_stop_hit_at
        from aggregate_path a
        left join endpoint e on true
        left join target_hit t on true
        left join stop_hit st on true;

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
            when v_expected_count=0 then 'INSUFFICIENT_POST_TRIGGER_WINDOW'
            when v_coverage>=80.0 then 'COMPLETE_ENOUGH'
            else 'INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
          end;

        if v_max_high is not null and v_min_low is not null then
          if v_episode.direction='LONG' then
            v_mfe := greatest(
              0.0,
              100.0*(v_max_high-v_fill_price)/v_fill_price
            );
            v_mae := greatest(
              0.0,
              100.0*(v_fill_price-v_min_low)/v_fill_price
            );
          else
            v_mfe := greatest(
              0.0,
              100.0*(v_fill_price-v_min_low)/v_fill_price
            );
            v_mae := greatest(
              0.0,
              100.0*(v_max_high-v_fill_price)/v_fill_price
            );
          end if;
        end if;

        if v_endpoint_close is not null then
          v_endpoint_return :=
            case
              when v_episode.direction='LONG'
                then 100.0*(v_endpoint_close/v_fill_price-1.0)
              else 100.0*(1.0-v_endpoint_close/v_fill_price)
            end;
        end if;

        if v_target_hit_at is not null
           and v_stop_hit_at is not null
           and v_target_hit_at=v_stop_hit_at
        then
          v_path_class := 'TARGET_STOP_SAME_CANDLE_AMBIGUOUS';
          v_ordering_ambiguous := true;
        elsif v_target_hit_at is not null
              and (
                v_stop_hit_at is null
                or v_target_hit_at<v_stop_hit_at
              )
        then
          v_path_class := 'TARGET_FIRST';
        elsif v_stop_hit_at is not null
              and (
                v_target_hit_at is null
                or v_stop_hit_at<v_target_hit_at
              )
        then
          v_path_class := 'STOP_FIRST';
        elsif v_observed_count>0 then
          v_path_class := 'OPEN_AT_HORIZON';
        else
          v_path_class := 'NO_POST_TRIGGER_CANDLES';
        end if;
      end if;

      insert into public.alpha_hunter_strategy_forward_outcomes_v01(
        episode_id,horizon_hours,evaluated_at_utc,horizon_end_utc,
        symbol,strategy_id,strategy_engine_version,direction,
        first_observed_at_utc,first_reference_price,
        earliest_identifiable_entry_price,first_reward_risk,
        first_candidate_at_utc,first_candidate_action,
        first_candidate_reference_price,first_candidate_entry_price,
        first_candidate_stop_price,first_candidate_target_price,
        remaining_r_at_candidate,remaining_r_delta_from_first,
        time_to_candidate_minutes,
        confirmation_tax_reference_pct,confirmation_tax_entry_pct,
        confirmation_tax_r,
        entry_trigger_status,entry_trigger_candle_open_utc,
        entry_trigger_known_at_utc,fill_price,time_to_entry_trigger_minutes,
        measurement_start_candle_open_utc,expected_path_candle_count,
        observed_path_candle_count,path_coverage_pct,path_measurement_quality,
        trigger_candle_excluded,partial_signal_hour_excluded,
        max_favorable_excursion_pct,max_adverse_excursion_pct,
        endpoint_close_price,direction_adjusted_endpoint_return_pct,
        first_target_hit_candle_open_utc,first_stop_hit_candle_open_utc,
        path_outcome_class,ordering_ambiguous,
        gross_only,net_of_cost_return_pct,cost_adjustment_status,
        scientific_role,model_version,shadow_only,trade_permission,
        threshold_change_permitted,production_promotion_permitted,order_path
      ) values (
        v_episode.episode_id,v_horizon,clock_timestamp(),v_horizon_end,
        v_episode.symbol,v_episode.strategy_id,
        v_episode.strategy_engine_version,v_episode.direction,
        v_episode.first_observed_at_utc,v_episode.first_reference_price,
        v_episode.earliest_identifiable_entry_price,v_episode.first_reward_risk,
        v_candidate.observed_at_utc,v_candidate.action,
        v_candidate.reference_price,v_candidate_entry,
        v_candidate_stop,v_candidate_target,
        v_candidate.reward_risk,v_remaining_r_delta,
        v_time_to_candidate,
        v_confirmation_tax_reference,v_confirmation_tax_entry,
        v_confirmation_tax_r,
        v_entry_status,v_trigger_candle_open,v_trigger_known_at,
        v_fill_price,v_time_to_entry,
        v_measurement_start,v_expected_count,v_observed_count,
        v_coverage,v_quality,true,true,
        v_mfe,v_mae,v_endpoint_close,v_endpoint_return,
        v_target_hit_at,v_stop_hit_at,v_path_class,v_ordering_ambiguous,
        true,null,'NOT_BOUND_TO_COST_EVIDENCE',
        'PROSPECTIVE_STRATEGY_FORWARD_OUTCOME',
        'strategy-forward-outcome-v0.1',
        true,false,false,false,'NONE'
      )
      on conflict(episode_id,horizon_hours) do nothing;

      if found then
        v_inserted := v_inserted+1;
      end if;
    end loop;
  end loop;

  return jsonb_build_object(
    'model_version','strategy-forward-outcome-v0.1',
    'inserted_outcomes',v_inserted,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_strategy_forward_outcomes_v01()
  from public,anon,authenticated,service_role;

