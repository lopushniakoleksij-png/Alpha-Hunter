# P2 sealed geometry study: capacity shortfall — independent no-peeking decision package

**Date:** 17 October 2026, read-only Supabase + original `main` SQL.
**Scope:** `AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01` ONLY, original study registered 2026-09-20 00:29:06.132018 UTC and planned to end **2026-11-19 00:29:06.132018 UTC**.
**Authority:** NONE. Do not merge or deploy this PR; no production cron/scheduler/DB writes, no market orders, no scientific unsealing or result access, no new spending.

## Newly confirmed operational evidence

- Study captured **30,697** candidate bindings, **3,915 eligible**, 26,782 excluded, no capture failures.
- Operational status `alpha_hunter_geometry_holdout_collection_status_v01` reported **15,816 sealed research rows**, comprising **3,954 complete binding/horizon sets**, with primary-results-exposed=false. These are aggregate operational counts, NOT per-variant outcomes or permission to analyse a hypothesis.
- `ELIGIBLE` bindings' original decision timestamps and exact protocol maturity rule (`decision_available_at_utc + 12H or 24H + 5min`) yield at snapshot **2026-10-17 01:30:43 UTC**: **3,866 due 12H sets**, **3,759 due 24H sets** = **7,625 due binding/horizon sets** in all.
- Given 3,954 recorded complete sets overall, at least **3,671 due sets lack completion as of the snapshot**, on aggregate. This subtraction does NOT identify which bindings have an output, whether an attempted evaluation occurred, or what any sealed results mean.
- Existing scheduler `cron.job` name `alpha-hunter-geometry-holdout-sealed-hourly` (MISLEADING NAME) is **actually configured `38 */6 * * *`**, active. The current evaluator function `private.alpha_hunter_run_geometry_holdout_sealed_v01()` selects **at most 40 binding/horizon sets per call**, so the currently scheduled four calls/day have a theoretical ceiling of **160 sets/day** before failures/timeouts.
- Original prospective eligible intake in the preceding seven rolling days is **1,330 bindings**, each creating two horizons; roughly **380 new horizon sets/day** on the trailing-seven-day average, **220/day above the current scheduled capacity**, if that rate persists.
- The existing **3,671-set** aggregate deficit requires **at least 23 days** even at 160 full completions/day **with zero further intake**. This lower bound ignores later entries, follow-up retries and market data retention. Do not present a fabricated catch-up ETA.
- Cron run history shows **261 recorded executions** since Sept 20, **258 succeeded and 3 non-success**, last run Oct 17 00:38 UTC. Those historical invocation counts do NOT establish a constant historical 4/day rate: the current schedule is the fact being assessed. A cron `succeeded` indicates the SQL call returned, NOT 40 valid completed sets.
- Previous [draft #366](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/366) confirms 218 failure events on 27 distinct bindings, 47 eligible non-ASCII symbols at systematic source-rejection risk, and 4,225 opposite-direction candidate pairs sharing their source capture. These are *additional distinct risks*; retry events are not independent candidates.

## Independent scientific and operational review needed BEFORE considering an intervention

**The active protocol stays untouched for now.** Any proposed change to cron, batch size, concurrency, evaluator behavior, endpoint, history source, symbol encoding or missing-data treatment requires:

1. **Independent scientific reviewer**, named and accountable: determine if an operational-only capacity restoration, using the *unchanged* frozen spec, evaluator, data source and per-binding processing logic, is permitted by pre-registered versioning. Explicitly decide no-lookahead/reproducibility constraints, interval between due and evaluation, censoring, survivor bias, source-independence and exact unchanged study denominator. If this cannot be supported, record `NO-GO / INCONCLUSIVE` rather than modifying the protocol or reading outcomes.
2. **Independent DBA/security reviewer**: reproduce the current `SELECT` census, inspect isolated PostgreSQL 16/17 test evidence, estimate Supabase resource/timeout/locks, permissions, HTTP data request rate and bounded cost of any proposed throughput option. Privileged operations require separate authorization and rollback plan; no cron edits without a signed risk approval.
3. **Independent execution/source reviewer**: verify that Bitget public 3m market data source/candle coverage remains authoritative for historical due horizons, especially if processed late. Later snapshots or server-side market candles never become authenticated historical filled trades or validated execution costs.
4. **Independent operations reviewer**: independently verify the Primary Hourly discovery and managed paper positions are unaffected, sealed R9 Oct4–Nov3, frozen 35min cap, admissions halted, no live authority, and no active study resets.

### Review decision branches (hypotheses, NOT authorized actions)

- **A. Separately approved operational throughput correction:** preserve original exposure/spec, ID/clock, source quote path, per-binding deterministic outcomes and missingness log; prove in isolated database that throttling/retry, concurrency and external HTTP behavior are safe; obtain written protocol compatibility approval before any production cron change.
- **B. Independent archive-based recovery** where allowed by protocol: only prove against the original source and independently verifiable full-window public market data, preserve provenance and missingness, no retrospective reinterpretation.
- **C. No trustworthy recovery:** keep incomplete/censored records visible, perform preregistered missing-not-at-random sensitivity analysis when permitted, report **inconclusive** if scientific power/coverage inadequate.

## P3 boundary

This original September geometry holdout is NOT the new P3 successor profitability experiment. PR #364’s **230 genuinely completed prospective candidate pairs / 60 symbols / 20 UTC days**, with independently bound execution costs and both symbol/day lower confidence bounds, remains unstarted without separate preregistration and approvals. Do not count any P2 collection rows toward P3.

**Verdict:** substantive P2 evaluator **throughput/censoring NO-GO**. Do not consider the study evaluable merely because it passes original entry capture quotas. Scientific primary results remain sealed. Request independent reviewer via [Issue #361](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/361); reviewer identity and signoff still NOT PROVIDED.
