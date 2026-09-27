-- P0 phone-first execution-decision freeze API wrapper.
-- Evidence capture only. No Bitget order-write authority is introduced.
--
-- The private freeze function remains the source of truth and re-checks that
-- the selected decision is still a current prospective attribution candidate.
-- This public wrapper exists only so the Render backend can call it through
-- PostgREST using its server-side service-role credential.

create or replace function public.alpha_hunter_freeze_execution_decision_api_v01(
  p_decision_observation_id text
)
returns jsonb
language sql
security invoker
set search_path = ''
as $$
  select private.alpha_hunter_freeze_execution_decision_v01(
    p_decision_observation_id
  );
$$;

revoke all on function public.alpha_hunter_freeze_execution_decision_api_v01(text)
from public, anon, authenticated;

grant execute on function public.alpha_hunter_freeze_execution_decision_api_v01(text)
to service_role;

comment on function public.alpha_hunter_freeze_execution_decision_api_v01(text)
is 'Service-role-only wrapper for explicit phone-selected prospective decision freeze. Evidence only; trade_permission=false; order_path=NONE.';
