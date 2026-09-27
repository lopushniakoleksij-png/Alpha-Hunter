-- Alpha Hunter V14 watchdog control-plane semantics v0.3
--
-- Explicit view replacement used because the connector safety layer rejects
-- dynamic DDL wrappers. Operations observability only; outside the sealed V14
-- scientific fingerprint.
--
-- The only semantic change from v0.1 is:
-- LEGACY_CONTROL_PLANE_NOT_PASSING is emitted for FAILED, not DEGRADED.

create or replace view public.alpha_hunter_v14_watchdog_status_v01
with (security_invoker=true, security_barrier=true) as
with engine as (
  select e.*
  from public.alpha_hunter_test_engine_latest_v01 e
  limit 1
),
validation as (
  select v.*
  from public.alpha_hunter_profitability_validation_status_v01 v
  join engine e on e.spec_id=v.spec_id
),
cadence as (
  select c.*
  from public.alpha_hunter_profitability_cadence_integrity_v01 c
  join engine e on e.spec_id=c.spec_id
),
continuity as (
  select f.*
  from public.alpha_hunter_private_fill_history_continuity_v01 f
  join engine e on e.spec_id=f.spec_id
),
storage as (
  select s.*
  from public.alpha_hunter_storage_reclaim_summary_v01 s
  limit 1
),
control_health as (
  select h.*
  from public.alpha_hunter_control_plane_health_events h
  order by h.checked_at_utc desc
  limit 1
),
base as (
  select
    clock_timestamp() as checked_at_utc,
    e.spec_id,
    e.engine_version,
    e.evaluated_at_utc as test_engine_evaluated_at_utc,
    e.operational_status,
    e.profitability_status,
    e.verdict,
    e.blockers,
    e.latest_live_run_id,
    e.latest_live_scan_at_utc,
    extract(
      epoch from (clock_timestamp()-e.latest_live_scan_at_utc)
    )::double precision as latest_live_scan_age_seconds,
    e.real_scans_since_registration,
    e.real_strategy_observations_since_registration,
    e.real_shadow_candidates_since_registration,
    e.real_24h_forward_outcomes_since_registration,
    e.completed_paper_trades,
    e.minimum_completed_paper_trades,
    e.test_days_elapsed,
    e.minimum_test_days,
    e.cost_model_validated,
    e.realistic_net_r_claim_permitted,
    e.trade_permission as engine_trade_permission,
    e.production_promotion_permitted as engine_promotion_permitted,
    e.order_path as engine_order_path,

    v.started_at_utc,
    v.test_activated,
    v.duration_gate_met,
    v.sample_gate_met,
    v.identity_drift_gate_met,
    v.identity_drift_scans,
    v.post_start_scans,
    v.scientific_fingerprint_enabled,
    v.frozen_scientific_fingerprint_sha256,
    v.baseline_scientific_fingerprint_sha256,
    v.cost_scientific_status,
    v.cost_next_gate,
    v.trade_permission as validation_trade_permission,
    v.production_promotion_permitted as validation_promotion_permitted,
    v.order_path as validation_order_path,

    c.expected_frequency_minutes,
    c.minimum_interval_minutes,
    c.maximum_interval_minutes,
    c.expected_schedule,
    c.cadence_integrity_ok,
    c.cadence_integrity_status,
    c.too_frequent_scan_intervals,
    c.excessive_gap_intervals,
    c.identity_mismatch_scan_count,

    f.continuity_status as private_fill_continuity_status,
    f.historical_fill_continuity_conflict,
    f.account_identity_probe_status,
    f.account_identity_expected_configured,
    f.account_identity_match,
    f.account_is_subaccount,
    f.current_fill_count,
    f.historical_fill_rows_same_window,
    f.historical_symbols_same_window,
    f.next_gate as private_fill_next_gate,
    f.trade_permission as continuity_trade_permission,
    f.production_promotion_permitted as continuity_promotion_permitted,
    f.order_path as continuity_order_path,

    s.database_bytes,
    s.database_size_pretty,
    s.audited_relation_bytes,
    s.audited_toast_bytes,
    s.live_toast_review_tables,

    h.checked_at_utc as legacy_control_plane_checked_at_utc,
    h.status as legacy_control_plane_status,
    h.safety_status as legacy_control_plane_safety_status,
    h.missing_stages as legacy_control_plane_missing_stages,
    h.warnings as legacy_control_plane_warnings
  from engine e
  left join validation v on true
  left join cadence c on true
  left join continuity f on true
  left join storage s on true
  left join control_health h on true
),
classified as (
  select
    b.*,
    array_remove(array[
      case when b.spec_id is null
        then 'TEST_ENGINE_MISSING' end,
      case when b.test_engine_evaluated_at_utc is null
             or clock_timestamp()-b.test_engine_evaluated_at_utc
                > interval '25 minutes'
        then 'TEST_ENGINE_STALE' end,
      case when b.latest_live_scan_at_utc is null
             or clock_timestamp()-b.latest_live_scan_at_utc
                > interval '35 minutes'
        then 'CANONICAL_SCAN_STALE' end,
      case when not coalesce(b.test_activated,false)
        then 'SEALED_TEST_NOT_ACTIVATED' end,
      case when not coalesce(b.identity_drift_gate_met,false)
        then 'SCIENTIFIC_IDENTITY_DRIFT' end,
      case when coalesce(b.test_activated,false)
             and not coalesce(b.cadence_integrity_ok,false)
        then 'CADENCE_INTEGRITY_FAILED' end,
      case when coalesce(b.profitability_status,'')
                like 'INVALIDATED_%'
        then 'PROFITABILITY_TEST_INVALIDATED' end,
      case when coalesce(b.operational_status,'MISSING')<>'PASS'
        then 'TEST_ENGINE_OPERATIONAL_BLOCKED' end,
      case when coalesce(b.engine_trade_permission,false)
             or coalesce(b.validation_trade_permission,false)
             or coalesce(b.continuity_trade_permission,false)
             or coalesce(b.engine_promotion_permitted,false)
             or coalesce(b.validation_promotion_permitted,false)
             or coalesce(b.continuity_promotion_permitted,false)
             or coalesce(b.engine_order_path,'NONE')<>'NONE'
             or coalesce(b.validation_order_path,'NONE')<>'NONE'
             or coalesce(b.continuity_order_path,'NONE')<>'NONE'
        then 'SAFETY_AUTHORITY_VIOLATION' end
    ]::text[],null) as critical_alerts,

    array_remove(array[
      case when coalesce(b.historical_fill_continuity_conflict,false)
        then 'BITGET_FILL_HISTORY_CONTINUITY_CONFLICT' end,
      case when coalesce(b.account_identity_probe_status,'NOT_CONFIGURED')
                  in ('UNPINNED','NOT_CONFIGURED')
        then 'BITGET_ACCOUNT_IDENTITY_UNPINNED' end,
      case when not coalesce(b.cost_model_validated,false)
        then 'EXECUTION_COST_MODEL_NOT_VALIDATED' end,
      case when coalesce(b.legacy_control_plane_status,'MISSING')='FAILED'
        then 'LEGACY_CONTROL_PLANE_NOT_PASSING' end,
      case when coalesce(b.live_toast_review_tables,0)>0
        then 'STORAGE_LIVE_TOAST_REVIEW_REQUIRED' end
    ]::text[],null) as warning_alerts,

    array_remove(array[
      case when not coalesce(b.duration_gate_met,false)
        then 'MINIMUM_30_DAY_DURATION_NOT_MET' end,
      case when not coalesce(b.sample_gate_met,false)
        then 'MINIMUM_100_PAPER_TRADES_NOT_MET' end,
      case when not coalesce(b.realistic_net_r_claim_permitted,false)
        then 'REALISTIC_NET_R_CLAIM_NOT_YET_PERMITTED' end
    ]::text[],null) as expected_gates
  from base b
)
select
  c.*,
  case
    when cardinality(c.critical_alerts)>0 then 'CRITICAL'
    when cardinality(c.warning_alerts)>0 then 'WARNING'
    else 'HEALTHY'
  end as watchdog_status,
  greatest(
    coalesce(c.minimum_test_days,30)::double precision
      - coalesce(c.test_days_elapsed,0)::double precision,
    0
  ) as test_days_remaining,
  greatest(
    coalesce(c.minimum_completed_paper_trades,100)
      - coalesce(c.completed_paper_trades,0),
    0
  ) as paper_trades_remaining,
  case
    when c.started_at_utc is not null
      then c.started_at_utc
        + make_interval(days=>coalesce(c.minimum_test_days,30))
    else null
  end as earliest_duration_gate_at_utc,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from classified c;

comment on view public.alpha_hunter_v14_watchdog_status_v01 is
  'Current V14 operational watchdog. Critical integrity failures are separated '
  'from expected duration/sample gates and non-scientific warnings.';

revoke all on public.alpha_hunter_v14_watchdog_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v14_watchdog_status_v01
  to service_role;
