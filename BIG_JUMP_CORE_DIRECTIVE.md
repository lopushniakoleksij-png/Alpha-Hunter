# Alpha Hunter — Big Jump Money Strategy Core Directive

Status: **CORE / PERMANENT RESEARCH & PRODUCTION-DEVELOPMENT DIRECTIVE**

## Mission

Alpha Hunter must continuously investigate materially large crypto price moves across the full Bitget USDT-M futures universe and convert that evidence into a validated, executable strategy for entering major expansions early enough to make money with controlled downside.

The first reconstruction batch (4USDT, SUSHIUSDT, 1000CATUSDT, BUSDT, XANUSDT) is only the starting sample. It is **not** a fixed watchlist. Every future materially informative large mover, LONG or SHORT, must be eligible for investigation and addition to the dataset — including coins never previously surfaced by Alpha Hunter.

## Core question

> At the earliest objectively identifiable point before a major expansion, could Alpha Hunter have entered LONG or SHORT with controlled downside and positive expectancy — and if not, exactly what prevented it?

## Big-Mover-First production-development architecture

The core learning loop is:

**ACTUAL BITGET MOVERS → PRE-MOVE RECONSTRUCTION → LONG/SHORT SIGNATURE LEARNING → LIVE UNIVERSE SIMILARITY RANKING → CONTROLLED ENTRY RESEARCH → FORWARD OUTCOME → LEARN**

The system must not treat mover research as a side report disconnected from discovery. The mover outcome stream is the empirical answer key for improving the scanner.

### Ground truth

Every hourly shadow evidence cycle records the full Bitget USDT-M mover answer key at canonical ±5%, ±10% and ±20% 24h thresholds. This ground truth is independent of whether Alpha Hunter surfaced the symbol.

### Pre-expansion training only

A feature snapshot may train the Big-Mover Signature Engine only while the symbol remains below the canonical 5% mover boundary in absolute 24h movement. Post-expansion snapshots must never be used to explain a move after it happened.

### Mover versus false-positive controls

For the first forward horizon:
- **MOVER:** same-direction ≥10% outcome inside the following 24h.
- **CONTROL:** no same-direction ≥5% outcome inside the following 24h.
- **GREY:** 5–10% outcomes are excluded from binary training rather than forced into either class.

False-positive/non-mover controls are mandatory. Winners alone are invalid training evidence.

### Direction

LONG and SHORT signatures are learned independently. The Big-Mover research layer scores every captured symbol in both directions. A legacy scanner direction may be retained as context but cannot prevent the research layer from evaluating the opposite direction.

### Lifecycle and money priority

Operational lifecycle:

**PRE-MOVER → IGNITION → EXPANSION → EXTENDED**

New-entry research must prioritize:
1. genuine early 1–5% ignition,
2. PRE-MOVER states below 1%,
3. only then later 5–15% ignition when remaining-R still exists.

EXPANSION is retest-only research. EXTENDED is no-chase / research-management only.

### Learned feature weighting

Feature importance must be derived from observed separation between real movers and controls plus feature coverage. Do not add arbitrary feature weights merely to increase signal count. Learned similarity is a research ranking, not a probability of profit and never grants trade permission.

## Required classification

Every significant mover must be classified as:

- FOUND & TRADED
- FOUND BUT MISSED
- LATE DETECTED
- NOT FOUND
- NOT AUDITABLE

## Required reconstruction record

For each material mover, persist and analyze:

- symbol and direction
- first Alpha Hunter detection timestamp
- earliest objectively identifiable entry window
- entry price / zone
- lifecycle state
- 1H / 4H / 12H / 1D directional context where available
- participation acceleration: turnover/volume, OI, persistence, relative strength/weakness
- liquidity/executability: spread, depth, slippage risk, mark/index alignment, venue anomalies
- price acceptance: breakout hold, retest quality, HL/LH structure, continuation participation
- exact gate, score, threshold, or rule that blocked or delayed execution
- maximum adverse excursion (MAE) before expansion
- maximum favorable excursion (MFE)
- realistic stop / invalidation
- leverage survivability under normal pullback behavior
- remaining realistic R at each decision point
- confirmation tax: price/R lost while waiting for extra confirmation
- theoretical PnL versus realistically achievable PnL after fees, slippage and survivability constraints
- final lesson for the Money Entry Engine

## Dataset design

Do not study winners alone. The dataset must include:

1. materially large movers (for example +20%, +30%, +50%, +100% or comparable downside moves), and
2. false positives / non-movers that displayed similar early signatures but failed to expand.

This is required to control hindsight bias and measure precision, recall, expectancy, drawdown cost and false-positive cost.

The growing sample should span different market regimes, liquidity tiers, sectors, weekdays/weekends, move sizes, directions and lifecycle paths where evidence exists.

## Strategy-development loop

**COLLECT → RECONSTRUCT → FIND REPEATING PATTERNS → BACKTEST → WALK-FORWARD TEST → SHADOW TRADE → MEASURE EXPECTANCY → PROMOTE ONLY VERIFIED RULES**

No rule may be promoted because it explains past winners. Promotion requires cross-coin and out-of-sample evidence showing improved forward expectancy without unacceptable adverse selection, false positives, liquidation risk or drawdown.

