-- Alpha Hunter Money Entry progression trigger restoration v0.1
--
-- Root cause:
--   trg_ah_after_portfolio_risk_capture_progression exists but is DISABLED
--   in production, leaving the append-only T0/T1/T2 ledger empty.
--
-- Safety:
--   * forward-only restoration;
--   * no historical backfill;
--   * no threshold activation;
--   * no trade/order authority;
--   * current DATA_INSUFFICIENT rows remain ignored by the existing writer.
--
-- This script intentionally does NOT call
-- private.alpha_hunter_backfill_money_entry_progressions().

do $block$
declare
  v_exists boolean;
  v_enabled "char";
begin
  select true,t.tgenabled
    into v_exists,v_enabled
  from pg_trigger t
  where t.tgname='trg_ah_after_portfolio_risk_capture_progression'
    and t.tgrelid='public.alpha_hunter_portfolio_risk_assessments'::regclass
    and not t.tgisinternal
  limit 1;

  if coalesce(v_exists,false) is not true then
    raise exception 'required progression trigger is missing';
  end if;

  if to_regprocedure(
       'private.alpha_hunter_after_portfolio_risk_capture_progression()'
     ) is null
  then
    raise exception 'required progression trigger function is missing';
  end if;

  alter table public.alpha_hunter_portfolio_risk_assessments
    enable trigger trg_ah_after_portfolio_risk_capture_progression;
end;
$block$;

create or replace view private.alpha_hunter_money_entry_progression_trigger_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  t.tgname as trigger_name,
  t.tgenabled,
  (t.tgenabled<>'D') as trigger_enabled,
  c.relname as source_table,
  p.proname as trigger_function,
  (select count(*) from public.alpha_hunter_money_entry_candidate_episodes) as episode_rows,
  (select count(*) from public.alpha_hunter_money_entry_stage_progressions) as progression_rows,
  (select count(*) from public.alpha_hunter_money_entry_progression_anomalies) as anomaly_rows,
  true as forward_only,
  false as historical_backfill_permitted,
  true as shadow_only,
  false as trade_permission,
  false as threshold_activation_permitted,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from pg_trigger t
join pg_class c on c.oid=t.tgrelid
join pg_proc p on p.oid=t.tgfoid
where t.tgname='trg_ah_after_portfolio_risk_capture_progression'
  and t.tgrelid='public.alpha_hunter_portfolio_risk_assessments'::regclass
  and not t.tgisinternal;

revoke all on private.alpha_hunter_money_entry_progression_trigger_status_v01
from public,anon,authenticated,service_role;
grant select on private.alpha_hunter_money_entry_progression_trigger_status_v01
to service_role;

-- No call to alpha_hunter_backfill_money_entry_progressions is permitted here.
