-- Alpha Hunter P0 Money Entry parent-direction NULL fail-closed repair v0.1
-- Forward-only function correction. Does not mutate historical stage rows.
-- Fixes PostgreSQL three-valued-logic behavior where NOT NULL is NULL and
-- therefore failed to emit PARENT_*_DATA_UNAVAILABLE blockers.
-- No thresholds, READY permission, risk, leverage, or exchange path changes.

do $$
declare
  v_def text;
  v_old_12h text := 'case when not n.parent_12h_aligned then case when n.direction_12h is null or n.direction_12h=''DATA_UNAVAILABLE'' then ''PARENT_12H_DATA_UNAVAILABLE'' else ''PARENT_12H_NOT_ALIGNED'' end end';
  v_new_12h text := 'case when n.parent_12h_aligned is not true then case when n.direction_12h is null or n.direction_12h=''DATA_UNAVAILABLE'' then ''PARENT_12H_DATA_UNAVAILABLE'' else ''PARENT_12H_NOT_ALIGNED'' end end';
  v_old_1d text := 'case when not n.parent_1d_aligned then case when n.direction_1d is null or n.direction_1d=''DATA_UNAVAILABLE'' then ''PARENT_1D_DATA_UNAVAILABLE'' else ''PARENT_1D_NOT_ALIGNED'' end end';
  v_new_1d text := 'case when n.parent_1d_aligned is not true then case when n.direction_1d is null or n.direction_1d=''DATA_UNAVAILABLE'' then ''PARENT_1D_DATA_UNAVAILABLE'' else ''PARENT_1D_NOT_ALIGNED'' end end';
begin
  select pg_get_functiondef('private.alpha_hunter_capture_money_entry_stage_snapshots(text)'::regprocedure)
    into v_def;

  if v_def is null then
    raise exception 'alpha_hunter_capture_money_entry_stage_snapshots(text) not found';
  end if;
  if position(v_old_12h in v_def)=0 then
    raise exception 'expected 12H parent-direction expression not found; refusing unsafe patch';
  end if;
  if position(v_old_1d in v_def)=0 then
    raise exception 'expected 1D parent-direction expression not found; refusing unsafe patch';
  end if;

  v_def := replace(v_def,v_old_12h,v_new_12h);
  v_def := replace(v_def,v_old_1d,v_new_1d);
  v_def := replace(
    v_def,
    'money-entry-stage-single-writer-v0.3-position-conflict-bound',
    'money-entry-stage-single-writer-v0.4-parent-direction-null-failclosed'
  );

  execute v_def;
end;
$$;

-- Safety permissions remain internal/service-role only.
revoke all on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_money_entry_stage_snapshots(text) to service_role;
