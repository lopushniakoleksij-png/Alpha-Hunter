# P2 source-ledger / Bitget quote-provenance acceptance contract (REVIEW ONLY)
**15 October 2026 | zero new spend | draft PR #341 | no production use**

## Decision

**ACCEPTANCE CONTRACT SPECIFICATION** is testable against submitted synthetic evidence. It is deliberately incapable of declaring actual live source authentication, authenticated Bitget-signed prices, complete operational position monitoring, delivered alerts, scientific R10 eligibility, validated net profitability, or trade authority.

Do **not** merge, deploy, create a paid service, create a production role, grant credentials, insert/modify paper positions, rescan the universe, change cron/timeouts, backfill missed scans, restart R10 or change Primary Hourly. Freeze the existing R10 **2,100 seconds (35 minutes)** maximum monitoring gap and fingerprint.

This contract integrates (rather than replacing) existing P2 investigations: `successor_pg16_repeatable_source_capture_v01.py`, `successor_forward_asof_inventory_v01.py`, `successor_public_https_capture_v01.py`, `successor_forward_quote_transport_custody_v01.py`, `successor_p2_ambiguous_http_monitor_gate_v01.py` and `successor_p03_residual_continuity_v01.py`. Previous isolated timeouts established that a success-logged scan can have missing child/monitoring evidence; never infer successful monitoring from a parent row.

## Required *future operational* evidence, exact acquisition boundaries

**S1 — independently captured complete source ledger.**
1. Owner-approved *least privilege* dedicated SELECT-only, no-BYPASSRLS PostgreSQL source role, narrow grants, TLS chain / server identity validation, bounded pool and query cost. Production creation is **NOT AUTHORISED**. The present test fixture has `SUPABASE_PG_SOURCE_TEST_ONLY` and makes no network calls.
2. Source collector records actual transport identity and DB server session identity; begins ONE `REPEATABLE READ, READ ONLY` transaction with real PostgreSQL `pg_current_snapshot()`, source time, and a bounded capture clock. Query unfiltered all-cohort physical orders/entry fills/exit fills and dispositions/protection records, not only today's managed view.
3. For **all three physical ledgers** persist individual ordered row IDs, count, deterministic canonical row digest, source snapshot token, minimum/maximum timestamps and row-watermark, transaction completion result; reject any missing table, inconsistent snapshot, missing/duplicate identity, malformed/future/over-exit/partial record, server timeout, unknown commit, empty inventory that cannot be proved complete, or missing seal.
4. Compute `filled - genuinely exited` for *every* positive residual; classify separately `MANAGED_WITH_STOP_TP`, `QUARANTINED_NOT_CLOSED` and `UNPROTECTED_INCIDENT`. The known NMRUSDT LONG 1.5 partial residual remains a real *paper ledger* incident, and 21 quarantines are not proof of closed exposure. Each managed row requires actual STOP and TARGET record identities bound to the SAME source snapshot; strings alone do not attest real stops.
5. Commit an append-only independently secured inventory receipt **before** any downstream success state, with a key administered separately from the source/collector; then a verifier, with trusted keys and a separate read channel, re-reads raw stored rows, recomputes digest and checks chain. HMAC proves key-holder integrity, **not** upstream completeness if the collector signs incomplete/fabricated rows. A caller's `complete=true`, `seal_verified=true`, raw hash or `pg_current_snapshot()` token by itself never establishes source authenticity.

**Q1 — transport-bound Bitget public market book.**
1. Obtain public **GET** for each distinct managed futures symbol at `https://api.bitget.com/api/v2/mix/market/ticker?symbol={SYMBOL}&productType=USDT-FUTURES`, no redirects, authenticated TLS hostname `api.bitget.com`, no exchange credentials and no order endpoints. Symbol universe scan is NOT needed.
2. Store request ID, exactly requested symbol/product type, HTTP status/content-type, original *raw response bytes*, bytes SHA256, source run, and actual UTC collector time; validate result code `00000`, single exact symbol, exchange quote timestamp, positive best bid/ask sizes and noncrossed prices. Accept source age **[-60,+120] seconds** at capture and quote alignment to source as-of within **120 seconds**. These quote windows are evidence-freshness checks, **not** a relaxation to R10's frozen 35-minute observation interval.
3. Seal quote bytes/digest in a separately managed append-only custody journal. Any stale quote, symbol mismatch, lost raw bytes, changed content, redirect/TLS failure, replayed request identifier or missing journal transaction becomes **UNKNOWN/FAIL**, not a good last price.
4. A public TLS-protected API response is **transport-authenticated only**: **Bitget has not supplied a cryptographically signed market-data price in these experiments**. A quote also does not verify executable fill/exit liquidity, realized slippage or a real trade. Do not print `VENUE_SIGNED`, `REAL_EXIT_EXECUTED` or fully cost-validated status.

