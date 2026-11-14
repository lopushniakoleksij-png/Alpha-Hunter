# Alpha Hunter / Stage 2 Private Clone Preflight — 2026-11-07

**Status:** PARTIAL / PRIVATE EXPORT AND RESTORE NOT EXECUTED
**Priority:** P0
**Release:** NO-GO — draft PR #445, no production change or paid infrastructure
**Production project:** yjgtjzymfurqzqqxcrnp
**Database version:** PostgreSQL 17.6.1.147
**Scope:** schema-only, no customer rows or secrets in Git

## Verified production fingerprint baseline (read-only)
The query `ops/sql/readonly_stage2_structural_fingerprint_v01.sql` was executed against production on 2026-11-07. This is the comparison baseline for any private restored clone.

| Metric | Production observation |
|---|---|
| public Alpha Hunter application tables | 128 |
| application tables with RLS enabled | 128 |
| public Alpha Hunter application columns | 3,012 |
| indexes | 360 |
| row policies on these tables | 0 |
| application triggers (broad matching scope) | 131 |
| trigger-bearing tables | 108 |
| distinct directly invoked trigger functions | 36 |
| SECURITY DEFINER trigger call sites | 21 |
| columns fingerprint (MD5) | c802a3e3d96d620a20adc8c3af350472 |
| indexes fingerprint (MD5) | 5a7e8cbe8b8450677f6be84a77caaa6e |
| triggers and function body fingerprint (MD5) | 5c5b202307ef6bb57b4a9b08082c2a1e |
| table grants/RLS fingerprint (MD5) | c9785c793fa51a732c2edc96ba22c7eb |

All fingerprint values are metadata-only; private SQL source, data rows and credentials must remain outside Git. This is a **necessary but insufficient** check for fidelity, since transitive dynamic SQL, ownership, extensions and runtime configuration may differ even if these hashes match. Do not treat MD5 fingerprints as cryptographic signatures or independent code custody.

The absence of explicit policies on these 128 RLS-enabled tables is **not** itself proof of a vulnerability. The independent security reviewer must inspect effective privilege paths including service_role, SECURITY DEFINER and any exposed RPCs before approval.

## Production installed extensions
| Extension | Installed version | Schema |
|---|---|---|
| http | 1.6 | extensions |
| pg_cron | 1.6.4 | pg_catalog |
| pg_net | 0.20.4 | extensions |
| pg_stat_statements | 1.11 | extensions |
| pgcrypto | 1.3 | extensions |
| plpgsql | 1.0 | pg_catalog |
| supabase_vault | 0.3.1 | vault |
| uuid-ossp | 1.1 | extensions |

**Compatibility finding:** The stock `postgres:17` container may not include Supabase extensions (particularly pg_net, pg_cron, http and supabase_vault). Before claiming a production-faithful restore, inventory the actual image's installed extensions and match the functions, versions, roles and background worker/config requirements. A Docker container merely running PostgreSQL 17 is not sufficient proof.

## Connection and backup route
- Supabase organisation: **Pro** (connected management metadata).
- Standard schema dump requires an authenticated PostgreSQL connection. `ops/local/export_private_pg_schema.sh` obtains the password by hidden terminal input and saves the export only beneath `$HOME/.alpha-hunter-private-dbqa`.
- The connected Supabase tools do not expose a full pg_dump archive or a write/command facility into the existing GitHub Codespace.
- On modern physical-backup projects, a managed backup restore is not the same as a portable downloadable logical dump. Do **not** restore an old backup into production or create a paid branch/project without explicit separate approval.
- No database password reset, credential leakage, public SQL upload, spending or production modification is authorised.

## Single next stage action
1. In the **existing** GitHub Codespace, confirm source access through the **Supabase Connect** panel or a previously stored authorised private connection. Do not paste secrets into GitHub source, chat, files, issue comments or logs.
2. If a valid authorised database password is already known, run `bash ops/local/export_private_pg_schema.sh` from the checkout root, using hidden prompt. Otherwise stop without guessing a password or resetting credentials.
3. Privately restore the archive to an isolated PostgreSQL 17 environment with all required extensions and roles. Preserve the exact restore logs privately.
4. Execute `ops/sql/readonly_stage2_structural_fingerprint_v01.sql` locally and independently against production; compare counts/digests and extension versions; inspect effective grants, RLS, ownership, triggers and nested side-effect graph.
5. Generate synthetic representative data; do not use raw production records. Only then move to 30/50/61-symbol performance and fault-injection tests.

## Acceptance record
**Schema exported:** NOT VERIFIED
**Private archive restored:** NOT VERIFIED
**Full trigger graph / role equivalence:** NOT VERIFIED
**Production-to-clone fingerprints match:** NOT VERIFIED
**Representative performance results:** NOT RUN
**Independent DBA/security signatures:** ABSENT
**Production changes made by this stage:** NONE

**Stage 2 result: BLOCKED. Recovery still PRODUCTION REPAIR REQUIRED — NO-GO.**
