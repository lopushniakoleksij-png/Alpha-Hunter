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
