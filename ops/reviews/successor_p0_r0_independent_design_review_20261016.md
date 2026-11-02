# R0 technical review: successor-only monitoring integrity repair
**2026-10-16; engineering review, not external approval. $0 new spending. No production changes.**
Reference: `ops/reviews/successor_p0_minimal_production_repair_change_request_20261016.md`
and existing draft PR #341. This review does not grant R1–R4 authorization.

## Review result: bounded design CONTINUES; release is still NO-GO
The smallest correct **successor-only** change has two independent deliverables:
(A) a fail-visible all-order paper residual census/incident classification,
and (B) an independent successor cycle with content-bound child, all-residual
and per-position records, followed by an immutable *local structural* seal
committed in a single new successor transaction, confirmed by independent
read-back. Neither alone is proof of actual monitoring, real STOP fillability,
independent externally durable alerting or R10 scientific readiness.

Critically, a new successor-only overlay **CANNOT REPAIR THE EXISTING PRIMARY
HOURLY WRITER**. If the owner keeps main/R10 immutable as directed, old parent
scan records may continue to be persisted before failed child writes. Thus
the only currently defensible claim is that **a separate successor authority
refuses to classify those old parent-only scans as complete**, and records
them as incidents when read. Eliminating the source timeout or changing
how the legacy writer commits is a **separately scoped production change**,
not silently included in this no-legacy-modification proposal.

## Fresh database-catalog source audit (read-only)
Reproduce with only `ops/reviews/successor_p0_write_pressure_catalog_readonly_20261016.sql`.
Executed via existing Supabase read-only SQL inspection
**2026-10-16 08:02:56 UTC**; no EXPLAIN ANALYZE, DB config, trigger or policy writes.

**Actual enabled PostgreSQL trigger cascade (source functions inspected):**
- `public.alpha_hunter_symbol_snapshots` AFTER INSERT / UPDATE ->
  `private.alpha_hunter_capture_strategy_observations_v01`, PL/pgSQL
  **row-level strategy loop** over payload array.
- Each strategy item may INSERT into
  `public.alpha_hunter_strategy_observations_v01`
  (`ON CONFLICT(observation_id) DO NOTHING`), in turn firing
  AFTER INSERT `private.alpha_hunter_capture_shadow_decision_quote_v01`
  when status SHADOW_CANDIDATE with LONG/SHORT.
- WATCH or SHADOW_CANDIDATE with strategy-instance ID and LONG/SHORT
  may INSERT a strategy episode (`ON CONFLICT DO NOTHING`), in turn
  enqueueing a 24-hour evaluation row via
  `private.alpha_hunter_enqueue_strategy_24h_outcome_v01`.
- These are enabled triggers, not proof that all branches fire for each
  symbol, nor proof the timeout is caused by them.

**Descriptive current catalogue estimate** (not `COUNT(*)`, nonzero staleness):
`alpha_hunter_symbol_snapshots` ~137,748 rows / 27.5 MB heap;
strategy observations ~971,052 rows / 1,947 MB heap;
strategy episodes ~65,965 rows / 144 MB heap.
A bounded read-only recent source count found **305** symbol rows and **3,050**
strategy-array items over ~2h across RENDER_CRON child rows when measured;
this suggests approximately 10 strategy items/child in that sample.
A new 61-symbol scan *can* cascade into hundreds of observation/episode
operations and index probes. Actual costs vary per branch and conflict;
production `pg_stat_statements` aggregate maximum samples span unrelated
historical query patterns and are NOT direct 57014 blame.

**Timeout configuration truth:**
`service_role` has database role-specific `statement_timeout=12s`;
`authenticator` and `authenticated` have 8s; `anon` 3s.
The inspection SQL session reports **2min (120s)** from its own effective
settings. This is NOT evidence that the scanner writer has 120s, since
per-role/session limits differ. Confirm the **exact effective app/PostgREST
role/session** in a separately approved safe review; do not assume a longer
timeout or change it. The frozen design stays **SQL 12s / HTTP 15s /
monitoring strictly <=2,100s**.

