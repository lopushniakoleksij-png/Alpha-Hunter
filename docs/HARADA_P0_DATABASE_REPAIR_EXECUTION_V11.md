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

**PASS 15 · ACTIVE 19 · BLOCKED 26 · NOT STARTED 4 · TOTAL 64.** Counts reflect evidence and known dependencies, not a percentage of production readiness.

## Verified recent execution

- **2026-11-08 Harada D / C1–C2 — four-way architecture/index benchmark COMPLETE in synthetic QA only:** [PG17 workflow #42488585902](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42488585902) **SUCCESS** at exact tested SHA `0780a5416d5f4c835010656ef55d07409df3bdd1`. 240 measurements (20 trials × 30/50/61 symbols × four configurations) with 505,569 synthetic historical outcomes and seven simulated nested side-effect branches. At 61 symbols, p95 SQL ms **sequential/current 2075, sequential/candidate 534, atomic/current 2077, atomic/candidate 673**; no sampled synthetic SQL statement exceeded 12 seconds. Real separate sequential commits proved a deliberately injected 57014 symbol-stage failure left **one parent, zero children**, while earlier atomic timeout regression confirms isolated rollback. Correctness checks passed for 120 paired synthetic percentile identities and downstream counts. [Inspect limitations/measurements](P0_ATOMIC_SEQUENTIAL_INDEX_2X2_20261108.md). No authentic private function graph, production roles/extension parity, true request latency or release certification. Existing active/blocked statuses unchanged because synthetic-only PASS does not close production-equivalent gates.

- **2026-11-08 A2/B7/C2/C6/C7 (new evidence; authentic clone still BLOCKED):** [PostgreSQL17 CI #42485377827](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42485377827) **SUCCESS**, exact measured code SHA `0d671b63915f9e5252472c5d5a2f84a9c7e8802c`. Added 505,569-row outcome-scale *synthetic* full-atomic-RPC workload with 7 nested sink tables (including episode/24h queue, payoff and calibrated-order branches). 20 independent runs each at 30/50/61 symbols, current-style versus candidate index, plus six concurrent candidate 61-symbol runs. Combined synthetic p95 **baseline 619/1003/1244 ms vs candidate 202/303/365 ms**, respectively; 61-symbol concurrent candidate p95 **582 ms** (n=6). Synthetic percentile parity and core/downstream mock cardinalities PASS. **Do not represent these as actual private production trigger measurements or certified production p99.** [Detailed evidence](P0_TRIGGER_GRAPH_LATENCY_EVIDENCE_20261108.md). Live production at 13:35 UTC still had stale Render 49/0 parents from 13:04 and 13:22. Atomic RPC and proposed index still absent in production. Secure private schema export/restoration not performed; prepared zero-write Codespace preflight cannot be run here without Codespace access.

- **2026-11-08 E2 (ACTIVE, contract tests PASS):** [PostgreSQL 17 + Python workflow #42483250686](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42483250686) **SUCCESS** at exact tested SHA `3741f9082385b6064edd6dbd0ac448de5a7cb16c`. **41 Python tests passed**, including four new transport-contract checks: simulated lost ConnectionError and Timeout after emulated committed RPC, exact unchanged retry payload/run_id, and fail-closed exhausted retries without sequential REST fallback. Server-side actual PostgreSQL E3/E6/57014 CI reran successfully. Mock transport tests do not prove a real network partition. Production read-only at 13:06 UTC showed historical 11:03, 11:22, 11:42, 12:04 stale parent-only failures; 12:42 complete (48/48); fresh 13:04 parent 49/0 was **UNDER 3-minute grace and PUBLISHING/UNVERIFIED**, not yet a confirmed stale failure. No production repair deployed.

- **2026-11-08 E6 (PASS, isolated scope):** [GitHub Actions PostgreSQL 17 run #42483028557](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42483028557) **SUCCESS**, exact tested commit `0586de9adf2e3301bab88d54196ff5e771dc15f7`. Two simultaneous PostgreSQL clients submitted an identical 61-symbol RPC and waited on a real advisory lock; both returned matching receipts with exactly 306 simulated trigger effects. A separately raced conflicting parent waited on the lock then received the required content mismatch, without overwriting committed evidence. Confirmed job logs; synthetic triggers are not production private triggers.

- **2026-11-08 E3 (PASS, isolated scope):** [Workflow #42481912510](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42481912510) completed SUCCESS on commit `cabba405b71f98fb1a97934e2fe0de8f56e7ac2e`: a real first PostgreSQL RPC committed while the test client discarded its response; independent second DB session replayed the same 61-symbol identity without further synthetic trigger effects. This simulates a lost ACK, **not** a real socket partition.


- **2026-11-08:** PostgreSQL 17 GitHub Actions [run #42480712005](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42480712005) **SUCCESS**, tested exact commit `1c9c0e7bd6e955ae2a2f9357255a3edc2c89b4fb`. A real PostgreSQL statement timeout (200ms) interrupted a nested 61-symbol synthetic trigger after an intentional 600ms delay. All five core table families and synthetic trigger side effects rolled back; retry committed once, duplicate replay zero new effects. This is a genuine PostgreSQL timeout, **not** a production-equivalent 12s latency benchmark.
- **2026-11-08:** Supabase read-only showed Render parent-only failures at 11:03 (43/0), 11:22 (45/0), 11:42 (43/0), 12:04 (46/0), and complete 12:22 scan (48/48). No production repair was performed.
- **Earlier:** 25 production PostgreSQL timeouts sampled; 21 in payoff-geometry call stack, 20 interrupted within percentile SQL; complete nested time attribution not yet measured.
- **Clone blocker:** secure production schema export not available to existing private Codespace; known private function bodies and credentials must not enter public GitHub. No paid Supabase branch provisioned.

## 64-action board

### Pillar A — Root cause and latency

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| A1 | Reconfirm production timeout evidence | **PASS** | 08 Nov structured PostgreSQL logs: 25 57014; 21 payoff path |
| A2 | Inventory full transitive trigger graph | **ACTIVE** | Live metadata-only graph confirmed strategy-episode/24h-queue, shadow/freeze, payoff and calibrated-order branches; private bodies, dynamic dependencies and clone parity unresolved. |
| A3 | Confirm schema/function/index/grant fingerprints | **PASS** | Four structural digests matched 07 Nov baseline (08 Nov check) |
| A4 | Reproduce historical percentile workloads | **ACTIVE** | 495k-row isolated synthetic percentile query benchmark; authentic workload outstanding |
| A5 | Isolate and time nested operations | **BLOCKED** | Requires secure authentic private trigger graph |
| A6 | Measure cost-floor lookup overhead | **BLOCKED** | Direct timeout context verified, per-operation latency not isolated |
| A7 | Measure locks, WAL, I/O and concurrency | **BLOCKED** | Authentic private clone required |
| A8 | Establish complete causal model | **ACTIVE** | Interrupt location proven, cumulative latency attribution unresolved |

### Pillar B — Production-equivalent QA

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| B1 | Inspect existing private PG17 environment | **ACTIVE** | Ephemeral CI PG17 validated; safe Codespace readiness script created but cannot run against inaccessible private Codespace terminal. |
| B2 | Confirm authorized private schema export route | **BLOCKED** | No authenticated private DB export connection available |
| B3 | Obtain private SQL safely | **BLOCKED** | Do not reveal private function bodies or credentials |
| B4 | Restore actual nested private trigger definitions | **BLOCKED** | No secure schema archive |
| B5 | Reproduce roles, grants, RLS and extensions | **BLOCKED** | Public synthetic role test passes; full Supabase equivalence unproven |
| B6 | Compare production and clone structural fingerprints | **BLOCKED** | Production baseline available; no authentic clone |
| B7 | Create representative synthetic data distributions | **ACTIVE** | New 505,569-row synthetic outcome-scale and seven-sink trigger analogue benchmark PASS; production data shape/distribution/conditional side effects remain unverified. |
| B8 | Certify clone equivalence | **BLOCKED** | Transitive triggers, extensions, owner roles, runtime GUCs missing |

### Pillar C — Performance optimization

| ID | Required action | Status | Current evidence / dependency |
|---|---|---|---|
| C1 | Benchmark existing query indexes | **ACTIVE** | 2x2 505,569-row synthetic full-SQL comparison verified at 30/50/61, 20 trials/config; authentic production triggers still missing. |
| C2 | Benchmark proposed targeted payoff index | **ACTIVE** | Four-way matrix verified in synthetic PG17: 61-symbol p95 sequential 2075→534 ms and atomic 2077→673 ms; authentic private workload still blocked. |
| C3 | Compare S3 and non-S3 workloads | **ACTIVE** | Read-only production correlations, isolated authentic comparison outstanding |
| C4 | Validate exact percentile results | **ACTIVE** | Synthetic comparison only; scientific parity pending |
| C5 | Compare alternate query plans | **ACTIVE** | Read-only production EXPLAIN and QA candidate plans |
| C6 | Benchmark concurrent/heavy workloads | **BLOCKED** | Six concurrent 61-symbol synthetic chain calls PASS, but authentic transitive private triggers/concurrency not benchmarked. |
| C7 | Record full-transaction p50/p95/p99 | **BLOCKED** | Isolated 20-run 30/50/61 full synthetic atomic RPC p50/p95/p99 measured in run #42485377827; production-equivalent measurement still blocked. |
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
| E2 | Reproduce HTTP and network failures | **ACTIVE** | Four new Python mock tests cover connection loss and timeout retry and exhaustion; 41 Python tests PASS in run #42483250686. Real HTTP/network partition not injected. |
| E3 | Inject response-lost acknowledgement | **PASS** | Isolated PostgreSQL 17 lost-ACK simulation via separate sessions; run #42481912510 PASS. No real network fault injected. |
| E4 | Test exact repeated submission | **PASS** | Isolated 61-symbol idempotent replay with no new effects |
| E5 | Reject conflicting duplicate evidence | **PASS** | Existing synthetic content mismatch negative tests |
| E6 | Test simultaneous writer requests | **PASS** | Two overlapping 61-symbol RPC clients (identical and conflicting), verified actual advisory-lock wait, exact side effects and no overwrite; run #42483028557 PASS. Synthetic trigger graph only. |
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

**B2 → B3 (secure authentic private schema access)** remains the critical dependency. E3 lost-ACK and E6 concurrency have now passed in isolated PostgreSQL. Next independent safe work: extend Python HTTP-loss retry contract tests and inspect source-custody enforcement, then secure the private trigger clone without exposing functions/credentials. Do not imply production-equivalent acceptance. Re-verify all GitHub CI at the exact changed code commit, then update this ledger and [roadmap #387](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/387).

**No production SQL/migration, no merge, no deployment, no scanner changes, no real orders, no spending and no self-issued independent approvals.**
