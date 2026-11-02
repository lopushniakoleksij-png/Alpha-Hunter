# P2 all-residual monitoring evidence gate — 12 Oct 2026

**Status:** isolated research only; no migration, merger, Render redeploy, task update, paper/real order, R10 restart, scientific evidence backfill or risk-gate relaxation.

## Fresh exact live diagnostic, read-only

At **2026-10-12 14:51:53 UTC**, canonical `RENDER_CRON` parent `403a00517276c12e65a57b5760a5efb3`, collected `14:43:39.429751 UTC`, stored all **62/62** symbol child rows and recorded **11** modeled paper exit attempts for the 11 currently managed positions.

- All 11 attempt rows have non-NULL and strictly positive best bid, ask, bid/ask depth sizes, `NO_TRIGGER` outcomes and an empty `blockers` array.
- 4 of 11 have `evidence.quote_source="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"`, 7 of 11 are **unlabeled** in `evidence.quote_source`. Do not invent venue provenance from values or table name. An incomplete source label blocks local quote qualification even though prices exist.
- 4 of 11 attempt timestamps deviate more than **30 seconds** from canonical parent collection time; maximum **36.437252 seconds**; 0 exceed 60 seconds. **30 seconds is a proposed research-review window, not an approved production threshold.** Offset by itself is not proof of missed stop/TP execution, nor a reason to widen existing frozen 35-minute monitoring cap.
- Historical parent-only or incomplete scans and already observed >35m gaps remain invalid scientific evidence; a successful latest scan cannot heal missing historic observations.
- Full historic modeled paper fill-minus-exit inventory has previously shown 33 positive residual orders vs 11 in managed protection view, with explicitly quarantined/legacy residuals (including NMRUSDT long 1.5 units). The exact present count must be recomputed forward from a genuinely authenticated source snapshot before any new deployment; never use a current managed view as full residual source.

## Code artifacts in draft PR #341

`ops/reviews/successor_all_residual_monitor_qualification_v01.py` is a **PURE** scorer of an externally supplied, consistently reconciled AS-OF all-cohort fill-minus-exit ledger, per-position disposition (managed, quarantined, unprotected incident), previous-observation source receipt and modeled exit-monitor attempt. It requires:

1. Every residual order ID to appear in exactly one explicit disposition; quarantined/unprotected residuals always remain a distinct **blocker** instead of being silently removed, optimistically closed or included in 35m scientific PASS.
2. Every managed entry order to have exactly one same-run, same-symbol, same-direction monitoring attempt with real positive bid/ask/book quantities, empty blockers and an explicitly approved source label, plus source timestamps within an **explicit review policy**.
3. The interval between a local quote observation and a previous **claimed independently sealed** per-position receipt or genuinely recent fill to be `0–2100 seconds` inclusive. Old fills alone cannot replace missing previous observations. Even a `seal_verified=True` caller claim remains unauthenticated until bound to a physically stored independent receipt.
4. The result always sets `scientific_pass_permitted=false`, `trade_permission=false`, `exchange_authority=false`, `production_promotion_permitted=false` and `independently_authenticated_source=false`, whether local evidence is present or missing.

`tests/test_successor_all_residual_monitor_qualification_v01.py` covers complete **supplied only** evidence, an omitted legacy partial's attempt, missing quote provenance, exact 35-minute accepted vs +1 second refused, old fill without previous observation, quarantine, explicit unprotected incident, duplicate attempts and missing dispositions.

`ops/reviews/successor_dual_pg16_position_diagnostic_v01.py` extends the draft-only **TWO separate ephemeral PostgreSQL 16 servers** test: writes per-order diagnostic records (including the unprotected historical partial) to an append-only internal secondary database, injects an independent MAIN analytics timeout and proves the diagnostic rows survive without inventing a main scan success. A timeout **inside the diagnostic journal itself** must rollback all rows from its incomplete transaction. Journal records intentionally hard-code **source_authenticated=false, scientific_pass=false, position_protection_proven=false, no trade authority**. The journal is an incident classifier, not a running quote observer, execution engine, stop protection, or authenticated source authority.

**Expected next gate, not silently considered done:** owner-reviewed prospective production source capture using one authenticated immutable as-of ledger watermark, direct per-order quote-source receipts (not unlabeled attempts), previous per-position sealed observations, independent failure delivery, and live-like 35-minute monitoring continuity under Supabase/PostgREST contention. Require proof for the **whole residual universe**, including quarantines/incidents, plus healthy database write path; frozen R10 admissions remain halted throughout.

The local journal and scoring artifacts are never imported into active `storage.py`, `paper_exit.py` or the Render cron; PR remains **DRAFT**.


## 15 October P0 hardening gate — research branch only

Read-only live window 2026-10-14 05:50Z to 2026-10-15 05:50Z: 72 canonical parent scans; 71 child-complete; one parent-only; a separate 61/61 child-complete cycle had zero exit attempts. All ten managed paper positions had a 38.637-minute gap between recorded exit attempts, exceeding the unchanged 35-minute limit. Of 770 observed paper attempts, 352 lacked quote_source; 13 were more than 30 seconds from parent scan time (30s is a research fixture, not a frozen production threshold). A NO_TRIGGER label with numeric prices but missing source custody is not authenticated monitoring.

The research-only receipt scorer now rejects missing attempt identity, time, or blocker list and mismatched quote book, source label or observed time. The all-residual scorer rejects missing prior sealed receipt time and self-referential previous run. These checks establish only caller-supplied local evidence consistency, never source authentication, scientific pass, trade authority or position protection.

### Required future source authentication and monitoring acceptance

- Authorized independent collector: verify genuine Bitget public HTTPS endpoint and TLS peer identity, exact requested symbol and request ID, exchange timestamp, positive uncrossed book and original response digest at transport acquisition. TLS authenticates a channel; it is not a Bitget-signed price receipt.
- Independently durable append-only custody: trusted collector identity, capture clock, canonical run and fingerprint, consistently read all-cohort paper fill-minus-exit watermark, source book identity and per-position prior sealed observations. Supplied metadata, mutable downstream labels and local mock HTTP plus ephemeral HMAC are not independently authenticated venue evidence.
- Per-position continuity: every managed residual position gets one qualified source-linked receipt within the existing 35-minute bound. No missing, stale, conflicted, mixed-run or retrospectively fabricated records may be labelled successful. Keep quarantined residuals and unprotected NMRUSDT 1.5 paper units visible as incidents, not closed trades.
- Fault-injection: transport timeout, primary PostgREST timeout, secondary journal timeout, both destinations failing, interrupted transaction, idempotent retry and replay, restart/recovery, and missing quote provenance must produce explicit UNKNOWN/FAIL and durable independent alerting or visible missing-evidence audit.
- Prospective proof: a separate owner-reviewed, load-representative forward window must meet zero unjustified 35-minute gaps, complete authentic source receipts and verified failure alert delivery before deployment permission. Isolated green CI does not prove live operations, executable exit capacity, slippage or profitability.

Boundary unchanged: production main and Render hourly, R10 original fingerprint/thresholds/admission halt, all positions and historical records, 12s SQL / 15s HTTP / 35-minute gates and real-order authority. No merge, production writes, migration, deploy, backfill or test restart.
