-- Alpha Hunter strategy forward-outcome ledger v0.1
--
-- Purpose:
--   Normalize S1-S10 shadow observations from the canonical symbol snapshot
--   stream and measure prospective outcomes using only later canonical
--   fully-closed 1H candles. No second universe scanner and no exchange
--   order path are introduced.
--
-- Scientific boundaries:
--   * immutable observations / episodes / horizon outcomes
--   * outcomes are anchored to the first persistent strategy observation
--   * first SHADOW_CANDIDATE is measured separately to quantify confirmation tax
--   * limit entry touches are detected only from fully closed future candles
--   * the trigger candle is excluded from MAE/MFE and target/stop ordering
--     because intrabar ordering cannot be known from OHLC
--   * incomplete/ambiguous evidence remains explicit
--   * no outcome can grant trade permission or production promotion

create table if not exists public.alpha_hunter_strategy_observations_v01 (
  observation_id text primary key,
  run_id text not null,
  symbol text not null,
  observed_at_utc timestamptz not null,

  strategy_id text not null,
  strategy_name text,
  strategy_engine_version text,
  status text not null,
  action text not null,
  direction text check(direction is null or direction in ('LONG','SHORT')),

  signal_score double precision,
  score_is_calibrated boolean not null default false,
  reference_price double precision,
  entry_price double precision,
  stop_price double precision,
  target_price double precision,
  risk_amount double precision,
  reward_amount double precision,
  reward_risk double precision,
  distance_to_entry_pct double precision,
  geometry_valid boolean not null default false,

  persistence_state text,
  strategy_instance_id text,
  first_seen_at_utc timestamptz,
  consecutive_scans integer not null default 0,

  market_phase text,
  opportunity_timing text,
  evidence jsonb not null default '{}'::jsonb,
  checks jsonb not null default '{}'::jsonb,
  reasons jsonb not null default '[]'::jsonb,
  strategy_payload jsonb not null,

  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_permission boolean not null default false check(production_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),

  unique(run_id,symbol,strategy_id)
);

create index if not exists idx_ah_strategy_obs_instance_time_v01
  on public.alpha_hunter_strategy_observations_v01(
    strategy_instance_id,observed_at_utc
  )
  where strategy_instance_id is not null;

create index if not exists idx_ah_strategy_obs_strategy_time_v01
  on public.alpha_hunter_strategy_observations_v01(
    strategy_id,observed_at_utc
  );

alter table public.alpha_hunter_strategy_observations_v01
  enable row level security;
revoke all on table public.alpha_hunter_strategy_observations_v01
  from public,anon,authenticated,service_role;
grant select on table public.alpha_hunter_strategy_observations_v01
  to service_role;

drop trigger if exists trg_ah_strategy_obs_append_only_v01
  on public.alpha_hunter_strategy_observations_v01;
