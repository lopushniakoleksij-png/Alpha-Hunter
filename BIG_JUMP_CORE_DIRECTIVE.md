# Alpha Hunter — Big Jump Money Strategy Core Directive

Status: **CORE / PERMANENT RESEARCH & PRODUCTION-DEVELOPMENT DIRECTIVE**

## Mission

Alpha Hunter must continuously investigate materially large crypto price moves across the full Bitget USDT-M futures universe and convert that evidence into a validated, executable strategy for entering major expansions early enough to make money with controlled downside.

The first reconstruction batch (4USDT, SUSHIUSDT, 1000CATUSDT, BUSDT, XANUSDT) is only the starting sample. It is **not** a fixed watchlist. Every future materially informative large mover, LONG or SHORT, must be eligible for investigation and addition to the dataset — including coins never previously surfaced by Alpha Hunter.

## Core question

> At the earliest objectively identifiable point before a major expansion, could Alpha Hunter have entered LONG or SHORT with controlled downside and positive expectancy — and if not, exactly what prevented it?

## Required classification

Every significant mover must be classified as:

- FOUND & TRADED
- FOUND BUT MISSED
- NOT FOUND

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
- Do not weaken live execution safeguards to increase signal count.
- Do not use leverage to compensate for weak edge or poor entry quality.
- Do not modify live trade permission from retrospective evidence alone.
- Production promotion requires explicit forward evidence, regression checks and safety review.

## Continuous scope rule

Every Alpha Hunter universe scan and review process should treat newly completed or developing large expansions as candidate research cases. Add new cases when materially informative, avoid duplicate low-value records, and keep growing the cross-coin dataset over time.

Canonical tracking issue: GitHub Issue #7 — P0 Research: Big Jump Money Strategy / Missed Mover Profit Record.
