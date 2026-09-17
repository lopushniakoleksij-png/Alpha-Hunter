-- Alpha Hunter geometry diagnostics v0.2.2 Money Entry scope alignment
-- Forward-only function replacement. Existing v0.2.1 rows remain immutable.
-- This migration changes only diagnostic capture scope/model identity.
-- It does NOT modify the Money Entry stage writer, thresholds, READY/T0 authority,
-- risk/leverage, exchange calls, cron schedule, or trade permission.

do $$
declare
  v_def text;
  v_old_scope text := E'where b.run_id=v_run_id\n    order by b.symbol,b.direction,b.updated_at desc';
  v_new_scope text := E'where b.run_id=v_run_id\n      and b.research_status=''SHADOW_QUEUE''\n      and b.lifecycle in (''PRE_MOVER'',''IGNITION'',''EXPANSION'')\n    order by b.symbol,b.direction,b.updated_at desc';
begin
  select pg_get_functiondef('private.alpha_hunter_capture_geometry_diagnostics()'::regprocedure)
    into v_def;

  if v_def is null then
    raise exception 'geometry diagnostics function not found';
  end if;

  if position(v_old_scope in v_def)=0 then
    raise exception 'expected v0.2.1 geometry bridge scope not found; refusing unsafe replacement';
  end if;

  if position('geometry-diagnostics-v0.2.1-volatility-context' in v_def)=0 then
    raise exception 'expected v0.2.1 model identity not found; refusing unsafe replacement';
  end if;

  v_def := replace(v_def, v_old_scope, v_new_scope);
  v_def := replace(
    v_def,
    'geometry-diagnostics-v0.2.1-volatility-context',
    'geometry-diagnostics-v0.2.2-money-entry-scope-aligned'
  );

  execute v_def;
end;
$$;

revoke all on function private.alpha_hunter_capture_geometry_diagnostics() from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_geometry_diagnostics() to service_role;
