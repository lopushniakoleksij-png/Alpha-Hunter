-- ALPHA HUNTER: isolated candidate, not deployed and not production-approved.
-- Prepared 2026-11-07. Intended for a cloned, private PostgreSQL/Supabase database.
-- Five core evidence tables written inside ONE PostgREST RPC transaction.
-- PostgreSQL rolls back all writes and trigger side-effects if ANY statement raises.
-- Paper lifecycle and auxiliary writes are NOT part of this RPC and require a separate
-- completeness gate before claiming a complete end-to-end canonical scan.
-- Do not enable the corresponding Python feature gate until an independent DBA and
-- security reviewer verify the exact trigger graph and test failure injection.
-- SECURITY INVOKER, explicit table names; no SECURITY DEFINER / search-path escalation.

create or replace function public.alpha_hunter_commit_core_scan_v01(
  p_parent jsonb,
  p_children jsonb,
  p_signals jsonb,
  p_features jsonb,
  p_readiness jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $fn$
declare
  v_run_id text;
  v_expected integer;
  v_errors integer;
  v_parent_written integer;
  v_children_written integer;
  v_signals_written integer;
  v_features_written integer;
  v_readiness_written integer;
  v_name text;
  v_rows jsonb;
begin
  if pg_catalog.jsonb_typeof(p_parent) <> 'array'
     or pg_catalog.jsonb_typeof(p_children) <> 'array'
     or pg_catalog.jsonb_typeof(p_signals) <> 'array'
     or pg_catalog.jsonb_typeof(p_features) <> 'array'
     or pg_catalog.jsonb_typeof(p_readiness) <> 'array'
     or pg_catalog.jsonb_array_length(p_parent) <> 1 then
    raise exception 'invalid atomic scan payload arrays';
  end if;

  v_run_id := nullif(p_parent->0->>'run_id', '');
  v_expected := (p_parent->0->>'symbol_count')::integer;
  v_errors := coalesce((p_parent->0->>'error_count')::integer,0);
  if v_run_id is null or v_expected is null
     or v_expected < 0 or v_errors < 0 or v_errors > v_expected
     or pg_catalog.jsonb_array_length(p_children) <> v_expected
     or pg_catalog.jsonb_array_length(p_readiness) <> v_expected - v_errors
     or pg_catalog.jsonb_array_length(p_signals) > pg_catalog.jsonb_array_length(p_readiness)
     or pg_catalog.jsonb_array_length(p_features) > pg_catalog.jsonb_array_length(p_signals) then
    raise exception 'core scan expected row counts invalid';
  end if;

  for v_name, v_rows in
    select 'children',p_children union all
    select 'signals',p_signals union all
    select 'features',p_features union all
    select 'readiness',p_readiness
  loop
    if exists (
      select 1 from pg_catalog.jsonb_array_elements(v_rows) x
      where pg_catalog.jsonb_typeof(x) <> 'object'
         or x->>'run_id' is distinct from v_run_id
    ) then
      raise exception 'core scan run_id mismatch in %', v_name;
    end if;
  end loop;

  if (select count(distinct x->>'symbol') from pg_catalog.jsonb_array_elements(p_children) x)
       <> pg_catalog.jsonb_array_length(p_children)
    or (select count(distinct x->>'symbol') from pg_catalog.jsonb_array_elements(p_readiness) x)
       <> pg_catalog.jsonb_array_length(p_readiness)
    or (select count(distinct x->>'signal_id') from pg_catalog.jsonb_array_elements(p_signals) x)
       <> pg_catalog.jsonb_array_length(p_signals)
    or (select count(distinct x->>'signal_id') from pg_catalog.jsonb_array_elements(p_features) x)
       <> pg_catalog.jsonb_array_length(p_features) then
      raise exception 'duplicate or missing scan symbol/signal identity';
  end if;

  insert into public.alpha_hunter_snapshots (
    run_id, collected_at_utc, version, product_type, symbol_count, error_count, payload
  )
  select r.run_id, r.collected_at_utc, r.version, r.product_type, r.symbol_count, r.error_count, r.payload
  from pg_catalog.jsonb_populate_recordset(null::public.alpha_hunter_snapshots, p_parent) as r
  where true
  on conflict (run_id) do update set
    collected_at_utc = excluded.collected_at_utc,
    version = excluded.version,
    product_type = excluded.product_type,
    symbol_count = excluded.symbol_count,
    error_count = excluded.error_count,
    payload = excluded.payload;
  get diagnostics v_parent_written = row_count;
  if v_parent_written <> pg_catalog.jsonb_array_length(p_parent) then
    raise exception 'core scan write count mismatch for alpha_hunter_snapshots';
  end if;

  insert into public.alpha_hunter_symbol_snapshots (
    run_id, symbol, collected_at_utc, state, previous_state, state_changed, trade_permission, direction, reward_risk, last_price, open_interest, funding_rate, data_integrity_score, error, payload
  )
  select r.run_id, r.symbol, r.collected_at_utc, r.state, r.previous_state, r.state_changed, r.trade_permission, r.direction, r.reward_risk, r.last_price, r.open_interest, r.funding_rate, r.data_integrity_score, r.error, r.payload
  from pg_catalog.jsonb_populate_recordset(null::public.alpha_hunter_symbol_snapshots, p_children) as r
  where true
  on conflict (run_id, symbol) do update set
    collected_at_utc = excluded.collected_at_utc,
    state = excluded.state,
    previous_state = excluded.previous_state,
    state_changed = excluded.state_changed,
    trade_permission = excluded.trade_permission,
    direction = excluded.direction,
    reward_risk = excluded.reward_risk,
    last_price = excluded.last_price,
    open_interest = excluded.open_interest,
    funding_rate = excluded.funding_rate,
    data_integrity_score = excluded.data_integrity_score,
    error = excluded.error,
    payload = excluded.payload;
  get diagnostics v_children_written = row_count;
  if v_children_written <> pg_catalog.jsonb_array_length(p_children) then
    raise exception 'core scan write count mismatch for alpha_hunter_symbol_snapshots';
  end if;

  insert into public.alpha_hunter_signals (
    signal_id, run_id, symbol, detected_at_utc, state, direction, trade_permission, huge_rr_score, confidence_estimate_pct, reward_risk, entry_price, stop_loss, take_profit, reference_price, payload
  )
  select r.signal_id, r.run_id, r.symbol, r.detected_at_utc, r.state, r.direction, r.trade_permission, r.huge_rr_score, r.confidence_estimate_pct, r.reward_risk, r.entry_price, r.stop_loss, r.take_profit, r.reference_price, r.payload
  from pg_catalog.jsonb_populate_recordset(null::public.alpha_hunter_signals, p_signals) as r
  where true
  on conflict (signal_id) do update set
    run_id = excluded.run_id,
    symbol = excluded.symbol,
    detected_at_utc = excluded.detected_at_utc,
    state = excluded.state,
    direction = excluded.direction,
    trade_permission = excluded.trade_permission,
    huge_rr_score = excluded.huge_rr_score,
    confidence_estimate_pct = excluded.confidence_estimate_pct,
    reward_risk = excluded.reward_risk,
    entry_price = excluded.entry_price,
    stop_loss = excluded.stop_loss,
    take_profit = excluded.take_profit,
    reference_price = excluded.reference_price,
    payload = excluded.payload;
  get diagnostics v_signals_written = row_count;
  if v_signals_written <> pg_catalog.jsonb_array_length(p_signals) then
    raise exception 'core scan write count mismatch for alpha_hunter_signals';
  end if;

  insert into public.alpha_hunter_signal_features (
    signal_id, run_id, symbol, captured_at_utc, state, direction, trade_permission, trend_15m, trend_1h, trend_4h, btc_regime, sector, session, weekday, hour_utc, huge_rr_score, confidence_estimate_pct, reward_risk, volume_ratio, volume_expansion, volatility_pct, compression_score, funding_rate, open_interest, open_interest_change_pct, relative_strength_btc, rsi_15m, rsi_1h, rsi_4h, distance_to_support_pct, distance_to_resistance_pct, ema_alignment_15m, ema_alignment_1h, ema_alignment_4h, liquidity_state, features, source_payload
  )
  select r.signal_id, r.run_id, r.symbol, r.captured_at_utc, r.state, r.direction, r.trade_permission, r.trend_15m, r.trend_1h, r.trend_4h, r.btc_regime, r.sector, r.session, r.weekday, r.hour_utc, r.huge_rr_score, r.confidence_estimate_pct, r.reward_risk, r.volume_ratio, r.volume_expansion, r.volatility_pct, r.compression_score, r.funding_rate, r.open_interest, r.open_interest_change_pct, r.relative_strength_btc, r.rsi_15m, r.rsi_1h, r.rsi_4h, r.distance_to_support_pct, r.distance_to_resistance_pct, r.ema_alignment_15m, r.ema_alignment_1h, r.ema_alignment_4h, r.liquidity_state, r.features, r.source_payload
  from pg_catalog.jsonb_populate_recordset(null::public.alpha_hunter_signal_features, p_features) as r
  where true
  on conflict (signal_id) do update set
    run_id = excluded.run_id,
    symbol = excluded.symbol,
    captured_at_utc = excluded.captured_at_utc,
    state = excluded.state,
    direction = excluded.direction,
    trade_permission = excluded.trade_permission,
    trend_15m = excluded.trend_15m,
    trend_1h = excluded.trend_1h,
    trend_4h = excluded.trend_4h,
    btc_regime = excluded.btc_regime,
    sector = excluded.sector,
    session = excluded.session,
    weekday = excluded.weekday,
    hour_utc = excluded.hour_utc,
    huge_rr_score = excluded.huge_rr_score,
    confidence_estimate_pct = excluded.confidence_estimate_pct,
    reward_risk = excluded.reward_risk,
    volume_ratio = excluded.volume_ratio,
    volume_expansion = excluded.volume_expansion,
    volatility_pct = excluded.volatility_pct,
    compression_score = excluded.compression_score,
    funding_rate = excluded.funding_rate,
    open_interest = excluded.open_interest,
    open_interest_change_pct = excluded.open_interest_change_pct,
    relative_strength_btc = excluded.relative_strength_btc,
    rsi_15m = excluded.rsi_15m,
    rsi_1h = excluded.rsi_1h,
    rsi_4h = excluded.rsi_4h,
    distance_to_support_pct = excluded.distance_to_support_pct,
    distance_to_resistance_pct = excluded.distance_to_resistance_pct,
    ema_alignment_15m = excluded.ema_alignment_15m,
    ema_alignment_1h = excluded.ema_alignment_1h,
    ema_alignment_4h = excluded.ema_alignment_4h,
    liquidity_state = excluded.liquidity_state,
    features = excluded.features,
    source_payload = excluded.source_payload;
  get diagnostics v_features_written = row_count;
  if v_features_written <> pg_catalog.jsonb_array_length(p_features) then
    raise exception 'core scan write count mismatch for alpha_hunter_signal_features';
  end if;

  insert into public.alpha_hunter_readiness_observations_v01 (
    run_id, symbol, observed_at_utc, state, direction, trade_permission, v7_trade_ready, reference_price, entry_price, stop_loss, take_profit, reward_risk, lifecycle_id, t1_id, lifecycle_stage, archetype, capital_risk_status
  )
  select r.run_id, r.symbol, r.observed_at_utc, r.state, r.direction, r.trade_permission, r.v7_trade_ready, r.reference_price, r.entry_price, r.stop_loss, r.take_profit, r.reward_risk, r.lifecycle_id, r.t1_id, r.lifecycle_stage, r.archetype, r.capital_risk_status
  from pg_catalog.jsonb_populate_recordset(null::public.alpha_hunter_readiness_observations_v01, p_readiness) as r
  where true
  on conflict (run_id, symbol) do update set
    observed_at_utc = excluded.observed_at_utc,
    state = excluded.state,
    direction = excluded.direction,
    trade_permission = excluded.trade_permission,
    v7_trade_ready = excluded.v7_trade_ready,
    reference_price = excluded.reference_price,
    entry_price = excluded.entry_price,
    stop_loss = excluded.stop_loss,
    take_profit = excluded.take_profit,
    reward_risk = excluded.reward_risk,
    lifecycle_id = excluded.lifecycle_id,
    t1_id = excluded.t1_id,
    lifecycle_stage = excluded.lifecycle_stage,
    archetype = excluded.archetype,
    capital_risk_status = excluded.capital_risk_status;
  get diagnostics v_readiness_written = row_count;
  if v_readiness_written <> pg_catalog.jsonb_array_length(p_readiness) then
    raise exception 'core scan write count mismatch for alpha_hunter_readiness_observations_v01';
  end if;

  return pg_catalog.jsonb_build_object(
    'committed', true,
    'run_id', v_run_id,
    'parent_count', v_parent_written,
    'symbol_count', v_children_written,
    'signal_count', v_signals_written,
    'feature_count', v_features_written,
    'readiness_count', v_readiness_written
  );
end;
$fn$;

-- Function EXECUTE is granted to PUBLIC by default; revoke before exposure.
revoke all on function public.alpha_hunter_commit_core_scan_v01(
  jsonb,jsonb,jsonb,jsonb,jsonb
) from public, anon, authenticated;
grant execute on function public.alpha_hunter_commit_core_scan_v01(
  jsonb,jsonb,jsonb,jsonb,jsonb
) to service_role;
