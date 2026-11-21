# Alpha Hunter — P0 Render run-ID-to-Supabase persistence join (20 November 2026)

**Purpose:** Establish a real provider-log-to-database identity join for the legacy production scanner, beyond time-window matching or self-reported `payload.validation_identity.run_source`. **READ-ONLY. PRODUCTION NO-GO.**

## Verified sources and join method

- From connected Render workspace `tea-d9nlevnqj5pc73f5antg`, original canonical cron resource `crn-d9nmbjbm8hqs73elu6hg`, query application logs for **`Run ID:`** and **`Supabase:`** separately over one-hour non-overlapping windows from **16:00 to 22:00 UTC** on 20 November. Each window returned 1–3 `Run ID:` lines and the same number of `Supabase:` lines; every pair had the identical second-level timestamp and was matched in chronological order within that provider resource. `Supabase:` records were explicitly `FAILED` or `SAVED`. One broader initial log query returned HTTP 503; retry with a bounded 17:00–18:00 window succeeded. No log processing used raw passwords, SQL, private archive paths or tokens.
- From connected production Supabase, execute a **SELECT-only** exact `run_id` lookup for all 16 *actual Render-log run IDs*, with left join to `public.alpha_hunter_snapshots` and read-only correlated counts in the four child families (`alpha_hunter_symbol_snapshots`, `alpha_hunter_signals`, `alpha_hunter_signal_features`, `alpha_hunter_readiness_observations_v01`). The lookup returned all 16 requested IDs; 3 had no parent, and 13 had parents.
- Direct exact ID correspondence proves **these records/lack of records share the run identities printed by the named Render service**, unlike earlier reliance on claimed publisher labels. It does **not** independently bind individual HTTP requests to PostgreSQL SQL statements or prove zero transient results outside these queried tables. A missing parent describes current readback, not necessarily whether an intermediate transaction ever existed.
- Columns below: counts are `(declared symbol_count, symbol rows, signal rows, feature rows, readiness rows)`. `NO_PARENT` indicates parent missing and each of four child counts zero.

## Exact 16-run matched evidence

| Render log UTC | Run ID from Render and queried in Supabase | Render save log | Database readback | Parent UTC | Counts |
|---|---|---|---|---|---|
| 2026-11-20 16:09:08 | `1dd09897fd04e1b12879f73d45aaea4b` | FAILED | NO_PARENT | — | — |
| 2026-11-20 16:26:03 | `ac7a99179594adf0a81992840a68cb14` | FAILED | PARENT_ONLY | 2026-11-20 16:24:17 | 60,0,0,0,0 |
| 2026-11-20 16:46:10 | `eeb967030db23f00d8d238165d326e0c` | FAILED | PARENT_ONLY | 2026-11-20 16:44:10 | 60,0,0,0,0 |
| 2026-11-20 17:08:25 | `0cb8ca6efdafa8d9f5fa6118a9ecb95e` | FAILED | NO_PARENT | — | — |
| 2026-11-20 17:25:43 | `1fd537f5de6352c584f637ad7d67c0e0` | FAILED | NO_PARENT | — | — |
| 2026-11-20 17:46:22 | `80f6914fd5767ecada551b980ce8ae14` | FAILED | PARENT_ONLY | 2026-11-20 17:44:05 | 60,0,0,0,0 |
| 2026-11-20 18:06:33 | `337e0ec81037054b377f106c63ce06ca` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 18:05:34 | 60,60,60,60,60 |
| 2026-11-20 18:23:53 | `aa88e7512d93700d44b954f9bc46330a` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 18:23:24 | 60,60,60,60,60 |
| 2026-11-20 18:43:45 | `8e839ee4f98650bb4cba5743b573c1cc` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 18:43:18 | 60,60,60,60,60 |
| 2026-11-20 19:06:20 | `bf96c1935efc17e8a771e4abbe0bfb57` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 19:05:43 | 60,60,60,60,60 |
| 2026-11-20 19:24:20 | `769bbd86091e62c62e0f914e5fa1a07a` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 19:23:26 | 60,60,60,60,60 |
| 2026-11-20 19:43:59 | `5cfd31a06e847dd409f44fe194c30fc7` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 19:43:26 | 60,60,60,60,60 |
| 2026-11-20 20:06:17 | `3f8def897319c4b50c4dffcf317b3544` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 20:05:49 | 60,60,60,60,60 |
| 2026-11-20 20:23:56 | `29c1725fd1beec3bba9f5f621d732108` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 20:23:23 | 60,60,60,60,60 |
| 2026-11-20 20:44:02 | `4fd2d8aee00a4c533340d6502951967a` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 20:43:25 | 60,60,60,60,60 |
| 2026-11-20 21:06:30 | `f42ecd0cfa4195738f9f744efb37edce` | SAVED | CORE_COUNTS_MATCH | 2026-11-20 21:05:57 | 60,60,60,60,60 |

**Exact result: 6 FAILED logs:** 3 `NO_PARENT` + 3 `PARENT_ONLY` (parent declared 60 symbols but zero four-family child rows). **10 SAVED logs:** all ten had `60,60,60,60,60` core counts. No contradictory `SAVED`/incomplete cases among **this bounded 16-run sample**. Identity and count parity alone do not validate field contents, downstream paper ledger, duplicate lifecycle side effects, transaction atomicity or a durable production fix.

Render provider event corroboration: 16:01–16:49 UTC and 17:01–17:49 UTC scheduled cron-job runs ended `unsuccessful` with **nonzero exit 2**. The succeeding 18:00, 19:01 and 20:01 provider cron jobs ended `successful`. The 21:01 run had **not yet returned a completed provider event at prior query time**, despite 21:06 `SAVED` application log; do not equate a scan's log success with completed cron status.

## Correctly limited engineering inference

**More than one failure shape is real.** At least 3 failed scanner logs have **zero current parent and children** in Supabase; another 3 retain **parent-only evidence**. A proposed five-family atomic RPC is intended to avoid partial persistence, but is **not installed in production** and is **not independently proven** against the authentic trigger graph. A transaction-level source error, API timeout vs commit ambiguity and exact cause of no-parent failures remain open. Current successful scans occurred on the October production revision, not the unmerged candidate.

## Mandatory follow-up and release boundaries

1. Preserve these exact 16 `run_id` values as a read-only incident reconciliation cohort; do not delete, backfill or silently reclassify failed history.
2. The next authentic isolated PG17 benchmark matrix must exercise **both** missing-parent and parent-only failure modes, including read timeout *before parent*, timeout *after parent before children*, lost acknowledgement, repeated same-run retries, conflicting retries, concurrent writers, rollback and nested downstream triggers.
3. DBA to review restored production-equivalent schema, extension/role/function/trigger fingerprints and WAL/locks/latency; independent security reviewer to verify effective privilege and safety boundaries. Both must sign for the immutable release commit. Private Codespace terminal/archive inaccessible to connected tools, so **NO** authentic QA restored-clone tests or independent sign-off are claimed.
4. Keep PR #445 draft/unmerged, only one canonical scanner, paper-only R10, real orders disabled, and production **NO-GO**. No production writes, migration, deployment, scanner restart, money or paid infrastructure.
