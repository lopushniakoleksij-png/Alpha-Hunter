# P3 offline execution-cost evidence preparation — 15 October 2026
**Research only — $0 new spend — separate from P2 PR #341 and frozen R10.**

## Current authoritative observation
Read-only public `alpha_hunter_execution_cost_validation_readiness_v04`:
- 247 historical/coarse benchmark fill rows (market-price comparison only, **not measured Alpha Hunter execution slippage**).
- 270 fee observations, **not exact prospectively bound Alpha Hunter freeze→venue fill→exit paths**.
- **0** verified Alpha Hunter execution attribution rows (0 verified TAKER, MAKER, LONG, SHORT).
- **0** verified exit-slippage rows; **0** verified post-fill markout rows.
- **0** active validated models; funding-path, missing-data-policy and out-of-sample replication gates false.
- `WAITING_FOR_FIRST_EXPLICIT_CONFIRMED_REAL_EXECUTION`; `realistic_net_r_claim_permitted=false`, `trade_permission=false`.
These are measured categories, not proof of a profitable or unprofitable strategy. **Do not request an actual trade to create a sample.**

## Reuse rather than duplicate existing research
- `ops/sql/verified_execution_slippage_readiness_v01.sql` on main already defines verification floors of **30** exact entries, **20 TAKER**, **10 MAKER**, **5 each LONG and SHORT**, with observed fee and signed entry-slippage evidence. Floors are **readiness**, not model validation.
- Existing unmerged PR #235 is a **DRAFT-only** empty-parameter cost-model governance proposal; do not promote it or invent fees.
- Existing unmerged PR #243 measures a prospective **observable fee+spread floor**, explicitly excluding full slippage/latency/impact/funding/markout. A floor-adjusted R is **NOT realistic net R**. Do not merge with the R10 sample.

## Exact-link evidence needed for future model validation
Each independently authenticated, prospective execution must bind:
1. Frozen strategy/decision ID, spec/source run and timestamp, exact intended order identity and arrived bid/ask quote, LONG/SHORT side, structural stop, and initial price/risk geometry.
2. Explicit independently confirmed venue order ID and each unique fill/trade ID, timestamp, quantity, realized maker/taker fee with currency and receipt, arrival-to-fill slippage and latency; partial fills are not manufactured complete.
3. Exact exit-fill trade IDs/quantities and contemporaneous quote, realized exit fee and slippage, and disposition within the originally frozen horizon. Censored, quarantined and expired/no-fill paths stay distinct.
4. Separate evidenced fees, spread, adverse entry/exit slippage, executable liquidity/market impact, signed post-fill markout/adverse selection, realized funding path and currency conversion where necessary; missing component = **UNKNOWN**, not zero. Stop/target geometry alone proves none of these.
5. Final **genuinely validated** prospective calibration under original maker/taker and LONG/SHORT segmentation, price/size regime, missingness and out-of-sample replication; never alter R10 fingerprint, 30-day/100 clean trade gates or 35m monitoring limit.

## What this PR does
Pure `ops/reviews/p3_offline_execution_cost_completeness_v01.py` and isolated synthetic tests:
- Validate decision→entry→exit links, signed source clocks, exact venue IDs, unique IDs, quantities, original side/stop geometry, all eight distinct cost evidence components with individual references.
- Reject absent funding, markout, exit-slippage, stop/TP geometry, unmatched/duplicated fills, unreconciled partials, stale/mismatched identities, malformed costs and benchmark-to-fill substitution.
- Even **30 perfect synthetic fixtures** passing sample floors produce **no real validated samples**, **no realistic_net_r**, **no activated model**, **no scientific PASS**, and **no paper/live order authority**. This is only a lab schema/evidence-completeness test, NOT exchange-origin verification, a cost estimate or a deployed collector.
- Do **not** import into production module paths, create migrations, run new scanners, alter thresholds, create any paper/real orders, deploy to Render, reopen R10, backfill old rows, or incur costs.

## Approval gate
**P3 OFFLINE PREP** may pass exact-head CI while **P3 LIVE COST VALIDATION remains BLOCKED** until verified real decision→fill links, independent venue/exchange evidence, complete costs, forward sample and replication exist. The P2 live monitoring acceptance is independently BLOCKED. No cost model or trade authority may be released from this branch.

Owner's revenue-first hold: **$0 new infrastructure, trials and subscriptions**. PR is draft and never merged into auto-deploying main while Primary Hourly operates.
