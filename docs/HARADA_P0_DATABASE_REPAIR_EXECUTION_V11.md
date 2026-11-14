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

**PASS 15 · ACTIVE 21 · BLOCKED 26 · NOT STARTED 2 · TOTAL 64.** Counts reflect evidence and known dependencies, not a percentage of production readiness.

## Verified recent execution

- **2026-11-08 Harada B2–B6 (safe tooling PASS, authentic export still BLOCKED):** Rechecked production read-only: 128 Alpha Hunter tables, 3012 columns, 360 indexes, 131 triggers; four stage2 structural fingerprints unchanged. New [120-function metadata-only custody inventory](../ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql) measured **110 `private` functions (65 SECURITY DEFINER), 10 `public.alpha_hunter_%` functions (5 SECURITY DEFINER)**, with body/owner/ACL/runtime config composite digests; zero application triggers on `private` schema tables. Prepared Codespace-only [offline archive TOC audit](../ops/local/inspect_private_pg_archive_topology_v01.sh), [offline clone fingerprint check](../ops/local/verify_restored_private_pg17_fingerprints_v01.sh) and strengthened credential-handling [export script](../ops/local/export_private_pg_schema.sh); GitHub Actions [#42490760120](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42490760120) **PASS** verifies shell syntax and refusal in GitHub Actions. **No schema archive exported, no private Codespace session opened, no restored trigger graph or authentic performance benchmark executed.** [Exact blocker and operator hand-off](P0_PRIVATE_CLONE_ACCESS_GATE_20261108.md). **NO-GO.**

- **2026-11-08 Harada D / C1–C2 — four-way architecture/index benchmark COMPLETE in synthetic QA only:** [PG17 workflow #42488585902](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42488585902) **SUCCESS** at exact tested SHA `0780a5416d5f4c835010656ef55d07409df3bdd1`. 240 measurements (20 trials × 30/50/61 symbols × four configurations) with 505,569 synthetic historical outcomes and seven simulated nested side-effect branches. At 61 symbols, p95 SQL ms **sequential/current 2075, sequential/candidate 534, atomic/current 2077, atomic/candidate 673**; no sampled synthetic SQL statement exceeded 12 seconds. Real separate sequential commits proved a deliberately injected 57014 symbol-stage failure left **one parent, zero children**, while earlier atomic timeout regression confirms isolated rollback. Correctness checks passed for 120 paired synthetic percentile identities and downstream counts. [Inspect limitations/measurements](P0_ATOMIC_SEQUENTIAL_INDEX_2X2_20261108.md). No authentic private function graph, production roles/extension parity, true request latency or release certification. Existing active/blocked statuses unchanged because synthetic-only PASS does not close production-equivalent gates.

- **2026-11-08 A2/B7/C2/C6/C7 (new evidence; authentic clone still BLOCKED):** [PostgreSQL17 CI #42485377827](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42485377827) **SUCCESS**, exact measured code SHA `0d671b63915f9e5252472c5d5a2f84a9c7e8802c`. Added 505,569-row outcome-scale *synthetic* full-atomic-RPC workload with 7 nested sink tables (including episode/24h queue, payoff and calibrated-order branches). 20 independent runs each at 30/50/61 symbols, current-style versus candidate index, plus six concurrent candidate 61-symbol runs. Combined synthetic p95 **baseline 619/1003/1244 ms vs candidate 202/303/365 ms**, respectively; 61-symbol concurrent candidate p95 **582 ms** (n=6). Synthetic percentile parity and core/downstream mock cardinalities PASS. **Do not represent these as actual private production trigger measurements or certified production p99.** [Detailed evidence](P0_TRIGGER_GRAPH_LATENCY_EVIDENCE_20261108.md). Live production at 13:35 UTC still had stale Render 49/0 parents from 13:04 and 13:22. Atomic RPC and proposed index still absent in production. Secure private schema export/restoration not performed; prepared zero-write Codespace preflight cannot be run here without Codespace access.

- **2026-11-08 E2 (ACTIVE, contract tests PASS):** [PostgreSQL 17 + Python workflow #42483250686](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42483250686) **SUCCESS** at exact tested SHA `3741f9082385b6064edd6dbd0ac448de5a7cb16c`. **41 Python tests passed**, including four new transport-contract checks: simulated lost ConnectionError and Timeout after emulated committed RPC, exact unchanged retry payload/run_id, and fail-closed exhausted retries without sequential REST fallback. Server-side actual PostgreSQL E3/E6/57014 CI reran successfully. Mock transport tests do not prove a real network partition. Production read-only at 13:06 UTC showed historical 11:03, 11:22, 11:42, 12:04 stale parent-only failures; 12:42 complete (48/48); fresh 13:04 parent 49/0 was **UNDER 3-minute grace and PUBLISHING/UNVERIFIED**, not yet a confirmed stale failure. No production repair deployed.

- **2026-11-08 E6 (PASS, isolated scope):** [GitHub Actions PostgreSQL 17 run #42483028557](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42483028557) **SUCCESS**, exact tested commit `0586de9adf2e3301bab88d54196ff5e771dc15f7`. Two simultaneous PostgreSQL clients submitted an identical 61-symbol RPC and waited on a real advisory lock; both returned matching receipts with exactly 306 simulated trigger effects. A separately raced conflicting parent waited on the lock then received the required content mismatch, without overwriting committed evidence. Confirmed job logs; synthetic triggers are not production private triggers.

- **2026-11-08 E3 (PASS, isolated scope):** [Workflow #42481912510](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42481912510) completed SUCCESS on commit `cabba405b71f98fb1a97934e2fe0de8f56e7ac2e`: a real first PostgreSQL RPC committed while the test client discarded its response; independent second DB session replayed the same 61-symbol identity without further synthetic trigger effects. This simulates a lost ACK, **not** a real socket partition.


- **2026-11-08:** PostgreSQL 17 GitHub Actions [run #42480712005](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42480712005) **SUCCESS**, tested exact commit `1c9c0e7bd6e955ae2a2f9357255a3edc2c89b4fb`. A real PostgreSQL statement timeout (200ms) interrupted a nested 61-symbol synthetic trigger after an intentional 600ms delay. All five core table families and synthetic trigger side effects rolled back; retry committed once, duplicate replay zero new effects. This is a genuine PostgreSQL timeout, **not** a production-equivalent 12s latency benchmark.
- **2026-11-08:** Supabase read-only showed Render parent-only failures at 11:03 (43/0), 11:22 (45/0), 11:42 (43/0), 12:04 (46/0), and complete 12:22 scan (48/48). No production repair was performed.
- **Earlier:** 25 production PostgreSQL timeouts sampled; 21 in payoff-geometry call stack, 20 interrupted within percentile SQL; complete nested time attribution not yet measured.
- **Clone blocker:** secure production schema export not available to existing private Codespace; known private function bodies and credentials must not enter public GitHub. No paid Supabase branch provisioned.

**2026-11-10 E2 — ACTIVE, CI PENDING:** Added a real loopback TCP regression for lost first acknowledgement followed by HTTP 200 with truncated JSON, requiring exact byte-identical retry and fail-closed handling without sequential REST fallback. Engineering SHA `3949990692fee2c8ab0b160e7b54960e97dad7b2`. Workflow runs not returned at initial inspection; do not mark PASS until actual CI logs are verified. This is transport-only, not real PostgreSQL commit-once or production-equivalent network proof. B2/B3 remain BLOCKED; production NO-GO.\n\n**2026-11-11 05:49 UTC — E2 ACTIVE, new CI pending:** At repair SHA `164d9e9b3dc95d9f8e5513ef3e2649169101bae6`, added an isolated HTTP/PG17 negative regression: conflicting `run_id` must return HTTP 400 before database RPC and must not increase the accepted request ledger. Prior combined E3/E6 synthetic integration PASS remains evidenced by [workflow #42955425461](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42955425461) at SHA `d028841df6a15e48265a7a61440f99385e1188b8`; **new negative case not yet CI-verified**, no new PASS claim. B2/B3 BLOCKED; production NO-GO.\n\n**2026-11-11 09:48 UTC — E2 synthetic HTTP/PG17 regression CI VERIFIED:** The previously unverified push-triggered [isolated PostgreSQL workflow #63](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42968361759) completed **SUCCESS** on code SHA `164d9e9b3dc95d9f8e5513ef3e2649169101bae6` (ledger-only later SHA `9ebf4dfb39094c7fa76acbe1acd95134e2cd95a6`). Retrieved full 71,274-character job log, all 24 steps SUCCESS, including E3/E6 two-client HTTP lost-ACK, conflicting-run-identity negative case, 61-symbol 57014 rollback, concurrent RPC serialization, simulated role/RLS checks, 505,569-row synthetic benchmark and 2×2 comparison. **E2 test subcase PASS in synthetic scope; E2 remains ACTIVE for authentic private-trigger/network and full production acceptance.** B2/B3 remain BLOCKED; production NO-GO. No release, main, scanner, database, trading or schedule changes.

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
| B1 | Inspect existing private PG17 environment | **ACTIVE** | Codespace readiness and archive-topology scripts prepared, CI safety-guard PASS; cannot inspect live Codespace filesystem with connected GitHub tools. |
| B2 | Confirm authorized private schema export route | **BLOCKED** | Supabase-connected SQL has metadata access only, no portable logical pg_dump transfer; GitHub connector lacks Codespace shell. Hidden-input guarded local export route exists. |
| B3 | Obtain private SQL safely | **BLOCKED** | Private schema archive NOT obtained; no authorized DB-password entry in Codespace. Never upload SQL or credentials to public GitHub. |
| B4 | Restore actual nested private trigger definitions | **BLOCKED** | No secure schema archive |
| B5 | Reproduce roles, grants, RLS and extensions | **BLOCKED** | Public synthetic role test passes; full Supabase equivalence unproven |
| B6 | Compare production and clone structural fingerprints | **BLOCKED** | 128-table digests and new 120-function custody fingerprints measured read-only; private clone verifier prepared but NOT executed/compared. |
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
| E2 | Reproduce HTTP and network failures | **ACTIVE** | 14 Nov 05:47 UTC: added six non-retryable HTTP rejection fail-closed mock cases (400/401/403/404/409/422) at SHA `e506f1e9d1c6c8b7b4035b45a79bd348b32e4324`; CI pending, no PASS claim.  10 Nov loopback lost-ACK then invalid 200 receipt (wrong run/count/commit flag), 3 parameterized cases at `ee956b3ca00891ef285f617185feed404fe54665`, CI PENDING; server commit simulated, fail-closed assertion;  Four new Python mock tests cover connection loss and timeout retry and exhaustion; 41 Python tests PASS in run #42483250686. Real HTTP/network partition not injected. Added 12 mock HTTP 408/429/500/502/503/504 retry/terminal-failure cases in `tests/test_atomic_core_scan_transport_retry_v01.py` at `01b56b7b69b97cdd253a474e6767e05c8f6db1c9`; GitHub Actions CI/log verification PENDING, so E2 remains ACTIVE.; 09 Nov actual loopback socket-close regression at `0dbf917b1aa4dac0f47c064ce4222500e350f6cd` (first connection dropped before HTTP status; byte-identical replay), **CI PENDING**, server receipt simulated; E2 remains ACTIVE. |
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
| F4 | Trace approved source workflows | **ACTIVE** | Read-only inspection confirms approved GitHub hourly workflow pins `main`, declares `GITHUB_REALTIME_HOURLY`, retains read-only repository permission, paper-only guards and explicit scan-failure propagation. Isolated static regression `tests/test_p0_approved_source_workflow_contract_v01.py` added at `2d5500f4f81b06e1c07aeab95ee0f5f6eb680b77`, CI wiring at `1bb95f4c9cf5bb8d81d62a7c44134e66bbd92f30`; CI VERIFIED at tested ledger SHA `90f1baeac915d00bdb89593b646fef8724b2c02e`: [full suite #42588489478](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42588489478) 1359 passed + 6 subtests; [PostgreSQL contract #42588489430](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42588489430) 31 passed, 0 failed; complete job logs inspected 09 Nov. Additional F4 regression at `2228a0feb342ad923661e19909527d5836f07659` binds the `continue-on-error` declaration to `live_scan` and the `always()`/`exit 1` failure guard to its named step; CI pending at time of commit (no PR-triggered runs returned yet). F4 remains ACTIVE because static workflow regression does not prove publisher custody. This does not identify external legacy publisher or authenticate any source claim. |
| F5 | Identify older-format writer host | **BLOCKED** | Host unknown; privileged telemetry lacks host identity |
| F6 | Review privileged credential custody | **BLOCKED** | Secure authorized custodian validation required |
| F7 | Test authenticated source-contract enforcement | **ACTIVE** | Isolated forged modern source claim regression added at `bc6fac570de78a62f88a7fa4402d1c6be80b98db`; requires `SOURCE_CLAIM_PRESENT_NOT_AUTHENTICATED` despite matching five-family counts. Earlier forged-source CI verified at `f6b05f9717a2f069e3f7ef1ea2aae7bd10d7fd67` (PostgreSQL contract run #42563938326). Added distinct partial-readiness fail-closed regression (2 declared symbols, 1 readiness) at `2a3e7bb4ecb0bcd336da0b1190e9c6b39d60a5e8`; new CI and complete logs PENDING verification. No authenticated identity or enforcement achieved. |
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

**B2 → B3 (secure authentic private schema access)** remains the critical blocker. Codespace-only guarded export, offline archive inspection and offline fingerprint verification are now prepared and safety-linted. An authorized owner/custodian must access the **existing private Codespace** and supply valid DB authentication in its hidden terminal; the connected tools cannot enter that private shell or transfer `pg_dump`. No password reset, paid branch, alternate credential or production change permitted. After that, match all structural/120 function/8 extension digests before adapting realistic 2×2 benchmarking to the actual private functions. See [private clone access gate](P0_PRIVATE_CLONE_ACCESS_GATE_20261108.md). Do not imply production-equivalent acceptance. Re-verify all GitHub CI at the exact changed code commit, then update this ledger and [roadmap #387](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/387).

**No production SQL/migration, no merge, no deployment, no scanner changes, no real orders, no spending and no self-issued independent approvals.**


### 2026-11-10 — E3/E6 concurrent transport lost-ACK QA (ACTIVE, CI pending)
- Commit `4ecbb86a7e040ed3376d693aa34fbec98f7f0a5e` adds a real loopback HTTP regression with two independent concurrent clients publishing the same deterministic run ID. The synthetic server loses the first response and emulates a single commit under a lock; the test asserts identical wire payloads, same receipts, and no legacy endpoint fallback.
- This is **transport-only synthetic commit emulation**, not authentic PostgreSQL concurrency, trigger execution, network-partition proof, or a release gate. Existing isolated PostgreSQL E3/E6 PASS evidence remains separately scoped; broader E2 remains ACTIVE. CI run was not yet returned for the new commit when recorded; **no new PASS claimed**.
- B2/B3 remain BLOCKED; PR #445 must remain DRAFT/UNMERGED; PRODUCTION NO-GO.

### 2026-11-10 — E2 HTTP success-without-receipt QA (ACTIVE; CI unverified)
- Isolated test commit `1c9b44d6649e0ee00722ab071c2d6676e12d46da` adds five synthetic transport cases: HTTP 200 empty, malformed JSON, JSON null, JSON list, and HTTP 204 empty. Each must fail closed without fallback to per-table writes. This tests only the receipt validation path, not PostgreSQL or real network faults.
- At initial check GitHub returned **zero PR-triggered CI runs** for the new SHA; do not claim PASS until actual workflow logs are inspected. E2 remains ACTIVE. B2/B3 remain BLOCKED. PR #445 DRAFT/UNMERGED; production NO-GO.


### 2026-11-12 18:48 UTC — E6 Stage 9 preflight regression CI verification
- Exact engineering SHA `d236ebe5285f913c0fb06566e5c9ffd9c5dc2df7` (two additional isolated fail-closed tests: incorrect disposable database identity and missing pg_cron extension). **E6 preflight regression subcases PASS in isolated scope only**; authentic private concurrency remains **ACTIVE**.
- All seven commit-associated PR workflows completed SUCCESS: `43272233140`, `43272232951`, `43272233245`, `43272232955`, `43272232936`, `43272233161`, `43272233136`. Full job logs inspected for all seven successful jobs. Full suite https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/43272232951: **1441 passed, 101 subtests passed**. Optional live-render-smoke job SKIPPED (not production evidence). Node.js 20 action deprecation warnings nonblocking.
- B2/B3 **BLOCKED** (no authorised private production trigger clone), production-equivalent C7 **BLOCKED**, private Codespaces container exit 255 unresolved. No private benchmark, production-equivalent certification, release signoffs, merge or deployment. Next: authorised private Codespaces read-only exit-255 diagnosis and guarded Stage 9 rerun; otherwise independent E3/E6 isolated QA. PR #445 stays DRAFT/UNMERGED; production NO-GO, £0, paper-only.

### 2026-11-13 — E6 Stage 9 distinct-table callback coverage (ACTIVE, CI PENDING)
- Isolated source SHA `386db61884f87f4551072c1831d1d577419619c9` changes Stage 9 private callback preflight from total trigger count to `count(DISTINCT c.relname)`, requiring enabled SECURITY DEFINER private callbacks across all five core evidence tables rather than accepting five callbacks concentrated on fewer tables. Negative offline regression SHA `4e31497ec8d0ce46dbb06246408d6bec0d4733ef` requires the distinct-table SQL guard and fails closed when only four tables are covered. Both commits are on existing draft PR #445; no private SQL or production access.
- Exact test-head PR workflow lookup returned zero runs at first check. **E6 additional preflight case ACTIVE / CI PENDING, NOT PASS.** Next run: fetch exact-SHA CI, inspect full logs, remediate any failures; then private Codespaces exit-255 diagnosis. B2/B3 BLOCKED; authentic E6 and C7 still outstanding. Production NO-GO.

### 2026-11-13 — E6 positive Stage 9 clone-preflight control (ACTIVE; CI PENDING)
- Isolated test commit `c08f4cd24dc55ecf460d7846d1013c553e804a98` adds a positive control to `tests/test_p0_stage9_race_classification_v01.py`: complete disposable identity, pg_cron presence, no cron jobs, distinct five-table private callback coverage and zero prior run rows must permit the guarded preflight. Complements prior negative fail-closed cases; no private SQL or production access.
- Immediate exact-commit PR workflow lookup returned **zero runs**; no CI PASS claimed. **E6 remains ACTIVE** for this new test and authentic private concurrency, despite earlier isolated E6 cases passing. B2/B3 BLOCKED; C7 BLOCKED. Next: retrieve exact-head CI and full logs; remediate if failing. PR #445 DRAFT/UNMERGED; production NO-GO.
