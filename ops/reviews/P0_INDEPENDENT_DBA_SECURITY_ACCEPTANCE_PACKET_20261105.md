# ALPHA HUNTER P0 — Independent DBA + Security Acceptance Packet

**Review decision today: PRODUCTION NO-GO.** Draft PR #418 remains unmerged and is stacked on draft #417. No production SQL, Render, cron, trading grants, paper-cohort or scanner changes are authorised. £0 new infrastructure.

## Evidence available for reviewers

1. PR #418 at https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/418 (review *exact current head SHA*, not just branch name).
2. Read-only production PostgreSQL 17.6 SHA256 catalog fingerprint: `ops/reviews/p0_readonly_production_fingerprints_20261105.json` (five canonical tables: columns/defaults/indexes, seven first-order trigger/function signatures; **not** all downstream triggers).
3. Isolated PG16/17 JWT/PostgREST test harness: `ops/reviews/p0_real_postgrest_canonical_publication_20261105.py`, using only local dummy JWT signing key; anonymous + authenticated rejected, explicit privileged writer accepted. Tests do NOT prove real Supabase auth parity.
4. Production SQL top-level statement timing and SQLSTATE 57014 logs were collected **read-only** on 5 Nov 2026. Production `track_functions=none`, so no true per-trigger p95/p99 has been measured.
5. `ops/reviews/p0_verify_isolated_production_catalog_clone_20261105.py` is a **read-only fingerprint checker**, not a full-graph attestation. It requires localhost `isolated_research`, `AH_P0_LOCAL_POSTGREST_ONLY=1` and no real cloud/exchange credentials; execute only after an authorised DBA privately establishes a sanitized PG17 clone.

### Database acceptance — independent qualified DBA

- Verify exact publication data contract (all five tables) against the frozen production catalog. Cloning only selected synthetic column types is insufficient.
- Privately export schema, function bodies, indexes, constraints, privileges, RLS policies, extension dependencies and **transitive** side-effect graph. Do not put actual private function source, credentials or live rows into the public repository.
- The production graph includes parent account materialisation, strategy observations, strategy episodes, shadow quotes, paper orders, geometry enrichment and associated downstream append-only triggers. Match actual executed closure, not merely seven initially attached hooks.
- Use only disposable PostgreSQL 16 and 17, with sanitized but representatively sized 61/62/63-symbol test inputs. No production database write, no production credentials, no real or paper trading-order side effects in the actual services.
- Reproduce 57014 trigger cancellations, parent/child partial-write prevention, transaction rollback, feature failure, unknown commit, lost ACK, concurrent duplicate requests, lock contention, and deterministic independent exact-count readback.
- Measure repeat runs with full trigger side effects, not synthetic no-op substitutes. Collect sample count, wall clock latency, p50/p95/p99, worst case, each trigger's execution count and latency, locks, WAL/IO, HTTP status and 15-second client timeout adherence. Do not raise production timeout to manufacture a pass.
- Show no mutation of existing run IDs, research history or paper orders. Produce explicit reproducible rollback proof.

### Security acceptance — different qualified reviewer

- Verify local JWT access denial for `anon` and `authenticated`, and success only for specifically authorised server-side identity, with valid and forged tokens. Review actual Supabase gateway settings separately: synthetic JWT tests do not prove them.
- Cross-check RPC `EXECUTE` grants, schema `USAGE`, `SECURITY INVOKER` execution context, owner, search_path and any privilege-escalating `SECURITY DEFINER` triggers.
- Production catalog shows `anon` and `authenticated` receive table-level `TRUNCATE`, `TRIGGER`, DML and other privileges on the canonical tables even though RLS denies row access. **RLS does not govern TRUNCATE.** Assess direct SQL/RPC exposure, effective privileges and least-privilege remediation; do not change production grants without authorisation.
- Confirm private account data, service credentials, JWT signing keys, exchange keys, trades and seals cannot leak into GitHub Actions artifacts/logs or public repository.
- Explicitly veto any change enabling live exchange trading, extending paper production authority, bypassing historical-immutability controls or exposing account internals.

