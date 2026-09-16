# Alpha Hunter — Core Execution Signal-Quality Contract

Status: **CORE / PERMANENT / FAIL-CLOSED**

Effective: 2026-09-16

## Primary rule

**READY = EXECUTABLE CONFLUENCE, NOT CONFIDENCE.**

A high score, a large number of signals, a narrative, a recent pump, or a strong historical pattern must never be enough to make a trade READY.

The execution chain is:

**DIRECTION → MOMENTUM → PARTICIPATION → STRUCTURE / ENTRY LOCATION → REMAINING REALISTIC R → PORTFOLIO RISK → READY**

If any required link is missing, false, stale, contradictory, or not auditable, the candidate must remain **NEAR / WATCH / DATA_INSUFFICIENT / NO_T0** rather than READY.

## Mandatory signal-quality gate

Before any Money Entry stage can persist as an eligible T0/T1/T2 state, all of the following must be positively verified:

1. `scanner_direction_aligned = true`
2. `scanner_momentum_confirmed = true`
3. `scanner_data_integrity_pass = true`

Fail-closed interpretation:

- missing direction evidence = no eligible stage;
- direction conflict = no eligible stage;
- missing momentum evidence = no eligible stage;
- momentum not confirmed = no eligible stage;
- missing minimum data-integrity evidence = no eligible stage;
- data integrity not verified = no eligible stage.

**No momentum = no READY.**

This is a minimum execution-quality invariant. It does not replace the existing requirements for parent direction, liquidity, participation, structural invalidation, entry location, remaining realistic R, cost evidence, open-position conflict, and portfolio risk.

## Direction contract

Direction must be resolved before execution:

- 12H + 1D define parent bias;
- 1H is execution timing;
- 1W is structural context where available;
- countertrend execution requires explicit evidence of a reversal event;
- a confidence score cannot override a direction conflict.

The system must not flip LONG → SHORT → LONG merely because a short-term indicator changes. A direction transition requires new evidence and must be traceable.

## Momentum and participation contract

Momentum and participation are separate concepts and both matter.

Momentum must show that price is actually beginning to move in the proposed direction. Participation must show that the move is being supported by sufficient market activity rather than a thin or isolated price print.

A candidate may remain valuable research evidence without being executable. Research ranking must never be promoted to trade permission merely because it is interesting or early.

## Structure and entry-location contract

READY requires a real structural invalidation and an entry close enough to that invalidation to keep downside controlled.

Late entries, chase entries, poor stop geometry, or insufficient remaining R remain blocked even if direction, momentum, and participation are strong.

## Safety boundary

This contract does not enable autonomous live trading.

Permanent safety invariants for the current production-development path:

- `shadow_only=true`
- `trade_permission=false`
- no private Bitget order endpoint
- no exchange order submission path
- no threshold relaxation to increase trade count
- no invented threshold, cost, leverage, or risk value
- no promotion from retrospective evidence alone

Any attempt to persist a Money Entry stage across the shadow/trade-permission boundary must fail rather than be silently repaired.

## Forward scientific test

The rule must be tested forward, not justified from losing trades after the fact.

Every hour the project must audit whether:

- any eligible Money Entry stage exists with missing/false direction alignment;
- any eligible Money Entry stage exists with missing/false momentum;
- any eligible Money Entry stage exists with missing/false data integrity;
- any Money Entry evidence violates `shadow_only=true` or `trade_permission=false`;
- signal-quality blockers are being recorded explicitly.

Any such invariant violation is a production-development failure and must remain visible until corrected.

Separately, once enough forward outcomes mature, compare candidates blocked by this signal-quality gate with candidates that pass it using MAE, MFE, stop survival, remaining R, realistic net R after costs, confirmation tax, and false-positive / missed-opportunity cost. The gate earns predictive credibility only if forward evidence supports it.

## Implementation record

PR #31 introduced the persistence-boundary fail-closed guard and was merged on 2026-09-16. The Supabase shadow production-evidence database has the same guard deployed.

This document makes that behavior a permanent Alpha Hunter core contract rather than a one-off repair.