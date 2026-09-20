-- Alpha Hunter money-entry universe liquidity binding v0.2
--
-- Verified defect in v0.1:
--   The binder required alpha_hunter_universe_hourly.selection_run_id to equal
--   the big-mover/source run_id. Those IDs belong to separate canonical
--   scanner processes and are not the same namespace.
--
-- Production evidence on 2026-09-20:
--   - big-mover source run: 4bab706820c7d44283b69377a41d004a
--   - universe selection run: 5294e884d74d39281ec2cde03c37bc78
--   - the v0.1 equality therefore returned NULL for every stage row.
--
-- Safe v0.2 rule:
--   bind only same symbol + same UTC hour + non-future universe evidence,
--   and only when that hour has exactly ONE distinct universe selection run.
--   If zero or multiple selection runs exist, return no row and remain
--   fail-closed. The selected universe observation_id / observed_at_utc /
--   selection_run_id are persisted by the existing stage writer.
--
-- Historical validation before this migration:
--   201 observed universe hours (2026-08-18 through 2026-09-20),
--   201/201 had exactly one selection_run_id per hour; 0 ambiguous hours.
--
-- p_source_run_id remains in the signature for writer compatibility and
-- provenance, but is deliberately not equated to universe selection_run_id.

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
  with candidates as (
    select
      u.observation_id,
      u.observed_at_utc,
      u.selection_run_id,
      u.liquidity_pass
    from public.alpha_hunter_universe_hourly u
    where u.symbol=upper(p_symbol)
      and u.observed_at_utc<=p_source_captured_at_utc
      and u.observed_at_utc>=date_trunc('hour',p_source_captured_at_utc)
      and u.observed_at_utc<date_trunc('hour',p_source_captured_at_utc)+interval '1 hour'
  ),
  run_guard as (
    select count(distinct selection_run_id)::integer as distinct_selection_runs
    from candidates
  )
  select
    c.observation_id,
    c.observed_at_utc,
    c.selection_run_id,
    c.liquidity_pass
  from candidates c
  cross join run_guard g
  where g.distinct_selection_runs=1
  order by c.observed_at_utc desc,c.observation_id
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
'Fail-closed universe liquidity binder v0.2: same symbol, same UTC hour, non-future, exactly one universe selection run. Big-mover source_run_id and universe selection_run_id are separate namespaces and are not equated.';
