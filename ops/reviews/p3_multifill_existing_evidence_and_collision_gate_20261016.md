# P3 offline execution-cost integrity: historical fill fragmentation and duplicate receipt controls
**2026-10-16 | PR #345 DRAFT ONLY | read-only historical Supabase SELECT and isolated synthetic tests**

## Reproducible current evidence
Source: `ops/reviews/p3_existing_multifill_cost_context_readonly_20261016.sql`,
executed as one SQL SELECT at **2026-10-16 00:35:14 UTC** on existing
Alpha Hunter Supabase data, with no order account IDs or raw trade identifiers
copied into this report.

| Existing data | Observed |
|---|---:|
| Venue order IDs, historically observed | 154 |
| Venue fill records | 282 |
| Orders with >=2 venue fills | 57 |
| Fill records among multi-fill orders | 185 |
| Maximum fills on one order | 12 |
| Orders with duplicate trade IDs within the same venue order | 0 |
| Fill records reporting USDT fee denomination + cost_fields_complete | 282 |
| Descriptive coarse market benchmark rows | 255 |
| Freeze-to-venue heuristic candidate pairs | 42 |
| Unique-*within-window* heuristic pairs (not confirmed execution) | 5 |
| Ambiguous heuristic pairs | 37 |
| Pairs with `PLACE_LIMIT` signal vs MARKET order | 23 (pairs, not unique orders) |
| Explicit owner-confirmed fill bindings | **0** |
| Independently verified Alpha Hunter executions | **0** |
| Independently verified exit-slippage and post-fill markout | **0, 0** |
| Active validated model / realistic net-R permission | **0 / false** |

`cost_fields_complete` and `fee_coin='USDT'` attest the fields of a
historical *venue fill record*. They do NOT show that this order originated
from a given frozen Alpha Hunter decision, or that any entry/exit slippage,
market impact, adverse selection or funding path was independently verified.
Do not compute a realized Alpha Hunter net R or trade-performance estimate
from this cohort. The 23 intent/order-type conflicts are **candidate rows**,
not 23 separately proven trade mistakes.

## Newly repaired offline safety issue
Previous `p3_offline_execution_cost_completeness_v01.review_fixture`
rejected duplicate fee/component receipt IDs inside each synthetic candidate
but **did not reject reuse across two different candidate rows**.
Likewise, entry trade IDs were checked globally but an EXIT venue trade ID
could be reused by a separate candidate or match another candidate's ENTRY.
Both gaps could artificially inflate a sample-floor count in a research-only
completeness review. The scoped draft-only fix now records global
`seen_component_receipt_ids` and global ENTRY+EXIT `seen_all_venue_trade_ids`,
rejecting `DUPLICATE_COMPONENT_RECEIPT_ACROSS_ROWS` and
`DUPLICATE_ENTRY_OR_EXIT_VENUE_TRADE_ACROSS_ROWS`, respectively.
The validation result continues to reject real IDs masquerading as
synthetic test data and never allows model promotion.

## Multiple fills require transaction-level closure proof
Existing single-fill cost fixtures intentionally do not model true orders with
fragmented entry and exit fills. The additional review-only
`p3_offline_partial_fill_cost_integrity_v01.py` uses groups of **synthetic
individual venue trade IDs** and separately evidenced fee, slippage, quote,
funding, markout, impact and spread items. It tests cumulative entry-minus-
exit quantity (not just last fill), trade side and clocks, receipt reuse,
adversely timed exits, per-fill fee denomination, mixed maker/taker roles,
and verified cancellation of any unfilled original order remainder.
Distinct fill IDs are required; no fill is a separate closed trade merely
because it shares a parent order ID. Synthetic source flags and trade
permission remain disabled, and **no numeric cost/PnL aggregation is
scientifically admissible**.

This reviewer is a **schema/fault contract, not a live full-volume broker-order
reconciliation**. Even if all its fixtures pass, code returns
`historical_actual_verified_execution_rows=0`, `realistic_net_r=null`,
`validated_cost_model=false`, `scientific_pass_permitted=false`,
`trade_permission=false` and `production_promotion_permitted=false`.

## Next P3 evidence boundary (requires no new trade)
- If preexisting independently attributable order/fill evidence becomes
  available, link the **exact frozen event/order intent** to venue order ID
  and **every** fill/trade ID, observing source run, account scope, side,
  order type, clock and any deliberate manual order-type change. The five
  unique heuristic matches remain NOT causal evidence; do not write
  `alpha_hunter_execution_fill_bindings_v01` without independent owner
  approval and exact proof.
- Prove full filled/exited quantity or retain residual as OPEN/CENSORED,
  QUARANTINED or UNPROTECTED as relevant. Never pretend a cancelled
  remainder was filled; never assert profit on still-open paper positions.
- Require observed venue fee and currency for each fill; separately signed
  arrival-to-fill and exit-cross slippage, quote identity/freshness, market
  impact, adverse markout, complete funding cash flows, and the actual
  maker/taker mix. An observed zero-cost component requires its own receipt;
  missing data is UNKNOWN, not zero. The historical fee/spread floor is NOT
  realistic execution cost.
- Apply existing model-independent sample floors (>=30 verified entries,
  >=20 TAKER, >=10 MAKER, >=5 LONG and >=5 SHORT) and then independent
  fee/slippage/funding/markout completeness and out-of-sample validation.
  These floors do not themselves validate a cost model.

## Safety gates
P2 operational receipts and live alert delivery remain BLOCKED, the 72-hour
pilot never started and the $0 spending hold remains in effect.
R10 admissions stay HALTED; original four integrity failures, original
35-minute/2,100-second monitoring maximum and immutable scientific
cohort are not modified. Preserve Primary Hourly and production main,
managed paper-position protection, SQL/HTTP timeouts, order path NONE.
No new trade, user prompt to manually execute, production DB write,
fill-binding backfill, billing, service, merge or deployment.

**Decision: descriptive historical fill fragmentation VERIFIED read-only;
offline receipt/graph regression acceptance subject to exact-head CI.
P3 COST VALIDATION AND REALISTIC NET-R CLAIM = BLOCKED.**
