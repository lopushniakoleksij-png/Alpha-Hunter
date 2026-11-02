# CR-AH-P0-20261016 — Smallest successor-only production safety repair
**STATUS: PROPOSAL FOR FORMAL REVIEW — NO DEPLOYMENT / NO BILLING / NO LIVE ROLE AUTHORIZATION**
**Repository:** `lopushniakoleksij-png/Alpha-Hunter` • draft PR #341 only • prepared 2026-10-16.
**Change type:** fail-closed paper-inventory and monitoring-evidence qualification; no exchange execution capability.
**Binding owner instruction:** spend **USD 0** until separate explicit authorization; USD 25/month is a **planning ceiling only**.
**Immutable constraints:** 12s DB statement limit; 15s HTTP request limit; 35m / 2,100s qualified observation maximum; old R10 admissions halted; original four integrity failures retained; Primary Hourly unmodified; no retrospective seals.

## 1. Decision requested from reviewers
Review and comment on this **design-only change request**, without authorizing a live role, schema, runtime, email, purchase, trial, migration or 72-hour pilot. **Do not merge or deploy draft PR #341.**
The only permissible current action is design review / revision and zero-spend **ephemeral** negative tests.

**Highest-priority defect A (partial-fill blindness):** The legacy managed-position view inner-joins STOP/TP records and requires FULL fill / latest state FILLED. Thus an order with a positive *partial* entry-minus-exit can be invisible. It MUST NOT be used as the authoritative universe.

**Highest-priority defect B (false parent completion):** Current canonical parent can persist when child and exit-attempt writes fail with PostgreSQL SQLSTATE `57014`; parent existence must not imply successful monitoring, scientific acceptance or completeness.

**Release objective:** A **separate successor-only** overlay that truthfully inventories and flags every residual and can accept **new prospective** source/child/position receipt sets atomically and verifiably, without changing existing scientific, model or exchange authority. Even after rollout, independent externally durable P2 journal/alert and actual monitoring acceptance remain separate prerequisites for a 72-hour pilot.

## 2. Grounded evidence, read-only
- At 2026-10-16 06:46:55 UTC, source ledger: **249** paper orders; **32** positive entry-minus-exit modeled residuals: **10 managed (10 with recorded STOP and TP references)**, **21 quarantined**, **1 unexplained/unmanaged**. Zero negative residual orders then. These numbers describe source records, not a verified live exchange book.
- **NMRUSDT LONG**, original 2026-10-02 22:04:12 UTC paper LIMIT qty **3.2**, cumulative entry fill **1.5** (2026-10-03 04:23:18 UTC), exit fill **0**, positive residual **1.5 paper units**, no recorded protection, exit attempt or quarantine. `paper_only=true`, no real order authority. This specific historic order is distinct from an older fully exited NMR paper trade.
- Rolling prior 24h at 06:46 UTC: **72** canonical RENDER_CRON parents; **4** missing all **61** child rows and all exit-attempt rows. Verified Render logs for corresponding UTC scan times **Oct15 17:23:31; Oct16 04:23:20, 05:23:27, 06:05:06** show Supabase child upsert **HTTP 500 / SQLSTATE 57014 canceling statement due to statement timeout**. 4 intervals between child-complete scans strictly >2,100s; maximum **2,394s / 39m54s**. These are a *necessary-evidence* gap, not a separately authenticated per-position monitoring trace. Exact performance cause of the timeout (trigger, lock, workload, etc.) is **not yet proven**.
- Read-only production status at 2026-10-16 07:42:31 UTC: deployed commit `33e8820bc8e4e2958e2fc20c7fb80899c4e2e65e` MATCHED, no drift, `trade_permission=false`, `order_path=NONE`; R10 **37 admitted / 1 completed / 4 integrity failures**, admission HALTED, exchange authority false; 10/10 managed paper positions retain both *recorded* STOP/TP legs.
- ALL twelve scoped existing base-source tables show RLS=true and **ZERO** RLS policy rows for a new least-privileged ordinary reader. Merely granting SELECT without role-specific RLS would yield misleading empty source results and MUST return `SOURCE_ACCESS_UNKNOWN`, not `ZERO_POSITIONS`.

