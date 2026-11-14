# ALPHA HUNTER — SCIENTIFIC VALIDATION V1.3
## PROSPECTIVE 30-DAY OBSERVATION PROTOCOL — SEALED BEFORE TEST WINDOW

**Frozen on 14 November 2026 (UTC)** in isolated Phase 2 research branch, **before** any V1.3 signal observations or outcome selection. Scientific-only read-only evaluation of **ONE EXISTING canonical Alpha Hunter scanner**, **not** a new scanner, new strategy, live trader, or a restart of a protected automated task.

### 1. Hard-coded cohort and cutoff

- **Observation interval:** [2026-11-15 00:00 UTC, **2026-12-15 00:00 UTC**) — exactly **30 UTC calendar days**, 15 November through 14 December inclusive.
- **Final required price horizon:** no earlier than **2026-12-16 00:00 UTC**; assessment only after all first-full-post-signal hourly candles have closed. Daily evidence may be collected earlier but not adjudicated until the precise individual horizon matures. Scheduled checks never enable real orders.
- **Fixed instruments:** BTCUSDT, ETHUSDT, SOLUSDT, USDT-FUTURES, 1H **market** OHLC (not index/mark). Complete historical instrument membership on a given day is NOT certified by current catalogue; tag `INSTRUMENT_ELIGIBILITY_UNKNOWN` unless dated evidence independently supports venue-tradability.
- **Controlling scanner evidence:** existing canonical `public.alpha_hunter_signals` read-only rows, `run_id`, `signal_id`, `symbol`, `detected_at_utc`, `created_at`, `direction`, `trade_permission`, `entry_price`, `stop_loss`, `take_profit`, `payload.execution_setup.checks`, `payload.trade_permission_reason`, `payload.decision_trace.blocking_gate`. Compare `run_id` against existing `alpha_hunter_snapshots` and `alpha_hunter_symbol_snapshots` as a **data-completeness diagnostic**, not an authorization gate. Because the P0 database-write repair is still NO-GO, missing scanner records/child rows imply **UNKNOWN COVERAGE**, never an empty opportunity set.

### 2. Prospective as-of candidate selection (frozen deterministic rule)

- Use **only facts stored by or before the start of the first full 1H candle after signal detection**; reject late-created or otherwise impossible-as-of records.
- UTC-day candidate: sort (detected_at_utc, signal_id); choose **earliest** directional LONG or SHORT record with finite positive EP/SL/TP and geometry: LONG `SL < EP < TP`, SHORT `TP < EP < SL`. **Do not select or reject based on future OHLC, target outcome, rewards, filter PASS/FAIL, `trade_permission`, scan's rank, or profitability.** The last two fields are retained as evidence, not sorting keys.
- If a candidate is selected, suppress **all subsequent records for the same symbol** while `detected_at_utc < candidate_detected_at + 24h` (cross-midnight 24h embargo). At most **one** candidate per symbol per UTC day; do not replace a censored/ambiguous signal with a later one. A cross-day carryover may consume the next day's eligibility; report `COOLDOWN_SUPPRESSED` and never fill the gap with a cherry-picked later signal. This cross-day conservatism is a **predeclared V1.3 addition** to the earlier one-per-UTC-day pilot; never misstate it as an unmodified V1.1 definition.
- Preserve ALL original qualifying and nonqualifying daily signal counts and exact missingness, not merely successful candidates; freeze the signal snapshot for each day from the existing service before market outcomes are interpreted.
- No retrospective replacement of a UTC date, symbol, direction, R:R threshold or economic assumptions based on results.

### 3. Regime and outcome rules (no lookahead)

- **Pre-day market regime:** prior **completed** BTCUSDT 1Dutc close-to-close percent change, computed from prior two daily closing bars. RISING > +1.00%, FALLING < −1.00%, otherwise SIDEWAYS. The regime is a *starting condition*, not an assertion that the following day rose/fell.
- **24-hour outcome:** start at first fully post-detection 1H UTC candle. Require **24 consecutive validated closed market OHLC bars**. Price-touch at EP is *hypothetical*, not fill proof. If the EP-touch hour also touches a stop or target, tag **AMBIGUOUS** (unknown ordering). If a subsequent hour touches TP and SL, **AMBIGUOUS**. Otherwise first later-hour TP → `TP_FIRST`, SL → `SL_FIRST`, no entry → `NO_ENTRY`, entry but no exit at 24h → `OPEN_AT_HORIZON`. If any market evidence missing/invalid, mark `UNKNOWN`, never count as loss/zero. 1H intrabar ordering remains unknown.
- **Maturity:** do not publish a candidate outcome before **the end of the 24th complete 1H candle**; first post-detection bar opening at e.g. 13:00 UTC means price coverage through next day 13:00 UTC.
- **Multiple concurrent symbols:** record correlation/day clusters and total nominal stop risk. Three symbol-level observations on a single date are **one correlated calendar market episode**, not three independent market environments.

