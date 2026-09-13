create or replace view private.alpha_hunter_money_entry_calibration_cohort_v01
with (security_invoker = true)
as
select
    c.scorecard_id,
    c.run_id,
    c.candidate_at_utc,
    c.symbol,
    c.direction,
    c.scanner_direction,
    c.candidate_entry,
    c.stop_price,
    c.target_price,
    c.risk_distance_pct,
    c.initial_remaining_r,
    o.horizon_hours,
    o.horizon_due_at_utc,
    o.evaluation_status,
    o.mfe_pct,
    o.mae_pct,
    o.stop_hit,
    o.stop_survived,
    o.target_hit,
    o.path_resolution,
    o.path_r_pre_cost,
    o.remaining_r,
    o.confirmation_tax_r,
    o.candidate_path_outcome,
    (c.candidate_at_utc >= timestamptz '2026-09-13T16:56:10Z') as post_direction_binding_fix,
    (c.geometry_valid is true) as explicit_geometry_valid,
    (c.scanner_direction is not null and c.scanner_direction = c.direction) as scanner_direction_bound,
    (c.frozen_evidence->>'geometry_source' = 'SCANNER_EXECUTION_SETUP') as scanner_execution_geometry,
    coalesce((c.frozen_evidence->>'geometry_direction_bound')::boolean, false) as geometry_direction_bound,
    coalesce((c.frozen_evidence->>'research_geometry_promoted')::boolean, false) as research_geometry_promoted,
    (
      c.candidate_at_utc >= timestamptz '2026-09-13T16:56:10Z'
      and c.geometry_valid is true
      and c.scanner_direction is not null
      and c.scanner_direction = c.direction
      and c.frozen_evidence->>'geometry_source' = 'SCANNER_EXECUTION_SETUP'
      and coalesce((c.frozen_evidence->>'geometry_direction_bound')::boolean, false)
      and not coalesce((c.frozen_evidence->>'research_geometry_promoted')::boolean, false)
      and c.shadow_only is true
      and c.trade_permission is false
      and o.shadow_only is true
      and o.trade_permission is false
    ) as calibration_eligible,
    case
      when c.candidate_at_utc < timestamptz '2026-09-13T16:56:10Z' then 'PRE_DIRECTION_BINDING_FIX'
      when c.geometry_valid is not true then 'EXPLICIT_GEOMETRY_INVALID_OR_MISSING'
      when c.scanner_direction is null then 'SCANNER_DIRECTION_MISSING'
      when c.scanner_direction <> c.direction then 'SCANNER_DIRECTION_MISMATCH'
      when c.frozen_evidence->>'geometry_source' is distinct from 'SCANNER_EXECUTION_SETUP' then 'NON_SCANNER_EXECUTION_GEOMETRY'
      when not coalesce((c.frozen_evidence->>'geometry_direction_bound')::boolean, false) then 'GEOMETRY_NOT_DIRECTION_BOUND'
      when coalesce((c.frozen_evidence->>'research_geometry_promoted')::boolean, false) then 'RESEARCH_GEOMETRY_PROMOTED'
      when c.shadow_only is not true or c.trade_permission is not false or o.shadow_only is not true or o.trade_permission is not false then 'SAFETY_BOUNDARY_VIOLATION'
      else 'ELIGIBLE'
    end as calibration_eligibility_status
from public.alpha_hunter_big_mover_money_scorecard_candidates c
join public.alpha_hunter_big_mover_money_scorecard_outcomes o using (scorecard_id);

revoke all on private.alpha_hunter_money_entry_calibration_cohort_v01 from public, anon, authenticated;
grant select on private.alpha_hunter_money_entry_calibration_cohort_v01 to service_role;
