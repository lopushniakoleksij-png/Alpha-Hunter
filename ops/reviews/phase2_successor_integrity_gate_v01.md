# Alpha Hunter Phase II — P0/P1 successor-only acceptance package

**Status:** Isolated research candidate; 0 production changes. Not a runtime repair or approval to trade.

## Evidence anchor (2 November 2026 UTC)

Connected read-only production Supabase check:

| Run | Declared children | Persisted children | exit-attempt receipts |
| --- | ---: | ---: | ---: |
| 09:05 | 61 | 61 | 3 |
| 09:23 | 61 | 0 | 0 |
| 09:43 | 61 | 0 | 0 |

Open paper-position view reported three rows, each with two **recorded** protective legs. These do **not** guarantee independently verified monitoring through the two missed scans.

## Contents

- ops/reviews/phase2_successor_integrity_gate_v01.py: Pure fail-closed validation of canonical child IDs, unique per-position current-run monitoring receipts, independently supplied previous observation timestamps and unmodified 35-minute ceiling, source and scientific fingerprint identity, immutable prior failure. Also diagnostic LONG bid / SHORT ask executable-side capacity check (never a fill claim).
- tests/test_phase2_successor_integrity_gate_v01.py: 17 standard-library unit tests, including 61 expected/0 persisted, failed monitoring, >35m gaps, drift, quote-side and unresolved stop precedence.
- .github/workflows/phase2-successor-integrity-contract-ci.yml: no-credentials PR CI; no market, account or production connection.

To run locally: python -m unittest discover -s tests -p 'test_phase2_successor_integrity_gate_v01.py' -v

## What this does **not** prove or change

- No production scanner/Supabase code path is wired; no issue is fixed in production.
- Synthetic local tests alone do not prove the combined PR #371/#372 publication repair or #375 index candidate works at production load.
- scientific_eligible is only a **local input-consistency gate**, never a profitability pass, executable quote provenance, verified exchange fill, or admission authorization.
- Continuous missing historical 35-minute observations remain scientific failures even if later scans recover. The initial previous receipt must have approved independent custody; no invented initial observation.
- Do not count R8/R9/R10 historic outcomes as successor confirmations.
- Frozen 24h horizon, 10 strategies, >=5R rule, management risks and existing old cohorts remain unchanged.

## External release requirements

1. Benchmark SQL trigger chain and canonical child persistence on isolated PostgreSQL 16/17 + real PostgREST with full-state and failure injection; compare #371 and #372, test #375 index candidate and rollback.
2. Obtain source-authenticated quote lineage, full as-of-run residual position inventory, atomic durable receipts and independent alert delivery.
3. Independent DBA/security, scientific, ops and release approvals; ensure no merge inadvertently auto-deploys protected cron.
4. On a separately approved future successor release only, establish prospective correct-cadence evidence under a new immutable fingerprint. Keep live order path off.

**No merge, deploy, SQL write, altered old record or new spending done in this package.**
