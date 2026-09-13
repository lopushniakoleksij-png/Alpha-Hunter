-- Alpha Hunter bridge geometry direction binding v0.1
-- Fail closed when scanner execution geometry belongs to the opposite direction.
-- Research support/resistance geometry remains diagnostics-only and is never promoted here.

create or replace function private.alpha_hunter_enforce_bridge_geometry_direction()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.scanner_direction is not null
     and new.direction is not null
     and upper(new.scanner_direction) <> upper(new.direction) then
    new.candidate_entry := null;
    new.stop_price := null;
    new.target_price := null;
    new.execution_rr := null;

    select coalesce(jsonb_agg(distinct value), '[]'::jsonb)
      into new.blockers
    from jsonb_array_elements(
      coalesce(new.blockers, '[]'::jsonb)
      || '["EXECUTION_GEOMETRY_DIRECTION_MISMATCH","EXECUTION_GEOMETRY_MISSING"]'::jsonb
    );

    if new.bridge_status = 'READY_FOR_MONEY_ENTRY_EVAL' then
      new.bridge_status := 'DATA_INSUFFICIENT';
    end if;

    new.evidence := coalesce(new.evidence, '{}'::jsonb)
      || jsonb_build_object(
        'geometry_direction_bound', false,
        'geometry_source', 'SCANNER_EXECUTION_SETUP',
        'geometry_fail_closed_reason', 'EXECUTION_GEOMETRY_DIRECTION_MISMATCH',
        'research_geometry_promoted', false,
        'trade_permission', false
      );
  else
    select coalesce(jsonb_agg(distinct value), '[]'::jsonb)
      into new.blockers
    from jsonb_array_elements(coalesce(new.blockers, '[]'::jsonb));

    if new.candidate_entry is not null
       and new.stop_price is not null
       and new.execution_rr is not null then
      new.evidence := coalesce(new.evidence, '{}'::jsonb)
        || jsonb_build_object(
          'geometry_direction_bound', true,
          'geometry_source', 'SCANNER_EXECUTION_SETUP',
          'research_geometry_promoted', false,
          'trade_permission', false
        );
    end if;
  end if;

  new.shadow_only := true;
  new.trade_permission := false;
  return new;
end;
$$;

revoke all on function private.alpha_hunter_enforce_bridge_geometry_direction() from public, anon, authenticated;
grant execute on function private.alpha_hunter_enforce_bridge_geometry_direction() to service_role;

drop trigger if exists alpha_hunter_enforce_bridge_geometry_direction on public.alpha_hunter_big_mover_money_entry_shadow;
create trigger alpha_hunter_enforce_bridge_geometry_direction
before insert or update on public.alpha_hunter_big_mover_money_entry_shadow
for each row execute function private.alpha_hunter_enforce_bridge_geometry_direction();
