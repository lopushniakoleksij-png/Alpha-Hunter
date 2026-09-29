-- Alpha Hunter storage-pressure view security hardening v0.1
--
-- Ops-only permission fix. No trading/scientific logic changes.

alter view public.alpha_hunter_storage_pressure_v01
  set (security_invoker=true,security_barrier=true);

revoke all on public.alpha_hunter_storage_pressure_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_storage_pressure_v01
  to service_role;
