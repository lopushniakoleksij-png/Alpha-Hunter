# P3 historical decision→venue-fill provenance and order-type conflict investigation
**16 October 2026 | draft PR #345 | READ-ONLY live source cross-check, offline negative regressions**

## Exact forensic evidence as of source read
Two reproducible SELECT-only SQL files:
- `ops/reviews/p3_all_existing_candidate_base_crosscheck_readonly_20261016.sql` executed 2026-10-16 **00:46:58 UTC**;
- `ops/reviews/p3_unique_candidate_method_audit_readonly_20261016.sql` executed **00:47:01 UTC**.

Starting candidate *pairings* come from the existing
`alpha_hunter_execution_fill_confirmation_candidates_v01` view. The new
first query then independently re-reads frozen decision, original venue
fill, private **GET-only** venue order-detail, source traceability-run
metadata, and explicit fill-binding physical tables to corroborate each
pair's source identity and authority. This cross-check is not a separately
authenticated upstream exchange receipt, not an execution-causality proof and
not an as-of historical market quote. No sensitive raw venue order/trade
identifiers, private client OIDs or credentials are copied into this report.

| Source-verified candidate tier | Unique-in-window | Ambiguous |
|---|---:|---:|
| Heuristic **PAIR ROWS** | 5 | 37 |
| Distinct frozen decision events | 5 | 14 |
| Distinct venue FILL records | 5 | 26 |
| Distinct venue ORDER IDs | 5 | 9 |
| Frozen decision attributes match source | 5/5 | 37/37 |
| Venue fill identities match source | 5/5 | 37/37 |
| Private order-GET source consistent | 5/5 | 37/37 |
| Trace run complete, schema validated, source matched | 5/5 | 37/37 |
| Frozen shadow-only and no trade authority | 5/5 | 37/37 |
| No Alpha Hunter exchange **ORDER WRITER** | 5/5 | 37/37 |
| Explicit binding required, automatic binding prohibited | 5/5 | 37/37 |
| Missing exact binding | 5/5 | 37/37 |
| PLACE_LIMIT frozen / MARKET venue conflict **PAIR ROWS** | 3 | 20 |
| Distinct venue ORDERS within these conflicting pairs | 3 | 5 |
| Fill record linked to >1 frozen event (row-level) | 0 | 21 |
| Frozen event linked to >1 fill (row-level) | 0 | 34 |
| Many-to-many pair rows on BOTH dimensions | 0 | 18 |

A total of 42 **candidate pairs** represent 19 frozen decision events and
31 venue fill records across **14 venue orders**. The 23 LIMIT→MARKET
**pair rows** are not 23 separately erroneous trades; they involve
**eight distinct venue orders** in this heuristic graph. The 37 ambiguous
pairs involve 14 events, 26 fills and 9 venue orders. Multiple fills per
order and multiple possible freezes per fill mean timestamps or nearest
match alone cannot disambiguate or create an execution-attribution row.

## Five unique heuristic pair cases (all iOS human UI / MARKET TAKER, source reads GET-only)

| Signal frozen UTC | Frozen method | Venue order UTC | Elapsed to order | Method verdict |
|---|---|---|---:|---|
| ALGOUSDT SHORT, 2026-10-08 09:43:27 | EXECUTE_NOW | 10:08:35 | 25.135m | MARKET method compatible; **causality UNVERIFIED** |
| MYXUSDT LONG, 2026-10-10 06:23:30 | PLACE_LIMIT | 06:40:57 | 17.457m | **LIMIT-versus-MARKET conflict**, causality UNVERIFIED |
| SAFEUSDT SHORT, 2026-10-12 09:43:36 | EXECUTE_NOW | 09:53:09 | 9.563m | MARKET method compatible; **causality UNVERIFIED** |
| WLDUSDT SHORT, 2026-10-12 11:43:33 | PLACE_LIMIT | 12:03:09 | 19.593m | **LIMIT-versus-MARKET conflict**, causality UNVERIFIED |
| **ZROUSDT LONG, 2026-10-15 15:24:00** | PLACE_LIMIT | 15:45:09 | 21.143m | **LIMIT-versus-MARKET conflict**, causality UNVERIFIED |

