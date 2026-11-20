# P1 historic modeled-paper partial-fill regression — final isolated review
**15 October 2026 10:33–10:36 UTC. Draft PR #337 only. Zero new spending, no production DB writes, no merge/restart/deployment.**

## EXACT LIVE source queries exercised (SELECT only)
Both original SQL files were executed **unchanged in their SELECT bodies**, with only an outer SELECT to aggregate output:
- `legacy_ledger_balance_readonly_20261012.sql`: 249 modeled paper orders: 217 `BALANCED_OR_UNFILLED`, **32 `POSITIVE_RESIDUAL_REQUIRES_COVERAGE_AUDIT`**, no orphan/overfilled/over-exit class in the observed production result.
- `legacy_residual_coverage_readonly_20261012.sql`: **10 `MANAGED_PROTECTION_RECORDS_PRESENT`**, **21 `QUARANTINED_RESIDUAL_PRESERVE_EVIDENCE`**, **1 `UNPROTECTED_RESIDUAL_REVIEW_REQUIRED`**; only NMRUSDT in the unprotected category, residual exactly **1.5**.
- Source snapshots were read sequentially at 2026-10-15 10:33:08 UTC and 10:33:12 UTC, respectively. These are **retrospective SELECTs**, not one independently authenticated cross-query AS-OF transaction or durable forward receipt. No claimed historical scientific monitoring pass.

## Exact NMR live ledger truth (separately read 2026-10-15 10:27:39 UTC)
- Pre-R8 modeled paper order ID `9975630880b549753d81aa4708eea321` NMRUSDT LONG.
- Original ordered **3.2**; one modeled fill **1.5** on 2026-10-03 04:23:18Z; unfilled entry remainder **1.7**; modeled exit 0; unexited modeled residual **1.5**. No legitimate recorded closure.
- **0** open protection records, **0** recorded exit-monitor attempts, **0** entry/exit/reconciliation quarantine records, and not a member of R10. The original 1.5 is a paper-ledger safety/evidence incident, NOT evidence of actual exchange exposure.
- Existing primary R10 admission halt and prior frozen failures remain immutable; no retroactive stop/target, cancellation, exit fill, result substitution or fake quarantine is permitted.

## NEW concrete P1 regression on actual ephemeral PostgreSQL 16
- `ops/reviews/legacy_p1_pg16_behavioral_regression_20261015.py` executes the two actual SQL files in one local disposable GitHub Actions PostgreSQL 16 database with no production/venue credentials.
- Dedicated `.github/workflows/legacy-p1-pg16-regression-review-20261015.yml` uses only `127.0.0.1:5441`, exact ephemeral DSN, explicit opt-in and driver pinned to `psycopg[binary]==3.2.10`. Ephemeral fixture DDL/DML are strictly inside this disposable DB, NEVER Supabase.
- The 2026-10-15 initial isolated workflow **SUCCESS** verified: NMR-like partial 3.2/1.5 retains exactly 1.5 positive residual and 1.7 unfilled is not confused for a modeled position; terminal lifecycle marker cannot erase positive residual; 1 STOP alone stays unprotected; STOP+TP without managed membership remains a coverage gap; quarantines remain incidents; synthetic legitimate exit alone clears synthetic residual; orphan fill/exit, overfill and over-exit classes fail visibly.
- The four existing static select-only/no-production-write SQL contract tests also PASS. Always verify exact final commit workflow again; first workflow commit `307fba2a39c1bb9b1038b325d7dd5028aac2d935` produced `P1_REAL_PG16_PARTIAL_FILL_REGRESSION_PASS`.

## Reviewer decision / rollout
1. **P1 READ-ONLY ROOT CAUSE: VERIFIED** — older pre-R8 partial was excluded by current managed/inventory cohort/full-fill predicates (current predicate explanation, not reconstructed historical runtime causation).
2. **P1 ISOLATED BEHAVIORAL REGRESSION: PASS** — original diagnostic SQL exposes errors on disposable PG16 and production SELECT checks match the expected categories.
3. **P1 HISTORICAL REMEDIATION: OPEN / NO-GO** — no archival incident/immutably reviewed disposition deployed, NMR has no real exit/protection, and no existing paper position was touched.
4. **NO MAIN MERGE.** Draft PR #337 and issue #338 remain open, unmerged, research/audit only. Do not corrupt R10 admission and pre-existing position management to make a dashboard look healthy.
5. **ROADMAP HANDOFF TO P2** — advance read-only canonical run completeness and exact managed per-position 35m gaps + provenance. Current successor-only P2 receipts/dual-PG16 CI remain separate in DRAFT PR #341; prospective durable source/quote authentication and real alert delivery are not yet proved and **paid deployment is on revenue-first hold**.

**P1 GATE: REVIEW PASS / OPERATIONAL REPAIR NOT IMPLEMENTED. P2 IS NEXT.**
