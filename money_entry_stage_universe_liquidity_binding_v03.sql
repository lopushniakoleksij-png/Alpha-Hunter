-- Alpha Hunter money-entry universe liquidity binding v0.3
--
-- Architecture change:
-- The canonical primary scanner now persists alpha_hunter_signals,
-- alpha_hunter_signal_features and alpha_hunter_universe_hourly under the SAME
-- canonical scanner run_id. The universe ledger also supports multiple
-- observations per UTC hour.
--
-- Therefore the old v0.2 "exactly one selection run in the hour" rule would
-- fail closed as soon as the :20/:40 canonical scans arrive.
--
-- Safe v0.3 rule:
--   bind the Money Entry source row to the exact canonical universe scan using
--   selection_run_id = p_source_run_id, same symbol, and non-future timestamp.
--   If the exact scan row is absent, return no row and remain fail-closed.
--
-- No trade, threshold, or order authority is changed.

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
set search_path=''
as $$
  select
    u.observation_id,
    u.observed_at_utc,
    u.selection_run_id,
    u.liquidity_pass
  from public.alpha_hunter_universe_hourly u
  where u.symbol=upper(p_symbol)
    and u.selection_run_id=p_source_run_id
    and u.observed_at_utc<=p_source_captured_at_utc
    and u.selection_snapshot_at_utc<=p_source_captured_at_utc
  order by u.observed_at_utc desc,u.observation_id
  limit 1;
$$;

revoke all on function private.alpha_hunter_stage_universe_liquidity(
  text,text,timestamptz
) from public,anon,authenticated;

grant execute on function private.alpha_hunter_stage_universe_liquidity(
  text,text,timestamptz
) to service_role;

comment on function private.alpha_hunter_stage_universe_liquidity(
  text,text,timestamptz
) is
'Fail-closed universe liquidity binder v0.3: exact canonical scanner run, same symbol, non-future evidence. Supports multiple immutable universe observations inside one UTC hour; never grants trade permission.';
