-- Alpha Hunter V14 watchdog control-plane semantics v0.2
--
-- Operations-only observability repair, outside the sealed V14 fingerprint.
--
-- The cloud control-plane contract treats DEGRADED as a completed chain that
-- may continue fail-closed at candidate/readiness level. FAILED means the
-- orchestration chain itself did not pass. The v0.1 watchdog incorrectly
-- collapsed both into LEGACY_CONTROL_PLANE_NOT_PASSING.
--
-- This migration changes only watchdog classification. It does not alter any
-- control-plane stage, threshold, strategy, risk gate, or trading authority.

do $outer$
declare
  v_def text;
  v_old text := $old$WHEN COALESCE(b.legacy_control_plane_status, 'MISSING'::text) = ANY (ARRAY['FAILED'::text, 'DEGRADED'::text]) THEN 'LEGACY_CONTROL_PLANE_NOT_PASSING'::text$old$;
  v_new text := $new$WHEN COALESCE(b.legacy_control_plane_status, 'MISSING'::text) = 'FAILED'::text THEN 'LEGACY_CONTROL_PLANE_NOT_PASSING'::text$new$;
begin
  select pg_get_viewdef(
    'public.alpha_hunter_v14_watchdog_status_v01'::regclass,
    true
  ) into v_def;

  if v_def is null then
    raise exception 'alpha_hunter_v14_watchdog_status_v01 not found';
  end if;

  if position(v_old in v_def)=0 then
    raise exception
      'expected v0.1 legacy-control-plane watchdog predicate not found; refusing unsafe patch';
  end if;

  v_def := replace(v_def,v_old,v_new);

  execute
    'create or replace view public.alpha_hunter_v14_watchdog_status_v01 '
    ||'with (security_invoker=true, security_barrier=true) as '
    ||v_def;
end;
$outer$;

comment on view public.alpha_hunter_v14_watchdog_status_v01 is
  'Current V14 operational watchdog. FAILED control-plane chains are warnings; '
  'DEGRADED completed chains remain represented by their specific readiness/evidence gates.';

revoke all on public.alpha_hunter_v14_watchdog_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v14_watchdog_status_v01
  to service_role;