### Acceptance fields — blank until independently evidenced

| Gate | Reviewer (qualified, independent) | Exact commit SHA | Dated evidence link | Result |
|---|---|---|---|---|
| Exact production clone + transitive trigger graph | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Real trigger p50/p95/p99 + concurrency + rollback | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Supabase/PostgREST RLS/JWT/GRANT matrix | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Custody, security boundaries, secret management | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Paper-scientific and downstream side-effect approval | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Operations: monitor/rollback/scanner continuity | **UNASSIGNED** | TBD | TBD | BLOCKED |
| Explicit owner-controlled scanner release | **OWNER DECISION PENDING** | TBD | TBD | BLOCKED |

**Signature rule:** CI/test author/bot approval is not independent DBA/security signoff. Evidence must point to immutable SHA and be reviewed by named qualified humans with appropriate authority. If a reviewer cannot access real schema safely or if qualification is unclear, keep release blocked.

**Current decision:** remain DRAFT, unmerged, untouched production. Only after all independent approvals and separate owner authorisation may a new controlled scanner change be considered.

## Cross-schema trigger and SQL TRUNCATE evidence — 5 Nov 2026 follow-up

- Earlier candidate manifest `p0_production_trigger_dependency_candidates_20261105.json` is **public-only and demonstrably incomplete**. It must not be used as an exact production graph.
- New `p0_cross_schema_write_candidate_graph_20261105.json` follows textual `INSERT INTO`, `UPDATE`, and `DELETE FROM` matches recursively across `public` and `private`, rooted at the five canonical publication tables. It identifies **20 candidate relations (six private), 21 attached triggers and 15 candidate DML edges**. The six private destinations include `private.alpha_hunter_paper_orders_v01`, `private.alpha_hunter_calibrated_paper_orders_v01`, snapshot slim, strategy 24h outcome queue, geometry enrichment events, payoff geometry observations. This is **not a verified runtime call graph** (function-call indirection, dynamic SQL, unqualified relation names, conditionals and nonmatching objects may be missing).
- The isolated read-only clone fingerprint checker now compares these cross-schema object/RLS definitions and attached trigger signatures, as well as the prior 22-table public-only reference. **Its source compilation is CI-tested; a genuine private DBA-supplied PostgreSQL 17 clone has not been created or checked.**
- Read-only production `pg_catalog` confirms all five canonical tables grant `TRUNCATE` and `INSERT` to both `anon` and `authenticated`. They have RLS enabled and no policies, but **TRUNCATE bypasses RLS**. This is a privilege-hardening finding, not proof of remotely exploitable PostgREST HTTP access; foreign keys and SQL privileges may constrain individual operations. Independent reviewer must assess all reachable SQL/RPC paths and recommend minimal grants.
- The isolated local PostgreSQL regression `test_disposable_truncate_security_gap` uses a disposable probe table: `anon` and `authenticated` each see zero rows under RLS but may TRUNCATE with an explicit table-level grant. All test transactions roll back; **no production grant or row was changed**.
- Read-only catalog also shows inspected production `SECURITY DEFINER` trigger functions owned by `postgres`, with explicit empty `search_path` and **no direct EXECUTE privilege** for `anon` or `authenticated`. Private schema `USAGE` is also denied to those roles. This does not prove downstream privileged trigger safety or a complete authentication attack-surface review.
- Production v03 research RPC remains uninstalled (`to_regprocedure(...) IS NULL`); `track_functions=none`; no measured authentic trigger p50/p95/p99.
- Release stays blocked until an independent qualified DBA supplies a privately reconstructed exact production schema and executed trigger closure, and a different qualified security reviewer signs the real-role authorization and least-privilege evidence against an immutable PR SHA. Do not place real DB schema function bodies, credentials or production customer data in the public repository.
