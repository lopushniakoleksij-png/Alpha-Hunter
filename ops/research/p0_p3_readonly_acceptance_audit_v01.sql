-- SELECT-ONLY RESEARCH AUDIT. NOT A MIGRATION, NO PRODUCTION WRITES.
-- Frozen initial 32 validated legacy exits, prior to 2026-10-16 23:23 UTC.
-- No access to sealed geometry/early-direction outcome tables. No order authority.

-- P0 original immutable 32 legacy exit composition, no reclassification.
with cohort as (
 select c.exit_fill_id,c.entry_order_id,c.symbol,c.direction,c.exit_reason,
        c.paper_net_pnl_ex_funding
 from public.alpha_hunter_paper_completed_trades_valid_v05 c
 where c.closed_at_utc < '2026-10-16T23:23:00Z'
)
select count(*) as original_legacy_exits,
       count(distinct exit_fill_id) as unique_exit_ids,
       count(*) filter (where exit_reason='STOP_LOSS') stop_exits,
       count(*) filter (where exit_reason='TAKE_PROFIT') target_exits,
       count(*) filter (where exit_reason='HORIZON_24H') horizon_exits,
       count(*) filter (where paper_net_pnl_ex_funding<0) observed_losers,
       count(*) filter (where paper_net_pnl_ex_funding>0) observed_winners,
       sum(paper_net_pnl_ex_funding) as total_paper_net_ex_funding
from cohort;

-- P0 quote count and source declarations are NOT exchange authenticity.
with cohort as (
 select distinct entry_order_id
 from public.alpha_hunter_paper_completed_trades_valid_v05
 where closed_at_utc < '2026-10-16T23:23:00Z'
)
select count(*) as archived_exit_quote_observations,
       count(*) filter (where a.best_bid is not null and a.best_ask is not null) as has_bid_ask,
       count(*) filter (where a.best_bid_size is not null and a.best_ask_size is not null) as has_top_level_sizes,
       count(*) filter (where nullif(a.evidence->>'quote_source','') is null) as missing_named_source,
       count(*) filter (where a.evidence->>'captured_quote_only'='true') as declared_quote_only,
       count(*) filter (where a.evidence->>'exchange_request_added'='true') as own_exchange_request_added
from public.alpha_hunter_paper_exit_attempts_v04 a
join cohort c on c.entry_order_id=a.entry_order_id;

-- P0 archive matching: these depth snapshots are not a historical exit proof.
with cohort as (
 select distinct entry_order_id
 from public.alpha_hunter_paper_completed_trades_valid_v05
 where closed_at_utc < '2026-10-16T23:23:00Z'
)
select count(*) as r9_depth_timing_rows,
       count(*) filter(where c.entry_order_id is not null) as legacy_order_id_matches
from public.alpha_hunter_r9_depth_timing_captures_v01 d
left join cohort c on c.entry_order_id=d.order_id;

-- P2 historically observed stop placement vs original support/resistance.
-- Descriptive comparisons ONLY: 4H support/resistance are NOT validated
-- exact structural invalidation points and do not validate wider stops.
with x as (
 select c.exit_fill_id,c.symbol,c.direction,c.exit_reason,
        c.entry_average_fill_price as entry_price,
        p.trigger_price as stop_price,
        c.paper_net_pnl_ex_funding as pnl,
        (s.payload->'timeframes'->'1H'->'indicators'->>'atr_pct')::numeric as atr_1h_pct,
        (s.payload->'timeframes'->'4H'->'indicators'->>'atr_pct')::numeric as atr_4h_pct,
        (s.payload->'timeframes'->'4H'->>'support')::numeric as support_4h,
        (s.payload->'timeframes'->'4H'->>'resistance')::numeric as resistance_4h
 from public.alpha_hunter_paper_completed_trades_valid_v05 c
 join public.alpha_hunter_paper_decisions_v01 d on d.decision_id=c.decision_id
 join public.alpha_hunter_symbol_snapshots s
   on s.run_id=d.run_id and s.symbol=c.symbol
 join public.alpha_hunter_paper_protective_orders_v03 p
   on p.entry_order_id=c.entry_order_id and p.protection_type='STOP_LOSS'
 where c.closed_at_utc<'2026-10-16T23:23:00Z'
), metrics as (
 select *,
        100*abs(entry_price-stop_price)/nullif(entry_price,0) as stop_pct
 from x
)
select direction,exit_reason,count(*) as trades,
       count(*) filter(where stop_pct<atr_1h_pct) inside_1h_atr,
       count(*) filter(where stop_pct<atr_4h_pct) inside_4h_atr,
       count(*) filter(where direction='LONG' and stop_price>support_4h) as long_stop_above_4h_support,
       count(*) filter(where direction='SHORT' and stop_price<resistance_4h) as short_stop_below_4h_resistance,
       round((percentile_cont(.5) within group(order by stop_pct))::numeric,4) median_stop_pct,
       round((percentile_cont(.5) within group(order by stop_pct/nullif(atr_1h_pct,0)))::numeric,4) median_stop_to_1h_atr,
       sum(pnl) as legacy_net_ex_funding
from metrics
group by direction,exit_reason
order by trades desc,direction;

-- P2 capture METADATA ONLY. Do NOT query or reveal sealed primary outcomes.
select spec_id, scientific_status, registered_at_utc,collection_ends_at_utc,
       captured,eligible,excluded,symbols,utc_days,long_eligible,short_eligible,
       capture_sample_gate_met,scientific_conclusion,production_promotion_permitted
from public.alpha_hunter_geometry_holdout_status_v01;

-- P1 directional holdout is a DISTINCT hypothesis and independent time window.
-- Do not borrow these samples/outcomes for the successor strategy cohort.
select spec_id,scientific_status,registered_at_utc,collection_ends_at_utc,
       test_bound,control_pool_bound,minimum_matched_pairs,
       minimum_symbols,minimum_utc_days,scientific_conclusion,
       outcome_access_permitted,production_promotion_permitted
from public.alpha_hunter_scientific_holdout_status_v02;

-- P2 realistic cost blockers: historical coarse benchmark is NOT validated
-- execution fill/slippage/funding economics, even if market-candle coverage=100%.
select eligible_market_fill_rows,benchmark_evaluated_rows,
       verified_execution_rows,verified_exit_slippage_rows,
       verified_post_fill_markout_rows,realized_funding_path_gate_met,
       out_of_sample_replication_gate_met,full_cost_validation_evidence_complete,
       realistic_net_r_model_activation_permitted,realistic_net_r_claim_permitted,
       validation_status
from public.alpha_hunter_execution_cost_validation_readiness_v04;

-- P3 sealed production R9 truth. Separate from September prospective
-- geometry study and any yet-to-be-preregistered successor study.
select spec_id,completed_paper_trades,verdict,
       trade_permission,production_promotion_permitted,
       activated_at_utc,admission_cutoff_at_utc
from public.alpha_hunter_paper_profitability_status_v09;