**What is PROVEN about the failing scan:**
Each of four previously inspected canonical parent-only timestamps from
Oct 15–16 aligned with an original Render `alpha_hunter_symbol_snapshots`
upsert HTTP 500 / SQLSTATE `57014` statement timeout. Immediate failure
stage = child snapshot upsert. Deepest latency origin (PL/pgSQL fanout,
table/index bloat, locked row, ongoing DB load, PostgREST time budget,
or an interaction) = **UNPROVEN**. Do not disable legacy triggers, vacuum
or reindex, change database role/timeouts, add triggers, modify main
scanner or retrospectively fill source rows under this review.

## Four reviewer checkpoints before requesting R1
1. **Inventory authority:** use all orders and cumulative exact entry/exit
   fill quantities, distinguish each source order ID, reject negative/missing
   source and non-paper flags, classify EVERY positive residual. The single
   original NMR LONG partial (3.2 ordered / 1.5 entered / 0 exited / 0
   protection/attempt/quarantine) remains unresolved, not a live Bitget
   position. Quarantined residuals remain incident, even if managed count=10.
2. **Structural success is subordinate:** successor-only immutable local
   seal is valid only for new prospective IDs after exact source/child/
   per-position identity, digest, quantities, clocks and readback, and
   successful same-DB transaction. If source child upsert times out 57014,
   lost HTTP ack, journal unavailable, unexpected residual, stale/missing
   quote or unknown predecessor: `UNKNOWN`/FAIL, never COMPLETE. Historical
   parent-only rows still fail without rewriting original history.
3. **Access/security:** all 12 live paper/canonical physical source tables
   have RLS enabled and 0 RLS policies for an ordinary new limited reader
   (separately rechecked 07:42 UTC). **No policy means UNKNOWN/ACCESS_DENIED,
   not zero positions.** R1 must enumerate column-level GRANT and each RLS
   policy, no BYPASSRLS/service_role reader, least privilege, ephemeral
   rollback rehearsal and independently verified source count/clock.
4. **Ops/rollback:** Primary Hourly main and R10 cohort never changed by
   R0 design. A successor deployment must be independently kill-switchable
   without altering or deleting historic orders, fills, STOP/TP, NMR incident
   or R10 four original integrity failures. If primary child writes still
   time out, produce a diagnostic; do not call it fixed. R3 external
   custody/emails, R4 72-hour pilot and P3 profit promotion require
   separate permissions and prospective evidence.

## Acceptance matrix with clear distinction
| Review criterion | Assessment |
| --- | --- |
| Existing incident reproduction: NMR 1.5 partial and 4 parent-only runs | **VERIFIED HISTORICAL SOURCE EVIDENCE** |
| Isolated PG16 synthetic all-residual inventory, wrong child, missing attempt and real 57014 rollback | **PASS** (previous draft exact-head CI) |
| PostgreSQL catalog identifies enabled trigger chain and source volume | **VERIFIED CATALOG; causal timeout source NOT PROVEN** |
| 12s service_role timeout and different catalog-reader timeout | **VERIFIED CONFIG; effective failing session still needs proof** |
| Minimal new successor-only contract without R10 writes | **REVIEWABLE DESIGN; NOT DEPLOYED** |
| Fix of existing primary scanner's child upsert/timeouts | **NOT IN SCOPE / UNRESOLVED** |
| Real NMR paper protection, complete independent 35m source/quote/alert receipts | **FAIL / UNPROVEN** |
| R1 restricted source-role policy or R2 successor deployment | **NOT AUTHORIZED** |
| R3 real independent durable journal/alerts or R4 72h pilot | **NOT AUTHORIZED** |
| P3 execution costs, scientific promotion or order authority | **NO-GO** |

## Narrow next action / permission dependency
The immediate **$0** task after R0 is to produce (without executing)
a *minimal signed-off R1 SQL security diff and rollback plan* for a dedicated
role read-only census of all 12 sources (column allowlist, policies and
expected row cardinality), plus a precisely bounded **read-only** PostgREST
role/latency profile request for the 57014 trigger cascade. Publishing a
proposed migration file is not consent to run it. R2 successor writer remains
separate and disabled even if R1 were later approved. DO NOT use the active
`service_role` as a workaround; do not spend or provision anything.

**Final R0 audit verdict: DESIGN SCOPE VERIFIED / MAJOR LEGACY-WRITER
DISTINCTION CLARIFIED / PRODUCTION SAFETY NO-GO.** Review does not constitute
approval from security, operations, science or project owner.
