# Alpha Hunter P0 — production-schema atomic publication release gate

**Status: PRODUCTION NO-GO.** Snapshot: 2026-11-05 08:00–08:12 UTC.
**Change classification:** research-only isolated successor. **Budget:** £0.
**Preserved:** production RENDER_CRON scanner, main, production Supabase data/schema, Render deployment, paper cohorts and order permissions. No real exchange orders or promotion.

## Read-only production evidence

Project: Alpha Hunter Supabase, PostgreSQL **17.6**, eu-west-1.
Real tables (2026-11-05 catalog, pg_total_relation_size):
- `public.alpha_hunter_snapshots`: 332 MB, 8 columns.
- `public.alpha_hunter_symbol_snapshots`: 2055 MB, 16 columns.
- `public.alpha_hunter_signals`: 798 MB, 16 columns.
- `public.alpha_hunter_signal_features`: 1207 MB, 38 columns.
- `public.alpha_hunter_readiness_observations_v01`: 18 columns.
- `public.alpha_hunter_strategy_observations_v01`: 3889 MB, 37 columns.

Required/defaulted NOT NULL columns relevant to composite JSON record conversion:
- parent: `error_count DEFAULT 0`, `created_at DEFAULT now()`;
- symbol: `state_changed DEFAULT false`, `trade_permission DEFAULT false`, `created_at DEFAULT now()`;
- signal: `trade_permission DEFAULT false`, `created_at DEFAULT now()`;
- feature: `trade_permission DEFAULT false`, `features DEFAULT '{}'`, `source_payload DEFAULT '{}'`, `created_at DEFAULT now()`;
- readiness: `trade_permission DEFAULT false`, `v7_trade_ready DEFAULT false`, `created_at DEFAULT now()`.

All five tables have RLS enabled. `anon` and `authenticated` have table-level CRUD grants on these five but do not bypass RLS. No `pg_policies` rows exist for the five; **table-level grants alone do not prove API access**. `service_role` bypasses RLS and has table DML grants for these five; this is privileged and not safe for a browser. New RPC remains `SECURITY INVOKER`, explicitly revoked from `PUBLIC`, and ungranted in this draft. API-level role denial, privileged grant and authorization still require real PostgREST tests in an approved isolated environment.

Active production triggers relevant to publication (2026-11-05):
1. parent AFTER INSERT/UPDATE OF payload — slim capture (`SECURITY DEFINER`);
2. parent AFTER INSERT — account-ledger materialization (`SECURITY DEFINER`);
3. symbols AFTER INSERT/UPDATE OF payload — strategy-observation capture (`SECURITY DEFINER`);
4. signals AFTER INSERT — paper-order creation (`SECURITY DEFINER`);
5. signal features BEFORE INSERT — geometry-context enrichment (`SECURITY DEFINER`);
6. strategy observations AFTER INSERT — shadow quote capture (`SECURITY DEFINER`);
7. strategy observations BEFORE UPDATE/DELETE — append-only guard.

**Trigger side effect requiring separate reviewer sign-off:** signal INSERT may create paper orders under the existing private paper policy, even though the inserted signal has `trade_permission=false`. Do not run an atomic test against production; require scientific/risk reviewer acceptance of all paper-side effects.

24h PostgreSQL logs ending 2026-11-05 08:00 UTC contained **180 SQLSTATE 57014 cancellation log events**. This is event count, not confirmed number of scanner runs or per-trigger failure count.

Real `extensions.pg_stat_statements`, stats reset 2026-09-30 22:01:58 UTC; top-level queries only (`pg_stat_statements.track=top`), `track_functions=none`:
- `alpha_hunter_symbol_snapshots` INSERT: **2724 calls**, mean **4843.40 ms**, maximum **11881.16 ms**.
- `alpha_hunter_signal_features` INSERT: **3454 calls**, mean **625.05 ms**, maximum **5865.23 ms**.
- `alpha_hunter_snapshots` INSERT: **3036 calls**, mean **391.95 ms**, maximum **9527.86 ms**.

