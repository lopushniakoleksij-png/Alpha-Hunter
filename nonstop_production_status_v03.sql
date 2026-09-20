-- Alpha Hunter nonstop production status v0.1
--
-- Purpose:
--   Provide one read-only service-role surface for the standing nonstop
--   production plan. It reports continuity, safety, prospective research
--   collection, geometry feasibility, confirmation tax, anti-drift state,
--   and the single next action.
--
-- This view does not execute trades, change thresholds, read sealed outcomes,
-- mutate research protocols, or authorize production promotion.

create or replace view public.alpha_hunter_nonstop_production_status_v03
with (security_invoker=true,security_barrier=true)
as
with latest_control as (
  select c.*
  from public.alpha_hunter_control_plane_runs c
  where c.finalized_at_utc is not null
  order by c.scheduled_hour_utc desc
  limit 1
),
holdout as (
  select h.*
  from public.alpha_hunter_geometry_holdout_collection_status_v01 h
  where h.spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
  limit 1
),
geometry as (
  select g.*
  from public.alpha_hunter_geometry_feasibility_status_v01 g
  where g.cohort='SCANNER_DIRECTION_ALIGNED'
  limit 1
),
confirmation as (
  select d.*
  from public.alpha_hunter_direction_confirmation_tax_status_v01 d
  limit 1
),
h2 as (
  select h.*
  from public.alpha_hunter_h2_direction_capture_status_v01 h
  where h.spec_id='AH-DIRECTION-ARCHITECTURE-H2-CAPTURE-V01'
  limit 1
),
mover_audit as (
  select m.*
  from public.alpha_hunter_forward_missed_mover_audit_status_v01 m
  limit 1
),
stage_safety as (
  select
    count(*) filter(
      where s.shadow_only is not true
         or s.trade_permission is not false
    )::bigint as safety_violation_rows,
    max(s.source_captured_at_utc) as latest_stage_source_at_utc
  from public.alpha_hunter_money_entry_stage_snapshots s
),
jobs as (
  select
    count(*) filter(where active)::bigint as active_job_count,
    count(*) filter(
      where active
        and jobname in (
          'alpha-hunter-big-mover-shadow-hourly',
          'alpha-hunter-big-mover-parent-direction-hourly',
          'alpha-hunter-big-mover-money-entry-bridge-hourly',
          'alpha-hunter-money-entry-stage-hourly',
          'alpha-hunter-big-mover-money-scorecard-hourly',
          'alpha-hunter-execution-cost-evidence-hourly',
          'alpha-hunter-portfolio-risk-veto-hourly',
          'alpha-hunter-control-plane-finalize-hourly',
          'alpha-hunter-signal-quality-forward-audit-hourly',
          'alpha-hunter-geometry-holdout-sealed-hourly',
          'alpha-hunter-execution-markouts-hourly',
          'alpha-hunter-h2-direction-capture-hourly',
          'alpha-hunter-forward-missed-mover-audit-hourly'
        )
    )::bigint as required_active_job_count
  from cron.job
),
assembled as (
  select
    c.control_run_id,
    c.scheduled_hour_utc as latest_finalized_hour_utc,
    c.finalized_at_utc as latest_finalized_at_utc,
    c.overall_status as control_plane_status,
    c.failed_stage_count,
    c.degraded_stage_count,
    c.passed_stage_count,
    c.data_freshness_status,
    c.safety_status,
    c.production_execution_enabled,
    c.research_trade_permission,

    j.active_job_count,
    j.required_active_job_count,

    h.scientific_status as holdout_status,
    h.captured as holdout_captured,
    h.eligible as holdout_eligible,
    h.excluded as holdout_excluded,
    h.capture_failures as holdout_capture_failures,
    h.capture_sample_gate_met as holdout_sample_gate_met,
    h.primary_results_exposed as holdout_primary_results_exposed,
    h.production_promotion_permitted as holdout_production_promotion_permitted,

    g.observations as aligned_geometry_observations,
    g.rr5_feasible_observations as aligned_rr5_feasible_observations,
    g.rr5_feasible_pct as aligned_rr5_feasible_pct,
    g.median_current_rr as aligned_median_rr,
    g.median_range_consumed_pct as aligned_median_range_consumed_pct,
    g.threshold_change_permitted as geometry_threshold_change_permitted,
    g.production_promotion_permitted as geometry_production_promotion_permitted,
    g.sealed_holdout_outcome_read as geometry_sealed_outcome_read,

    d.early_episode_anchors,
    d.paired_scanner_confirmations,
    d.no_scanner_alignment_within_24h,
    d.early_rr5_episodes,
    d.scanner_rr5_episodes,
    d.lost_rr5_after_confirmation,
    d.gained_rr5_after_confirmation,
    d.median_confirmation_delay_hours,
    d.median_confirmation_price_tax_pct,
    d.median_early_rr,
    d.median_scanner_rr,
    d.outcome_evidence_used as confirmation_outcome_evidence_used,
    d.sealed_holdout_outcome_read as confirmation_sealed_outcome_read,
    d.t0_authorized,
    d.threshold_change_permitted as confirmation_threshold_change_permitted,
    d.production_promotion_permitted as confirmation_production_promotion_permitted,

    h2s.scientific_status as h2_scientific_status,
    h2s.captured_rows as h2_captured_rows,
    h2s.h2_context_rows,
    h2s.h2_triggered_rows,
    h2s.legacy_aligned_rows as h2_legacy_aligned_rows,
    h2s.anchor_prices_resolved as h2_anchor_prices_resolved,
    h2s.capture_or_anchor_failure_events as h2_capture_failure_events,
    h2s.independent_h2_anchors,
    h2s.independent_symbols as h2_independent_symbols,
    h2s.utc_days as h2_utc_days,
    h2s.long_anchors as h2_long_anchors,
    h2s.short_anchors as h2_short_anchors,
    h2s.source_geometry_rr5_anchors as h2_rr5_anchors,
    h2s.capture_maturity_gate_met as h2_capture_maturity_gate_met,
    h2s.outcome_access_permitted as h2_outcome_access_permitted,
    h2s.confirmatory_analysis_permitted as h2_confirmatory_analysis_permitted,
    h2s.t0_authorized as h2_t0_authorized,
    h2s.threshold_change_permitted as h2_threshold_change_permitted,
    h2s.production_promotion_permitted as h2_production_promotion_permitted,

    ma.answer_key_episode_count as mover_answer_key_episode_count,
    ma.audited_episode_count as mover_audited_episode_count,
    ma.unaudited_episode_count as mover_unaudited_episode_count,
    ma.latest_audit_capture_at_utc as mover_latest_audit_capture_at_utc,
    ma.latest_answer_key_episode_at_utc as mover_latest_answer_key_episode_at_utc,
    ma.found_executable_shadow,
    ma.found_direction_premove,
    ma.wrong_direction_premove,
    ma.found_unconfirmed_premove,
    ma.prefiltered_not_deep_scanned,
    ma.seen_not_prefiltered,
    ma.not_auditable as mover_not_auditable,
    ma.discovery_root_causes,
    ma.ranking_root_causes,
    ma.direction_root_causes,
    ma.confirmation_tax_root_causes,
    ma.execution_rr_root_causes,
    ma.data_root_causes,
    ma.second_market_scan_used as mover_second_market_scan_used,
    ma.root_cause_uses_only_pre5_evidence as mover_root_cause_uses_only_pre5_evidence,
    ma.post_event_magnitude_used_for_classification as mover_post_event_magnitude_used_for_classification,
    ma.future_outcome_used_for_classification as mover_future_outcome_used_for_classification,

    s.safety_violation_rows as money_entry_safety_violation_rows,
    s.latest_stage_source_at_utc
  from latest_control c
  cross join holdout h
  cross join geometry g
  cross join confirmation d
  cross join h2 h2s
  cross join mover_audit ma
  cross join stage_safety s
  cross join jobs j
)
select
  a.*,

  case
    when a.safety_status<>'PASS'
      or a.money_entry_safety_violation_rows>0
      or a.production_execution_enabled is true
      or a.research_trade_permission is true
    then 'SAFETY_BLOCK'

    when a.latest_finalized_at_utc < clock_timestamp()-interval '2 hours'
    then 'P0_STALE'

    when a.failed_stage_count>0
    then 'P0_FAILED'

    when a.data_freshness_status<>'FRESH'
    then 'DATA_NOT_FRESH'

    else 'RUNNING'
  end as p0_continuity_status,

  case
    when a.geometry_threshold_change_permitted is true
      or a.geometry_production_promotion_permitted is true
      or a.geometry_sealed_outcome_read is true
      or a.confirmation_outcome_evidence_used is true
      or a.confirmation_sealed_outcome_read is true
      or a.t0_authorized is true
      or a.confirmation_threshold_change_permitted is true
      or a.confirmation_production_promotion_permitted is true
      or a.holdout_production_promotion_permitted is true
      or a.h2_outcome_access_permitted is true
      or a.h2_confirmatory_analysis_permitted is true
      or a.h2_t0_authorized is true
      or a.h2_threshold_change_permitted is true
      or a.h2_production_promotion_permitted is true
      or a.mover_second_market_scan_used is true
      or a.mover_root_cause_uses_only_pre5_evidence is not true
      or a.mover_post_event_magnitude_used_for_classification is true
      or a.mover_future_outcome_used_for_classification is true
    then 'REVIEW_REQUIRED'
    else 'ON_TRACK'
  end as anti_drift_status,

  case
    when a.safety_status<>'PASS'
      or a.money_entry_safety_violation_rows>0
      or a.production_execution_enabled is true
      or a.research_trade_permission is true
    then 'INVESTIGATE_SAFETY_IMMEDIATELY'

    when a.latest_finalized_at_utc < clock_timestamp()-interval '2 hours'
    then 'RESTORE_P0_CONTINUITY'

    when a.failed_stage_count>0
    then 'REPAIR_FAILED_PRODUCTION_STAGE'

    when a.data_freshness_status<>'FRESH'
    then 'RESTORE_DATA_FRESHNESS'

    when a.holdout_capture_failures>0
    then 'REPAIR_PROSPECTIVE_CAPTURE'

    when a.h2_capture_failure_events>0
    then 'REPAIR_H2_CAPTURE'

    when a.mover_unaudited_episode_count>0
      and a.mover_latest_answer_key_episode_at_utc
            < clock_timestamp()-interval '90 minutes'
    then 'REPAIR_MISSED_MOVER_AUDIT'

    when a.holdout_sample_gate_met is not true
      or a.h2_capture_maturity_gate_met is not true
    then 'COLLECT_PROSPECTIVE_EVIDENCE'

    when a.holdout_primary_results_exposed is not true
    then 'WAIT_FOR_SEALED_EVALUATOR'

    else 'SCIENTIFIC_REVIEW_ONLY_NO_AUTOMATIC_PROMOTION'
  end as single_next_action,

  'DISCOVERY_TO_EARLY_ENTRY_TO_EXECUTABLE_GEOMETRY_TO_VERIFIED_EXPECTANCY'::text
    as primary_development_priority,

  false as automatic_threshold_change_permitted,
  false as automatic_production_promotion_permitted,
  false as live_order_path_permitted,
  true as shadow_only,
  false as trade_permission,
  'nonstop-production-status-v0.3'::text as model_version
from assembled a;


revoke all on public.alpha_hunter_nonstop_production_status_v03
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_nonstop_production_status_v03
  to service_role;