Existing evidence:
`ops/reviews/successor_p0_residual_and_scan_gate_readonly_20261016.sql`,
`ops/reviews/successor_p0_residual_and_scan_safety_verdict_20261016.md`,
`ops/reviews/successor_pg16_p0_partial_atomic_monitor_gate_v01.py`.
Exactly the synthetic P0 PG16 test already passed true SQLSTATE 57014 rollback, mismatched child identity and missing position membership on prior draft SHA. These are **proof of isolated design semantics only**.

## 3. Minimal successor-only logical change set (NOT yet implemented on production)

### M1 — Source-complete read-only expected inventory
- Read all original paper orders, individual entry fills, exit fills, protective orders, 3 quarantine sources, events and available exit-attempt evidence from one coherent `REPEATABLE READ READ ONLY` transaction with source snapshot ID, server clock, collection timestamp, exact table counts and scan/fingerprint identity.
- For every unique source `order_id`, aggregate `entered_quantity=sum(entry fill quantities)`; `exited_quantity=sum(exit fill quantities)`; `residual=entered-exited`. Reject negative quantity, duplicate source IDs, unknown linkage, mismatched flags, invalid/future clocks, inconsistent states or missing source/policy. Do not clamp missing to zero when source access failed. A zero-residual *closed* order cannot erase a different NMR order ID.
- Every `residual>0` must have exactly one fail-visible classification: **MANAGED_VERIFIED_CANDIDATE**, **QUARANTINED_UNRESOLVED**, **UNPROTECTED_OR_UNKNOWN_INCIDENT**. The original view is an extra diagnostic only. Recorded STOP+TP *identifiers* alone do **not** establish active protection, actual fillability or quote quality. Quarantined/unprotected positions remain part of the expected inventory and cause scientific **NO-GO**, even when a diagnostic census itself was read successfully.
- For NMR 1.5, output a durable-to-be-stored **incident proposal** tied to its original order ID and fill sequence; never invent stop/target fills, mark it completed, auto-insert a legacy quarantine, automatically close its paper balance, or alter R10 historical rows. Without an approved persistent incident store, the result is **local/read-only diagnostic only**, not a delivered incident.
- No new trading decisions/admissions, strategy scoring, funding, profit aggregation or market orders.

### M2 — Successor-only atomic forward write + strict completion seal
- A separate **disabled-by-default successor** write endpoint/schema (naming and full SQL require review) may be prepared; neither the current parent writer nor R10 tables, triggers, source protection view, scanner schedule or cron shall be changed by this proposal.
- For **prospective new successor run IDs only**, one local PostgreSQL transaction/approved scoped RPC must bind **(a)** source parent ID + snapshot/fingerprint, **(b)** exact expected child symbol **ID + contents** manifest, **(c)** full positive-residual order-ID/entry-minus-exit **source digest** with explicit quarantine/unprotected classifications, **(d)** monitored-position quote/STOP+TP attempts with source clock/quality, and **(e)** immutable structural completion receipt. The receipt is inserted only after database read-back of **all** required rows/IDs, not only counts, and exact manifest matches; unexpected/missing row/incorrect model cohort fails CLOSED.
- Parent committed alone (including **historic** parent-only originals) is never `COMPLETE`. New success requires an exact sealed receipt and a separate **independent verifier**, which cannot rely solely on a caller-provided `complete=true` flag. Producer and verifier use distinct permissions, and local structural seal must say **NOT_INDEPENDENT_LIVE_MONITORING** until real external custody, qualified source and quote receipts exist.
- A 57014 cancellation, missing child, missing position attempt, wrong quote, 15s HTTP ambiguous write, failure before seal or same-run conflicting retry means `INCOMPLETE/UNKNOWN`, no successful seal, no promotion. Within the new successor transaction, rollback is ALL-OR-NOTHING; production legacy tables are read-only and their historic parent-only rows remain unchanged. Ambiguous HTTP response cannot be classified as no-write or as success until exact independent committed-state read-back.
- Multi-DB third-party durable journal and real external email **cannot be rolled back atomically** with Postgres by this design; they require separate outbox/append-only verified receipt chain and later independent P2 approval. Do **not** claim this single-DB transaction proves independently delivered observation.

