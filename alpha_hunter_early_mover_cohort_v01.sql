-- Alpha Hunter prospective early-mover cohort v0.1
-- Purpose: freeze contemporaneous 0-5% mover observations from the existing canonical
-- Money Scorecard stream without hindsight, threshold invention, or a second scanner.

create table if not exists public.alpha_hunter_early_mover_cohort (
    cohort_observation_id text primary key,
    scorecard_id text not null unique,
    source_bridge_id text,
    source_run_id text not null,
    observed_at_utc timestamptz not null,
    symbol text not null,
    direction text not null,
    raw_change_24h_pct double precision not null,
    direction_normalized_move_pct double precision not null,
    early_window_lower_pct double precision not null default 0.0,
    early_window_upper_pct double precision not null default 5.0,
    early_window_eligible boolean not null,
    lifecycle text,
    research_status text,
    bridge_status text,
    scanner_direction text,
    direction_1h text,
    direction_4h text,
    direction_12h text,
    direction_1d text,
    liquidity_state text,
    opportunity_timing text,
    candidate_quality_status text,
    candidate_entry double precision,
    stop_price double precision,
    target_price double precision,
    geometry_valid boolean not null,
    risk_distance_pct double precision,
    initial_remaining_r double precision,
    similarity_score double precision,
    feature_coverage double precision,
    stage_snapshot_status text,
    t0_snapshot_available boolean not null,
    t1_snapshot_available boolean not null,
    t2_snapshot_available boolean not null,
    money_entry_stage_snapshot_id text,
    bridge_blockers jsonb not null default '[]'::jsonb,
    frozen_evidence jsonb not null default '{}'::jsonb,
    capture_contract_version text not null default 'prospective-early-mover-cohort-v0.1',
    shadow_only boolean not null default true,
    trade_permission boolean not null default false,
    captured_at_utc timestamptz not null default now(),
    constraint alpha_hunter_early_mover_window_check
        check (early_window_eligible and abs(raw_change_24h_pct) between 0.0 and 5.0),
    constraint alpha_hunter_early_mover_shadow_only_check
        check (shadow_only = true),
    constraint alpha_hunter_early_mover_no_trade_check
        check (trade_permission = false)
);

alter table public.alpha_hunter_early_mover_cohort enable row level security;
revoke all on public.alpha_hunter_early_mover_cohort from anon, authenticated;
grant select, insert on public.alpha_hunter_early_mover_cohort to service_role;

create or replace function public.alpha_hunter_block_early_mover_cohort_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    raise exception 'alpha_hunter_early_mover_cohort is append-only';
end;
$$;

revoke all on function public.alpha_hunter_block_early_mover_cohort_mutation() from public, anon, authenticated;
grant execute on function public.alpha_hunter_block_early_mover_cohort_mutation() to service_role;

drop trigger if exists alpha_hunter_early_mover_cohort_append_only on public.alpha_hunter_early_mover_cohort;
create trigger alpha_hunter_early_mover_cohort_append_only
before update or delete on public.alpha_hunter_early_mover_cohort
for each row execute function public.alpha_hunter_block_early_mover_cohort_mutation();

create or replace function public.alpha_hunter_capture_early_mover_cohort()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    -- Prospective only: this trigger observes NEW candidate rows at insertion time.
    -- It intentionally performs no historical backfill.
    if new.raw_change_24h_pct is not null
       and abs(new.raw_change_24h_pct) between 0.0 and 5.0 then
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

drop trigger if exists alpha_hunter_capture_early_mover_cohort_after_insert
on public.alpha_hunter_big_mover_money_scorecard_candidates;
create trigger alpha_hunter_capture_early_mover_cohort_after_insert
after insert on public.alpha_hunter_big_mover_money_scorecard_candidates
for each row execute function public.alpha_hunter_capture_early_mover_cohort();

-- Read-only service-role status view. Outcomes remain in the canonical scorecard table;
-- this view does not mutate or relabel them.
create or replace view public.alpha_hunter_early_mover_cohort_status
with (security_invoker = true)
as
select
    c.cohort_observation_id,
    c.scorecard_id,
    c.source_run_id,
    c.observed_at_utc,
    c.symbol,
    c.direction,
    c.raw_change_24h_pct,
    c.lifecycle,
    c.geometry_valid,
    c.risk_distance_pct,
    c.initial_remaining_r,
    c.stage_snapshot_status,
    c.t0_snapshot_available,
    c.t1_snapshot_available,
    c.t2_snapshot_available,
    count(o.outcome_id) filter (where o.evaluation_status = 'EVALUATED') as matured_horizon_count,
    bool_or(o.evaluation_status = 'EVALUATED' and o.horizon_hours = 1) as matured_1h,
    bool_or(o.evaluation_status = 'EVALUATED' and o.horizon_hours = 4) as matured_4h,
    bool_or(o.evaluation_status = 'EVALUATED' and o.horizon_hours = 12) as matured_12h,
    bool_or(o.evaluation_status = 'EVALUATED' and o.horizon_hours = 24) as matured_24h,
    c.shadow_only,
    c.trade_permission
from public.alpha_hunter_early_mover_cohort c
left join public.alpha_hunter_big_mover_money_scorecard_outcomes o
    on o.scorecard_id = c.scorecard_id
group by c.cohort_observation_id;

revoke all on public.alpha_hunter_early_mover_cohort_status from anon, authenticated;
grant select on public.alpha_hunter_early_mover_cohort_status to service_role;