**M1 — every managed position must be observed, never inferred.**
1. For each positive-residual managed *order_id* (including partial fills), independently recorded observation binds source-manifest digest, source event digest, exact stop/target IDs, matched quote event digest, symbol/direction, side-specific book fields, UTC actual quote-observation time, and predecessor signed receipt digest. One unique observation per order per cycle; quote can be shared across same-symbol positions only with independently confirmed linkage.
2. Verifier checks receipt MAC from a **separately held verifier key**, event digest against stored raw bytes, previous journal observation exists and is independently verified, exact order ID and source run, no unknown/duplicate/omitted managed positions. **Historical attempts with only quote_source text or self-attested `seal_verified` are insufficient.**
3. Frozen R10 comparison: previous and current **independently qualified observation** timestamps must be monotonic and no more than **2,100 seconds apart**. **35:00 PASS boundary; 35:01 FAIL boundary**. First future observation is `NO_PRIOR_SEALED_OBSERVATION`, cannot prove prior 35-minute coverage. No reconstruction or restarting failed R10 evidence.
4. Explicitly preserve `QUARANTINED_NOT_CLOSED` and `UNPROTECTED_INCIDENT` as separate **unresolved diagnostic incidents**. Stop/target records alone do not establish independent quote observation or an actual protective exchange order.

**F1 — failure, custody and alert delivery.**
1. A parent with missing child, missing current/prior quote seal, wrong source snapshot, missing one per-position receipt, DB ambiguous HTTP commit or secondary journal timeout is **UNKNOWN/INCOMPLETE**. Only re-read independently persisted exact bytes to resolve ambiguity; never retry an unknown production fill/order or manufacture a new scan.
2. Add append-only unique incident/outbox events: unknown inventory, stale quote, invalid source, receipt missing, 35m breach, collector dead, journal unreachable, unprotected residual and changed quarantine. Durable outbox `ENQUEUED` != provider `ACCEPTED` != independently tested `RECIPIENT_DELIVERED`. Do not claim the latter on a CI-only dummy event.
3. The collector itself can fail; external dead-man monitor must watch heartbeat independent of BOTH Supabase and custody, and independently alert on outage. Persistent custody, restore tests, long-lived keys, verified source role and external alarm receipt require separate deployment owner approval, which is withheld until earned revenue and explicit payment approval.

## Current acceptance code and falsification

`ops/reviews/successor_p2_source_quote_provenance_contract_v01.py` is a PURE reference verifier. Its caller must provide three verifier-held independent test keys (source/quote/position), sealed source metadata and rows, raw Bitget JSON-response bytes and signed quote records, per-order predecessor and current sealed observation records. It never accepts caller-provided `seal_verified` as evidence. It explicitly rejects source table omissions/count or digest mismatch, unreconciled or unclassified historical partial fills, forgery/wrong signing key, unsafe role/transaction claims, changed raw bytes, false quote price-signature claims, wrong venue URL, stale/crossed book, wrong symbol, wrong stop/target, source-quote chain mismatch, missing managed position, journal record omission, time backdating and >35-minute gap.

Its ONLY positive local classification is:
`LOCAL_SIGNED_EVIDENCE_CANDIDATE_NOT_UPSTREAM_AUTHENTICATED`, with
`source_authenticated_by_independent_live_connection=false`,
`venue_quote_signed_by_bitget=false`,
`operational_independent_custody_proven=false`,
`continuous_prospective_35m_proven=false`,
`actual_alert_delivery_verified=false`,
`scientific_pass_permitted=false` and all trade permissions false.

Negative tests in `tests/test_successor_p2_source_quote_provenance_contract_v01.py` only use synthetic static fixtures, ephemeral signing keys, a fake `SUPABASE_PG_SOURCE_TEST_ONLY` identity, and *no web/Supabase/database connection*. They do not by themselves prove a live source or persistent operational custody. The previously passing actual PG16 isolated tests demonstrate a separate short-lived journal commit and PostgREST HTTP rollback/timeouts, not live monitoring.

## Release decision and next cost-free step

**P2 CONTRACT REVIEW acceptance requires:** (1) this spec and strict negative tests PASS on the exact draft PR head, (2) tests confirm no class can issue scientific/trading PASS, (3) all protected R10 and Primary Hourly settings remain unchanged. A pass means only **CONTRACT TESTED**, not operational monitoring.

**P2 LIVE SOURCE/QUOTE ACCEPTANCE remains BLOCKED** until separately approved real read-only source role + authenticated source capture, live HTTPS quote custody with separately controlled keys, long-lived independently backed up journal, verified alert delivery and a prospective forward window with every managed position observed within frozen 2,100 seconds. Owner has prohibited new spending until genuine earned revenue plus a separate charge approval. Do not merge or deploy.

After contract review, next engineering gate is evidence of exact source/custody identity and forward missing/ambiguous cycle classification on an independently persistent collector; **do not spend** to accelerate it. Next financial/profitability step (P3) is execution cost validation, which cannot promote R10 while P2 remains blocked.
