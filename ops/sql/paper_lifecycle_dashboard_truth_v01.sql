begin;

-- Alpha Hunter paper evidence truth surface v0.1.
-- Observability only. Separates execution-lifecycle evidence from the sealed
-- 24H profitability sample so the dashboard never conflates the two.

create or replace view public.alpha_hunter_paper_lifecycle_status_v05
with (security_invoker=true,security_barrier=true)
as
select
  (select count(*)::integer
   from public.alpha_hunter_paper_completed_trades_v04) as raw_completed_trades,
  (select count(*)::integer
   from public.alpha_hunter_paper_completed_trades_valid_v05) as valid_completed_trades,
  (select count(*)::integer
   from public.alpha_hunter_paper_exit_quarantine_v04
   where reason='INVALID_ENTRY_GEOMETRY_PRE_FIX') as invalid_geometry_quarantined,
  (select count(*)::integer
   from public.alpha_hunter_paper_protection_open_v04) as active_valid_positions,
  (select max(closed_at_utc)
   from public.alpha_hunter_paper_completed_trades_valid_v05)
     as latest_valid_close_at_utc,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path;

revoke all on public.alpha_hunter_paper_lifecycle_status_v05
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_lifecycle_status_v05
  to service_role;

commit;