### M3 — Fail-visible incident diagnostics without rewriting history
- Classifications: `POSITIVE_PARTIAL_UNPROTECTED`, `QUARANTINED_RESIDUAL`, `INCOMPLETE_CHILD_MANIFEST`, `POSITION_ATTEMPT_MISSING`, `57014_CHILD_UPSERT_CANCELED`, `AMBIGUOUS_COMMIT`, `SOURCE_ACCESS_UNKNOWN`, `QUOTES_UNVERIFIED`, `35M_BREACH`.
- On any incident record **UNKNOWN/FAIL** in a successor-only audit trail **only if separately approved persistent custody exists**; otherwise report research-only status, never claim alert delivery. Preserve original four R10 failure labels, older >2,100s gaps, source run IDs/timestamps and the unprotected NMR incident. No automated legacy remediation and no backdated completion receipts.
- Preserve 12s SQL, 15s HTTP, and exactly 2,100s monitoring cap (2,100 permitted at boundary; 2,101 violation). When an outage prevents new qualification, monitor-age assessment fails closed; a subsequent successful scan never retrospectively fixes the gap.
- Full cycle `scientific_pass_permitted=false`, `trade_permission=false`, `exchange_authority=false`, `order_path=NONE`. An actual qualified scientific result is a later independent decision, not this change.

## 4. Proposed file / database surface boundaries (scope is a ceiling, not authorization)
- **Included in future diff:** successor-only source reader logic; successor-only inventory classification and immutable forensic receipt model; successor-only atomic HTTP/SQL stage and readback verifier; fail-closed incident classifier; regression fixtures; separate draft-only migration/rollback scripts if and only if reviewed.
- **Excluded:** any edit to existing R10 `alpha_hunter_paper_*` source tables/views/triggers, `alpha_hunter_snapshots` legacy writers, existing scanner entry path, R10 cohort/admissions, strategy score thresholds, 35m setting, the Render Primary Hourly service, Bitget API/keys, real-order code or P3 models.
- Existing isolated `successor_pg16_p0_partial_atomic_monitor_gate_v01.py` and `successor_pg16_atomic_http_cycle_v01.py` are **tests**, NOT approved as live migrations. Production SQL, exact source column allowlist, RLS role policies and rollback DDL **do not yet exist as accepted release artifacts**.
- New dedicated production source reader, role-specific RLS policies on 12 sources, successor restricted receipt writer, persistent independent evidence store, observer deployment and provider email all require **separate itemized authorization**, even if an existing free resource were available. Do not enable a bypass-RLS `service_role` as a shortcut.

## 5. Required acceptance tests before requesting each permission
**Offline release candidate (zero-spend now):**
1. PG16 with synthetic **10 managed / 21 quarantine / 1 NMR-style partial unprotected**. Read all 32 residuals; unprotected and quarantine fail qualification; fake "observed NMR" cannot change state. Missing/duplicate entry-exit, order ID collision, negative residual and source missing policy must fail.
2. Atomic parent/child/position read-back with true SQLSTATE 57014 cancellation at child upsert: **0 newly committed parent, child, position attempts, completion receipts**. Independently seeded *old* parent-only rows remain unsealed and visible. Reject incorrect child ID with equal count, missing exact order ID, wrong digest, missing managed position evidence and conflicting retries; verify idempotence on same exact payload; deny writes via reader role.
3. Preserve 12s/15s under representative 61–63 symbol payload and concurrent normal Primary Hourly load in an **approved** nonproduction test; no claim about production p99 from a CI runner.
4. 2,100s exact boundary and 2,101s incident; inability to deliver quote/source proof and to persist recipient alerts cannot be counted as monitoring. No real protected historical positions declared safe by a synthetic pass.
5. Source RLS SELECT policies/grants tested on all 12 sources as **no-policy => UNKNOWN**, cannot read unapproved columns, cannot WRITE/SET ROLE, cannot hide anomalous `paper_only=false` row, source counts tie to a privileged independent catalog baseline.

**Preproduction review required before any live reader/write/deploy:** scoped SQL migrations/rollback and table/column list, live query plan/lock/trigger investigation of `57014` *read-only*, worst-case cost/overlap benchmark, DBA security signoff, persistent custody and real delivery review, encrypted/rotatable scoped secrets, rollout health probes and on-call availability. Existing historical writes must remain unmodified.

