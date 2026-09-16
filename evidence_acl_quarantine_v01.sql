-- Alpha Hunter evidence ACL quarantine v0.1
--
-- Purpose:
--   Repair the live append-only boundary before starting a scientific holdout.
--   The project-level public-schema default ACL currently gives service_role
--   TRUNCATE/UPDATE/DELETE even where migrations later grant only SELECT.
--
-- Scope:
--   * immutable research evidence only;
--   * fail-closed quarantine of PR #19's now-merged recorder until it uses a
--     stable episode ID;
--   * no scanner, cron, threshold, portfolio-risk, execution, or order changes.

do $$
declare
  v_table text;
begin
  foreach v_table in array array[
    'alpha_hunter_early_mover_cohort',
    'alpha_hunter_money_entry_candidate_episodes',
    'alpha_hunter_money_entry_stage_progressions',
    'alpha_hunter_money_entry_progression_anomalies'
  ]
  loop
    if pg_catalog.to_regclass('public.' || v_table) is not null then
      execute pg_catalog.format(
        'revoke all on table public.%I from service_role',
        v_table
      );
      execute pg_catalog.format(
        'grant select on table public.%I to service_role',
        v_table
      );
    end if;
  end loop;

  -- PR #19 is now in main. Its symbol+direction lookup can associate unrelated
  -- opportunities. Preserve the empty ledger, remove direct entry points, and
  -- stop future trigger use as an explicit fail-closed hotfix.
  if pg_catalog.to_regprocedure(
       'private.alpha_hunter_record_money_entry_progression(text)'
     ) is not null then
    execute 'revoke all on function private.alpha_hunter_record_money_entry_progression(text) from service_role';
  end if;

  if pg_catalog.to_regprocedure(
       'private.alpha_hunter_backfill_money_entry_progressions()'
     ) is not null then
    execute 'revoke all on function private.alpha_hunter_backfill_money_entry_progressions() from service_role';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_trigger t
    where t.tgrelid = pg_catalog.to_regclass(
            'public.alpha_hunter_portfolio_risk_assessments'
          )
      and t.tgname = 'trg_ah_after_portfolio_risk_capture_progression'
      and not t.tgisinternal
  ) then
    execute 'alter table public.alpha_hunter_portfolio_risk_assessments disable trigger trg_ah_after_portfolio_risk_capture_progression';
  end if;
end;
$$;
