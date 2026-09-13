# Alpha Hunter Production Gates v0.3

## Objective

Extend the phone/cloud control plane from evidence collection into a fail-closed production-readiness chain without enabling live trading.

The canonical new-hour sequence is:

1. `:10` ANSWER_KEY — Bitget USDT-M answer key + Big-Mover shadow.
2. `:11` PARENT_DIRECTION — 12H/1D parent-direction evidence.
3. `:12` MONEY_ENTRY_BRIDGE — Big-Mover → Money Entry handoff.
4. `:13` MONEY_ENTRY_STAGE — immutable exact-stage single writer.
5. `:14` MONEY_SCORECARD — forward 1H/4H/12H/24H path evidence.
6. `:15` COST_EVIDENCE — contemporaneous spread/funding + validated cost-model lookup.
7. `:16` PORTFOLIO_RISK — account/position/policy veto assessment.
8. `:20` FINALIZE — completeness, order, source consistency, freshness, safety and readiness.

Historical 4-stage and 5-stage control runs remain auditable; only newly created v0.3 runs expect seven controlled stages.

## Money Entry stage single writer

`alpha_hunter_money_entry_stage_snapshots` is append-only and freezes contemporaneous scanner/bridge inputs. Numeric thresholds are not embedded in the writer. Exact T0/T1/T2 requires an `ACTIVE` row in `alpha_hunter_money_entry_threshold_sets` with validation/activation timestamps and evidence reference.

With no active validated threshold set, the correct output is `DATA_INSUFFICIENT` plus explicit blockers. Old PR #6 numeric test fixtures are not production policy and are not seeded by this upgrade.

## Cost evidence

`alpha_hunter_execution_cost_evidence` consumes the same contemporaneous scanner evidence instead of rescanning the full market. It records observed spread and funding when present. Maker/taker fees and slippage are supplied only by an evidence-backed `ACTIVE` cost model.

`realistic_net_r` remains withheld until the complete cost path is verifiable. A spread observation by itself is not a fee/slippage model, and a fee/slippage model by itself is not a complete funding/holding-period path.

Live validation on `AHCLOUD-20260913T1000Z` produced 35 cost-evidence rows: 35/35 had spread evidence, 35/35 had funding evidence, and 0 rows claimed cost-adjusted net R because no active validated cost model exists.

## Portfolio risk veto

The risk engine is deliberately independent of the strategy engine and cannot authorize an order. It consumes:

- a valid Money Entry stage snapshot;
- verified cost evidence;
- an active validated risk-policy version;
- a recent complete `CONNECTED_READ_ONLY` account snapshot;
- a complete open-position snapshot with planned-risk fields.

It can return only `BLOCK` or `ELIGIBLE_FOR_RISK_REVIEW`. Even `ELIGIBLE_FOR_RISK_REVIEW` is not trade permission. Leverage is not selected by this engine; structural stop and monetary risk must determine position size before leverage is considered.

Live validation on the same 35-candidate cohort returned `BLOCK` for all 35 because no validated Money Entry thresholds, cost model, risk policy or verified account/position feed are active. `execution_authorized=false` and `trade_permission=false` remained intact.

## Account and position input contracts

The new account/position tables are append-only read-only evidence contracts for the future credentialed Bitget reconciliation path. They do not contain credentials and do not call private trading endpoints.

A usable account snapshot must explicitly say `CONNECTED_READ_ONLY`, `complete=true`, and `schema_validated=true`. This aligns with the still-open PR #4 fill-traceability gate; the cloud system does not pretend the private account connection exists while the credentialed smoke test is unavailable.

## Health vs readiness

The finalizer distinguishes a broken production process from an incomplete readiness gate.

Actual safety/freshness/order/source failures can open a production incident. Missing validated Money Entry thresholds, cost model, risk policy or account state remain explicit readiness warnings and make the chain `DEGRADED`, but they do not create a false operational incident by themselves.

## Safety invariants

- `production_execution_enabled=false`
- `research_trade_permission=false`
- all new evidence `shadow_only=true`
- all new evidence `trade_permission=false`
- no private Bitget credential added
- no order-submission route added
- no threshold, fee, slippage, risk amount or leverage limit invented
- no live execution authorization added

Production execution remains blocked until the evidence gates are validated, read-only account/fill traceability is proven, and any future order state machine is reviewed separately.
