-- Alpha Hunter H2 source freshness cadence alignment v0.1
--
-- Root cause:
--   H2 requires every required source input to become available within 15 minutes
--   of source_captured_at_utc.
--
--   Current downstream cadence materializes geometry at :24, while recent source
--   rows are captured around :03-:05. Geometry-created time therefore controls
--   decision_available_at_utc at roughly +19 to +20 minutes and forces otherwise
--   eligible H2 rows into EXCLUDED_SOURCE_STALE_FOR_15M_TRIGGER.
--
-- Repair:
--   Keep ANSWER_KEY and PARENT_DIRECTION unchanged.
--   Move MONEY_ENTRY_BRIDGE from :21 -> :17.
--   Move MONEY_ENTRY_STAGE (which captures geometry) from :24 -> :18.
--   Preserve the currently deployed 6-hour H2 cadence but move H2 from :18 -> :20
--   so it runs after geometry and does not collide with the :19 missed-mover audit.
--
-- This migration changes scheduling only.
-- It does NOT change the H2 15-minute freshness contract, parent-direction rule,
-- EARLY rule, 1H timing rule, 15m acceptance rule, geometry rule, thresholds,
-- R3, trade permission, production promotion, or order routing.

create or replace view public.alpha_hunter_h2_source_freshness_status_v01
with (security_invoker=true,security_barrier=true)
as
with recent as (
  select *
  from public.alpha_hunter_h2_direction_captures_v01
  where decision_available_at_utc>=clock_timestamp()-interval '48 hours'
), by_direction as (
  select
    direction,
    count(*)::bigint as captured_rows,
    count(*) filter(
      where opportunity_timing='EARLY'
        and parent_12h_1d_aligned
        and timing_1h_aligned
        and geometry_valid
    )::bigint as pre_fresh_context_rows,
    count(*) filter(
      where opportunity_timing='EARLY'
        and parent_12h_1d_aligned
        and timing_1h_aligned
        and geometry_valid
        and source_fresh_for_15m_trigger
    )::bigint as fresh_context_rows,
    count(*) filter(
      where opportunity_timing='EARLY'
        and parent_12h_1d_aligned
        and timing_1h_aligned
        and geometry_valid
        and not source_fresh_for_15m_trigger
    )::bigint as stale_context_rows,
    percentile_cont(0.5) within group(order by source_age_seconds)
      filter(
        where opportunity_timing='EARLY'
          and parent_12h_1d_aligned
          and timing_1h_aligned
          and geometry_valid
      ) as median_source_age_seconds,
    percentile_cont(0.9) within group(order by source_age_seconds)
      filter(
        where opportunity_timing='EARLY'
          and parent_12h_1d_aligned
          and timing_1h_aligned
          and geometry_valid
      ) as p90_source_age_seconds
  from recent
  group by direction
)
select
  direction,
  captured_rows,
  pre_fresh_context_rows,
  fresh_context_rows,
  stale_context_rows,
  100.0*fresh_context_rows/nullif(pre_fresh_context_rows,0)
    as fresh_context_pct,
  median_source_age_seconds,
  p90_source_age_seconds,
  15::integer as frozen_maximum_source_age_minutes,
  case
    when pre_fresh_context_rows=0 then 'NO_ELIGIBLE_CONTEXT_IN_WINDOW'
    when fresh_context_rows=0 then 'PIPELINE_FRESHNESS_STALLED'
    when stale_context_rows>fresh_context_rows then 'FRESHNESS_DEGRADED'
    else 'FRESHNESS_PASS'
  end as freshness_status,
  false as outcome_evidence_used,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  'h2-source-freshness-status-v0.1'::text as model_version
from by_direction;

revoke all on public.alpha_hunter_h2_source_freshness_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_h2_source_freshness_status_v01
  to service_role;


do $$
declare
  v_bridge cron.job%rowtype;
  v_stage cron.job%rowtype;
  v_h2 cron.job%rowtype;
begin
  select * into v_bridge
  from cron.job
  where jobname='alpha-hunter-big-mover-money-entry-bridge-hourly';

  select * into v_stage
  from cron.job
  where jobname='alpha-hunter-money-entry-stage-hourly';

  select * into v_h2
  from cron.job
  where jobname='alpha-hunter-h2-direction-capture-hourly';

  if v_bridge.jobid is null or v_stage.jobid is null or v_h2.jobid is null then
    raise exception 'H2 cadence alignment requires bridge, money-entry-stage, and H2 jobs';
  end if;

  if v_bridge.active is not true
     or v_stage.active is not true
     or v_h2.active is not true then
    raise exception 'H2 cadence alignment refuses to modify inactive required jobs';
  end if;

  if v_bridge.command<>
      'select private.alpha_hunter_run_controlled_stage(''MONEY_ENTRY_BRIDGE'',clock_timestamp());'
     or v_stage.command<>
      'select private.alpha_hunter_run_money_entry_stage_with_geometry(clock_timestamp());'
     or v_h2.command<>
      'select private.alpha_hunter_capture_h2_direction_v01();'
  then
    raise exception 'H2 cadence alignment command contract mismatch';
  end if;

  if v_bridge.schedule not in ('21 * * * *','17 * * * *')
     or v_stage.schedule not in ('24 * * * *','18 * * * *')
     or v_h2.schedule not in ('18 * * * *','18 */6 * * *','20 */6 * * *')
  then
    raise exception 'H2 cadence alignment unexpected existing schedule';
  end if;

  perform cron.alter_job(
    job_id:=v_bridge.jobid,
    schedule:='17 * * * *'
  );

  perform cron.alter_job(
    job_id:=v_stage.jobid,
    schedule:='18 * * * *'
  );

  perform cron.alter_job(
    job_id:=v_h2.jobid,
    schedule:='20 */6 * * *'
  );
end;
$$;

-- Scheduling only: parent-direction collection stays at :16, the 15-minute H2
-- freshness contract stays frozen, and H2 remains a 6-hour capture job.
