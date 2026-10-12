# Alpha Hunter — forward-only exit-book feasibility study v0.1

**Research protocol committed 2026-10-08, before pilot start.** **No activation, no merge, no deployment to R10, no exchange trading.**

## 1. Evidence receipt and exploratory baseline (NOT holdout)

Supabase project `yjgtjzymfurqzqqxcrnp`, read-only queries on `public.alpha_hunter_snapshots`, `public.alpha_hunter_symbol_snapshots`, and `public.alpha_hunter_paper_exit_attempts_v04`. Exploratory cutoff was PR #335's creation **2026-10-08 03:38:50Z**; query inspected through approximately **08:27Z**. The PR had NOT preregistered the statistic definitions before this analysis. **Never call these exploratory statistics independent out-of-sample validation.**

- 15 canonical Render scanner snapshots starting **03:43Z** to **08:23Z** were available after that cutoff (16 total since the 03:05 Supabase timeout migration, of which the 03:23Z scan predates this research cutoff); 0 unpersisted children, no frozen-fingerprint drift or >35-minute canonical gaps.
- The 15 canonical snapshots produced **908** selected/deep-scanned symbol records spanning **98 distinct symbols**. At 08:23Z, **62/62** symbol payloads had both top-of-book price/size pairs and valid size multipliers, but only **21/62** had a complete proposed entry+stop geometry (7 LONG/14 SHORT). This is a selected sample of the scanned universe, **not** all 816 contracts on every scan.
- Monitoring ledger after the research cutoff contained **301** attempt rows across 20 historical open paper positions and 16 source run IDs, including one extra noncanonical web source. Filtering only canonical RENDER_CRON run identity leaves **287** usable top-size rows (each positive on both sides); the correct independent unit is **13 distinct symbol/direction series**, after collapsing 7 QUSDT LONG entries and 2 SOONUSDT SHORT entries, and collapsing repeated quotes within a source run. This yields **182 distinct symbol-direction-by-canonical-run records**.
- Using each independent series' first observed exit-side top-book size as a baseline and its later minimum in this <5-hour exploratory observation window: **12/13** shrank, **9/13** fell below 50%, **7/13** fell below 25%, **4/13** fell below 10%; minimum later/initial ratio **0.0172**. These numbers are **descriptive conditional on being observed**, not probabilities, fill-quality estimates, robust thresholds, or prospective 24-hour results.
- The capture methods vary: some quote_source tags identify a public all-tickers reconciliation refresh; others have no explicit source label in the attempt evidence. Include the missing-source rate in quality accounting. 20-minute top-of-book observations cannot prove continuous depth, hidden liquidity, queue position, market impact, or stop-time fill certainty. Exited positions have shorter followup and must be **right-censored**, not counted as stable.

### Actual historical defects (excluded from any clean score)

MAGMA R10 LONG: 143-unit risk size vs contemporaneous entry bid 46 / ask 848; 24-hour attempted SELL bid 40. SUPER R10 SHORT: 892-unit risk size vs entry ask 266; later first STOP BUY ask only 13. Both existing R10 scientific failures remain irreversible; WLD/MEGA monitoring-gap failures are independent. Do not fit a threshold to these cases.

As of 08:27Z there are **18** active paper positions (20 earlier, two genuine modeled closures): ZECUSDT stopped and USUSDT closed at 24-hour horizon. Historical economic totals cannot establish expectancy or profits: these are modeled paper results with missing true funding and fill uncertainty. R10 admitted 37, with 4 historical failures and one completed-quality-valid USUSDT; **zero new R10 admissions**.

## 2. Precommitted FUTURE instrumentation pilot (new observations only)

- **Observation window:** **2026-10-08 12:00:00 UTC (13:00 London)** through **2026-10-09 12:00:00 UTC (13:00 London)**, fixed in `ops/reviews/future_exit_liquidity_24h_readonly_v01.sql` **before the window starts**.
- **Sources:** immutable existing `alpha_hunter_paper_exit_attempts_v04` joined on `source_run_id` to a `RENDER_CRON` snapshot, frozen fingerprint `50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834`, and valid positive bid+ask prices/sizes. This uses data already captured by P0; **do not create extra collectors or change positions**.
- **Unit / duplicate rule:** one `(symbol,direction,canonical source_run_id)` row; multiple orders of the same symbol+direction **never count as independent liquidity evidence**. Long exit consumes bid; short exit consumes ask. Observe passive historical paper positions, **not newly admitted trades**.
- **Primary measurement:** for each symbol/direction series, compare minimum *subsequent* exit-side best-level size to the first in-window exit-side size. Report the absolute quantities and ratio. Descriptive reference bands `<0.5`, `<0.25` and their counts are measurement probes, **not a preselected production participation policy**.
- **Maturity:** no conclusion at all before 2026-10-09 12:00:00Z. For a **complete** series require two or more scans, first quote within 35 minutes of window start, last quote within 35 minutes of window end, every interior observed interval <=35 minutes. Report missing/censored series explicitly; do not infer stable liquidity in gaps. A position closed before end is not a 24h complete series.
- **Quality:** show canonical coverage, unique symbol/direction series, de-duplicated quotes, censoring, quotes with source tag absent. A canonical gap >35 minutes or missing quote makes scientific completeness fail rather than being excused. Do not modify the **frozen 35-minute maximum**.
- **Decision:** this one-day passive pilot tests instrumentation and whether 20-minute top-book snapshots are even adequate to form a reliable 24-hour series. It **does not** grant any successor admission, claim quote persistence guarantees, validate future exits, choose a cap, or conclude profitability. If sample/coverage is inadequate, verdict **INSUFFICIENT_EVIDENCE / NEED_DIFFERENT_MEASUREMENT**.

## 3. Later successor-only production gates — separate owner review

1. Validate at least multiple independent UTC days and sufficiently diverse unique symbol/direction windows, with explicit dependence-robust confidence intervals, actual exit occurrence strata, independent holdout cutoff, and no lookahead. Do not repeatedly tune a percentage on these exploratory observations.
2. Develop realistic order-book depth (not just ticker top), stop-time liquidity, cost and latency uncertainty, and fail-closed deterministic partial/remainder management if explicitly preregistered. No invented multi-level fills. An admissible position size at entry is **not** proof of its size at the eventual stop.
3. Freeze future-cohort parameters (including participation maximum and quote-age limit) and quantitative sufficiency before any holdout; compare risk-adjusted and cost-adjusted outcomes on new, scientifically valid 24h paper positions. Any new model/fingerprint must be successor-only with explicit protection continuity approval.
4. Preserve R9/R10 history, R10 halt, running P0 Primary Hourly, Supabase 12s operational mitigation, existing protected positions and `exchange_authority=false`. PR #335 is draft, unmerged and undeployed; it changes the hash if ever merged into current runtime.

## Verification

At creation, the prospective SQL query was run **read-only before 12:00Z** and correctly returned `pilot_status=NOT_STARTED`, `canonical_runs=0`, `symbol_direction_series=0`, `complete_24h_series=0`. It does **not write** any tables or backfill missing scans.

**Never call a read-only query “automatically scheduled.”** The pilot is preregistered for the existing production evidence, but this document alone does not install a scheduled runner or send future notifications.
