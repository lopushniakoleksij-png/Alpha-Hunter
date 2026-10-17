# Independent P2 capacity restoration signoff dossier — NOT APPROVED

**Prepared 17 Oct 2026; research only; zero production authority.**
Study: `AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01` running 20 Sep to **19 Nov 2026 00:29:06.132018 UTC**.
Original spec hash: `5855cc635a5f1442138a32e840eaf9d9645771a5bef77007d6baf7b46213f194`.
Frozen hypothesis `H_15M_STOP_4H_TARGET_Q5_PATH_VS_1H_BASELINE_24H_V1`: do not change primary endpoint, paired geometry, 12/24-hour horizons, recruitment denominator, direction policy or protocol time boundaries. R9 is a separate sealed test (Oct4–Nov3); no admissions, trading authority or risk-limit change.

This is a real decision request for two **separate, qualified human reviewers**, not a ChatGPT signoff or a CI promotion. Source: [P2 capacity incident #368](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/368), [draft #367](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/367), censoring review [draft #366](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/366). GitHub review status: **NO APPROVAL RECORDED** at dossier preparation. Signature fields below must stay empty until each independent human approves on the matching PR/issue.

## A. Verified operational evidence and competing throughput assumptions

Read-only verified 2026-10-17 01:59:49 UTC: eligible 3,915; 12H due 3,866; 24H due 3,759; due total 7,625; operational completed sets 3,954; **aggregate completion deficit 3,671**. Observed trailing seven days: **1,330 additional eligible bindings**, thus (1330×2÷7 = 380) newly generated horizon sets/day on average. Worker selected `LIMIT 40`; actual **cron schedule `38 */6 * * *`**, four calls/day, theoretical **160 sets/day**. The cron job name has "hourly" but its present real schedule is every six hours. These counts are operational aggregate metadata, **never individual sealed scientific outcomes**.

This is not necessarily proof all missing sets are permanently unobservable. Individual failures (218 retries/27 distinct affected bindings; 47 eligible non-ASCII source symbols; 4,225 same-symbol two-way LONG/SHORT shared source IDs) and future missingness require protocol-preserving treatment. No access to sealed outcomes has occurred.

At constant recent intake, the theoretical schedule-only options with **unchanged 40 maximum selections per call**, no new infrastructure, and hypothetical successful completion fractions are:

| Interval | Max selected sets/day | Hypothetical yield | Assumed completions/day | Net backlog reduction/day at 380 new/day | Projected catch-up |
|---|---:|---:|---:|---:|---|
| Existing 6h | 160 | 100% | 160 | −220 | Never at sustained intake |
| 2h proposal (NOT approved) | 480 | 100% | 480 | 100 | 36.71 days, after study endpoint |
| Hourly proposal (NOT approved) | 960 | 50% | 480 | 100 | 36.71 days, after study endpoint |
| Hourly proposal (NOT approved) | 960 | 60% | 576 | 196 | ~18.73 days; mathematically possible |
| Hourly proposal (NOT approved) | 960 | 80% | 768 | 388 | ~9.46 days; mathematically possible |

**These are scenarios, NOT performance observations, permission to change the schedule, a deadline promise or sufficient proof of data recoverability.** They ignore market data history coverage, upload latency, Cron concurrency/locks, provider validity, hidden error mixing, API 429s, network timeouts, downstream CPU, Supabase fees and future intake spikes. In particular, current Bitget V3 public **/api/v3/market/candles** claims up to 1,000 3-minute bars and 20 requests/s/IP; real venue continuity and historical-window coverage for late evaluations remain unverified and require separate testing. Official public source: https://www.bitget.com/docs/catalog/market/market-data. Provider market candles do not prove actual exchange fills.

**CRITICAL: even a cron-only change may alter science.** The frozen evaluator has a retry branch `v_prior_failures>=3 and clock_timestamp()>horizon_due+interval '6 hours'` that seals `DATA_INSUFFICIENT`. A synthetic always-failing binding due at 00:00, with cron at :38, reaches terminal at **12:38** on the current six-hour schedule but **06:38** with hypothetical hourly runs. Error count and missingness treatment can therefore differ despite unchanged formula. This is why scientific, not merely DBA, approval must precede intervention.

## B. Independent scientific protocol decision — signer mandatory

**Reviewer identity (GitHub username + qualifications): UNASSIGNED**
**Decision: PENDING.** Choose exactly one:
- `APPROVE_COMPATIBLE_OPERATIONAL_RESTORATION`: after independently verifying this is allowed by *original preregistered protocol* with **unchanged** enrollment, cutoffs, outcomes and analysis plan, and documenting an enforceable remedy for retry-dependent missingness and lagged source data.
- `REQUIRE_DISTINCT_PRE_REGISTERED_REPLACEMENT`: the current study is maintained to November 19 unchanged; any hourly cadence study needs a separately frozen **successor research spec**, not retrofitted controls to this one.
- `REJECT_REPAIR_REPORT_INCONCLUSIVE`: continued biased/unrecoverable observations; retain censored candidates and report negative or inconclusive outcomes under authorized future analysis.

The reviewer must explicitly evaluate whether a schedule change can change the frozen observation process, survivorship/missing-not-at-random sensitivity for non-ASCII symbol censoring, 4,225 paired LONG/SHORT source IDs, UTC-day/symbol/source clustering, revised deadlines and retention, prospectively complete first-touch public-candle evidence, and whether any observed-cost performance claim is scientifically inadmissible. **The reviewer must neither peek at primary sealed outcomes nor approve a new strategy from this research audit.**

Signature requirement: a qualified nonauthor reviewer posts a GitHub `APPROVE` or `REQUEST_CHANGES` review on the exact changed commit and comments the selected decision, dated UTC, credentials/scope, evidence limitations, and immutable SHA. Silence, an open issue, GitHub CI green or an AI comment is not approval.

## C. Independent DBA/security/operations decision — signer mandatory

**DBA/security reviewer identity (GitHub username + qualifications): UNASSIGNED**
**Decision: PENDING.** Require:

- Repeat exact read-only due/capture/cron audit, map `LIMIT 40`, `FOR UPDATE` or advisory locks and unique row constraints; reproduce idempotent replay including ambiguous response and retry-safe transaction commit/rollback in isolated PostgreSQL 16 and 17. The existing research #362 synthetic atomic exit tests do **not** validate this separate sealed geometry evaluator.
- Isolated load testing of an unchanged `LIMIT 40` evaluator driven at hypothetical 6h, 2h, 1h cadences, with measured real elapsed time, simulated provider timeout, rate limiting, multi-run conflicts, DB connections, private sealed table grants and provider source pagination/age. No production side effects, no real unseal and no new paid resources.
- Verify future `/api/v3/market/candles` interval boundaries, 3m max 1,000, complete 12H/24H path, independent request/response custody and source provenance. Partial, stale or impossible history must remain `DATA_INSUFFICIENT`, not synthetic success.
- Written new-infrastructure cost impact with **$0 new expenditure by default**, explicit user approval for any expense. Verify Primary Hourly and protected managed positions unaffected, frozen R9 monitor cap 35 minutes, admission halt, no live orders.
- Stage exact previous `cron.job` state and rollback method; choose metric thresholds BEFORE execution (e.g., 6h observation lag distribution, failure rate, per-run complete sets, DNS/HTTP errors) and fail-closed rollback/stop criteria for any separately authorized change. No rollback should remove sealed evidence, delete original errors or restart the test.

**DBA signoff is neither scientific signoff nor permission to deploy.** Exact DBA approval and separate risk/operations authorization must each be recorded before even requesting a scoped production change. If one signer is missing, **NO-GO**.

## D. Final operational freeze / actual decision

- Scientific signoff: **NOT_GRANTED**
- DBA/security signoff: **NOT_GRANTED**
- Risk/operations signoff: **NOT_GRANTED**
- Cost commitment: **NONE**
- Production P2 evaluator or cron change: **NONE**
- P2 result unseal, primary analysis or denominator rewrite: **FORBIDDEN**
- New successor P3 230/60/20 profitability gate: **SEPARATE / NOT ACTIVATED**
- R9 experiment, original paper positions, Primary Hourly, 35m cap, paper admission halt and live authority: **UNCHANGED**.

Deadline for obtaining an external decision: **before 19 November 2026**. No real independent reviewer identities are currently established; send the exact GitHub usernames of one qualified scientific reviewer and a separate DBA/security reviewer to request formal GitHub review. The study cannot legitimately be promoted just because this dossier is complete.