All five frozen records have `shadow_only=true`, `trade_permission=false`,
`automatic_binding_permitted=false`, no Alpha Hunter order writer and no
exact `alpha_hunter_execution_fill_bindings_v01` record. Each venue order
detail has `order_source=MARKET`, `order_type=MARKET`, `trade_scope=TAKER`,
`order_enter_point_source=IOS` and `fill_origin_class=HUMAN_UI_EXTERNAL`.
Their recorded order type and source GET trace are independently
corroborated by original underlying tables.

No exact owner execution-intent confirmation correlating the new ZROUSDT
decision to that later order has been established. An actual manual trade
might have been inspired by an Alpha Hunter signal, a separate independent
decision, or a deliberately modified plan; **the existing records cannot
resolve which**. Even an independently confirmed manually *inspired* order
would not be the exact automated order method or R10 paper execution.

**Scientific classifications:** all five are
`VENUE_ORDER_DOCUMENTED / EXACT_SIGNAL_CAUSALITY_UNVERIFIED`; MYX, WLD,
ZRO have additional `ORDER_METHOD_CONFLICT`. None can be included in
Alpha Hunter's verified execution-cost calibration; no realistic net-R
computed. The original WLDUSDT iOS venue order is *not* the separate
frozen R10 PAPER integrity failure and must not relabel or repair it.

## Research-only anti-attribution and safety tests
New pure, **synthetic-only** `ops/reviews/p3_historical_candidate_causality_guard_v01.py`
and negative regression `tests/test_p3_historical_candidate_causality_guard_v01.py`
fail closed when a unique matching method is mistaken for causality,
PLACE_LIMIT MARKET mismatch treated as faithful execution, multiple fills
counted as independent unique trades, missing exact binding, or a duplicate
heuristic pair counted again. The two new SQL audit files are parse-tested to
contain one SELECT each with zero writes; no raw private order IDs are
projected by the five-case report. Every synthetic test output has
`verified_ah_executions=0`, no auto-binding, no realistic net-R or trading
promotion. Acceptance is subject to exact-head CI; **CI cannot validate
real manual causation**.

## What is still missing and what is disallowed
For pre-existing fills *only*, future operator/source evidence would need
the exact frozen decision/event, account scope, independently authenticated
venue order/trade identifiers, contemporaneous user execution decision and
method-change history. A screenshot or retrospective heuristic alone is
not a cryptographic or causal bridge; owner confirmation can inform a
separate governance review but is **not an automated execution proof**.
No new trades are necessary to continue evaluating existing records.
No automatic binding, backfill or user-directed real-money order.

P3 still has **zero** independently verified Alpha Hunter execution sample
rows, zero validated exit slippage/markout rows and zero validated full-cost
models. Keep fee/spread floors descriptive; no Alpha Hunter realistic net-R or
profitability claim. P2 actual independent source receipt/alert delivery and
72-hour forward pilot remain blocked.

Preserve production main and enabled Primary Hourly, original R10 halted
admissions, scientific fingerprint/four integrity failures, all managed
paper positions, 35 minutes exactly 2,100 seconds maximum; no retroactive
repairs. **$0 new spending, zero production writes, zero trades, zero new
providers, zero deployment/restart/merge.**

**Verdict:** HISTORICAL SOURCE-RECORD IDENTITY CROSS-CHECK PASS;
EXACT DECISION→TRADE CAUSAL LINK BLOCKED;
LIMIT-v-MARKET INTENT CONFLICT DOCUMENTED;
P3 REALISTIC EXECUTION COST VALIDATION NO-GO.
