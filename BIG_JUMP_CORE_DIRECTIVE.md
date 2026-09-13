# Alpha Hunter — Bitget Futures Big-Mover-First Core Directive

Status: **CORE / PERMANENT RESEARCH & PRODUCTION-DEVELOPMENT DIRECTIVE**

## Mission

Alpha Hunter must be built backward from the actual biggest LONG and SHORT moves in the full Bitget USDT-M futures universe.

The system must continuously identify materially large movers, reconstruct what was objectively visible before expansion, extract repeatable pre-move signatures, and compare the live universe against those signatures so future movers can be surfaced while they are still early enough for controlled-risk execution.

The first reconstruction batch (4USDT, SUSHIUSDT, 1000CATUSDT, BUSDT, XANUSDT) is only a starting sample. It is **not** a fixed watchlist.

## Primary question

> What did the actual Bitget Futures big movers look like before they became obvious movers, which of those features repeat out of sample, and which live coins look like that now while controlled downside and realistic remaining R still exist?

## Big-Mover-First learning loop

**ACTUAL BITGET MOVERS → RECONSTRUCT PRE-MOVE STATE → LEARN LONG/SHORT SIGNATURES → COMPARE LIVE UNIVERSE → RANK EARLY CANDIDATES → SHADOW OUTCOME → FEED VERIFIED EVIDENCE BACK**

Every protected universe cycle should preserve the distinction between:

1. **Ground truth:** actual current/recent Bitget USDT-M Futures biggest gainers and losers.
2. **Historical reconstruction:** what was visible at T−24h, T−12h, T−6h, T−3h, T−1h, ignition, breakout and expansion.
3. **Live prediction:** which not-yet-obvious coins most resemble validated pre-move signatures now.

Historical explanation must never be presented as forward predictive evidence unless it survives control samples and out-of-sample testing.

## Required mover classification

Every material mover must be classified as exactly one of:

- **FOUND & TRADED**
- **FOUND BUT MISSED**
- **LATE DETECTED**
- **NOT FOUND**
- **NOT AUDITABLE**

A miss must also identify the primary failure class where evidence allows:

- discovery
- direction
- readiness gate
- entry timing
- stop / management
- data quality

## Required reconstruction record

For each material mover, persist and analyze:

- symbol and direction
- first Alpha Hunter detection timestamp
- T−24h / T−12h / T−6h / T−3h / T−1h snapshots where evidence exists
- earliest objectively detectable anomaly
- earliest evidence-backed LONG / SHORT bias
- earliest objectively identifiable controlled-risk entry window
- entry price / zone and structural invalidation
- lifecycle state
- 1H / 12H / 1D / 1W directional context where available
- participation acceleration: turnover/volume, OI, persistence, relative strength/weakness
- liquidity/executability: spread, depth, slippage risk, mark/index alignment, venue anomalies
- price acceptance: breakout hold, retest quality, HL/LH structure, continuation participation
- taker/order-flow imbalance when available
- funding and funding change
- spot-perp confirmation when available
- volatility compression → expansion behaviour
- sweep / reclaim / acceptance evidence
- liquidation / squeeze conditions when available
- catalyst / narrative context when available
- exact gate, score, threshold, or rule that blocked or delayed execution
- maximum adverse excursion (MAE) before expansion
- maximum favorable excursion (MFE)
- realistic stop / invalidation
- leverage survivability under normal pullback behaviour
- remaining realistic R at each decision point
- confirmation tax: price/R lost while waiting for extra confirmation
- theoretical PnL versus realistically achievable PnL after fees, slippage and survivability constraints
- final lesson for the Money Entry Engine and live scanner

## Lifecycle

Use the common mover lifecycle:

**PRE-MOVER → IGNITION → EXPANSION → EXTENDED**

- **PRE-MOVER:** abnormal behaviour exists before an obvious directional repricing.
- **IGNITION:** direction is becoming measurable and a controlled-risk entry may still exist.
- **EXPANSION:** the move is underway; new entry is retest-only and must still pass remaining-R / no-chase checks.
- **EXTENDED:** research/management state; do not create a fresh chase entry.

The primary new-entry research zone is PRE-MOVER / IGNITION plus a controlled first retest when evidence supports it.

## Separate LONG and SHORT models

LONG and SHORT expansions must be learned and ranked separately. Do not assume a downside liquidation cascade has the same precursor structure as an upside squeeze or accumulation-driven breakout.

## Signature engine

The Big-Mover Signature Engine is the bridge between missed-mover research and live discovery.

Its first shadow implementation must:

1. learn directional feature profiles only from **pre-expansion** mover snapshots;
2. require **false-positive / non-mover controls** so hindsight winners cannot define the model alone;
3. derive feature importance from observed mover-vs-control separation rather than adding new hand-written weights;
4. compare live LONG and SHORT candidates with the corresponding learned signature;
5. expose similarity, feature coverage, lifecycle, evidence contributions and blockers;
6. keep `shadow_only=true` and `trade_permission=false`;
7. never turn an EXTENDED candidate into a new-entry queue item.

The signature score is a research-ranking signal, **not** a trade authorization and not a claimed probability of profit.

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
- LONG and SHORT signature performance separately
- MAE distribution before expansion
- MFE distribution
- confirmation tax by gate
- R available at first detection versus READY state
- percentage of proposed entries surviving realistic stop/leverage assumptions
- realized/shadow expectancy after fees and slippage
- false-positive rate
- opportunity cost
- feature coverage and signature stability over time

## Relationship to Money Entry Engine

This is a core evidence stream for the Money Entry Engine. The system must ultimately answer both:

1. Which live coin is showing a repeatable pre-expansion signature?
2. Where can Alpha Hunter enter with a stop/leverage combination that survives normal pullbacks while preserving positive expectancy?

The objective is to identify and queue opportunities before most of the move is consumed by confirmation.

## Production safety boundary

- Keep signature learning/ranking research/shadow-only until validated.
- Do not weaken live execution safeguards to increase signal count.
- Do not use leverage to compensate for weak edge or poor entry quality.
- Do not modify live trade permission from retrospective evidence alone.
- Do not allow signature similarity to bypass liquidity, direction, structural invalidation, remaining-R, no-chase or position-conflict gates.
- Production promotion requires explicit forward evidence, regression checks and safety review.

## Continuous scope rule

Every Alpha Hunter universe scan and review process should treat newly completed or developing large expansions as candidate research cases. Add new cases when materially informative, avoid duplicate low-value records, and keep growing the cross-coin dataset over time.

Canonical tracking issue: GitHub Issue #7 — P0 Research: Big Jump Money Strategy / Missed Mover Profit Record.
