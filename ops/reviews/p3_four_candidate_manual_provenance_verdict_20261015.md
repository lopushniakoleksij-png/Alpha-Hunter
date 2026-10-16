# P3 historical manual execution provenance — four-candidate verified-source review
**15 October 2026, 16:52:28 UTC | READ-ONLY forensic classification, no approval to bind.**
**Draft PR #345 only | no merge/deploy/DB change/trade/payment.**

## Scope, evidence strength, reproducibility
This review pins four prior **frozen decision identities by exact symbol, side, action and UTC microsecond timestamp**. Its source is the existing Alpha Hunter Supabase:
- \`alpha_hunter_execution_decision_freezes_v01\` (signed/intended shadow decision; *automatically* frozen \`capture_mode=AUTO_FREEZE_AT_DECISION_QUOTE_INSERT\`, \`trade_permission=false\`, \`explicit_exact_fill_binding_required=true\`).
- \`alpha_hunter_execution_fill_confirmation_candidates_v01\` (heuristic symbol+OPEN side+freeze→order timestamp interval and traceable fee/order detail rows; *not* causal linkage).
- \`alpha_hunter_fill_evidence\` and \`alpha_hunter_execution_order_evidence_v01\` (stored private Bitget GET-derived exact trade/order evidence, iOS entry point, order type, opaque client OID observed and identity hash).
- \`alpha_hunter_execution_fill_bindings_v01\` and \`alpha_hunter_verified_execution_attribution_v01\` (absence of explicit causal confirmation and validated execution attribution).
- Independent **current** account diagnostic \`alpha_hunter_bitget_account_scope_diagnostic_v02\` (at 16:51 UTC, CONNECTED, subaccount=true, 46 current scan fills, complete/schema validated, \`NO_ACCOUNT_SCOPE_CONFLICT_DETECTED\`; this diagnoses account continuity, not the causation of an individual order).
- Historical prior user confirmation check for each *exact* named trade found none. A general admission of manual trading in a different symbol does not attribute these executions.

Reproducible non-mutating SELECT: \`ops/reviews/p3_four_manual_order_provenance_readonly_20261015.sql\`.
The query deliberately emits no underlying private exchange order/trade identifiers, signing secrets, or credentials. The original venue IDs remain preserved in source; no new copy or binding is created.

## Each of four exact matches (UTC)
| Frozen signal | Venue order created | Venue fill | From signal to order | Method | Evidence rating |
|---|---|---|---:|---|---|
| **ALGOUSDT SHORT EXECUTE_NOW** 2026-10-08 09:43:27.104652 | 10:08:35.179 | 10:08:35.189 | 25.135 min | iOS MARKET/TAKER OPEN | Time+side+method compatible; **causation UNVERIFIED** |
| **MYXUSDT LONG PLACE_LIMIT** 2026-10-10 06:23:30.108448 | 06:40:57.556 | 06:40:57.565 | 17.457 min | iOS MARKET/TAKER OPEN | **LIMIT-v-MARKET intent mismatch** and causation UNVERIFIED |
| **SAFEUSDT SHORT EXECUTE_NOW** 2026-10-12 09:43:36.071720 | 09:53:09.857 | 09:53:09.865 | 9.563 min | iOS MARKET/TAKER OPEN | Time+side+method compatible; **causation UNVERIFIED** |
| **WLDUSDT SHORT PLACE_LIMIT** 2026-10-12 11:43:33.982301 | 12:03:09.590 | 12:03:09.599 | 19.593 min | iOS MARKET/TAKER OPEN | **LIMIT-v-MARKET intent mismatch** and causation UNVERIFIED |

Each is a *unique heuristic pair in the existing matching view* (one event and one fill for that event within this temporal algorithm). Every stored venue detail has \`order_state=FILLED\`, \`origin_consistent=true\`, \`trace_complete=true\`, \`trace_schema_validated=true\`; client OID is observed but raw ID is not recopied in the audit table; the stored account reads are GET-only with \`order_write_path_present=false\`. The matching frozen signals are **shadow-only and not order-enabled**. All four private order-detail rows explicitly have \`alpha_hunter_execution_claim_permitted=false\`; fill traceability and source hashes are not proof of user response to a recommendation.

## Why independent exact causal proof is not available
1. The frozen decisions are *automatically produced*, not authenticated user instructions or account order submissions. Their \`execution_event_id\` is **not** a raw Bitget order ID nor an independently confirmed instruction correlator.
2. The venue orders were independently submitted from **iOS**, not through a tracked Alpha Hunter order-write path. Time, symbol, direction, and even a unique short-window match do NOT establish the reason for a human submission. Current account-scope consistency rules out one class of mismatch but proves nothing about this causal dependency.
3. **MYX and WLD:** shadow \`PLACE_LIMIT\` vs actual \`MARKET\`. A future explicit statement that the trade was inspired by the app would NOT retroactively make the exact limit-order execution faithful. A deliberate changed method must be recorded separately and never applied to original frozen geometry.
4. **ALGO and SAFE:** \`EXECUTE_NOW\` is compatible with a market submission, but zero signed/evidenced link to the specific frozen recommendation exists.
5. The original exact user confirmations and DB entries in \`alpha_hunter_execution_fill_bindings_v01\` are **absent**. No generic confirmation in earlier conversation for a separate symbol can fill this gap. Auto-binding remains disallowed; there are zero verified Alpha Hunter executions.
6. \`WLDUSDT\` may also occur in R10's *paper* incident records; these iOS **real exchange** order records must **never** be confused with, used to repair, or netted against the separate paper cohort's missing/horizon evidence.

## Decision / future no-trade action
**ALL FOUR: \`VENUE_ORDER_AND_FILL_DOCUMENTED; USER_SIGNAL_CAUSALITY_NOT_ESTABLISHED\`.**
**Zero** eligible confirmed decision→fill pairs; **zero** verified Alpha Hunter executions and measured entry slippage; **zero** real cost validation permissions. Don't write a binding, reinterpret science, backfill, or count these trades in Alpha Hunter net profitability. No real trade is required or authorized.

If independent historical evidence is later presented voluntarily, conduct a *read-only* source comparison of the original frozen event, exact venue order/trade ID, subaccount, order type, user decision timestamp, and contemporaneous screenshot/log/statement **before** proposing any prospective governance review. An owner memory or screenshot alone is not an exchange-verifiable exact bound pair. Manual signal-following must be reported as manual, not Alpha Hunter autonomous order execution.

**P2 live monitoring:** still blocked. **P3 complete cost validation:** still blocked. **R10:** unchanged and halted; 35-minute maximum, four integrity failures, existing protections and scientific identity preserved. **New spend:** $0. **Production deployment:** none.
