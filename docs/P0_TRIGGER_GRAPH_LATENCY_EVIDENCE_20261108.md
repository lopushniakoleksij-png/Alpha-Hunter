# Alpha Hunter P0 — Trigger Graph and Atomic RPC Latency Evidence

**Date:** 8 November 2026 (UTC)  
**Release:** PRODUCTION NO-GO  
**Branch:** `fix/supabase-write-timeout-qa` · draft/unmerged PR #445  
**Budget:** £0 · no production SQL mutations, deploys, trading changes or secret exports.

## 1. Verified authentic production *metadata*, NOT a restored private clone

- Supabase inspected read-only at **2026-11-08 13:20–13:35 UTC**.
- Historical outcomes row count was **505,569** at 13:20, rising to **505,605** by 13:35; relation + indexes approx **237 MB** at 13:20.
- `service_role` is configured with `statement_timeout=12s`. Production atomic RPC and proposed payoff partial index were **both absent** at 13:35.
- Read-only metadata inventory [`readonly_p0_synchronous_trigger_write_graph_v01.sql`](../ops/sql/readonly_p0_synchronous_trigger_write_graph_v01.sql) **executed against live PostgreSQL** and confirmed static branch topology:
  1. `alpha_hunter_symbol_snapshots` → private strategy-capture trigger → `alpha_hunter_strategy_episodes_v01` and `alpha_hunter_strategy_observations_v01`.
  2. Episode INSERT → private outcome-queue trigger → `private.alpha_hunter_strategy_24h_outcome_queue_v01`.
  3. Observation INSERT → private shadow-quote trigger → `alpha_hunter_shadow_decision_quotes_v01`.
  4. Quote INSERT → private freeze trigger → `alpha_hunter_execution_decision_freezes_v01`.
  5. Freeze INSERT → **separate active triggers**: private payoff-geometry health → `private.alpha_hunter_payoff_geometry_health_observations_v01`; and calibrated paper-order creation → `private.alpha_hunter_calibrated_paper_orders_v01`.
- The three private destination tables were checked and have **zero further direct application triggers**.
- This is a **static write-reference graph**, not a full assessment of dynamic SQL, function-internal calls, conditions, runtime cost or side-effect equivalence. All private definitions and production credentials remain outside Git.

## 2. Isolated benchmark — independently measured, synthetic only

**Exact code SHA tested:** `0d671b63915f9e5252472c5d5a2f84a9c7e8802c`  
**Passing GitHub Actions:** [PostgreSQL 17 job #42485377827](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42485377827) — **SUCCESS**.

- Fresh isolated PostgreSQL 17 database in disposable GitHub Actions, NO connection to production.
- Synthetic historical outcomes expanded to **505,569 records**.
- The **actual candidate five-family atomic RPC** executed in distinct client requests; a synthetic seven-table nested trigger analogue recreated the *topology*, including strategy-episode queue and both payoff/calibrated-order branches.
- Two index configurations: representative pre-existing synthetic indexes vs the proposed targeted partial index. No production index installed.
- **20 independent full-RPC calls per scan size per index configuration** (30/50/61 symbols); six additional concurrent 61-symbol candidate calls.
- Receipt and synthetic downstream side-effect cardinalities verified; all compared synthetic payoff percentile results remained exactly equal.

| Synthetic scenario | p50 (ms) | p95 (ms) | p99 (ms) | Max (ms) | n |
|---|---:|---:|---:|---:|---:|
| 30 symbols, baseline | 597 | 619 | 670 | 683 | 20 |
| 30 symbols, proposed index | 196 | 202 | 210 | 213 | 20 |
| 50 symbols, baseline | 979 | 1,003 | 1,010 | 1,011 | 20 |
| 50 symbols, proposed index | 295 | 303 | 304 | 305 | 20 |
| 61 symbols, baseline | 1,202 | 1,244 | 1,265 | 1,270 | 20 |
| 61 symbols, proposed index | 355 | 365 | 372 | 374 | 20 |
| 61 symbols, proposed index, three workers | 477 | 582 | 582 | 582 | 6 |

**Interpretation:** Candidate index produced approximately 67–71% lower observed p95 within this isolated synthetic run, while preserving simulated scientific outputs and core transaction integrity. These p99 values describe only small synthetic cohorts; they cannot quantify true production tail risk. Synthetic concurrency and cache/distribution conditions are not a credible proxy for real deployment without authentic functions/roles/extension environment and production-like contention.

The previous synthetic-run numbers differed because runner/cache/test conditions vary; avoid merging different CI cohorts or presenting synthetic differences as an assured production improvement.

## 3. Production failure continues

At **13:35 UTC**, read-only evidence recorded **two newly stale 49/0 Render parent-only scans**, collected at 13:04 and 13:22 UTC. Both lacked readiness children and were older than the three-minute publication grace. Historical 11:03–12:04 failures remain. The repair is **not deployed**.

## 4. Authentic private clone gate — NOT MET

- Public GitHub repository cannot hold private SQL function bodies, credentials or production rows.
- The connected Supabase inspector can read metadata, but it does **not** provide an authenticated full `pg_dump` export into the user's **existing private Codespace**.
- Existing guarded [schema export](../ops/local/export_private_pg_schema.sh) requires authorized private PostgreSQL connectivity and secret input **directly into a hidden Codespace terminal**, not GitHub or this chat.
- New zero-write [Codespace clone-readiness check](../ops/local/check_private_pg17_clone_readiness_v01.sh) is prepared; **not executed in the Codespace** because no terminal session to that specific private environment is available through this connection.
- Private restore, production-equivalent role/extension/ownership checks and matching full trigger fingerprints **not done**. Stock `postgres:17` does not automatically include Supabase extensions/roles.
- Future acceptance: restore private schema with compatible extensions and roles, run structural fingerprints, seed representative synthetic historical data, execute **authentic** full RPC+trigger+side branches at 30/50/61 and concurrency, verify exact row/side-effect/privilege equivalence, p50/p95/p99 and latency headroom under the actual 12s server budget; obtain qualified independent DBA/security approval against an exact final commit.

**No full production-equivalent latency certification or production readiness claimed. PRODUCTION NO-GO.**
