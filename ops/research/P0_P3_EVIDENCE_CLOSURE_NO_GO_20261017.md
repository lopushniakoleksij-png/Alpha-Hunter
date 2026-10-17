# Alpha Hunter P0–P3 forensic completion and promotion NO-GO record

**As of 17 October 2026 — verification and independent acceptance are different gates.**

This document is a research-only readout. No production deployment, migration, new paper admission, orders, historical trade rewrite, or sealed-outcome read is authorized. Script: `ops/research/p0_p3_readonly_acceptance_audit_v01.sql`.

## P0 — Historical execution evidence (historical reconstruction complete, executable-source proof missing)

- Frozen original legacy cohort: **32** completed modeled paper exits (29 STOP_LOSS, two TAKE_PROFIT, one HORIZON_24H); original modeled outcome chronology untouched.
- [Research PR #363](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/363) retrieved complete public Bitget 1-minute market-candle paths for 32/32 entries; inferred first protective touch agrees with recorded reason for 28, disagrees for EVAA (first market candle TAKE_PROFIT but recorded STOP_LOSS), two entry-minute cases are unorderable, one horizon case has no prior protective touch. These are **bar-level** inferences only.
- Among 29 unambiguous first protective touches, median first-touch-to-observed-paper-exit is ~17.44 minutes, 11 above 35 minutes, six above 24 hours. This lag is NOT the scheduler's R9 max-gap metric.
- For the same original 32, 4,302 archived exit observations capture bid/ask and sizes but **1,452 lack a quote_source identifier**. All 4,302 report `captured_quote_only=true`, no independent exchange requests added. R8 depth shadow contains zero archived rows; five R9 depth timing captures have **zero matching original 32 entry_order IDs**. Ordinary hash of downloaded candle bytes is not an independently attested historic exit-side top of book.
- Therefore **historical price-path reconstruction: completed**; **independent quoted executable depth and actual fills: NOT VALIDATED / NO-GO**. No claim of 32/32 fill verification and no retroactive outcome changes.

## P1 — Direction audit (retrospective research complete, independent review pending)

- 14 S2 historical LONGs lost; nine `DISTRIBUTION_RISK` all lost. 12H/1D/weekly descriptive public-market reconstructions with BTC/ETH for 31/32 decision-time windows, using closed-before-entry bars only.
- MARSCOINUSDT lacked the contract history for 50 daily / ten weekly research descriptors: only 33 closed daily and four completed UTC weekly bars existed before its early-October entry. This is **INSUFFICIENT_PRE_LISTING_HISTORY**, not a permissible zero/future fill.
- On the defined retrospective moving averages, both big winning SHORTs MEGA/WLD appear bullish on 12H/1D. Do not implement a simple filter that would selectively delete these winners. The original signal snapshots only recorded 15m,1H,4H; reconstructed higher timeframes were NOT original inputs.
- **Research reconstruction: completed with 1 explicit unavailable case**. Scientific counterfactual impact and independent approval: NOT completed.

## P2 — Stop/target evidence (historic descriptive geometry complete; forward scientific evaluation sealed)

- Legacy 29 STOP_LOSS orders had median stop distance **1.782%**, approximately **1.005 times 1H ATR**; nine within 1H ATR and 25 within 4H ATR. Historical winners had similar stop-to-ATR scaling; do not reflexively widen stops.
- Of 23 losing LONGs, **21** had stop price above captured 4H support; all **six** losing SHORTs had stop price below recorded 4H resistance. Critically **both large winning SHORTs** also had stops below that resistance. Captured support/resistance are indicative context, not independently certified structural invalidation points or evidence that wider stops pay.
- **Existing distinct prospective geometry holdout** (spec `AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01`) is already collecting since 20 Sep with planned end 19 November 2026: 30,697 captures / 3,915 eligible / 447 symbols / 23 UTC days / 1,837 LONG + 2,078 SHORT, capture gate marked met, **scientific conclusion NONE**, outcome access not authorized by protocol before freeze. This existing study compares 15m stop/4H target versus 1H baseline, NOT an approved successor execution/cost strategy.
- Separate directional holdout v02 likewise still collecting with blinded primary outcomes until 19 Nov; cannot borrow 287 test / 233 control pool records for the new scientific strategy.
- Execution-cost readiness: 270 coarse benchmark rows and 293 fee observations do NOT establish realistic slippage. **Zero verified Alpha Hunter executions, zero verified exit slippage, no fully bound funding path, cost model activation false**.
- **Descriptive geometry: completed. Prospective P2 trial: actively collecting independently frozen data; outcome validation blocked until correct preregistered release and separate source/fee validation.**

## P3 — Successor holdout (scientific contract tested, evidence NOT complete)

- Research PR #364 provides an isolated, nonauthoritative forward acceptance contract: after independently authorized preregistration, post-R9 prospective paired candidate evaluation, immutable baseline and successor identity, nonmissing bid/ask/depth/fill/funding/protection custody, and at least 230 completions, 60 symbol clusters, 20 UTC-day clusters; both symbol-equal and day-equal positive LCBs after costs.
- Those requirements are for a **new, separately registered successor** and **cannot be met** by the 32 legacy exits, the later seven correlated QUSDT legacy take-profits, the current sealed R9 zero-completion experiment, or the old geometry holdout.
- No independently approved new successor cohort or genuine qualifying forward completion exists. Positive scores from synthetic unit tests NEVER authorize production or demonstrate profit.
- Qualified independent risk, DBA/security, scientific and operations approvals are still not granted; [Issue #361](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/361) contains the open external review request.

## Immutable protection / next decisions

1. Maintain sealed R9 4 Oct–3 Nov window, primary hourly scanner, 35-minute monitoring limit, active protective management, admission halt, current legacy outcomes and no live execution authority.
2. Source/depth custody team and independent reviewers must either produce **contemporaneous, independently verifiable historical source material** or explicitly fail-close those historical fill proofs as unrecoverable; later synthetic reconstruction cannot make them authentic.
3. Keep existing Sept–Nov 19 geometry/direction outcome studies sealed. Await their preregistered analysis release; do not read primary outcomes now or switch their denominator, hypothesis, time windows or sample policy.
4. An independent risk and scientific board must authorize exact new prospective successor protocol *before* any P3 activation. Required evidence will take real elapsed market time; cannot be manufactured by software tests.

**Current final strategy-change verdict: NO-GO.** All PRs draft/unmerged. Source report is a bounded engineering deliverable, not a P0–P3 scientific signoff.
