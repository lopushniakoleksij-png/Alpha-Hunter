# Alpha Hunter P0 — Four-Way Persistence Architecture / Index Benchmark

**Executed:** 8 November 2026, approximately 14:12–14:17 UTC  
**Safety:** £0, disposable GitHub Actions PostgreSQL 17, no production schema changes/exports/orders  
**Exact tested code SHA:** `0780a5416d5f4c835010656ef55d07409df3bdd1`  
**GitHub Actions:** [#42488585902](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42488585902) — **SUCCESS**, logs examined.

## Question and test method

Compare the four requested configurations:

| Test | Storage behavior | Indexes |
|---|---|---|
| A | Five separately committed PostgreSQL SQL statements | Existing-style synthetic |
| B | Five separately committed PostgreSQL SQL statements | Proposed partial index |
| C | Single atomic RPC transaction | Existing-style synthetic |
| D | Single atomic RPC transaction | Proposed partial index |

- **Historical scale:** 505,569 generated forward outcomes, not actual production data.
- **Graph:** seven synthetic downstream sink tables approximating verified live static path (episode→24h queue, observation→quote→freeze→payoff/calibrated-order). It does **not** replicate actual private functions, RLS, ownership, extensions, conditions or true production strategy distribution.
- **Sample:** 20 independent scan requests per `30/50/61`-symbol size per architecture/index combination; **240 total benchmark records**.
- Sequential stages were genuinely separated into five committed psql sessions (parent, symbols, signals, features, readiness), copying rows from prior atomic fixture records. This is **not the actual five PostgREST/HTTP calls**, so request network overhead is excluded; SQL SELECT-copy overhead is included. Atomic timings measure only inner RPC execution, not caller payload serialization. Absolute architecture speed comparison is therefore not a controlled apples-to-apples production estimate.
- Benchmarks were ordered rather than fully randomized; warm-cache effects, load and synthetic distribution may differ. p99 on **n=20** does not characterize real tail risk.
- Both index phases used the same synthetic outcomes and full-transaction core+downstream logic. All payloads remained paper-only and QA-labelled.

## Actual p95 SQL latencies (ms) — not production

| Architecture | Index | 30 symbols | 50 symbols | 61 symbols |
|---|---|---:|---:|---:|
| Sequential | Current-style | **1,037.18** | **1,721.46** | **2,075.44** |
| Sequential | Candidate partial | **273.24** | **434.27** | **533.90** |
| Atomic | Current-style | **999.17** | **1,672.05** | **2,077.01** |
| Atomic | Candidate partial | **366.52** | **539.15** | **672.68** |

For the synthetic 61-symbol cohort, candidate indexing lowered measured p95 by approximately **74%** with sequential SQL stages and **68%** with the atomic SQL RPC. The atomic candidate is not necessarily faster than sequential SQL in this fixture; its primary benefit is **transaction integrity**. No sampled synthetic SQL call exceeded 12 seconds. These results **must not be extrapolated to production latency**.

## Fault injection: exact non-atomic failure mechanism reproduced

- In a separate disposable 30-symbol synthetic request, parent INSERT committed in its own SQL connection.
- Symbol INSERT in a *second independent connection* failed via **deliberately injected SQLSTATE 57014**.
- Persistent QA state was **one parent, zero symbols, zero simulated observations, zero payoff records**. This demonstrates how sequential committed stages can retain a misleading parent.
- The earlier **real PostgreSQL-enforced statement_timeout** tests of the atomic RPC already verified all-five-family rollback and idempotent retry in isolated PostgreSQL 17; this new test does not constitute an authentic full-graph cancellation test.
- The 2x2 verification script compared all sequential-vs-atomic synthetic payoff percentiles across **120 identity-matched pairs**, and checked required core/downstream cardinalities. All passed.

## Required release gates still unmet

**Do not upgrade production release status from NO-GO.** Before the repair is production-ready:
1. Use an authorised **private** schema-only production PostgreSQL export restored into existing private QA with the complete transitive private function graph.
2. Verify exact schema, role, extension, trigger, ownership, configuration, data distribution and scientific cutoff parity. Check baseline/modified trigger timing, locks, WAL, cache and p50/p95/p99 across realistic workloads and concurrency at actual effective statement timeout.
3. Verify full deferred/scientific/paper side effects and source custody.
4. Obtain qualified independent DBA, security and operational approvals bound to the tested release commit and explicit owner authorization.
5. Only then consider controlled production release, ten consecutive complete scans, 24-hour observation and rollback evidence.

No public repository artifacts contain private function bodies, production credentials or real customer data. No production database writes, scanner modifications, deployments, merges or real-money trades were authorised or performed.
