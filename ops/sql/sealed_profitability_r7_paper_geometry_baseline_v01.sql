begin;

-- Alpha Hunter sealed profitability R7 preregistration v0.1.
--
-- Prospective clean baseline after paper-entry geometry hardening.
-- Historical R1-R6 evidence remains immutable and is not reused.
-- This is paper/shadow validation only: no trade permission or order path.

insert into public.alpha_hunter_profitability_test_specs_v01 (
  spec_id,
  protocol_version,
  frozen_git_commit,
  required_strategy_count,
  required_minimum_rr,
  evaluation_horizon_hours,
  minimum_test_days,
  minimum_completed_paper_trades,
  confidence_z,
  require_validated_cost_model,
  preregistered_at_utc,
  scientific_role,
  shadow_only,
  trade_permission,
  production_promotion_permitted,
  order_path,
  required_run_source,
  frozen_scientific_fingerprint_sha256
) values (
  'SEALED-ARCH-V14R7-FP-20M-20261003',
  'sealed-profitability-v0.4-baseline-fingerprint-guard',
  'e15a6d984bfed05021308b9180bebc1385079b5b',
  10,
  5.0,
  24,
  30,
  100,
  1.96,
  true,
  clock_timestamp(),
  'SEALED_PROFITABILITY_PREREGISTRATION',
  true,
  false,
  false,
  'NONE',
  'RENDER_CRON',
  'a69cfb66c070640238d2ff480988c02c7da7f6955b43d4f1a12f10c4fc6095db'
)
on conflict(spec_id) do nothing;

insert into public.alpha_hunter_profitability_cadence_contract_v01 (
  spec_id,
  baseline_not_before_utc,
  expected_frequency_minutes,
  minimum_interval_minutes,
  maximum_interval_minutes,
  expected_schedule,
  no_manual_scans_after_baseline,
  scientific_role,
  frozen,
  trade_permission,
  production_promotion_permitted,
  order_path
)
select
  s.spec_id,
  s.preregistered_at_utc,
  20,
  15,
  35,
  'RENDER_CRON_ALIGNED_00_20_40',
  true,
  'SEALED_SCAN_CADENCE_CONTRACT',
  true,
  false,
  false,
  'NONE'
from public.alpha_hunter_profitability_test_specs_v01 s
where s.spec_id='SEALED-ARCH-V14R7-FP-20M-20261003'
on conflict(spec_id) do nothing;

commit;