create trigger trg_ah_strategy_obs_append_only_v01
before update or delete on public.alpha_hunter_strategy_observations_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create table if not exists public.alpha_hunter_strategy_episodes_v01 (
  episode_id text primary key,
  symbol text not null,
  strategy_id text not null,
  strategy_name text,
  strategy_engine_version text,
  direction text not null check(direction in ('LONG','SHORT')),

  first_observed_at_utc timestamptz not null,
  first_observation_id text not null unique,
  first_status text not null,
  first_action text not null,
  first_signal_score double precision,
  first_reference_price double precision,
  earliest_identifiable_entry_price double precision,
  first_stop_price double precision,
  first_target_price double precision,
  first_risk_amount double precision,
  first_reward_amount double precision,
  first_reward_risk double precision,
  first_geometry_valid boolean not null default false,
  first_market_phase text,
  first_opportunity_timing text,
  first_strategy_payload jsonb not null,

  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_permission boolean not null default false check(production_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_strategy_episode_time_v01
  on public.alpha_hunter_strategy_episodes_v01(first_observed_at_utc);

create index if not exists idx_ah_strategy_episode_strategy_time_v01
  on public.alpha_hunter_strategy_episodes_v01(
    strategy_id,first_observed_at_utc
  );

alter table public.alpha_hunter_strategy_episodes_v01
  enable row level security;
revoke all on table public.alpha_hunter_strategy_episodes_v01
  from public,anon,authenticated,service_role;
grant select on table public.alpha_hunter_strategy_episodes_v01
  to service_role;

drop trigger if exists trg_ah_strategy_episode_append_only_v01
  on public.alpha_hunter_strategy_episodes_v01;
create trigger trg_ah_strategy_episode_append_only_v01
before update or delete on public.alpha_hunter_strategy_episodes_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create table if not exists public.alpha_hunter_strategy_forward_outcomes_v01 (
  episode_id text not null,
  horizon_hours integer not null check(horizon_hours in (1,4,12,24)),
  evaluated_at_utc timestamptz not null default clock_timestamp(),
  horizon_end_utc timestamptz not null,

  symbol text not null,
  strategy_id text not null,
  strategy_engine_version text,
  direction text not null check(direction in ('LONG','SHORT')),

  first_observed_at_utc timestamptz not null,
  first_reference_price double precision,
  earliest_identifiable_entry_price double precision,
  first_reward_risk double precision,

  first_candidate_at_utc timestamptz,
  first_candidate_action text,
  first_candidate_reference_price double precision,
  first_candidate_entry_price double precision,
  first_candidate_stop_price double precision,
  first_candidate_target_price double precision,
  remaining_r_at_candidate double precision,
  remaining_r_delta_from_first double precision,
  time_to_candidate_minutes double precision,

  confirmation_tax_reference_pct double precision,
  confirmation_tax_entry_pct double precision,
  confirmation_tax_r double precision,

  entry_trigger_status text not null,
  entry_trigger_candle_open_utc timestamptz,
  entry_trigger_known_at_utc timestamptz,
  fill_price double precision,
  time_to_entry_trigger_minutes double precision,

  measurement_start_candle_open_utc timestamptz,
  expected_path_candle_count integer not null default 0,
  observed_path_candle_count integer not null default 0,
  path_coverage_pct double precision,
  path_measurement_quality text not null,
  trigger_candle_excluded boolean not null default true check(trigger_candle_excluded=true),
  partial_signal_hour_excluded boolean not null default true check(partial_signal_hour_excluded=true),

  max_favorable_excursion_pct double precision,
  max_adverse_excursion_pct double precision,
  endpoint_close_price double precision,
  direction_adjusted_endpoint_return_pct double precision,

  first_target_hit_candle_open_utc timestamptz,
  first_stop_hit_candle_open_utc timestamptz,
  path_outcome_class text not null,
  ordering_ambiguous boolean not null default false,

  gross_only boolean not null default true check(gross_only=true),
  net_of_cost_return_pct double precision,
  cost_adjustment_status text not null default 'NOT_BOUND_TO_COST_EVIDENCE',

  scientific_role text not null default 'PROSPECTIVE_STRATEGY_FORWARD_OUTCOME',
  model_version text not null default 'strategy-forward-outcome-v0.1',
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

create index if not exists idx_ah_strategy_forward_outcome_strategy_v01
  on public.alpha_hunter_strategy_forward_outcomes_v01(
    strategy_id,horizon_hours,evaluated_at_utc
  );

alter table public.alpha_hunter_strategy_forward_outcomes_v01
  enable row level security;
revoke all on table public.alpha_hunter_strategy_forward_outcomes_v01
  from public,anon,authenticated,service_role;
grant select on table public.alpha_hunter_strategy_forward_outcomes_v01
  to service_role;

drop trigger if exists trg_ah_strategy_forward_outcome_append_only_v01
  on public.alpha_hunter_strategy_forward_outcomes_v01;
create trigger trg_ah_strategy_forward_outcome_append_only_v01
before update or delete on public.alpha_hunter_strategy_forward_outcomes_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_capture_strategy_observations_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $$
declare
  v_strategy jsonb;
  v_persistence jsonb;
  v_observation_id text;
  v_instance_id text;
  v_direction text;
  v_first_seen timestamptz;
begin
  if new.payload is null
     or jsonb_typeof(new.payload->'multi_strategy_engine'->'strategies') <> 'array'
  then
    return new;
  end if;

  for v_strategy in
    select value
    from jsonb_array_elements(
      new.payload->'multi_strategy_engine'->'strategies'
    )
  loop
    v_persistence := coalesce(v_strategy->'persistence','{}'::jsonb);
    v_instance_id := nullif(v_persistence->>'strategy_instance_id','');
    v_direction := nullif(upper(v_strategy->>'direction'),'');
    v_first_seen := coalesce(
      nullif(v_persistence->>'first_seen_at_utc','')::timestamptz,
      new.collected_at_utc
    );

    v_observation_id := pg_catalog.md5(
      'strategy-observation-v0.1|'
      ||coalesce(new.run_id,'')||'|'
      ||coalesce(new.symbol,'')||'|'
      ||coalesce(v_strategy->>'strategy_id','')||'|'
      ||new.collected_at_utc::text
    );

    insert into public.alpha_hunter_strategy_observations_v01(
      observation_id,run_id,symbol,observed_at_utc,
      strategy_id,strategy_name,strategy_engine_version,status,action,direction,
      signal_score,score_is_calibrated,reference_price,
      entry_price,stop_price,target_price,risk_amount,reward_amount,reward_risk,
      distance_to_entry_pct,geometry_valid,
      persistence_state,strategy_instance_id,first_seen_at_utc,consecutive_scans,
      market_phase,opportunity_timing,evidence,checks,reasons,strategy_payload,
      shadow_only,trade_permission,production_permission,
      production_promotion_permitted,order_path
    ) values (
      v_observation_id,new.run_id,new.symbol,new.collected_at_utc,
      v_strategy->>'strategy_id',v_strategy->>'strategy_name',
      v_strategy->>'engine_version',coalesce(v_strategy->>'status','UNKNOWN'),
      coalesce(v_strategy->>'action','NO_SAFE_TRADE'),v_direction,
      nullif(v_strategy->>'signal_score','')::double precision,
      coalesce((v_strategy->>'score_is_calibrated')::boolean,false),
      nullif(new.payload->>'last_price','')::double precision,
      nullif(v_strategy->>'entry','')::double precision,
      nullif(v_strategy->>'stop','')::double precision,
      nullif(v_strategy->>'target','')::double precision,
      nullif(v_strategy->>'risk','')::double precision,
      nullif(v_strategy->>'reward','')::double precision,
      nullif(v_strategy->>'rr','')::double precision,
      nullif(v_strategy->>'distance_to_entry_pct','')::double precision,
      coalesce((v_strategy->>'geometry_valid')::boolean,false),
      v_persistence->>'state',v_instance_id,v_first_seen,
      coalesce(nullif(v_persistence->>'consecutive_scans','')::integer,0),
      new.payload->>'market_phase',new.payload->>'opportunity_timing',
      coalesce(v_strategy->'evidence','{}'::jsonb),
      coalesce(v_strategy->'checks','{}'::jsonb),
      coalesce(v_strategy->'reasons','[]'::jsonb),
      v_strategy,
      true,false,false,false,'NONE'
    )
    on conflict(observation_id) do nothing;

    if v_instance_id is not null
       and v_direction in ('LONG','SHORT')
       and coalesce(v_strategy->>'status','') in ('WATCH','SHADOW_CANDIDATE')
    then
      insert into public.alpha_hunter_strategy_episodes_v01(
        episode_id,symbol,strategy_id,strategy_name,strategy_engine_version,direction,
        first_observed_at_utc,first_observation_id,first_status,first_action,
        first_signal_score,first_reference_price,earliest_identifiable_entry_price,
        first_stop_price,first_target_price,first_risk_amount,first_reward_amount,
        first_reward_risk,first_geometry_valid,first_market_phase,
        first_opportunity_timing,first_strategy_payload,
        shadow_only,trade_permission,production_permission,
        production_promotion_permitted,order_path
      ) values (
        v_instance_id,new.symbol,v_strategy->>'strategy_id',
        v_strategy->>'strategy_name',v_strategy->>'engine_version',v_direction,
        v_first_seen,v_observation_id,coalesce(v_strategy->>'status','UNKNOWN'),
        coalesce(v_strategy->>'action','NO_SAFE_TRADE'),
        nullif(v_strategy->>'signal_score','')::double precision,
        nullif(new.payload->>'last_price','')::double precision,
        nullif(v_strategy->>'entry','')::double precision,
        nullif(v_strategy->>'stop','')::double precision,
        nullif(v_strategy->>'target','')::double precision,
        nullif(v_strategy->>'risk','')::double precision,
        nullif(v_strategy->>'reward','')::double precision,
        nullif(v_strategy->>'rr','')::double precision,
        coalesce((v_strategy->>'geometry_valid')::boolean,false),
        new.payload->>'market_phase',new.payload->>'opportunity_timing',
        v_strategy,true,false,false,false,'NONE'
      )
      on conflict(episode_id) do nothing;
    end if;
  end loop;

  return new;
end;
$$;

revoke all on function private.alpha_hunter_capture_strategy_observations_v01()
  from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_capture_strategy_observations_v01
  on public.alpha_hunter_symbol_snapshots;
create trigger trg_ah_capture_strategy_observations_v01
after insert or update of payload on public.alpha_hunter_symbol_snapshots
for each row execute function private.alpha_hunter_capture_strategy_observations_v01();


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
    order by e.first_observed_at_utc
    limit 500
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


create or replace view public.alpha_hunter_strategy_forward_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  strategy_id,
  strategy_engine_version,
  horizon_hours,
  count(*) as evaluated_episodes,
  count(*) filter(where first_candidate_at_utc is not null) as candidate_episodes,
  count(*) filter(
    where entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
  ) as triggered_episodes,
  count(*) filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as complete_path_episodes,
  avg(confirmation_tax_reference_pct)
    filter(where confirmation_tax_reference_pct is not null)
    as avg_confirmation_tax_reference_pct,
  avg(confirmation_tax_entry_pct)
    filter(where confirmation_tax_entry_pct is not null)
    as avg_confirmation_tax_entry_pct,
  avg(remaining_r_at_candidate)
    filter(where remaining_r_at_candidate is not null)
    as avg_remaining_r_at_candidate,
  avg(max_favorable_excursion_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_mfe_pct,
  avg(max_adverse_excursion_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_mae_pct,
  avg(direction_adjusted_endpoint_return_pct)
    filter(where path_measurement_quality='COMPLETE_ENOUGH')
    as avg_direction_adjusted_endpoint_return_pct,
  count(*) filter(where path_outcome_class='TARGET_FIRST') as target_first,
  count(*) filter(where path_outcome_class='STOP_FIRST') as stop_first,
  count(*) filter(where ordering_ambiguous) as ordering_ambiguous,
  count(*) filter(where entry_trigger_status='NOT_TRIGGERED_WITHIN_HORIZON')
    as not_triggered,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_strategy_forward_outcomes_v01
group by strategy_id,strategy_engine_version,horizon_hours;

revoke all on public.alpha_hunter_strategy_forward_scorecard_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_strategy_forward_scorecard_v01
  to service_role;


create or replace view public.alpha_hunter_strategy_forward_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  (select count(*) from public.alpha_hunter_strategy_observations_v01)
    as normalized_observations,
  (select count(*) from public.alpha_hunter_strategy_episodes_v01)
    as strategy_episodes,
  (select count(*) from public.alpha_hunter_strategy_forward_outcomes_v01)
    as forward_outcomes,
  (select max(observed_at_utc) from public.alpha_hunter_strategy_observations_v01)
    as latest_observation_at_utc,
  (select max(evaluated_at_utc) from public.alpha_hunter_strategy_forward_outcomes_v01)
    as latest_outcome_at_utc,
  'CANONICAL_SYMBOL_SNAPSHOTS_ONLY'::text as market_data_source,
  'FULLY_CLOSED_1H_CANDLES_ONLY'::text as path_measurement_source,
  true as trigger_candle_excluded,
  true as partial_signal_hour_excluded,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path;

revoke all on public.alpha_hunter_strategy_forward_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_strategy_forward_status_v01
  to service_role;


do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname='alpha-hunter-strategy-forward-outcome-v01-hourly'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'alpha-hunter-strategy-forward-outcome-v01-hourly',
  '53 * * * *',
  'select private.alpha_hunter_capture_strategy_forward_outcomes_v01();'
);
