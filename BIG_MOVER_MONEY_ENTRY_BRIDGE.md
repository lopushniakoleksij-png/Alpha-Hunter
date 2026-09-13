# Big-Mover → Money Entry Shadow Bridge

## Objective

Convert Big-Mover signature discoveries into a fail-closed Money Entry evaluation path without changing production trade permissions, legacy scanner thresholds, or order routing.

## Runtime order

1. `:10` — existing Big-Mover answer-key + signature shadow cycle.
2. `:11` — isolated public-Bitget 12H/1D parent-direction collection for the top five early candidates per side.
3. `:12` — Big-Mover → Money Entry bridge and parent-direction enrichment.

## Key rules

- Raw signed 24h change and direction-normalized move are stored separately.
- 12H/1D collection is isolated from the legacy 15m/1H/4H scanner state machine.
- Parent direction must align with the Big-Mover model direction before a candidate can reach Money Entry evaluation.
- Missing parent data, direction conflict, or missing execution geometry fail closed.
- `READY_FOR_MONEY_ENTRY_EVAL` means only that the bridge has enough evidence to hand the candidate to the later Money Entry evaluator. It is **not** trade readiness and cannot grant an order.
- Exact T0/T1/T2 authorization remains disabled until the required Money Entry fields and evidence-derived thresholds are present.

## Safety boundary

- `shadow_only=true`
- `trade_permission=false`
- no exchange private credentials
- no order/write path
- no production threshold relaxation
- new security-definer runtime functions live in the private schema
- public evidence tables use RLS and service-role-only access
