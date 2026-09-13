-- Alpha Hunter geometry diagnostics v0.1
-- Shadow-only observability for the measured EXECUTION_GEOMETRY_MISSING blocker.
-- This migration does not alter execution permission, thresholds, costs, risk policy, or order routing.

create table if not exists public.alpha_hunter_geometry_diagnostics (
  diagnostic_id text primary key,
  run_id text not null,
  source_signal_id text,
  captured_at_utc timestamptz not null,
  symbol text not null,
  candidate_direction text not null check (candidate_direction in ('LONG','SHORT')),
  scanner_direction text,
  explicit_entry double precision,
  explicit_stop double precision,
  explicit_target double precision,
  explicit_rr double precision,
  support_price double precision,
  resistance_price double precision,
  research_stop double precision,
  research_target double precision,
  research_rr double precision,
  explicit_geometry_complete boolean not null,
  research_geometry_recoverable boolean not null,
  classification text not null,
  evidence jsonb not null default '{}'::jsonb,
  model_version text not null default 'geometry-diagnostics-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default now()
);

alter table public.alpha_hunter_geometry_diagnostics enable row level security;
revoke all on table public.alpha_hunter_geometry_diagnostics from public, anon, authenticated;
grant select, insert on table public.alpha_hunter_geometry_diagnostics to service_role;

drop trigger if exists alpha_hunter_geometry_diagnostics_append_only on public.alpha_hunter_geometry_diagnostics;
create trigger alpha_hunter_geometry_diagnostics_append_only
before update or delete on public.alpha_hunter_geometry_diagnostics
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_capture_geometry_diagnostics()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_run_id text;
  v_inserted integer:=0;
  v_counts jsonb:='{}'::jsonb;
begin
  select b.run_id into v_run_id
  from public.alpha_hunter_big_mover_money_entry_shadow b
  order by b.captured_at_utc desc limit 1;
  if v_run_id is null then
    return jsonb_build_object('status','DATA_INSUFFICIENT','blocker','NO_BRIDGE_RUN','shadow_only',true,'trade_permission',false);
  end if;

  with bridge as (
    select distinct on (b.symbol,b.direction) b.*
    from public.alpha_hunter_big_mover_money_entry_shadow b
    where b.run_id=v_run_id
    order by b.symbol,b.direction,b.updated_at desc
  ), src as (
    select b.*, sf.signal_id, sf.source_payload,
      case when (sf.source_payload->>'support') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' then (sf.source_payload->>'support')::double precision end as support_price,
      case when (sf.source_payload->>'resistance') ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' then (sf.source_payload->>'resistance')::double precision end as resistance_price
    from bridge b
    left join lateral (
      select s.signal_id,s.source_payload
      from public.alpha_hunter_signal_features s
      where s.run_id=b.run_id and s.symbol=b.symbol
      order by s.captured_at_utc desc limit 1
    ) sf on true
  ), geom as (
    select s.*,
      case when s.direction='LONG' then s.support_price else s.resistance_price end as research_stop,
      case when s.direction='LONG' then s.resistance_price else s.support_price end as research_target
    from src s
  ), calc as (
    select g.*,
      (g.candidate_entry is not null and g.stop_price is not null and g.target_price is not null and g.execution_rr is not null and
       ((g.direction='LONG' and g.stop_price<g.candidate_entry and g.target_price>g.candidate_entry) or
        (g.direction='SHORT' and g.stop_price>g.candidate_entry and g.target_price<g.candidate_entry))) as explicit_complete,
      (g.candidate_entry is not null and g.research_stop is not null and g.research_target is not null and
       ((g.direction='LONG' and g.research_stop<g.candidate_entry and g.research_target>g.candidate_entry) or
        (g.direction='SHORT' and g.research_stop>g.candidate_entry and g.research_target<g.candidate_entry))) as research_recoverable,
      case when g.candidate_entry is not null and g.research_stop is not null and g.research_target is not null and abs(g.candidate_entry-g.research_stop)>0
        then abs(g.research_target-g.candidate_entry)/abs(g.candidate_entry-g.research_stop) end as research_rr_calc
    from geom g
  ), ins as (
    insert into public.alpha_hunter_geometry_diagnostics(
      diagnostic_id,run_id,source_signal_id,captured_at_utc,symbol,candidate_direction,scanner_direction,
      explicit_entry,explicit_stop,explicit_target,explicit_rr,support_price,resistance_price,research_stop,research_target,research_rr,
      explicit_geometry_complete,research_geometry_recoverable,classification,evidence,shadow_only,trade_permission
    )
    select md5('geometry-diagnostics-v0.1|'||c.run_id||'|'||c.symbol||'|'||c.direction),c.run_id,c.signal_id,c.captured_at_utc,c.symbol,c.direction,c.scanner_direction,
      c.candidate_entry,c.stop_price,c.target_price,c.execution_rr,c.support_price,c.resistance_price,c.research_stop,c.research_target,c.research_rr_calc,
      c.explicit_complete,c.research_recoverable,
      case
        when c.explicit_complete then 'EXPLICIT_EXECUTION_GEOMETRY'
        when c.research_recoverable then 'RESEARCH_SR_GEOMETRY_RECOVERABLE'
        when c.candidate_entry is null then 'ENTRY_MISSING'
        when c.support_price is null or c.resistance_price is null then 'SUPPORT_RESISTANCE_MISSING'
        else 'SUPPORT_RESISTANCE_DIRECTION_INVALID'
      end,
      jsonb_build_object('purpose','diagnose geometry coverage only','research_geometry_is_not_execution_permission',true,'thresholds_invented',false,'source_bridge_id',c.bridge_id,'source_bridge_status',c.bridge_status),true,false
    from calc c
    on conflict(diagnostic_id) do nothing
    returning classification
  ) select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(classification,n),'{}'::jsonb) into v_counts
  from (select classification,count(*)::integer n from public.alpha_hunter_geometry_diagnostics where run_id=v_run_id group by classification) q;

  return jsonb_build_object('status','CAPTURED','run_id',v_run_id,'rows_inserted',v_inserted,'classification_counts',v_counts,'research_geometry_is_not_execution_permission',true,'shadow_only',true,'trade_permission',false);
end;
$$;
revoke all on function private.alpha_hunter_capture_geometry_diagnostics() from public, anon, authenticated;
grant execute on function private.alpha_hunter_capture_geometry_diagnostics() to service_role;
