# P3 existing execution exact-attribution forensic decision — 2026-10-15
**READ-ONLY LIVE SQL + zero-cost OFFLINE TEST; draft PR #345 only, no source writes.**

## Evidence source and reproducibility
The SELECT-only report in \`ops/reviews/p3_existing_execution_exact_linkage_readonly_20261015.sql\` was executed against the existing Alpha Hunter Supabase production project, at **2026-10-15 15:57:32 UTC**. It operates on the already deployed public read-only verification views and existing immutable decision/fill/order tables. Every number here is an as-of observation, not a fixed future count. No raw account credential, venue order ID or venue trade ID is copied into this review.

| Evidence tier | Read-only observation | Meaning |
|---|---:|---|
| Frozen prospective Alpha Hunter events | **2,162** | 2,162 shadow-only / trade_permission=false / explicit exact fill binding required |
| Venue fill evidence | **270** | 270 distinct venue trade IDs across **150** distinct venue order IDs; 0 missing order/trade identity |
| Venue order evidence | **270** | All 270 have client OID present, order-identity hash, source-to-order consistency; **0 allow Alpha Hunter execution claim** |
| Upstream venue origin | 260 iOS, 10 non-API system | Human/outside-API classifications; NOT automatic AH order origination |
| Frozen-event + venue-fill *heuristic* candidate pairs | **29** | 14 distinct frozen events, 24 distinct fills; symbol, OPEN side, 35-minute freeze→order time, valid trace and cost-field presence |
| Unique candidate pairs | **4** | Unique **within the heuristic search window**, not independently causal |
| Ambiguous candidate pairs | **25** | Multiple possible frozen-event/fill pairings |
| Exact explicit fill bindings | **0** | No authenticated relation of a frozen Alpha Hunter event to an individual venue fill |
| Verified Alpha Hunter execution attributions | **0** | No validated slippage/fee calibration sample |
| Auto-binding permission | **false** | Correct independent manual/external confirmation gate enforced |

## Four time-symbol unique candidates — DO NOT mark as executed
- **ALGOUSDT SHORT**, frozen 2026-10-08 09:43:27Z, filled 10:08:35Z: \`EXECUTE_NOW\` shadow decision vs an actual iOS \`MARKET\`/TAKER order. Causal attribution unproved.
- **MYXUSDT LONG**, frozen 2026-10-10 06:23:30Z, filled 06:40:57Z: \`PLACE_LIMIT\` shadow decision vs actual iOS \`MARKET\`/TAKER order. **Intent/order-type conflict**.
- **SAFEUSDT SHORT**, frozen 2026-10-12 09:43:36Z, filled 09:53:09Z: \`EXECUTE_NOW\` shadow decision vs iOS \`MARKET\`/TAKER. Causal attribution unproved.
- **WLDUSDT SHORT**, frozen 2026-10-12 11:43:33Z, filled 12:03:09Z: \`PLACE_LIMIT\` shadow decision vs iOS \`MARKET\`/TAKER. **Intent/order-type conflict**.

Exactly **2/4 unique heuristic pairs conflict on PLACE_LIMIT vs actual MARKET order type**. Historical matches can indicate price/side/time proximity, NOT evidence of having placed the proposed limit order. The other two are still NOT confirmed. The 25 ambiguous rows must not be promoted by arbitrary ranking or tie-break. The SQL's \`NO_VERIFIED_EXACT_DECISION_TO_VENUE_FILL_ATTRIBUTION\` verdict correctly remains regardless of coarse benchmark count, external venue fills or matching symbols.

## Verified causal limitation
The deployed candidate view joins:
- \`alpha_hunter_execution_decision_freezes_v01\`: exact R10 spec, freeze event, strategy, symbol, LONG/SHORT and time;
- \`alpha_hunter_fill_evidence\`: venue-side \`trade_id\` and \`order_id\`, OPEN BUY/SELL, price/fee and time;
- \`alpha_hunter_execution_order_evidence_v01\`: venue order-detail hash and consistent human/outside-API origin;
- \`alpha_hunter_fill_traceability_runs\`: complete+schema-validated source-run evidence;
- temporal eligibility: order created between frozen decision and that freeze+35m, followed by venue fill.

It does **not** use an exact shared order/client-order identifier stored in the frozen decision nor independently authenticated evidence of operator action in response to that specific signal. All source freezes carry \`automatic_fill_binding_permitted=false\` and \`explicit_exact_fill_binding_required=true\`. Thus both unique and ambiguous matching **lack the decisive link**. This is not a diagnosed failure of venue fill capture; it is missing authority/causal linkage and prospective measurement chain.

## Read-only next step — never manufacture a trade
For **existing** candidate records only, independently establish from already available source evidence (or optional explicit owner-supplied trade confirmation) the exact frozen event, operator execution intent/time, actual Bitget order ID and fill trade ID, account/subaccount scope, instrument/side, execution method, contemporaneous expected quote and material execution amendments. Reject a claimed \`PLACE_LIMIT\` fill when the only verified exchange order was \`MARKET\` absent a separately documented deliberate change; even if the owner confirms reliance on a signal, maintain distinction between manually inspired trade, matching shadow recommendation and Alpha Hunter-authorized/executed order. Preserve original event/venue details and timestamps; do not silently write \`alpha_hunter_execution_fill_bindings_v01\` or relabel trades as Alpha Hunter orders.

Only after strict owner-approved independent identity verification can any future calibration row be proposed, separately from frozen R10 science. A future confirmed manual trade is not proof that the autonomous system had order authority. No need to place another trade.

## Safety and scientific boundaries
- **P2 live independent monitoring:** BLOCKED; offline CI HMAC/mock time replay is not 72h real custody.
- **P3 realistic after-cost validation:** BLOCKED; 0 genuinely verified execution-linked sample rows, 0 exit-slippage/markout, no validated funding/missingness/OOS.
- **R10** admissions halted, four original integrity failures retained, scientific fingerprint unchanged, no cost model activated, paper-only, trade authority false.
- **Primary Hourly / Render production cron:** do not stop, restart, reconfigure or auto-deploy. Production main autoDeploy=yes means DO NOT MERGE PR #345.
- **Budget:** owner has authorized **$0** new infrastructure. No database modification, runtime deploy, order placement or historical backfill performed.

**P3 exact-link verdict = UNVERIFIED; live cost validation remains NO-GO.** The new query and parser regressions are offline-only audit tooling. A Green CI result cannot manufacture missing identities.
