-- Alpha Hunter authoritative latest test-engine view v0.3
--
-- Prefer the DB-native engine while its status is fresh. Fall back to the
-- latest persisted row only if the DB-native refresh becomes stale.
--
-- This avoids transient dashboard regression to the older GitHub/Python
-- evaluator when an ad-hoc workflow happens between DB refreshes.

create or replace view public.alpha_hunter_test_engine_latest_v01
with (security_invoker=true,security_barrier=true)
as
select *
from public.alpha_hunter_test_engine_runs_v01
order by
  case
    when engine_version='realtime-test-engine-db-v0.2'
     and evaluated_at_utc>=clock_timestamp()-interval '25 minutes'
      then 0
    else 1
  end,
  evaluated_at_utc desc
limit 1;

revoke all on public.alpha_hunter_test_engine_latest_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_test_engine_latest_v01
  to service_role;