## Key metrics

Track at minimum:

- detection recall of major movers
- precision of early-entry candidates
- MAE distribution before expansion
- MFE distribution
- confirmation tax by gate
- R available at first detection versus READY state
- percentage of proposed entries surviving realistic stop/leverage assumptions
- realized/shadow expectancy after fees and slippage
- false-positive rate
- opportunity cost

## Relationship to Money Entry Engine

This is a core evidence stream for the Money Entry Engine. The engine must ultimately answer both:

1. Which coin is showing a repeatable pre-expansion signature?
2. Where can we enter with a stop/leverage combination that survives normal pullbacks while preserving positive expectancy?

The objective is to identify and queue opportunities before most of the move is consumed by confirmation.

## Production safety boundary

- Keep this work research/shadow-only until validated.
- `shadow_only=true` is mandatory for this development path.
- `trade_permission=false` is mandatory and is enforced in both code and database constraints.
- Do not weaken live execution safeguards to increase signal count.
- Do not use leverage to compensate for weak edge or poor entry quality.
- Do not modify live trade permission from retrospective evidence alone.
- Production promotion requires explicit forward evidence, regression checks and safety review.
- The protected P0 Primary Hourly execution cycle remains independent and must not be paused or replaced by this shadow research loop.

## Forward evidence transition

Historical missed-mover audit data may bootstrap the model. Fresh Bitget all-ticker mover answer-key observations are the canonical forward source going forward.

During the first 24 hours of answer-key collection, absence of a mover event must **not** be interpreted as a control. Only snapshots whose complete forward horizon is covered may receive answer-key mover/control labels. Once coverage exists, the fresh answer-key stream becomes authoritative for overlapping timestamps.

## Current implementation milestone — 2026-09-13

PR #12 implements the first production-evidence shadow path:
- mover/control signature learner
- real Supabase evidence adapter
- LONG/SHORT live similarity ranking
- early-mover priority
- append-only Bitget full-universe mover answer key
- persistent shadow ranking table
- automatic forward-source cutover logic
- fail-closed CI tests and database constraints
- database-native Supabase hourly runtime committed as `big_mover_supabase_runtime.sql`

PR #13 connects Big-Mover discovery to Money Entry research without granting execution:
- explicit raw versus direction-normalized 24h movement
- isolated public-Bitget 12H/1D parent-direction shadow collection
- parent-direction alignment without changing the legacy 15m/1H/4H state machine
- fail-closed scanner-direction and execution-geometry blockers
- deterministic model-version handling
- Supabase production-evidence sequence at :10 → :11 → :12

The hourly production-evidence loop is **ACTIVE in Supabase**. It fetches public Bitget data and runs without a notebook, laptop, Bitget private credential, or GitHub Actions production scheduler.

No execution permission is promoted by these milestones.

## Forward Money Scorecard milestone — 2026-09-13

The production-evidence shadow runtime now includes a forward Money Scorecard at **14 minutes past every hour**, after the :10 Big-Mover cycle, :11 parent-direction cycle and :12 Money Entry bridge.

For every PRE-MOVER/IGNITION `SHADOW_QUEUE` bridge candidate, the scorecard freezes an append-only candidate snapshot and creates four forward horizons: **1H, 4H, 12H and 24H**.

Forward path measurement uses public Bitget **3-minute market candles**, allowing up to 480 path observations over 24 hours. The scorecard measures:
- frozen entry, stop, target and structural geometry
- stop survival
- MAE and MFE
- +3%, +5% and +10% favorable-move hits
- direction-adjusted horizon return
- stop-first / target-first / open-at-horizon path resolution
- explicit ambiguous handling when stop and target occur in the same 3-minute candle
- path R before execution costs
- remaining structural R
- legacy DETECTION → EMERGING → CONFIRMED confirmation-tax linkage only when symbol, direction and episode timing match
- explicit placeholders for T0/T1/T2 path outcomes
- explicit placeholder for cost-adjusted realistic net R

The first live seed persisted **34 candidates and 136 horizon records**. Fourteen candidates had direction-valid entry/stop/target geometry and twenty did not; invalid geometry is retained as false-positive evidence rather than silently discarded. Candidate and outcome safety violations were zero.

The scorecard must not manufacture evidence:
- Exact `T0/T1/T2` results stay `NOT_EVALUABLE` until exact stage snapshots exist.
- `realistic_net_r` stays withheld until a verified execution-cost model exists; `path_r_pre_cost` is recorded separately.
- Same-candle stop/target conflicts are marked ambiguous rather than choosing a favorable ordering.
- Candidate snapshots are append-only.
- `shadow_only=true` and `trade_permission=false` remain mandatory.

The next evidence gate is to let the 1H/4H/12H/24H cohorts mature, then compare early-candidate precision, stop survival, MAE/MFE, remaining-R, confirmation tax, false-positive cost and path R before deciding exactly one measured strategy change.

## Continuous scope rule

Every Alpha Hunter universe scan and review process should treat newly completed or developing large expansions as candidate research cases. Add new cases when materially informative, avoid duplicate low-value records, and keep growing the cross-coin dataset over time.

Canonical tracking issue: GitHub Issue #7 — P0 Research: Big Jump Money Strategy / Missed Mover Profit Record.