**Prospective production acceptance, after separate authorizations only:** first new successor read must see ALL historical positive residuals including NMR 1.5 as **unprotected incident**; no false scientific seal while NMR or quarantine remains unresolved. Any parent-only or read/child write failure shows `INCOMPLETE` and an independently persisted incident, not success. Confirm original R10 stats/positions unchanged after change and ability to rollback successor-only components without deleting incidents. Only after real independent source/quote, durable off-failure-domain custody, external deadman and **actually confirmed email inbox delivery** could a separately authorized **72 consecutive real hours** of forward observations begin. Success does not imply permission to place orders or claim profitability.

## 6. Rollout order, exact separate authorization and no-go triggers
| Stage | Review request | Permitted now? | Evidence / rollback boundary |
| --- | --- | --- | --- |
| R0 | Draft architecture & ephemeral PG16 regression | **YES, $0** | Draft PR only, all exact-head CI green |
| R1 | Create narrowly scoped real production SELECT reader & policies | **NO** | Separate SQL/security signoff and explicit approval; revoke grants + role on rollback |
| R2 | Provision scoped successor structural writer/atomic schema or observer | **NO** | Explicit code, migration & hosting/cost approval; disabled-by-default, source tables untouched; disable successor and revoke writer on rollback |
| R3 | Persistent independent second-failure-domain receipts + alert sender + external deadman | **NO** | Separate custody/provider/billing and real delivery approval; rollback preserves immutable incidents |
| R4 | Start first genuine 72-hour forward pilot | **NO** | Only after R1–R3 acceptance and **fresh explicit pilot authorization**; stop/requalify if any 2,101s gap |
| R5 | Re-evaluate scientific promotion, cost calibration and order authority | **NO** | Separate R10/P3 scientific approvals and verified causality; not part of this change |

**Automatic NO-GO/rollback triggers:** unexplained or vanished positive residual; partially filled NMR absent from independent inventory; unprotected marked managed; quarantined marked scientifically qualified; one canonical parent without child/position receipt accepted; 57014 classified successful; source roles return 0 due to missing RLS policy; duplicate/conflicting seal; >2,100s position observation gap; independent custody unavailable; provider acceptance misreported as inbox delivery; scanner/cron contention, unintended role expansion, cost/billing or R10 modification. A rollback never erases a real incident.

## 7. Reviewer questions and required future approval record
**Engineering reviewer:** Is M1 the only admissible inventory source? Is per-order partial fill/exit sequence correct? Are manifests content-bound, not merely row counts? Does R2 preserve the original parent-only evidence and timeout behavior? Is the actual cause of 57014 investigated rather than bypassed with longer timeouts?

**Security/DB reviewer:** Name the **12** exact source tables, required columns and RLS grant/policy diff. Identify separate snapshot reader and write-only successor producer. Confirm NO BYPASSRLS/service_role, TLS, role revocation, statement/load limits and SQL explain. Certify no source-schema writes and no shared admin credentials.

**Operations/science reviewer:** Confirm 10 recorded managed STOP/TP legs, 21 quarantined and NMR unprotected still fail scientific qualification; no prior R10 seals/failed horizons edited, no last-success masking; separate external receipt and alarm proofs for future pilot.

**Owner approval to be sought LATER, as distinct explicit decisions (NOT approved by reviewing this file):**
- [ ] R1 production least-privilege SQL/role changes, exact diff + rollback
- [ ] R2 successor-only schema/writer/observer, exact pinned SHA, no legacy edits
- [ ] R3 independent custody/recipient delivery, selected vendors + currency, precise monthly/one-off ceiling, no trial auto-charge
- [ ] R4 start time and scope for **72 consecutive real hours**; no retrospective start
- [ ] Separate approval if a specific R10 historical NMR repair/quarantine action is ever proposed (outside this successor change)

**Approvals granted by this document: NONE.**
**Spend authorization: USD 0.** **Live P0/P2 readiness: NO-GO.**
**Recommended next immediate step:** collect review signoffs/corrections on R0 and keep R1–R4 blocked until individually authorized.
