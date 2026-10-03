-- Alpha Hunter shadow decision-time quote ledger v0.1
--
-- Purpose:
--   Freeze the decision-time top-of-book context for every future
--   SHADOW_CANDIDATE observation using the already persisted canonical
--   Bitget public microstructure snapshot.
--
-- Scientific boundary:
--   - this is quote/spread evidence, not an executed fill;
--   - quote-cross price is a top-of-book proxy only;
--   - it does not measure latency, queue position, market impact, adverse
--     selection, or realized slippage;
--   - it cannot activate a realistic net execution-cost model by itself.
--
-- Safety:
--   read-only market evidence; no order authority.

create table if not exists public.alpha_hunter_shadow_decision_quotes_v01 (
  observation_id text primary key
    references public.alpha_hunter_strategy_observations_v01(observation_id),
  strategy_instance_id text,
  run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  action text not null,
  observed_at_utc timestamptz not null,
  captured_at_utc timestamptz not null default clock_timestamp(),

  run_source text,
  git_commit text,
  config_sha256 text,

  reference_price double precision,
  planned_entry_price double precision,
  best_bid double precision,
  best_ask double precision,
  midpoint double precision,
  spread_pct double precision,
  entry_cross_price double precision,
  entry_cross_half_spread_bps double precision,
  planned_entry_directional_distance_bps double precision,

  depth_imbalance double precision,
  trade_imbalance double precision,
  source_skew_ms bigint,
  order_book_exchange_timestamp_ms bigint,
  newest_trade_timestamp_ms bigint,

  microstructure_status text,
  quote_status text not null,
  quote_complete boolean not null default false,

  evidence_source text not null
    default 'CANONICAL_SYMBOL_SNAPSHOT_MICROSTRUCTURE',
  prospective_capture boolean not null default true
    check(prospective_capture=true),
  slippage_measured boolean not null default false
    check(slippage_measured=false),
  fill_claim_permitted boolean not null default false
    check(fill_claim_permitted=false),
  cost_model_activation_permitted boolean not null default false
    check(cost_model_activation_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false
    check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

create index if not exists idx_ah_shadow_quote_time_v01
  on public.alpha_hunter_shadow_decision_quotes_v01(observed_at_utc desc);

create index if not exists idx_ah_shadow_quote_source_time_v01
  on public.alpha_hunter_shadow_decision_quotes_v01(
    run_source,observed_at_utc desc
  );

create index if not exists idx_ah_shadow_quote_instance_v01
  on public.alpha_hunter_shadow_decision_quotes_v01(strategy_instance_id);

alter table public.alpha_hunter_shadow_decision_quotes_v01
  enable row level security;

revoke all on public.alpha_hunter_shadow_decision_quotes_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_shadow_decision_quotes_v01
  to service_role;

drop trigger if exists trg_ah_shadow_decision_quotes_append_only_v01
  on public.alpha_hunter_shadow_decision_quotes_v01;

create trigger trg_ah_shadow_decision_quotes_append_only_v01
before update or delete on public.alpha_hunter_shadow_decision_quotes_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_capture_shadow_decision_quote_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $$
declare
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_symbol public.alpha_hunter_symbol_snapshots%rowtype;
  v_book jsonb;
  v_recent jsonb;
  v_bid double precision;
  v_ask double precision;
  v_mid double precision;
  v_entry_cross double precision;
  v_half_spread_bps double precision;
  v_entry_distance_bps double precision;
  v_complete boolean;
  v_status text;
begin
  if new.status<>'SHADOW_CANDIDATE'
     or new.direction not in ('LONG','SHORT')
  then
    return new;
  end if;

  select p.* into v_parent
  from public.alpha_hunter_snapshots p
  where p.run_id=new.run_id
  limit 1;

  select s.* into v_symbol
  from public.alpha_hunter_symbol_snapshots s
  where s.run_id=new.run_id
    and s.symbol=new.symbol
  limit 1;

  v_book := v_symbol.payload->'microstructure'->'order_book';
  v_recent := v_symbol.payload->'microstructure'->'recent_trades';

  v_bid := nullif(v_book->>'best_bid','')::double precision;
  v_ask := nullif(v_book->>'best_ask','')::double precision;
  v_mid := nullif(v_book->>'midpoint','')::double precision;

  v_complete := (
    v_parent.run_id is not null
    and v_symbol.run_id is not null
    and coalesce(v_symbol.payload->'microstructure'->>'status','')='COMPLETE'
    and v_bid is not null
    and v_ask is not null
    and v_mid is not null
    and v_mid>0
    and v_ask>=v_bid
  );

  if v_complete then
    v_entry_cross := case
      when new.direction='LONG' then v_ask
      else v_bid
    end;

    v_half_spread_bps := case
      when new.direction='LONG'
        then (v_ask-v_mid)/v_mid*10000.0
      else (v_mid-v_bid)/v_mid*10000.0
    end;

    v_entry_distance_bps := case
      when new.entry_price is null then null
      when new.direction='LONG'
        then (new.entry_price-v_mid)/v_mid*10000.0
      else (v_mid-new.entry_price)/v_mid*10000.0
    end;

    v_status := 'COMPLETE_DECISION_TIME_QUOTE';
  else
    v_status := 'INCOMPLETE_DECISION_TIME_QUOTE';
  end if;

  insert into public.alpha_hunter_shadow_decision_quotes_v01(
    observation_id,
    strategy_instance_id,
    run_id,
    symbol,
    strategy_id,
    direction,
    action,
    observed_at_utc,
    run_source,
    git_commit,
    config_sha256,
    reference_price,
    planned_entry_price,
    best_bid,
    best_ask,
    midpoint,
    spread_pct,
    entry_cross_price,
    entry_cross_half_spread_bps,
    planned_entry_directional_distance_bps,
    depth_imbalance,
    trade_imbalance,
    source_skew_ms,
    order_book_exchange_timestamp_ms,
    newest_trade_timestamp_ms,
    microstructure_status,
    quote_status,
    quote_complete
  ) values (
    new.observation_id,
    new.strategy_instance_id,
    new.run_id,
    new.symbol,
    new.strategy_id,
    new.direction,
    new.action,
    new.observed_at_utc,
    v_parent.payload->'validation_identity'->>'run_source',
    v_parent.payload->'validation_identity'->>'git_commit',
    v_parent.payload->'validation_identity'->>'config_sha256',
    new.reference_price,
    new.entry_price,
    v_bid,
    v_ask,
    v_mid,
    nullif(v_book->>'spread_pct','')::double precision,
    v_entry_cross,
    v_half_spread_bps,
    v_entry_distance_bps,
    nullif(v_book->>'depth_imbalance','')::double precision,
    nullif(v_recent->>'trade_imbalance','')::double precision,
    nullif(v_symbol.payload->'microstructure'->>'source_skew_ms','')::bigint,
    nullif(v_book->>'exchange_timestamp_ms','')::bigint,
    nullif(v_recent->>'newest_trade_timestamp_ms','')::bigint,
    v_symbol.payload->'microstructure'->>'status',
    v_status,
    v_complete
  )
  on conflict(observation_id) do nothing;

  return new;
end;
$$;

revoke all on function private.alpha_hunter_capture_shadow_decision_quote_v01()
  from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_capture_shadow_decision_quote_v01
  on public.alpha_hunter_strategy_observations_v01;

create trigger trg_ah_capture_shadow_decision_quote_v01
after insert on public.alpha_hunter_strategy_observations_v01
for each row execute function private.alpha_hunter_capture_shadow_decision_quote_v01();


create or replace view public.alpha_hunter_shadow_decision_quote_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::bigint as captured_candidate_quotes,
  count(*) filter(where quote_complete)::bigint as complete_candidate_quotes,
  count(*) filter(where not quote_complete)::bigint
    as incomplete_candidate_quotes,
  count(*) filter(where action='EXECUTE_NOW')::bigint
    as execute_now_quotes,
  count(*) filter(where action='PLACE_LIMIT')::bigint
    as place_limit_quotes,
  min(observed_at_utc) as first_quote_at_utc,
  max(observed_at_utc) as latest_quote_at_utc,
  avg(entry_cross_half_spread_bps) filter(where quote_complete)
    as avg_entry_cross_half_spread_bps,
  percentile_cont(0.5) within group(
    order by entry_cross_half_spread_bps
  ) filter(where quote_complete)
    as median_entry_cross_half_spread_bps,
  percentile_cont(0.9) within group(
    order by entry_cross_half_spread_bps
  ) filter(where quote_complete)
    as p90_entry_cross_half_spread_bps,
  false as slippage_measured,
  false as fill_claim_permitted,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  'DECISION_TIME_TOP_OF_BOOK_CAPTURE_ACTIVE'::text as scientific_status,
  'MATCH_DECISION_QUOTE_TO_PROSPECTIVE_REAL_FILL_BEFORE_SLIPPAGE_CLAIM'::text
    as next_gate,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_shadow_decision_quotes_v01;

revoke all on public.alpha_hunter_shadow_decision_quote_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_shadow_decision_quote_status_v01
  to service_role;
