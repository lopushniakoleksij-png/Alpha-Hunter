# P0: Live trigger fan-out inventory — 2026-11-09

**Evidence class:** read-only production `pg_trigger` / `pg_proc` metadata and body-reference *booleans* (no function bodies exported). **Not a timing benchmark, not a complete parsed dependency graph, not release certification.**

## Confirmed direct trigger edges

| Parent table | Trigger / event | Function | Observed function body references |
|---|---|---|---|
| `alpha_hunter_symbol_snapshots` | `trg_ah_capture_strategy_observations_v01`, AFTER INSERT/UPDATE | `private.alpha_hunter_capture_strategy_observations_v01` | `alpha_hunter_strategy_observations_v01`, `alpha_hunter_strategy_episodes_v01`; INSERT and ON CONFLICT |
| `alpha_hunter_strategy_observations_v01` | `trg_ah_capture_shadow_decision_quote_v01`, AFTER INSERT | `private.alpha_hunter_capture_shadow_decision_quote_v01` | `alpha_hunter_shadow_decision_quotes_v01`, `alpha_hunter_symbol_snapshots`; INSERT and ON CONFLICT |
| `alpha_hunter_strategy_episodes_v01` | `trg_ah_enqueue_strategy_24h_outcome_v01`, AFTER INSERT | `private.alpha_hunter_enqueue_strategy_24h_outcome_v01` | 24h-outcome target; INSERT and ON CONFLICT |
| `alpha_hunter_signal_features` | `trg_ah_enrich_signal_feature_geometry_context_v01`, BEFORE INSERT | `private.alpha_hunter_enrich_signal_feature_geometry_context_v01` | `alpha_hunter_symbol_snapshots`; INSERT and ON CONFLICT |
| `alpha_hunter_signals` | `trg_ah_create_paper_order_v01`, AFTER INSERT | `private.alpha_hunter_create_paper_order_v01` | `alpha_hunter_paper_orders`; INSERT and ON CONFLICT |
| `alpha_hunter_snapshots` | `trg_ah_capture_snapshot_slim_v01`, AFTER INSERT/UPDATE | `private.alpha_hunter_capture_snapshot_slim_v01` | Not expanded |
| `alpha_hunter_snapshots` | `trg_ah_materialize_account_ledger_from_snapshot`, AFTER INSERT | `private.alpha_hunter_materialize_account_ledger_from_snapshot` | `private.alpha_hunter_text_float` textual reference |

Strategy observations and strategy episodes also each have an append-only guard BEFORE UPDATE/DELETE. The inventory is based on direct trigger metadata and text matching for referenced relations; conditional branches, dynamic SQL, and further downstream triggers are not exhaustively resolved.

## What is and is not measured

Live cumulative `pg_stat_statements` symbol UPSERT fingerprint `153440d36d3f` at **2026-11-09 14:24 UTC**: **3,032 calls**, **4,828.6 ms mean**, **11,881.2 ms max**, **12,786,432,712 WAL bytes** since last reset. These are top-level SQL statement statistics; `pg_stat_statements.track=top` and `track_functions=none`. They **cannot rank the nested trigger functions by elapsed time**. Function source length, call depth and fan-out are *candidate prioritization signals*, not timing measurements.

**Highest-priority timing hypothesis:** symbol UPSERT → strategy-observation/episode capture → observation INSERT triggers shadow-quote capture; episode INSERT triggers 24h-outcome enqueue. Also isolate geometry feature BEFORE INSERT and paper-order AFTER INSERT separately. An INSERT/UPDATE trigger on symbol rows could be re-entered during conflict updates; exact conditions need private-function validation.

## Next required acceptance evidence

1. Authorized private schema archive into isolated PostgreSQL 17; preserve all private function bodies, ACL/RLS, indexes, triggers and extensions. No SQL source or credentials in public repository.
2. Reproduce exact trigger graph, including dynamic SQL and trigger-induced downstream calls; compare fingerprints.
3. Benchmark isolated authentic graph at 30/50/61 synthetic symbols, with per-stage timing for symbol upsert, strategy observation/episode, shadow quote, 24h enqueue, feature enrichment and paper order; record p50/p95/p99, locks and WAL under realistic concurrency.
4. Validate atomic RPC rollback, idempotent retries, no duplicate children, permissions and all downstream effects. Independent DBA and security reviewers sign the exact release commit.

**Production NO-GO; protected scanner unchanged, no production writes or credentials changed.**
