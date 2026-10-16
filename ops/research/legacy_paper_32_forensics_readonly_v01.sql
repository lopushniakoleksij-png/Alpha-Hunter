-- P0/P1/P2 read-only forensic queries. NEVER a migration or scientific promotion.
-- Source: legacy paper_completed_trades_valid_v05, not sealed R9 outcomes.
-- Do not write, backfill, reclassify exits, lift admission halt or change schedules.

-- P1: contemporaneous 1H/4H trends, regime and S1-S10 strategy evidence.
with legacy as (
  select c.exit_fill_id, c.symbol, c.direction, c.exit_reason,
    c.paper_net_pnl_ex_funding, c.net_r_ex_funding,
    d.strategy_id, d.evidence->>'market_phase' as phase,
    d.evidence->'validation_identity'->>'run_source' as run_source,
    s.payload->'timeframes'->'1H'->>'trend' as trend_1h,
    s.payload->'timeframes'->'4H'->>'trend' as trend_4h,
    s.payload->'timeframes'?'12H' as has_12h,
    s.payload->'timeframes'?'1D' as has_1d,
    s.payload->'timeframes'?'1W' as has_1w
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_decisions_v01 d on d.decision_id=c.decision_id
  join public.alpha_hunter_symbol_snapshots s
    on s.run_id=d.run_id and s.symbol=c.symbol
)
select strategy_id, direction, phase, trend_1h, trend_4h, run_source,
  count(*) as orders,
  count(*) filter(where paper_net_pnl_ex_funding>0) as wins,
  sum(paper_net_pnl_ex_funding) as net_usdt_ex_funding,
  avg(net_r_ex_funding) as avg_net_r,
  count(*) filter(where not(has_12h and has_1d and has_1w)) as missing_required_high_tfs
from legacy
group by strategy_id,direction,phase,trend_1h,trend_4h,run_source
order by orders desc,strategy_id,direction;

-- P2: stop geometry should be evaluated in ATR units, not widened blindly.
with stops as (
  select c.exit_fill_id, c.symbol, c.exit_reason, c.direction,
    c.entry_average_fill_price, c.paper_net_pnl_ex_funding,
    p.trigger_price as stop_price,
    (s.payload->'timeframes'->'1H'->'indicators'->>'atr_pct')::numeric as atr_1h_pct,
    (s.payload->'timeframes'->'4H'->'indicators'->>'atr_pct')::numeric as atr_4h_pct
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_decisions_v01 d on d.decision_id=c.decision_id
  join public.alpha_hunter_symbol_snapshots s on s.run_id=d.run_id and s.symbol=c.symbol
  join public.alpha_hunter_paper_protective_orders_v03 p
    on p.entry_order_id=c.entry_order_id and p.protection_type='STOP_LOSS'
), metrics as (
  select *,
    100*abs(entry_average_fill_price-stop_price)
      /nullif(entry_average_fill_price,0) as stop_pct
  from stops
)
select exit_reason, count(*) as orders,
  avg(stop_pct/nullif(atr_1h_pct,0)) as avg_stop_to_1h_atr,
  percentile_cont(.5) within group(order by stop_pct/nullif(atr_1h_pct,0))
    as median_stop_to_1h_atr,
  count(*) filter(where stop_pct<atr_1h_pct) as stop_inside_1h_atr,
  count(*) filter(where stop_pct<atr_4h_pct) as stop_inside_4h_atr,
  sum(paper_net_pnl_ex_funding) as net_usdt_ex_funding
from metrics
group by exit_reason
order by orders desc;

-- P0: recorded-vs-trigger-anchored sensitivity; a hypothetical NON-claim.
select c.exit_reason, count(*) as audited_orders,
  sum(c.paper_net_pnl_ex_funding) as observed_net_ex_funding,
  sum(a.trigger_anchored_net_pnl_ex_funding) as anchor_counterfactual_nonclaim,
  sum(a.observation_delay_tax_r) as observation_delay_tax_r,
  count(*) filter(where a.counterfactual_only is not true) as unsafe_audit_rows,
  count(*) filter(where a.profitability_claim_permitted is true) as claimable_rows,
  count(*) filter(where a.trigger_observed_quote_source is null) as missing_quote_source
from public.alpha_hunter_paper_completed_trades_valid_v05 c
join public.alpha_hunter_paper_exit_observation_delay_audit_v01 a using(exit_fill_id)
group by c.exit_reason
order by audited_orders desc;

-- P0: 1-minute historical path coverage must include winners and losers.
select c.exit_reason,count(*) as clean_legacy_orders,
  count(m.exit_fill_id) as path_audits,
  count(*) filter(where m.candle_count_checked=m.expected_candle_count
    and m.exit_fill_id is not null) as complete_1m_paths,
  count(*) filter(where m.profitability_claim_permitted is true) as unsafe_claims,
  count(*) filter(where m.observed_exit_reason_matches is false) as path_disagreement
from public.alpha_hunter_paper_completed_trades_valid_v05 c
left join public.alpha_hunter_paper_exit_minute_path_audit_v01 m using(exit_fill_id)
group by c.exit_reason
order by clean_legacy_orders desc;