These are historical **statement** statistics including trigger work, not independently measured trigger timings, concurrency-safe p95/p99, or new-RPC timings. Do not claim production root cause or end-to-end acceptance from these values.

## Successor v03 research amendment

File: `research/p0_successor_atomic_canonical_v03_PRODUCTION_SCHEMA_REVIEW_ONLY.sql`.
Based on the v02 five-stage transaction in draft PR #416; separate draft from PR #417. Fixes composite JSON's lack of SQL DEFAULT evaluation by injecting exact currently observed default values only when JSON keys are absent; explicit nulls remain failures. Preserves optional captured columns. Inserts `_canonical_publication_state=VERIFIED` in the **initial parent INSERT** inside the transaction; removes the extra parent payload UPDATE. Adds parent payload identity/marker validation. Keeps uniqueness, symbol alignment, no trade-permission promotion, immutable-run refusal, transaction rollback, `SECURITY INVOKER`, and no production grant.

**Limitations:** live schema/trigger code was inspected read-only; no production or exact-schema clone write was run. Fixture mirrors selected default/NOT NULL columns but does not reproduce all production types, indexes, triggers, RLS or load. No production RPC or migration installed; no real approval received.

## Independent acceptance checklist — ALL required

- [ ] Source-custody reviewer: record immutable exact branch/head SHA, diff, and verified original source; no protected main merge.
- [ ] DBA: approve a **disposable** PG16 and PG17 schema replica containing exact five-table columns, types, defaults, indexes, constraints, RLS, real trigger definitions and sanitized fixture data; do not copy sensitive records or reuse production secrets.
- [ ] DBA: execute the v03 five-stage PostgREST RPC with real trigger graph at 61/62/63-symbol representative scan size; verify COMPLETE/ABSENT only, exact parent+symbol+signal+feature+readiness/observation counts, all source identities, no duplicate/partial paper effects, and deterministic no-replay readback.
- [ ] DBA: fault-inject `57014`, downstream feature failure, partial/unknown COMMIT, disconnect, concurrent duplicate, lock contention and statement timeout; verify atomic rollback, no rerun of stale updates, bounded retry and audit custody.
- [ ] DBA + operations: measure full transaction and each true trigger's call counts and p50/p95/p99 latency under representative concurrent load; capture PostgREST HTTP timeouts, WAL, locks and DB resource use. Agree p99 safety margin below the **existing minimum timeout**. Never raise the timeout merely to hide trigger work.
- [ ] Security reviewer: test actual PostgREST `anon` and `authenticated` denial, privileged server-only role acceptance, RPC EXECUTE grants, `SECURITY INVOKER`, RLS, search_path, trigger definer boundaries and privilege escalation resistance; no credentials in GitHub or chat.
- [ ] Risk/scientific reviewer: inspect the production signal-to-paper-order trigger and ensure no paper cohort, order history or sealed research claims are silently altered.
- [ ] Independent DBA reviewer: dated, named **APPROVE** with exact commit SHA, logs and rollback evidence. The author or automated tests cannot self-approve.
- [ ] Independent security reviewer: dated, named **APPROVE** with exact commit SHA and authenticated permission matrix. The author or automated tests cannot self-approve.
- [ ] Operations/source custodian: rollback, alert delivery, hourly scanner continuity, production/main boundaries and explicit owner release authorisation all PASS.

**Decision:** Until every gate is independently evidenced and authorised, do not merge, install grants, migrate Supabase, alter live triggers, deploy to Render, interrupt cron, enable trading or change scanner execution.

Documentation cross-check: https://supabase.com/docs/guides/database/postgres/triggers ; https://supabase.com/docs/guides/database/functions ; https://supabase.com/docs/guides/deployment/going-into-prod .
