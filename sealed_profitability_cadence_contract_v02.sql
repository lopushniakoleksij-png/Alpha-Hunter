-- Alpha Hunter sealed cadence contract v0.2
--
-- Extends the scientific cadence contract to support the canonical
-- 20-minute Render scanner without weakening the existing 60-minute cohorts.
--
-- Safety/science:
-- - only 20m or 60m sealed cadence contracts are permitted;
-- - minimum interval may not exceed expected frequency;
-- - maximum interval may not be below expected frequency;
-- - all existing append-only / no-manual-scan / no-trade constraints remain.

alter table public.alpha_hunter_profitability_cadence_contract_v01
  drop constraint if exists
    alpha_hunter_profitability_cad_expected_frequency_minutes_check;

alter table public.alpha_hunter_profitability_cadence_contract_v01
  drop constraint if exists
    alpha_hunter_profitability_caden_minimum_interval_minutes_check;

alter table public.alpha_hunter_profitability_cadence_contract_v01
  drop constraint if exists
    alpha_hunter_profitability_caden_maximum_interval_minutes_check;

alter table public.alpha_hunter_profitability_cadence_contract_v01
  add constraint alpha_hunter_profitability_cad_expected_frequency_minutes_check
  check (expected_frequency_minutes in (20,60));

alter table public.alpha_hunter_profitability_cadence_contract_v01
  add constraint alpha_hunter_profitability_caden_minimum_interval_minutes_check
  check (
    minimum_interval_minutes >= 1
    and minimum_interval_minutes <= expected_frequency_minutes
  );

alter table public.alpha_hunter_profitability_cadence_contract_v01
  add constraint alpha_hunter_profitability_caden_maximum_interval_minutes_check
  check (
    maximum_interval_minutes >= expected_frequency_minutes
    and maximum_interval_minutes >= minimum_interval_minutes
  );
