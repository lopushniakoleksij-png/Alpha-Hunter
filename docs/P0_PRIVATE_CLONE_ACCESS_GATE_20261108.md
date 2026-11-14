# Alpha Hunter — Harada B2–B8 Private Clone Gate, 8 November 2026

**Current state: BLOCKED, NOT EXECUTED.** This note is a specific blocker and private hand-off, not a production release plan.  
**Existing repair:** draft PR #445 on `fix/supabase-write-timeout-qa`.  
**Budget:** £0. **Production:** read-only. **Real orders:** disabled.

## Access boundary verified

1. Connected Supabase tools permit authorised read-only SQL inspection, but **do not expose an authenticated `pg_dump` archive or transfer it into a Codespace**.
2. Connected GitHub tooling can edit the isolated source branch and inspect CI but **does not expose the user's existing Codespace terminal, filesystem or Codespaces-only secrets**. GitHub public-repo fetch access is not equivalent to Codespace shell access.
3. The existing project is **Supabase PostgreSQL 17.6.1.147**, EU region; the read-only production fingerprints below were rechecked on 8 November 2026. There are no configured Supabase development branches.
4. Supabase currently uses physical backups. They are not portable, downloadable logical `pg_dump` archives. Do **not** restore a backup in place, buy a Supabase development branch, rotate passwords or publish credentials.
5. Because the repo is public, **never commit private SQL function bodies, schema dump, database password, role file or actual customer/paper records**. Export must happen in the owner's existing private Codespace.

## Production read-only fingerprint baseline, rechecked today

| Measurement | Verified production |
|---|---|
| Application tables / RLS enabled | 128 / 128 |
| Public application columns / indexes | 3012 / 360 |
| Application triggers / trigger-bearing tables | 131 / 108 |
| Distinct direct trigger functions / definer trigger sites | 36 / 21 |
| Column digest | `c802a3e3d96d620a20adc8c3af350472` |
| Index digest | `5a7e8cbe8b8450677f6be84a77caaa6e` |
| Trigger + direct function digest | `5c5b202307ef6bb57b4a9b08082c2a1e` |
| Table grants / RLS digest | `c9785c793fa51a732c2edc96ba22c7eb` |
| Complete `private` function count / SECURITY DEFINER count | 110 / 65 |
| Complete `private` function custody digest | `8fae5afad12f3040d30d0416cbfd9be1` |
| `public.alpha_hunter_%` function count / SECURITY DEFINER count | 10 / 5 |
| Public Alpha Hunter function custody digest | `a75b1d2ed683766dbd5ffa3830f7f087` |
| Direct application triggers on tables within `private` | 0 |

The new [read-only full function custody inventory](../ops/sql/readonly_p0_private_function_catalog_fingerprint_v01.sql) fingerprints **all 120 selected functions**, including bodies, owner, argument signature, security/volatility flags, explicit runtime settings and ACLs, but **returns hashes only**. Matching catalog fingerprints are **necessary but insufficient**: dynamic SQL calls, runtime data shape, role inheritance and extension workers still require private QA.

Production extensions and versions: `http 1.6`, `pg_cron 1.6.4`, `pg_net 0.20.4`, `pg_stat_statements 1.11`, `pgcrypto 1.3`, `plpgsql 1.0`, `supabase_vault 0.3.1`, `uuid-ossp 1.1`. The isolated clone must match these, or record exact reviewed compatibility exceptions. Plain `postgres:17` generally cannot provide all Supabase-specific extensions.

## Single authorized operator hand-off, no credentials in chat

Open the **existing** Alpha Hunter Codespace in GitHub's browser, switch to the isolated draft branch, and run:

```bash
git checkout fix/supabase-write-timeout-qa
git pull --ff-only
bash ops/local/check_private_pg17_clone_readiness_v01.sh
```

If the preflight confirms **no existing private archive**, the owner or authorized custodian can run, **only within that Codespace**:

```bash
bash ops/local/export_private_pg_schema.sh
```

The guarded script asks for the Session pooler host and accepts a **hidden database-password input locally**. It uses TLS verification, read-only PostgreSQL session defaults, a schema-only dump and a no-password role inventory; saves them exclusively under `$HOME/.alpha-hunter-private-dbqa` with owner-only permissions. **Do not paste the database password or the archive into ChatGPT, issues, files or Git.** If the existing authorized password is not available, stop here: do not substitute a Render password, API key, service-role key, or rotate credentials without explicit separate authorization.

Once a successful local archive exists, run:

```bash
bash ops/local/inspect_private_pg_archive_topology_v01.sh
```

This validates the **offline** archive's known direct hot-path objects and private file modes. It does **not** restore or certify the schema.

Only after an authorized, privately isolated PostgreSQL 17 environment with compatible extensions, roles, ownership and a deliberately completed schema restore exists, run:

```bash
bash ops/local/verify_restored_private_pg17_fingerprints_v01.sh
```

This script requires a **network-isolated** container named `alpha-hunter-private-postgres17-qa`, local database `alpha_hunter_private_qa`, matches the same 128-table structural fingerprints, six named critical routines, **all 120 public/private function custody fingerprints**, and eight extension versions. It rejects mismatches without changing anything.

**Neither restore nor real-trigger benchmark has been executed.** Do not mark B2–B8 PASS based on script creation or shell syntax checks.

## What still separates a matched schema from release certification

- Verify dynamic and transitive private SQL dependencies, trigger timing, effective privileged role/RLS/owner context, extensions/background workers and scientific outcomes on the private restored copy.
- Seed realistic **synthetic** cohorts and run the existing 2×2 architecture/index harness against authentic function behavior (the public fixture uses synthetic triggers and is **not directly suitable for an authentic schema** without a private-only adapted adapter).
- Measure per-scan 30/50/61 p50/p95/p99, contention, WAL, lock waits and real effective 12-second service-role and client timeout margins.
- Test rollback, lost acknowledgement, conflicting replay, and all downstream scientific/paper side effects without live orders.
- Obtain qualified independent DBA and security/custody approvals against exact release SHA, then explicit owner deployment approval.

## Verified code-level safety CI

[GitHub Actions #42490760120](https://github.com/lopushniakoleksij-png/Alpha-Hunter/actions/runs/42490760120) **PASS** at `d866a110df7851bc8cf0ee18750545fec5658d8b`: shell syntax validation and confirmation that private archive/restore preflight scripts and export refuse unattended CI. **No authentic archive, restore or benchmark** was created by this test.

**Final decision:** **PRODUCTION NO-GO** until private access and authentic test prerequisites are completed. Do not touch main, live scanner, production SQL, trading permissions, scheduled safety tasks or spending.
