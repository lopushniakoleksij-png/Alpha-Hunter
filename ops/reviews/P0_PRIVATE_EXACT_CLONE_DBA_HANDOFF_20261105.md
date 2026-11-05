# P0 — Independent DBA exact-clone acceptance runbook (PRIVATE operator workflow)

**Status: BLOCKED / PRODUCTION NO-GO.** This is an operator handoff, not a claim that an exact clone, genuine trigger benchmark or independent review exists. Related: draft [PR #418](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/418), draft [PR #419](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/419), review [issue #420](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/420).

## 1. Scope, custody and resource boundary

An **independent named DBA**, separately approved for read-only production metadata access, must own this work. The connected application author and the synthetic CI tests are *not* independent approval. Use an **existing** DBA-controlled isolated machine with PostgreSQL 17 and no purchased infrastructure; do not rent a cloud instance or add paid services. The linked ChatGPT runtime does not include PostgreSQL or Docker. Do not expose any production database URL, role passwords, JWT signing keys, database function bodies, account values or user records in this public repository or in GitHub Actions logs/artifacts.

Before any metadata export, DBA must confirm an approved maintenance window and a **read-only** principal with sufficient catalogue access, because schema dumping can still consume production resources. Do not change the active scanner, schedules, Supabase grants, SQL functions, data or configuration.

## 2. Schema-only capture — on the DBA's approved PRIVATE workstation

Check the current [Supabase schema-dump/restore documentation](https://supabase.com/docs/guides/self-hosting/restore-from-platform) and locally installed PostgreSQL tooling. For an *approved* DBA-managed machine only, use its password manager / secure libpq service to connect; never pass a secret URL as an argument displayed in a public log or shell history.

Example of the **shape of the DBA-only operation**, *not a command the automated agent may run against production*:

```sh
umask 077
mkdir -p ./private-p0-schema && chmod 700 ./private-p0-schema
# Configure a locally secured libpq service file (not in this repository).
# Verify the selected service is the approved READ-ONLY production source.
pg_dump --version
pg_dump --schema-only --format=custom --schema=public --schema=private \
  --file=./private-p0-schema/source-schema.dump \
  "service=<DBA_APPROVED_READ_ONLY_SOURCE>"
```

The dump may contain confidential SQL function bodies or embedded defaults: **never commit it, attach it to an issue, or upload it as a public CI artifact.** Compare definitions and SHA-256 fingerprints privately. The production project includes cross-schema trigger functions and tables, with `private` paper-order destinations. The earlier public-only and regex-based graphs are insufficient to prove executed dependency closure.

**Important:** The schema dump alone may omit required extension objects, other referenced schemas, privileges, object ownership, database roles, or global settings; the DBA must capture/reconstruct every needed dependency without copying real user data. If reconstruction needs a paid product, production privileges, or a real credential on an untrusted service, **STOP — NO-GO**.

## 3. Restore on disposable PG17, never on production

Use an isolated container/VM, database name `isolated_research`, and a local-only endpoint `127.0.0.1:5432`. No network route or credentials to Bitget, Render, production Supabase, or other execution endpoints. Install necessary **permitted** extensions and replace external service endpoints with strictly disconnected local stubs only when doing so does not change the acceptance code path; otherwise flag the untestable dependency rather than claiming parity.

DBA-owned restore uses PostgreSQL restore tools and explicit error-on-failure transaction control. Preserve/compare function owner and `SECURITY DEFINER` semantics; `--no-owner` or `--no-acl` may make a restore succeed but **invalidates owner/grant equivalence unless separately reproduced and verified**. Compare `pg_get_functiondef`, `pg_get_triggerdef`, indexes, constraints, RLS, permissions, and any extension dependencies.

After the private restore, run the code from the draft branch on the **isolated clone** only, with ordinary disposable local database connection settings:

```sh
export AH_P0_LOCAL_POSTGREST_ONLY=1
export AH_P0_PG_DSN='host=127.0.0.1 port=5432 dbname=isolated_research user=postgres'
python ops/reviews/p0_verify_isolated_production_catalog_clone_20261105.py
```

The verifier checks exact first-order fingerprints and selected public/private candidate objects, but **it is NOT a proof of complete dynamic execution graph**. It must refuse production URLs and libpq indirection. A synthetic fixture **must fail** this gate; green fixture tests never substitute for a real clone.

## 4. Real trigger, permissions and performance evidence

- DBA must privately create **sanitized, realistic** 61-, 62-, and 63-symbol payloads, production-shaped indexes and representative data volume/distributions. No real account identifiers, customer rows or exchange credentials.
- On an actual exact-code clone, instrument real nested trigger executions. Capture each relevant trigger's **real** timing samples and sample count sufficient to compute descriptive p50/p95/p99 and maxima. Also collect full atomic RPC HTTP latency, lock wait, WAL/IO, concurrency, SQLSTATE 57014 behaviour and 15-second deadline. Use isolated PostgreSQL `track_functions=all` for function-call totals and, if approved and available, isolated `auto_explain` nested statement/trigger logs. **Cumulative means alone are not trigger p95/p99.**
- Perform repeat runs under concurrency and with fault injection. Prove zero partial publication after any thrown exception; count parent, children, signals, features, readiness and all downstream observation/episode/quote/order tables before and after; prove that duplicate-run and lost-ACK cases do not create second publications.
- Verify paper-order and calibrated-paper-order side effects, `trade_permission=false`, and no real-order authority. If the actual triggers create unexpected paper orders or have external effects, **hold** for separate paper-risk/security evaluation. Do not disable those hooks merely to get a fast benchmark.
- Separate security reviewer must check actual local JWT verification for `anon`, `authenticated` and privileged writer, forbidden direct grants, `SECURITY DEFINER` owners and search paths, the private schema, and `TRUNCATE` grants (RLS does not govern `TRUNCATE`). Never run destructive SQL against production.
- Report versions and SHA-256 of the schema dump privately, source review commit SHA, table/function/trigger closure, representative dataset statistics, measured latency distributions, API/SQL errors, reproducible rollback, and unanswered issues. Publish **sanitized summary only**.

## 5. Sign-off and immutable release boundary

A qualified independent DBA must approve the exact cloned execution evidence; **a different qualified independent security reviewer** must approve effective permissions and paper/side-effect safety. Each reviewer should file their GitHub review and link sanitized evidence in [issue #420](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/420), identifying the **exact immutable tested commit SHA** and their role/qualification. The author, assistant, bots or CI cannot self-sign. Source-custody, paper-risk, operations and owner release authority are separate gates.

Until those reviews exist, **PR #418 and #419 stay DRAFT and UNMERGED. No production scanner change, no actual migration, no grant changes, no extra spending, no live-order authority. PRODUCTION NO-GO.**
