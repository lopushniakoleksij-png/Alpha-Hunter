# Alpha Hunter — Harada V1.1 P0 Repair Execution Ledger

**Activated:** 8 November 2026 UTC (owner-requested execution mode)  
**Repository:** `lopushniakoleksij-png/Alpha-Hunter`  
**Working branch:** `fix/supabase-write-timeout-qa` — [draft PR #445](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/445)  
**Goal:** Eliminate symbol-write latency/partial commits, establish authenticated publishers and complete independent release acceptance.  
**Release:** **PRODUCTION NO-GO** · **£0** · paper/research only · protected scanner unchanged.

## Live execution rule

Select one highest-priority **non-blocked** action, execute actual engineering, verify CI/read-only evidence and update the matching ID. The **critical path** is **authentic private trigger-graph clone → combined atomic writer + index p95/p99 and rollback → source custody → independent DBA/security approvals → controlled owner-authorized release**. If the private clone is blocked, advance genuinely independent nonproduction QA instead of reproducing planning documents.

**Crucial scope warning:** The PASS statuses for isolated PostgreSQL fixtures mean **only that specific synthetic test passed**. No synthetic/CI PASS is a substitute for production-equivalent performance, downstream authenticity or an external signature. Every broader stage remains OPEN until its own gates are met. Never change current production DB, scanner, main, trading permissions or spend money.

## Current action counts

**PASS 13 · ACTIVE 20 · BLOCKED 26 · NOT STARTED 5 · TOTAL 64.** Counts reflect evidence and known dependencies, not a percentage of production readiness.

## Verified recent execution

- **2026-11-08 E3 (ACTIVE, CI pending):** Added ephemeral-only lost-ack simulation using separate PostgreSQL client sessions, a discarded successful first RPC receipt, exact 61-child and 306 synthetic-trigger-effect assertions, and an idempotent retry. Exact branch head `cabba405b71f98fb1a97934e2fe0de8f56e7ac2e`; no passing CI claimed yet. This is not a real network partition or authentic private trigger graph. Next: inspect exact-head Actions run and full logs; fix failures before marking scoped PASS.


- **2026-11-08:** PostgreSQL 17 GitHub Actions [run #42480712005](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42480712005) **SUCCESS**, tested exact commit `1c9c0e7bd6e955ae2a2f9357255a3edc2c89b4fb`. A real PostgreSQL statement timeout (200ms) interrupted a nested 61-symbol synthetic trigger after an intentional 600ms delay. All five core table families and synthetic trigger side effects rolled back; retry committed once, duplicate replay zero new effects. This is a genuine PostgreSQL timeout, **not** a production-equivalent 12s latency benchmark.
- **2026-11-08:** Supabase read-only showed Render parent-only failures at 11:03 (43/0), 11:22 (45/0), 11:42 (43/0), 12:04 (46/0), and complete 12:22 scan (48/48). No production repair was performed.
- **Earlier:** 25 production PostgreSQL timeouts sampled; 21 in payoff-geometry call stack, 20 interrupted within percentile SQL; complete nested time attribution not yet measured.
- **Clone blocker:** secure production schema export not available to existing private Codespace; known private function bodies and credentials must not enter public GitHub. No paid Supabase branch provisioned.

## 64-action board

### Pillar A — Root cause and latency

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| A1 | Reconfirm production timeout evidence | **PASS** | 08 Nov structured PostgreSQL logs: 25 57014; 21 payoff path |
| A2 | Inventory full transitive trigger graph | **ACTIVE** | Production path identified; full transitive private graph not cloned |
| A3 | Confirm schema/function/index/grant fingerprints | **PASS** | Four structural digests matched 07 Nov baseline (08 Nov check) |
| A4 | Reproduce historical percentile workloads | **ACTIVE** | 495k-row isolated synthetic percentile query benchmark; authentic workload outstanding |
| A5 | Isolate and time nested operations | **BLOCKED** | Requires secure authentic private trigger graph |
| A6 | Measure cost-floor lookup overhead | **BLOCKED** | Direct timeout context verified, per-operation latency not isolated |
| A7 | Measure locks, WAL, I/O and concurrency | **BLOCKED** | Authentic private clone required |
| A8 | Establish complete causal model | **ACTIVE** | Interrupt location proven, cumulative latency attribution unresolved |

### Pillar B — Production-equivalent QA

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| B1 | Inspect existing private PG17 environment | **ACTIVE** | GitHub CI ephemeral PG17 verified; private Codespace environment not accessed |
| B2 | Confirm authorized private schema export route | **BLOCKED** | No authenticated private DB export connection available |
| B3 | Obtain private SQL safely | **BLOCKED** | Do not reveal private function bodies or credentials |
| B4 | Restore actual nested private trigger definitions | **BLOCKED** | No secure schema archive |
| B5 | Reproduce roles, grants, RLS and extensions | **BLOCKED** | Public synthetic role test passes; full Supabase equivalence unproven |
| B6 | Compare production and clone structural fingerprints | **BLOCKED** | Production baseline available; no authentic clone |
| B7 | Create representative synthetic data distributions | **ACTIVE** | 495k synthetic outcome rows exist; distribution parity unproven |
| B8 | Certify clone equivalence | **BLOCKED** | Transitive triggers, extensions, owner roles, runtime GUCs missing |

### Pillar C — Performance optimization

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| C1 | Benchmark existing query indexes | **ACTIVE** | Isolated percentile-only baseline, not full transaction |
| C2 | Benchmark proposed targeted payoff index | **ACTIVE** | Isolated percentile-only comparison; index not on production |
| C3 | Compare S3 and non-S3 workloads | **ACTIVE** | Read-only production correlations, isolated authentic comparison outstanding |
| C4 | Validate exact percentile results | **ACTIVE** | Synthetic comparison only; scientific parity pending |
| C5 | Compare alternate query plans | **ACTIVE** | Read-only production EXPLAIN and QA candidate plans |
| C6 | Benchmark concurrent/heavy workloads | **BLOCKED** | Production-equivalent private database required |
| C7 | Record full-transaction p50/p95/p99 | **BLOCKED** | Authentic triggers + realistic concurrency required |
| C8 | Select and accept lowest-risk optimization | **BLOCKED** | No authentic full-request benchmark yet |

### Pillar D — Atomic persistence

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| D1 | Audit existing atomic RPC | **ACTIVE** | Candidate reviewed; comprehensive private schema/permissions audit outstanding |
| D2 | Validate all core families in one transaction | **PASS** | Synthetic PG17 verified; no production equivalence implied |
| D3 | Verify 30-symbol source-aware publication | **PASS** | Isolated 30-symbol fixture passed |
| D4 | Verify 50-symbol complete publication | **PASS** | Isolated 50-symbol fixture passed |
| D5 | Verify 61-symbol complete publication | **PASS** | Isolated 61-symbol fixture passed |
| D6 | Validate exact identity and cardinalities | **PASS** | Source-aware 30 symbols, 28 signals, 28 features, 29 readiness |
| D7 | Verify rollback including nested effects | **PASS** | Real PG-enforced SQLSTATE 57014 (200ms) + synthetic trigger effects |
| D8 | Validate exact persisted receipt | **PASS** | Isolated receipt, rollback and idempotent replay assertions |

### Pillar E — Retry and recovery

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| E1 | Reproduce PostgreSQL timeout cancellation | **PASS** | Real PostgreSQL statement_timeout in ephemeral PG17, run 42480712005 |
| E2 | Reproduce HTTP and network failures | **ACTIVE** | Mock HTTP errors covered, live transport loss not reproduced |
| E3 | Inject response-lost acknowledgement | **ACTIVE** | Separate-session simulated committed-but-lost-receipt test committed at `cabba405b71f98fb1a97934e2fe0de8f56e7ac2e`; exact-head CI pending. Real transport loss not yet tested. |
| E4 | Test exact repeated submission | **PASS** | Isolated 61-symbol idempotent replay with no new effects |
| E5 | Reject conflicting duplicate evidence | **PASS** | Existing synthetic content mismatch negative tests |
| E6 | Test simultaneous writer requests | **NOT STARTED** | Controlled isolated concurrency only |
| E7 | Verify complete downstream side effects | **BLOCKED** | Authentic trigger clone not yet available |
| E8 | Verify fail-closed monitoring/reconciliation | **ACTIVE** | Read-only Integrity Watch running; full contract acceptance pending |

### Pillar F — Legacy source custody

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| F1 | Inventory known canonical producers | **ACTIVE** | Render/GitHub/UNKNOWN found; exhaustive inventory pending |
| F2 | Fingerprint source-specific revisions | **ACTIVE** | Distinct Python clients, payload identity, origin metadata |
| F3 | Inspect read-only request metadata | **PASS** | 08 Nov 10:16 legacy source metadata confirmed |
| F4 | Trace approved source workflows | **NOT STARTED** | Do not infer host from network ISP |
| F5 | Identify older-format writer host | **BLOCKED** | Host unknown; privileged telemetry lacks host identity |
| F6 | Review privileged credential custody | **BLOCKED** | Secure authorized custodian validation required |
| F7 | Test authenticated source-contract enforcement | **NOT STARTED** | Do not trust self-reported payload-only source |
| F8 | Verify obsolete publishers fail closed | **BLOCKED** | No production change authorized |

### Pillar G — Scientific and security integrity

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| G1 | Verify frozen methodology unchanged | **ACTIVE** | Draft unmerged; comparative scientific parity pending |
| G2 | Verify strategy observation lineage | **BLOCKED** | Requires authentic downstream trigger reproduction |
| G3 | Verify shadow quotes and decision freezes | **BLOCKED** | Requires authentic downstream trigger reproduction |
| G4 | Validate payoff scientific equivalence | **BLOCKED** | Requires full private function source and representative workload |
| G5 | Verify paper lifecycle reconciliation | **BLOCKED** | Synthetic core tests cannot certify entire downstream chain |
| G6 | Verify unchanged disabled live authority | **ACTIVE** | No permission changes performed; full independent release audit pending |
| G7 | Verify RPC security/invoker and RLS | **ACTIVE** | Synthetic service_role tests PASS; actual Supabase roles unresolved |
| G8 | Prepare exact SHA technical review packet | **ACTIVE** | PR #445 evidence and QA logs recorded; final commit not frozen |

### Pillar H — Release and operations

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| H1 | Freeze tested release-candidate SHA | **NOT STARTED** | Engineering work and authentic acceptance outstanding |
| H2 | Complete release/rollback procedures | **NOT STARTED** | No production change authorized |
| H3 | Obtain independent DBA signoff | **BLOCKED** | Authentic clone + qualified reviewer required |
| H4 | Obtain security/custody independent signoffs | **BLOCKED** | Qualified reviewer/custodian required |
| H5 | Obtain all signoffs and owner authorization | **BLOCKED** | No approvals granted |
| H6 | Run controlled production deployment | **BLOCKED** | PRODUCTION NO-GO |
| H7 | Verify ten complete scans plus 24h observation | **BLOCKED** | Requires authorized controlled release |
| H8 | Close P0 on completed production acceptance | **BLOCKED** | Incident ongoing |

## Next authorized engineering action

**B2 → B3 (secure authentic private schema access)** is the critical dependency. With current permissions, pursue a safe authorized read-only export into the existing *private* PostgreSQL 17 environment; if impossible, make progress on **E3 lost-ACK** and **E6 concurrent writer** isolated tests on draft PR #445. Test real DB transaction semantics without implying private schema equivalence. Re-verify all GitHub CI at the exact changed code commit, then update this ledger and [roadmap #387](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/387).

**No production SQL/migration, no merge, no deployment, no scanner changes, no real orders, no spending and no self-issued independent approvals.**
