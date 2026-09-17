-- Alpha Hunter P0 Money Entry stage -> canonical universe liquidity binding v0.1
-- Forward-only. No historical stage mutation/backfill. No new scanner. No thresholds.
-- Applied after money_entry_stage_single_writer.sql.

create or replace function private.alpha_hunter_stage_universe_liquidity(
  p_symbol text,
  p_source_run_id text,
  p_source_captured_at_utc timestamptz
)
returns table(
  observation_id text,
  observed_at_utc timestamptz,
  selection_run_id text,
  liquidity_pass boolean
)
language sql
stable
security definer
set search_path = ''
as $$
  select u.observation_id,u.observed_at_utc,u.selection_run_id,u.liquidity_pass
  from public.alpha_hunter_universe_hourly u
  where u.symbol=upper(p_symbol)
    and u.selection_run_id=p_source_run_id
    and u.observed_at_utc<=p_source_captured_at_utc
    and u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)
  order by u.observed_at_utc desc
  limit 1;
$$;
revoke all on function private.alpha_hunter_stage_universe_liquidity(text,text,timestamptz) from public,anon,authenticated;
grant execute on function private.alpha_hunter_stage_universe_liquidity(text,text,timestamptz) to service_role;

-- Contract for the single stage writer:
-- In its src/normalized pipeline, LEFT JOIN LATERAL the function above using
-- (b.symbol,b.run_id,b.captured_at_utc). `liquidity_ok` MUST be sourced only as:
--   ul.liquidity_pass
-- and evidence MUST persist the immutable binding:
--   universe_observation_id, universe_observed_at_utc, universe_selection_run_id.
-- If no exact same-run, same-hour, non-future universe observation exists,
-- liquidity_ok remains NULL and the existing LIQUIDITY_PASS_NOT_CAPTURED blocker
-- keeps the observation fail-closed. Never fall back to another run/hour or
-- source_payload, because that would permit hindsight/cross-run evidence binding.
-- Existing alpha_hunter_money_entry_stage_snapshots rows remain append-only and
-- are intentionally untouched.