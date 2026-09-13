-- Alpha Hunter prospective early-mover cohort v0.2
-- Tightens prospective scientific capture without deleting or relabeling v0.1 evidence.
-- No historical backfill. No threshold invention. No second scanner. No trade permission.

create or replace function public.alpha_hunter_capture_early_mover_cohort()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    -- Prospective only. A scientific TEST observation must be genuinely early and
    -- directionally identified by the canonical scanner at observation time.
    -- Ambiguous/null scanner direction is not converted into LONG/SHORT hindsight.
    if new.raw_change_24h_pct is not null
       and abs(new.raw_change_24h_pct) between 0.0 and 5.0
       and upper(coalesce(new.opportunity_timing, '')) = 'EARLY'
       and new.scanner_direction is not null
       and upper(new.scanner_direction) = upper(new.direction) then
        insert into public.alpha_hunter_early_mover_cohort (
            cohort_observation_id,
            scorecard_id,
            source_bridge_id,
            source_run_id,
            observed_at_utc,
            symbol,
            direction,
            raw_change_24h_pct,
            direction_normalized_move_pct,
            early_window_eligible,
            lifecycle,
            research_status,
            bridge_status,
            scanner_direction,
            direction_1h,
            direction_4h,
            direction_12h,
            direction_1d,
            liquidity_state,
            opportunity_timing,
            candidate_quality_status,
            candidate_entry,
            stop_price,
            target_price,
            geometry_valid,
            risk_distance_pct,
            initial_remaining_r,
            similarity_score,
            feature_coverage,
            stage_snapshot_status,
            t0_snapshot_available,
            t1_snapshot_available,
            t2_snapshot_available,
            money_entry_stage_snapshot_id,
            bridge_blockers,
            frozen_evidence,
            capture_contract_version,
            shadow_only,
            trade_permission
        ) values (
            'EARLY-' || new.scorecard_id,
            new.scorecard_id,
            new.source_bridge_id,
            new.run_id,
            new.candidate_at_utc,
            new.symbol,
            new.direction,
            new.raw_change_24h_pct,
            new.direction_normalized_move_pct,
            true,
            new.lifecycle,
            new.research_status,
            new.bridge_status,
            new.scanner_direction,
            new.direction_1h,
            new.direction_4h,
            new.direction_12h,
            new.direction_1d,
            new.liquidity_state,
            new.opportunity_timing,
            new.candidate_quality_status,
            new.candidate_entry,
            new.stop_price,
            new.target_price,
            new.geometry_valid,
            new.risk_distance_pct,
            new.initial_remaining_r,
            new.similarity_score,
            new.feature_coverage,
            new.stage_snapshot_status,
            new.t0_snapshot_available,
            new.t1_snapshot_available,
            new.t2_snapshot_available,
            new.money_entry_stage_snapshot_id,
            coalesce(new.bridge_blockers, '[]'::jsonb),
            coalesce(new.frozen_evidence, '{}'::jsonb),
            'prospective-early-mover-cohort-v0.2',
            true,
            false
        )
        on conflict (scorecard_id) do nothing;
    end if;
    return new;
end;
$$;

revoke all on function public.alpha_hunter_capture_early_mover_cohort() from public, anon, authenticated;
grant execute on function public.alpha_hunter_capture_early_mover_cohort() to service_role;

-- Scientific eligibility view preserves the append-only v0.1 records while preventing
-- ambiguous bidirectional signature rows from entering the TEST cohort.
create or replace view public.alpha_hunter_early_mover_scientific_status
with (security_invoker = true)
as
select
    s.*,
    c.scanner_direction,
    c.opportunity_timing,
    c.capture_contract_version,
    (
      c.early_window_eligible
      and upper(coalesce(c.opportunity_timing, '')) = 'EARLY'
      and c.scanner_direction is not null
      and upper(c.scanner_direction) = upper(c.direction)
    ) as scientific_test_eligible,
    case
      when not c.early_window_eligible then 'OUTSIDE_0_5_WINDOW'
      when upper(coalesce(c.opportunity_timing, '')) <> 'EARLY' then 'NOT_EARLY_TIMING'
      when c.scanner_direction is null then 'SCANNER_DIRECTION_MISSING'
      when upper(c.scanner_direction) <> upper(c.direction) then 'SCANNER_DIRECTION_CONFLICT'
      else 'ELIGIBLE'
    end as scientific_eligibility_reason
from public.alpha_hunter_early_mover_cohort_status s
join public.alpha_hunter_early_mover_cohort c
  on c.cohort_observation_id = s.cohort_observation_id;

revoke all on public.alpha_hunter_early_mover_scientific_status from anon, authenticated;
grant select on public.alpha_hunter_early_mover_scientific_status to service_role;
