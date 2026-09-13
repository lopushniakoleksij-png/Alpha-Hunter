# Alpha Hunter — Bitget Futures Big-Mover-First Architecture

Status: **CORE STRATEGY / SHADOW IMPLEMENTATION V0.1**

This document extends `BIG_JUMP_CORE_DIRECTIVE.md`. The research target is no longer a generic collection of technically attractive coins. The system must work backward from the actual largest Bitget USDT-M Futures movers and use their pre-move evidence to rank the live futures universe before the move becomes obvious.

## Primary loop

**BITGET BIG MOVERS → PRE-MOVE RECONSTRUCTION → MOVER/NON-MOVER COMPARISON → EMPIRICAL LONG/SHORT SIGNATURES → FULL-UNIVERSE SHADOW SCORING → ENTRY RESEARCH → OUTCOME → LEARN**

### 1. Ground-truth answer key

For each protected cycle, preserve the actual materially important Bitget USDT-M Futures gainers and losers as the answer key. Completed movers become research cases; similar-looking coins that did not expand become controls.

### 2. Reconstruct before expansion

For every auditable mover reconstruct the evidence available at:

- T-24h
- T-12h
- T-6h
- T-3h
- T-1h
- ignition
- expansion/current state

No hindsight feature may be inserted into an earlier snapshot.

### 3. Learn rather than guess feature importance

Compare mover snapshots with non-mover controls. Candidate inputs include, where recorded:

- turnover/volume acceleration
- open-interest acceleration
- relative strength/weakness versus BTC/ETH/sector/universe
- volatility compression/transition
- funding and funding change
- structure proximity
- taker/order-flow imbalance
- spot/perp confirmation
- liquidity/spread/sweep/reclaim/acceptance
- liquidation/squeeze conditions
- catalyst/narrative context

Feature weights must come from observed mover-versus-control separation and later forward validation. Do not promote a hand-set feature weight merely because it explains past winners.

### 4. Separate LONG and SHORT signatures

Maintain independent LONG-mover and SHORT-mover models. A squeeze-driven upside expansion and a downside liquidation cascade are not assumed to share the same precursor signature.

### 5. Score the verified futures universe early

The learned signature layer should score every **verified active Bitget USDT-M Futures** symbol that clears hard data, liquidity, and safety eligibility. It must **not** inherit legacy `READY`, pre-move, or execution-readiness gates as a prerequisite for research scoring; doing so would reproduce the same discovery blind spot we are trying to measure.

This does **not** grant execution permission. The v0.1 signature engine is shadow-only and always emits `trade_permission=false`.

### 6. Lifecycle

Use the research lifecycle:

**PRE_MOVER → IGNITION → EXPANSION → EXTENDED**

The desired discovery window is PRE_MOVER or early IGNITION. EXPANSION can still be considered for a controlled first retest when evidence supports it. EXTENDED is primarily management/research evidence, not a chase entry.

Lifecycle thresholds remain caller-owned and cannot be silently loosened by the signature engine.

### 7. Mandatory mover audit classification

Every material mover must end in exactly one auditable state:

- `FOUND_AND_TRADED`
- `FOUND_BUT_MISSED`
- `LATE_DETECTED`
- `NOT_FOUND`
- `NOT_AUDITABLE`

For misses, identify whether the dominant failure was discovery, data, direction, readiness/confirmation, entry timing, risk geometry, or management. Measure confirmation tax and remaining-R lost where evidence supports it.

## V0.1 implementation

`alpha_hunter/big_mover_signature.py` provides a fail-closed, research-only core that:

1. fits empirical LONG and SHORT mover signatures from labelled pre-move snapshots plus controls;
2. refuses scoring when the caller-defined minimum mover/control evidence is not met;
3. scores candidate similarity with missing-feature coverage penalties;
4. never grants trade permission;
5. accepts only hard safety eligibility as a scoring block, not legacy readiness eligibility;
6. reconstructs T-24h/T-12h/T-6h/T-3h/T-1h/ignition snapshots from timestamped evidence;
7. classifies the required discovery-audit states;
8. exposes PRE_MOVER/IGNITION/EXPANSION/EXTENDED classification using caller-owned thresholds.

## Evidence contract required for live shadow integration

The live adapter must provide append-only timestamped rows for the verified full Bitget USDT-M Futures universe, including enough fields to join a later realized mover to the exact evidence that existed before ignition. It must also retain non-mover controls from the same periods/regimes.

The adapter must not:

- substitute spot symbols or another exchange for Bitget Futures eligibility;
- backfill T0/T1/T2 or pre-move snapshots with hindsight data;
- treat a high similarity score as trade permission;
- weaken liquidity, stop, leverage, no-chase, or execution safeguards.

## Validation order

1. Unit/regression safety tests.
2. Bind real historical/missed-mover evidence and controls.
3. Measure in-sample separation only as a diagnostic, not a promotion gate.
4. Walk-forward replay on held-out periods/coins.
5. Live full-universe shadow scoring.
6. Measure mover recall, precision, confirmation tax, MAE/MFE, remaining R and realistic net expectancy.
7. Consider production promotion only after explicit evidence and safety review.

## Definition of success

The system succeeds when it can repeatedly surface future Bitget Futures top movers **before most of the expansion is consumed**, while maintaining acceptable false-positive cost, executable liquidity, controlled downside, and positive forward expectancy. A higher signal count by itself is not success.