### 4. Original filter and trade-authority comparison

- Preserve and classify exactly as recorded: `rr_minimum_met`, `participation_confirmed`, `momentum_confirmed`, plus `direction_aligned`, `structure_valid`, `funding_not_extreme`, `data_integrity_min_88`; each one `PASS` / `FAIL` / `MISSING`. Track separately `trade_permission` and `trade_permission_reason` and `decision_trace.blocking_gate`. **trade_permission=false does not equal an execution-quality filter failure**; it may reflect global paper-only controls. Do not weaken any production filter.
- A "fully passed execution-checks" comparison group requires all checked gates present and true. Any gate missing ⇒ `MISSING`, not PASS; retain missingness denominators. If no PASS group, report `NOT_COMPARABLE`. Compare counts, coverage, resolved-only hypothetical P&L and ex-ante stop-distance risk by gate, direction and BTC regime. No causal claims without comparable, predeclared groups.
- Make no changes to R8/R9/R10 sealed science or the separate paper execution profitability cohort; V1.3 is a research-only supplemental observational study.

### 5. Frozen conservative execution-cost sensitivity

- Reference notional **1,000 USDT per hypothetical signal**, **no leverage**, no real orders. Baseline Bitget-standard USDT-futures **taker fee 0.06% each side** of adverse execution notional (0.0006 fractional; not assertion about user's historical fee tier).
- Fee-only (0 bp additional slippage); baseline **5 bp adverse slippage per side**, stress **10 bp per side**. SHORT: entry = EP×(1−s), exit at TP or SL = boundary×(1+s). LONG: entry = EP×(1+s), exit = boundary×(1−s). Quantity = 1000 / EP. Fees charged on both assumed fill prices.
- **No P&L for NO_ENTRY, OPEN_AT_HORIZON, AMBIGUOUS or UNKNOWN**; record unresolved/not-adjudicated separately, not as flat outcomes. Funding, borrow/financing, market impact, historical bid/ask spread, mark-price-based triggers and partial fill execution are UNKNOWN until independently evidenced and are not silently included.
- Output per candidate hypothetical gross, net (all three scenarios), baseline nominal stop distance, nominal R-multiple; per group report `n_all`, `n_entered`, `n_resolved`, `n_unknown`, `n_no_entry`, regime, and denominators. Distinguish **resolved-only**, **candidate-unconditional not estimable with censoring**, and actual `executed_trades=0`.

### 6. Sequential QA gates and stop rules

- Daily read-only evidence must be captured and SHA-256 sealed in **new private QA folders**; preserve immutable V1.0, V1.1, V1.2 manifest/raw files/certificates. No raw private rows, passwords or credentials committed to GitHub. Public research branch may carry **only non-sensitive aggregate counts and source references** after QA.
- Require source continuity, raw market response SHA, signal unique IDs and UTC timestamps; check canonical scanner freshness and parent-child completeness. P0 writer failures, missing candles, unsupported symbol instrument dates, stale source / signal revisions, impossible chronology, or duplicate IDs mean **SOURCE_INCOMPLETE/UNKNOWN** and no success-rate or profitability assertions for affected records.
- Daily review uses **only matured prior dates** and creates no new scanner, no cron, no Render deployment, no Supabase write, no main merge, no live order, no permission change or spending. V1.3 processing must not interrupt the Primary Hourly task or R10 safeguards.
- For independent scientific validation beyond 30 days require **>=30 covered UTC days AND >=100 distinct valid opportunities**, diversity across all three regimes and adequate pass/fail samples, independently reviewed capture/benchmark/QA methodology, and predeclared effective sample-size and uncertainty assessment. Failure to meet thresholds ⇒ `INSUFFICIENT_SAMPLE`, not extrapolated profits. These are minimum research gates; they do NOT supersede R10's independent frozen paper-execution acceptance standards.
- Final research conclusion only after **2026-12-16 00:00 UTC** and independent review. Even any research PASS **NEVER authorizes live trading**, which remains a separate owner-controlled release gate.

### 7. Accountability

Source repository: `lopushniakoleksij-png/Alpha-Hunter`; isolated draft PR #449 branch `research/phase2-signal-investigation-v21`. Frozen date: **2026-11-14**. Decision baseline: V1.2 private replay PASSED, but 7 resolved hypothetical cases in 3 regimes total **−55.290172 USDT** under 5 bp adverse-slippage baseline, two unknown; no independent profitability certification.

**Status at protocol commit: V1.3 PROSPECTIVE / NO FUTURE OUTCOMES OBSERVED.** Existing scanner remains unchanged and sole full-universe producer. Historical universe/cost-fill certification and production/live trading remain **NO-GO**.
