-- Alpha Hunter Big-Mover forward Money Scorecard
--
-- Live sequence:
--   :10 Big-Mover answer-key/signature shadow
--   :11 parent-direction 12H/1D shadow
--   :12 Big-Mover -> Money Entry bridge
--   :14 forward Money Scorecard
--
-- Safety:
--   shadow_only=true
--   trade_permission=false
--   public Bitget market data only
--   exact T0/T1/T2 outcomes are NOT claimed until exact stage snapshots exist
--   realistic_net_r is withheld until a verified execution-cost model exists
--
-- Supabase runtime uses pg_cron via cron.schedule() and private SECURITY DEFINER
-- functions with execution revoked from PUBLIC/anon/authenticated.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_big_mover_money_scorecard_candidates (
  scorecard_id text primary key,
  source_bridge_id text not null unique,
  run_id text not null,
  candidate_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  candidate_entry double precision,
  stop_price double precision,
  target_price double precision,
  geometry_valid boolean not null,
  risk_distance_abs double precision,
  risk_distance_pct double precision,
  initial_remaining_r double precision,
  similarity_score double precision,
  feature_coverage double precision,
  lifecycle text not null,
  research_status text not null,
  bridge_status text not null,
  raw_change_24h_pct double precision,
  direction_normalized_move_pct double precision,
  scanner_direction text,
  direction_1h text,
  direction_4h text,
  direction_12h text,
  direction_1d text,
  liquidity_state text,
  opportunity_timing text,
  candidate_quality_status text,
  bridge_blockers jsonb not null default '[]'::jsonb,
  frozen_evidence jsonb not null default '{}'::jsonb,
  stage_snapshot_status text not null default 'EXACT_T0_T1_T2_NOT_CAPTURED',
  t0_snapshot_available boolean not null default false,
  t1_snapshot_available boolean not null default false,
  t2_snapshot_available boolean not null default false,
  model_version text not null default 'big-mover-money-scorecard-v0.1',
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_big_mover_money_scorecard_candidate_time
  on public.alpha_hunter_big_mover_money_scorecard_candidates(candidate_at_utc desc);
create index if not exists idx_ah_big_mover_money_scorecard_candidate_symbol
  on public.alpha_hunter_big_mover_money_scorecard_candidates(symbol, candidate_at_utc desc);

alter table public.alpha_hunter_big_mover_money_scorecard_candidates enable row level security;
revoke all on table public.alpha_hunter_big_mover_money_scorecard_candidates from anon, authenticated;
grant select, insert on table public.alpha_hunter_big_mover_money_scorecard_candidates to service_role;

create table if not exists public.alpha_hunter_big_mover_money_scorecard_outcomes (
  outcome_id text primary key,
  scorecard_id text not null references public.alpha_hunter_big_mover_money_scorecard_candidates(scorecard_id),
  horizon_hours integer not null check (horizon_hours in (1,4,12,24)),
  horizon_due_at_utc timestamptz not null,
  evaluation_status text not null default 'PENDING' check (evaluation_status in ('PENDING','EVALUATED','AMBIGUOUS_INTRABAR','DATA_INSUFFICIENT','RETRYABLE_ERROR')),
  evaluation_attempts integer not null default 0 check (evaluation_attempts >= 0),
  evaluated_at_utc timestamptz,
  candle_interval text not null default '3m',
  candle_count integer,
  first_candle_at_utc timestamptz,
  last_candle_at_utc timestamptz,
  boundary_gap_seconds double precision,
  evaluation_close double precision,
  mfe_pct double precision,
  mae_pct double precision,
  direction_adjusted_close_return_pct double precision,
  hit_3pct boolean,
  hit_5pct boolean,
  hit_10pct boolean,
  stop_hit boolean,
  stop_survived boolean,
  target_hit boolean,
  first_stop_candle_at_utc timestamptz,
  first_target_candle_at_utc timestamptz,
  path_resolution text,
  path_r_pre_cost double precision,
  remaining_r double precision,
  realistic_net_r double precision,
  realistic_net_r_status text not null default 'UNVERIFIED_EXECUTION_COST_MODEL',
  legacy_episode_id text,
  legacy_detection_rr double precision,
  legacy_emerging_rr double precision,
  legacy_confirmed_rr double precision,
  confirmation_tax_r double precision,
  confirmation_tax_status text not null default 'NOT_LINKED',
  t0_path_result text not null default 'NOT_EVALUABLE',
  t1_path_result text not null default 'NOT_EVALUABLE',
  t2_path_result text not null default 'NOT_EVALUABLE',
  stage_outcome_status text not null default 'EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE',
  candidate_path_outcome text,
  evidence jsonb not null default '{}'::jsonb,
  last_error text,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  unique(scorecard_id, horizon_hours)
);

create index if not exists idx_ah_big_mover_money_scorecard_outcome_due
  on public.alpha_hunter_big_mover_money_scorecard_outcomes(evaluation_status, horizon_due_at_utc);
create index if not exists idx_ah_big_mover_money_scorecard_outcome_scorecard
  on public.alpha_hunter_big_mover_money_scorecard_outcomes(scorecard_id, horizon_hours);

alter table public.alpha_hunter_big_mover_money_scorecard_outcomes enable row level security;
revoke all on table public.alpha_hunter_big_mover_money_scorecard_outcomes from anon, authenticated;
grant select, insert, update on table public.alpha_hunter_big_mover_money_scorecard_outcomes to service_role;

create or replace function private.alpha_hunter_block_money_scorecard_candidate_mutation()
returns trigger
language plpgsql
security invoker
set search_path = public, private
as $$
begin
  raise exception 'money scorecard candidate snapshots are append-only';
end;
$$;
revoke all on function private.alpha_hunter_block_money_scorecard_candidate_mutation() from public, anon, authenticated;
grant execute on function private.alpha_hunter_block_money_scorecard_candidate_mutation() to service_role;

drop trigger if exists trg_ah_big_mover_money_scorecard_candidate_immutable
  on public.alpha_hunter_big_mover_money_scorecard_candidates;
create trigger trg_ah_big_mover_money_scorecard_candidate_immutable
before update or delete on public.alpha_hunter_big_mover_money_scorecard_candidates
for each row execute function private.alpha_hunter_block_money_scorecard_candidate_mutation();

create or replace function private.alpha_hunter_seed_big_mover_money_scorecard()
returns jsonb
language plpgsql
security definer
set search_path = public, private, extensions
as $$
declare
  v_candidates integer := 0;
  v_outcomes integer := 0;
begin
  with src as (
    select
      b.*,
      case
        when b.direction='LONG' and b.candidate_entry is not null and b.stop_price is not null and b.target_price is not null
          and b.stop_price < b.candidate_entry and b.target_price > b.candidate_entry then true
        when b.direction='SHORT' and b.candidate_entry is not null and b.stop_price is not null and b.target_price is not null
          and b.stop_price > b.candidate_entry and b.target_price < b.candidate_entry then true
        else false
      end as geometry_ok
    from public.alpha_hunter_big_mover_money_entry_shadow b
    where b.research_status='SHADOW_QUEUE'
      and b.lifecycle in ('PRE_MOVER','IGNITION')
  ), ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_candidates(
      scorecard_id,source_bridge_id,run_id,candidate_at_utc,symbol,direction,
      candidate_entry,stop_price,target_price,geometry_valid,risk_distance_abs,risk_distance_pct,initial_remaining_r,
      similarity_score,feature_coverage,lifecycle,research_status,bridge_status,
      raw_change_24h_pct,direction_normalized_move_pct,scanner_direction,
      direction_1h,direction_4h,direction_12h,direction_1d,liquidity_state,opportunity_timing,candidate_quality_status,
      bridge_blockers,frozen_evidence,stage_snapshot_status,t0_snapshot_available,t1_snapshot_available,t2_snapshot_available,
      model_version,shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-v0.1|'||s.bridge_id),
      s.bridge_id,s.run_id,s.captured_at_utc,s.symbol,s.direction,
      s.candidate_entry,s.stop_price,s.target_price,s.geometry_ok,
      case when s.geometry_ok then abs(s.candidate_entry-s.stop_price) end,
      case when s.geometry_ok and s.candidate_entry<>0 then abs(s.candidate_entry-s.stop_price)/s.candidate_entry*100.0 end,
      case when s.geometry_ok and abs(s.candidate_entry-s.stop_price)>0
        then abs(s.target_price-s.candidate_entry)/abs(s.candidate_entry-s.stop_price) end,
      s.similarity_score,s.feature_coverage,s.lifecycle,s.research_status,s.bridge_status,
      s.raw_change_24h_pct,s.direction_normalized_move_pct,s.scanner_direction,
      s.direction_1h,s.direction_4h,s.direction_12h,s.direction_1d,s.liquidity_state,s.opportunity_timing,s.candidate_quality_status,
      s.blockers,
      coalesce(s.evidence,'{}'::jsonb) || jsonb_build_object(
        'frozen_from_bridge_at_utc',clock_timestamp(),
        'source_bridge_model_version',s.model_version,
        'geometry_valid_for_signature_direction',s.geometry_ok,
        'exact_t0_t1_t2_claim_permitted',false
      ),
      'EXACT_T0_T1_T2_NOT_CAPTURED',false,false,false,
      'big-mover-money-scorecard-v0.1',true,false
    from src s
    on conflict(source_bridge_id) do nothing
    returning 1
  ) select count(*) into v_candidates from ins;

  with ins as (
    insert into public.alpha_hunter_big_mover_money_scorecard_outcomes(
      outcome_id,scorecard_id,horizon_hours,horizon_due_at_utc,
      evaluation_status,realistic_net_r_status,confirmation_tax_status,
      t0_path_result,t1_path_result,t2_path_result,stage_outcome_status,
      evidence,shadow_only,trade_permission
    )
    select
      md5('big-mover-money-scorecard-outcome-v0.1|'||c.scorecard_id||'|'||h.h::text),
      c.scorecard_id,h.h,c.candidate_at_utc + make_interval(hours=>h.h),
      'PENDING','UNVERIFIED_EXECUTION_COST_MODEL','NOT_LINKED',
      'NOT_EVALUABLE','NOT_EVALUABLE','NOT_EVALUABLE','EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE',
      jsonb_build_object('measurement_source','BITGET_PUBLIC_V3_3M_CANDLES','exact_stage_claim_permitted',false),
      true,false
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    cross join (values(1),(4),(12),(24)) h(h)
    on conflict(scorecard_id,horizon_hours) do nothing
    returning 1
  ) select count(*) into v_outcomes from ins;

  return jsonb_build_object(
    'mode','BIG_MOVER_FORWARD_MONEY_SCORECARD_SEED',
    'candidates_seeded',v_candidates,
    'outcomes_seeded',v_outcomes,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_seed_big_mover_money_scorecard() from public, anon, authenticated;
grant execute on function private.alpha_hunter_seed_big_mover_money_scorecard() to service_role;

create or replace function private.alpha_hunter_run_big_mover_money_scorecard()
returns jsonb
language plpgsql
security definer
set search_path = public, private, extensions
as $$
declare
  r record;
  v_seed jsonb;
  v_url text;
  v_status integer;
  v_content text;
  v_payload jsonb;
  v_candle_count integer;
  v_first_ts timestamptz;
  v_last_ts timestamptz;
  v_max_high double precision;
  v_min_low double precision;
  v_close double precision;
  v_first_stop timestamptz;
  v_first_target timestamptz;
  v_mfe double precision;
  v_mae double precision;
  v_dir_close_return double precision;
  v_stop_hit boolean;
  v_target_hit boolean;
  v_path text;
  v_path_r double precision;
  v_remaining_r double precision;
  v_candidate_outcome text;
  v_episode text;
  v_detection_rr double precision;
  v_emerging_rr double precision;
  v_confirmed_rr double precision;
  v_confirmation_tax double precision;
  v_confirmation_status text;
  v_eval_status text;
  v_processed integer := 0;
  v_evaluated integer := 0;
  v_ambiguous integer := 0;
  v_insufficient integer := 0;
  v_retry integer := 0;
  v_err text;
begin
  v_seed := private.alpha_hunter_seed_big_mover_money_scorecard();

  for r in
    select o.*,c.symbol,c.direction,c.candidate_at_utc,c.candidate_entry,c.stop_price,c.target_price,
           c.geometry_valid,c.risk_distance_abs,c.initial_remaining_r
    from public.alpha_hunter_big_mover_money_scorecard_outcomes o
    join public.alpha_hunter_big_mover_money_scorecard_candidates c using(scorecard_id)
    where o.horizon_due_at_utc <= clock_timestamp()
      and o.evaluation_status in ('PENDING','RETRYABLE_ERROR')
      and o.evaluation_attempts < 3
    order by o.horizon_due_at_utc,o.created_at
    limit 80
  loop
    v_processed := v_processed + 1;
    v_err := null;
    v_eval_status := null;
    v_episode := null;
    v_detection_rr := null;
    v_emerging_rr := null;
    v_confirmed_rr := null;
    v_confirmation_tax := null;
    v_confirmation_status := 'NOT_LINKED';

    begin
      if r.candidate_entry is null or r.candidate_entry <= 0 then
        update public.alpha_hunter_big_mover_money_scorecard_outcomes
        set evaluation_status='DATA_INSUFFICIENT',evaluation_attempts=evaluation_attempts+1,
            evaluated_at_utc=clock_timestamp(),last_error='CANDIDATE_ENTRY_MISSING_OR_INVALID',
            evidence=evidence||jsonb_build_object('scorecard_blocker','CANDIDATE_ENTRY_MISSING_OR_INVALID'),
            updated_at=clock_timestamp(),shadow_only=true,trade_permission=false
        where outcome_id=r.outcome_id;
        v_insufficient := v_insufficient + 1;
        continue;
      end if;

      if r.symbol !~ '^[A-Z0-9]+USDT$' then
        update public.alpha_hunter_big_mover_money_scorecard_outcomes
        set evaluation_status='DATA_INSUFFICIENT',evaluation_attempts=evaluation_attempts+1,
            evaluated_at_utc=clock_timestamp(),last_error='SYMBOL_NOT_URL_SAFE_FOR_DB_HTTP',
            evidence=evidence||jsonb_build_object('scorecard_blocker','SYMBOL_NOT_URL_SAFE_FOR_DB_HTTP'),
            updated_at=clock_timestamp(),shadow_only=true,trade_permission=false
        where outcome_id=r.outcome_id;
        v_insufficient := v_insufficient + 1;
        continue;
      end if;

      v_url := format(
        'https://api.bitget.com/api/v3/market/candles?category=USDT-FUTURES&symbol=%s&interval=3m&startTime=%s&endTime=%s&limit=1000',
        r.symbol,
        floor(extract(epoch from r.candidate_at_utc)*1000)::bigint,
        floor(extract(epoch from r.horizon_due_at_utc)*1000)::bigint
      );

      select (x).status,(x).content into v_status,v_content
      from (select extensions.http_get(v_url) as x) q;

      if v_status<>200 then
        raise exception 'Bitget candle HTTP status %',v_status;
      end if;
      v_payload := v_content::jsonb;
      if coalesce(v_payload->>'code','')<>'00000' then
        raise exception 'Bitget candle payload code %',v_payload->>'code';
      end if;

      with raw as (
        select value as bar from jsonb_array_elements(coalesce(v_payload->'data','[]'::jsonb))
      ), candles as (
        select
          to_timestamp((bar->>0)::double precision/1000.0) as ts,
          (bar->>1)::double precision as open_price,
          (bar->>2)::double precision as high_price,
          (bar->>3)::double precision as low_price,
          (bar->>4)::double precision as close_price
        from raw
        where (bar->>0) ~ '^[0-9]+$'
          and (bar->>1) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>2) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>3) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
          and (bar->>4) ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      ), w as (
        select * from candles
        where ts >= r.candidate_at_utc and ts <= r.horizon_due_at_utc
      )
      select
        count(*)::integer,min(ts),max(ts),max(high_price),min(low_price),
        (array_agg(close_price order by ts desc))[1],
        min(ts) filter(where r.geometry_valid and ((r.direction='LONG' and low_price<=r.stop_price) or (r.direction='SHORT' and high_price>=r.stop_price))),
        min(ts) filter(where r.geometry_valid and ((r.direction='LONG' and high_price>=r.target_price) or (r.direction='SHORT' and low_price<=r.target_price)))
      into v_candle_count,v_first_ts,v_last_ts,v_max_high,v_min_low,v_close,v_first_stop,v_first_target
      from w;

      if coalesce(v_candle_count,0)=0 or v_close is null then
        if r.evaluation_attempts < 2 then
          v_eval_status := 'RETRYABLE_ERROR';
          v_retry := v_retry + 1;
        else
          v_eval_status := 'DATA_INSUFFICIENT';
          v_insufficient := v_insufficient + 1;
        end if;
        update public.alpha_hunter_big_mover_money_scorecard_outcomes
        set evaluation_status=v_eval_status,evaluation_attempts=evaluation_attempts+1,
            evaluated_at_utc=clock_timestamp(),last_error='NO_FINISHED_3M_CANDLES_IN_HORIZON',
            evidence=evidence||jsonb_build_object('scorecard_blocker','NO_FINISHED_3M_CANDLES_IN_HORIZON'),
            updated_at=clock_timestamp(),shadow_only=true,trade_permission=false
        where outcome_id=r.outcome_id;
        continue;
      end if;

      if r.direction='LONG' then
        v_mfe := (v_max_high-r.candidate_entry)/r.candidate_entry*100.0;
        v_mae := (r.candidate_entry-v_min_low)/r.candidate_entry*100.0;
        v_dir_close_return := (v_close-r.candidate_entry)/r.candidate_entry*100.0;
      else
        v_mfe := (r.candidate_entry-v_min_low)/r.candidate_entry*100.0;
        v_mae := (v_max_high-r.candidate_entry)/r.candidate_entry*100.0;
        v_dir_close_return := (r.candidate_entry-v_close)/r.candidate_entry*100.0;
      end if;
      v_mfe := greatest(0.0,v_mfe);
      v_mae := greatest(0.0,v_mae);
      v_stop_hit := case when r.geometry_valid then v_first_stop is not null else null end;
      v_target_hit := case when r.geometry_valid then v_first_target is not null else null end;

      if not r.geometry_valid then
        v_path := 'GEOMETRY_NOT_EVALUABLE';
      elsif v_first_stop is not null and v_first_target is not null and v_first_stop=v_first_target then
        v_path := 'BOTH_SAME_3M_CANDLE_AMBIGUOUS';
      elsif v_first_stop is not null and (v_first_target is null or v_first_stop<v_first_target) then
        v_path := 'STOP_FIRST';
      elsif v_first_target is not null and (v_first_stop is null or v_first_target<v_first_stop) then
        v_path := 'TARGET_FIRST';
      else
        v_path := 'OPEN_AT_HORIZON';
      end if;

      v_path_r := null;
      v_remaining_r := null;
      if r.geometry_valid and r.risk_distance_abs is not null and r.risk_distance_abs>0 then
        if v_path='STOP_FIRST' then
          v_path_r := -1.0;
        elsif v_path='TARGET_FIRST' then
          v_path_r := r.initial_remaining_r;
        elsif v_path='OPEN_AT_HORIZON' then
          if r.direction='LONG' then
            v_path_r := (v_close-r.candidate_entry)/r.risk_distance_abs;
            if v_close>r.stop_price then v_remaining_r := (r.target_price-v_close)/(v_close-r.stop_price); end if;
          else
            v_path_r := (r.candidate_entry-v_close)/r.risk_distance_abs;
            if v_close<r.stop_price then v_remaining_r := (v_close-r.target_price)/(r.stop_price-v_close); end if;
          end if;
        end if;
      end if;

      v_candidate_outcome := case
        when v_path='TARGET_FIRST' then 'WIN'
        when v_path='STOP_FIRST' then 'LOSS'
        when v_path='BOTH_SAME_3M_CANDLE_AMBIGUOUS' then 'AMBIGUOUS'
        when v_path='OPEN_AT_HORIZON' then case when v_dir_close_return>0 then 'OPEN_POSITIVE' when v_dir_close_return<0 then 'OPEN_NEGATIVE' else 'OPEN_FLAT' end
        else 'NOT_EVALUABLE'
      end;

      select t.episode_id into v_episode
      from public.alpha_hunter_timing_rr_shadow t
      where t.symbol=r.symbol and t.direction=r.direction and t.phase='DETECTION'
        and t.phase_at_utc between r.candidate_at_utc-interval '2 hours' and r.candidate_at_utc+interval '2 hours'
      order by abs(extract(epoch from(t.phase_at_utc-r.candidate_at_utc)))
      limit 1;

      if v_episode is not null then
        select
          max(rr_to_structure) filter(where phase='DETECTION'),
          max(rr_to_structure) filter(where phase='EMERGING'),
          max(rr_to_structure) filter(where phase='CONFIRMED')
        into v_detection_rr,v_emerging_rr,v_confirmed_rr
        from public.alpha_hunter_timing_rr_shadow
        where episode_id=v_episode;
        if v_detection_rr is not null and v_confirmed_rr is not null then
          v_confirmation_tax := v_detection_rr-v_confirmed_rr;
          v_confirmation_status := 'MEASURED_LEGACY_PHASE_PROXY';
        else
          v_confirmation_status := 'PARTIAL_LEGACY_PHASE_EVIDENCE';
        end if;
      end if;

      v_eval_status := case when v_path='BOTH_SAME_3M_CANDLE_AMBIGUOUS' then 'AMBIGUOUS_INTRABAR' else 'EVALUATED' end;
      if v_eval_status='AMBIGUOUS_INTRABAR' then v_ambiguous := v_ambiguous+1; else v_evaluated := v_evaluated+1; end if;

      update public.alpha_hunter_big_mover_money_scorecard_outcomes
      set evaluation_status=v_eval_status,
          evaluation_attempts=evaluation_attempts+1,
          evaluated_at_utc=clock_timestamp(),
          candle_count=v_candle_count,first_candle_at_utc=v_first_ts,last_candle_at_utc=v_last_ts,
          boundary_gap_seconds=greatest(0,extract(epoch from(v_first_ts-r.candidate_at_utc))),
          evaluation_close=v_close,mfe_pct=v_mfe,mae_pct=v_mae,direction_adjusted_close_return_pct=v_dir_close_return,
          hit_3pct=(v_mfe>=3.0),hit_5pct=(v_mfe>=5.0),hit_10pct=(v_mfe>=10.0),
          stop_hit=v_stop_hit,stop_survived=case when r.geometry_valid then not coalesce(v_stop_hit,false) else null end,
          target_hit=v_target_hit,first_stop_candle_at_utc=v_first_stop,first_target_candle_at_utc=v_first_target,
          path_resolution=v_path,path_r_pre_cost=v_path_r,remaining_r=v_remaining_r,
          realistic_net_r=null,
          realistic_net_r_status=case
            when v_path='BOTH_SAME_3M_CANDLE_AMBIGUOUS' then 'PATH_AMBIGUOUS'
            when not r.geometry_valid then 'GEOMETRY_NOT_EVALUABLE'
            else 'UNVERIFIED_EXECUTION_COST_MODEL'
          end,
          legacy_episode_id=v_episode,legacy_detection_rr=v_detection_rr,legacy_emerging_rr=v_emerging_rr,legacy_confirmed_rr=v_confirmed_rr,
          confirmation_tax_r=v_confirmation_tax,confirmation_tax_status=v_confirmation_status,
          t0_path_result='NOT_EVALUABLE',t1_path_result='NOT_EVALUABLE',t2_path_result='NOT_EVALUABLE',
          stage_outcome_status='EXACT_T0_T1_T2_SNAPSHOTS_NOT_AVAILABLE',
          candidate_path_outcome=v_candidate_outcome,
          evidence=evidence||jsonb_build_object(
            'measurement_source','BITGET_PUBLIC_V3_3M_CANDLES',
            'path_resolution',v_path,
            'path_r_is_before_execution_costs',true,
            'realistic_net_r_withheld_until_verified_cost_model',true,
            't0_t1_t2_exact_outcomes_withheld_until_exact_stage_snapshots',true
          ),
          last_error=null,updated_at=clock_timestamp(),shadow_only=true,trade_permission=false
      where outcome_id=r.outcome_id;

    exception when others then
      v_err := sqlerrm;
      if r.evaluation_attempts < 2 then
        v_eval_status := 'RETRYABLE_ERROR';
        v_retry := v_retry+1;
      else
        v_eval_status := 'DATA_INSUFFICIENT';
        v_insufficient := v_insufficient+1;
      end if;
      update public.alpha_hunter_big_mover_money_scorecard_outcomes
      set evaluation_status=v_eval_status,evaluation_attempts=evaluation_attempts+1,evaluated_at_utc=clock_timestamp(),
          last_error=left(v_err,500),updated_at=clock_timestamp(),shadow_only=true,trade_permission=false
      where outcome_id=r.outcome_id;
    end;
  end loop;

  return jsonb_build_object(
    'mode','BIG_MOVER_FORWARD_MONEY_SCORECARD',
    'seed',v_seed,
    'due_rows_processed',v_processed,
    'evaluated',v_evaluated,
    'ambiguous_intrabar',v_ambiguous,
    'data_insufficient',v_insufficient,
    'retryable_errors',v_retry,
    'horizons',jsonb_build_array(1,4,12,24),
    'candle_interval','3m',
    'realistic_net_r_status','WITHHELD_UNTIL_VERIFIED_EXECUTION_COST_MODEL',
    'exact_t0_t1_t2_status','WITHHELD_UNTIL_EXACT_STAGE_SNAPSHOTS',
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_run_big_mover_money_scorecard() from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_big_mover_money_scorecard() to service_role;

do $$
begin
  if not exists(select 1 from cron.job where jobname='alpha-hunter-big-mover-money-scorecard-hourly') then
    perform cron.schedule(
      'alpha-hunter-big-mover-money-scorecard-hourly',
      '14 * * * *',
      'select private.alpha_hunter_run_big_mover_money_scorecard();'
    );
  end if;
end;
$$;
