# Successor-only exit liquidity and residual-position protection — independent approval gate

**Review state: FAIL-CLOSED / RESEARCH ONLY. DO NOT MERGE OR DEPLOY.**

RISK_APPROVAL: NOT_GRANTED
DBA_APPROVAL: NOT_GRANTED
SCIENTIFIC_APPROVAL: NOT_GRANTED
LIVE_TRADING_AUTHORITY: DISABLED
PRODUCTION_ADMISSIONS: HALTED
SEALED_R9_FINGERPRINT: UNCHANGED

## Purpose and scope

Isolated, synthetic executable *contract tests* following evidence from EVAAUSDT (362 units):
44 sampled eligible target triggers and 11 eligible stop triggers had less top-level liquidity than 362 units. All-or-nothing model deferred both sides; 7 legacy monitoring intervals exceeded 35m, and the final recorded stop was worse than the original target touch. This is **not** a retroactive repair to the recorded EVAA loss. Current historic 32 exits and current R9 0/100 qualifying completions remain immutable.

The original model's safe fail-closed protection must never be weakened to manufacture a trade. **Partial fills are hypothetical test fixtures, not trade receipts or permission to execute.**

## Contract invariants (necessary, not sufficient)

1. Research state alone accepts **synthetic fixture receipts** (not market candles, scraped quotes or unknown exchange fills). Future implementation requires provider-authenticated execution receipts with immutable source, independent quote/bid/ask/depth provenance and custody, trade side, exact filled quantity and price, monotone time and sequence, venue fee/funding receipts; even an authenticated order acknowledgement is not proof of a fill.
2. Every accepted synthetic exit uses a unique event ID and quote ID. Duplicate identical event is a no-op. Contradictory event ID halts custody. Optimistic revision checks reject stale replays. Neither two book sizes nor two observations are aggregated to fabricate a fill.
3. Sum of exit quantities must never exceed entry quantity. Each partial exit must atomically record realized quantity, residual and independently acknowledged **both** stop AND take-profit protective legs sized to the entire residual, with a shared OCO reference. Both legs are linked protection of one residual, **not** two independent positions. No naked/oversized protective leg or phantom flip.
4. Position baseline stop/target geometry is unchanged. No stop widening, target changes, increased risk budget or risk-gate relaxation. If protection acknowledgements are absent after an apparent fill, mark **HALTED_UNRESOLVED** and block all new events; do not silently claim the original quantity is safely protected or that exit executed. Real-world handling needs transaction/saga recovery with authoritative venue position and protection reconciliation before restart.
5. Fully closed positions require **both** terminal protective cancellation acknowledgements, not merely a theoretical zero residual. A failed OCO resize, cancel/rearm or ambiguous HTTP response leaves an incident unresolved and must trigger human-safe reconciliation. Existing paper/Bitget positions never passed into this prototype.
6. Fee accounting uses `fee_bps * exit_price * filled_quantity / 10_000` per confirmed synthetic fill; entry fee allocated proportional to each partial quantity, with final remainder to avoid drift. Gross and net P/L use adverse-execution fill prices; modeled spread/slippage are recorded as **diagnostics** and **not double-subtracted** when embedded in price. Funding remains unknown; `profitability_claim_permitted=false`.
7. Research-only fee/slippage bounds are not reviewed production thresholds. Any eventual live/paper successor requires independent market-impact and depth-of-book cost validation, partial-lot/min-notional/precision constraints, adverse price bounds, failure recovery and real quote-source custody.
8. Frozen sealed R9 start `2026-10-04T12:37:51.632971Z`, cutoff `2026-11-03T12:37:51.632971Z`, 35-minute monitoring limit, admissions halt, protective evidence flags and no live-trade authority are immutable. Never backfill R9 outcomes, overwrite losses or reset test dates.

## Isolated test acceptance, scope-limited

- EVAA-shaped 362 units: 100 + 200 + 62 hypothetical exit path with residual guards 262, 62, then 0 + both cancellation acknowledgements; invariant and exact accounting checks
- Bid size 100 cannot close 362; insufficient/missing stop or TP protection enters unresolved state, never automatically ignores fills
- Duplicate and contradicting IDs, stale revision and reused quote samples, terminal OCO cancellation ambiguity; timestamp/order and stop geometry
- For LONG exit use bid-side SELL; for SHORT exit use ask-side BUY; bound adverse slippage and fee rates
- Reject negative/zero/overfill, invalid prices, negative liquidity and unsupported provider-fills based on mere quote evidence
- No app imports, no Supabase writes, no exchange API, no cron changes, no PR merge until signoffs

## Distinct blockers for independent risk/DBA/security/scientific review

**RISK REVIEW — NOT APPROVED:** Evaluate against live depth/impact distributions, partial fills, long/short symmetry, stress gaps, stop-vs-target first-touch, liquidation, sizing and collateral. Define residual risk caps and safe emergency circuit-breaker. Test both protective legs and OCO semantics with actual venue acknowledgements and independent documented venue policy.

**DBA/SECURITY — NOT APPROVED:** Design isolated synthetic PostgreSQL 16/17 migration, serializable atomic custody or fail-closed saga, idempotent constraints, signed evidence custody, scoped read and write permissions and rollback. No production migration or real credential access in this PR.

**SCIENTIFIC REVIEW — NOT APPROVED:** Define frozen successor scientific identity, preregistered cost assumptions, baseline vs successor holdout, symbol/day equal weighting, positive confidence-bound gate and no changes to R9 denominator. Treat historical EVAA alternative exits only as counterfactual, never an earned winner.

**OPERATIONS REVIEW — NOT APPROVED:** Independently verify source and quote monitoring, 35-minute breach detection, alert delivery and recovery from ambiguous HTTP writes. No protected cron or position action until separately approved.

### Approval signature placeholders — intentionally blank

Risk reviewer: __________________ / Decision: PENDING / Date: ______

DBA/security reviewer: __________ / Decision: PENDING / Date: ______

Scientific reviewer: _____________ / Decision: PENDING / Date: ______

Operations reviewer: _____________ / Decision: PENDING / Date: ______

Final production/go-live authority: **NOT REQUESTED**.
