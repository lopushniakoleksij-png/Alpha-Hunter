# R1 migration-identity security finding — strictly isolated PG16
**Date: 2026-10-16. Review-only. NO production access or migration authorization.**

## Why this additional gate was necessary
The saved owner-facing `R1_FORWARD_V2_REVIEW_ONLY.sql` and
`R1_ROLLBACK_V2_REVIEW_ONLY.sql` are still the **unchanged, separately
hash-verified offline exact candidates** and have not been copied into
production, a live Supabase migration or this repository. Earlier rehearsal
instructions used the disposable GitHub PostgreSQL service's default
`bench` account, which is effectively **SUPERUSER**, whereas read-only
production catalog inspection established the actual Supabase inspection
role `postgres` has **rolsuper=false** and **rolcreaterole=true**.

In PostgreSQL 16 and 17, a non-superuser with CREATEROLE that creates
another role gains automatic ADMIN membership with `SET FALSE` and
`INHERIT FALSE`. Changing ownership of an existing VIEW requires the
migrator to be able to `SET ROLE` to the proposed owner, **and** the new
owner must have CREATE privilege in the destination schema. See official:
- https://www.postgresql.org/docs/17/role-attributes.html
- https://www.postgresql.org/docs/17/sql-alterview.html

Consequently the V2 SQL sequence
`CREATE ROLE ... NOLOGIN` → `CREATE SCHEMA ... AUTHORIZATION owner` →
`CREATE VIEW ...` → `ALTER VIEW ... OWNER TO owner` must NOT be assumed
deployable by the actual non-superuser migration executor merely because it
works as a synthetic superuser in CI. Changing a VIEW owner to the existing
`postgres` bypass-RLS account would **violate** the proposed redaction
isolation and is NOT an acceptable shortcut.

## Reproducible existing free CI test
`ops/reviews/successor_pg16_r1_non_superuser_owner_gate_v01.py`
is wired into the pre-existing
`.github/workflows/successor-pg16-isolated-review-v01.yml`.
It requires `GITHUB_ACTIONS=true` and the strict existing
`guard_dsn` bound to `bench@127.0.0.1:5432/postgres`; creates its
own ephemeral disposable DB `ah_r1_owner_gate_ephemeral` and two
synthetic no-login roles. It deliberately impersonates a **NON-superuser
CREATEROLE** migrator and checks:
- created owner membership `ADMIN TRUE / SET FALSE / INHERIT FALSE`;
- `pg_has_role(current_user, owner, 'SET')` is false;
- attempted schema creation AUTHORIZATION owner and attempted ALTER
  VIEW owner without the necessary role privileges are rejected;
- rejected ownership transfer leaves the original synthetic owner
  unchanged.
No real SQL, production secrets or real source relations are touched.
A green synthetic test is a **confirmed isolated blocker**, not an R1
migration PASS or a signed DBA approval.

## Minimal review request, no actual changes
1. DBA/security must approve the precise identity **and privilege sequence**
   for the future migration. If a temporary `SET TRUE` membership / CREATE
   grant is proposed, it must be acquired deliberately by the limited
   migration principal, removed before final acceptance, and checked for
   surviving unexpected memberships (especially the automatic ADMIN
   grant). A superuser-only SQL runner is not an equivalent surrogate.
2. Rehearse the **exact unchanged V2** forward+rollback with the
   non-superuser migrator and capture expected fail-closed behavior.
   Then author a **new versioned candidate** including the reviewed
   permission fix; independently hash it and execute its EXACT bytes in
   isolated PG16 and PG17 using production-equivalent restrictions.
   Never silently modify V2 or its recorded SHA256 evidence.
3. Test the projection owner `NOLOGIN`, `NOBYPASSRLS`, base-table
   RLS policy visibility, inability of reader to fetch `payload`,
   unexpected nonpaper source rows, missing identity, writer DML denial
   and forward/rollback source-row equality. First confirm non-SUPERUSER
   migrator can actually CREATE SCHEMA/VIEW and ALTER VIEW OWNER under
   approved limited permissions.
4. The R1 rollback must verify **definitions, expected role memberships,
   RLS policy identities, view owners and source counts**, not just 14
   policies by pattern. Unexpected modifications always fail closed.

## Release conditions
R1: NO-GO. R2/R3/R4 and new paper admissions: NO-GO.
Historic NMRUSDT LONG partial residual 1.5 paper units and four original
R10 horizon-integrity failures remain unresolved evidence. The source
`57014` child upserts are not repaired here. Never backfill source
history or claim independent 35-minute monitoring from local CI.
Frozen monitoring <=2,100s; SQL 12s; HTTP 15s.
Primary Hourly main remains unchanged; no merged production change,
credentials, billable resource, new trades, or 72h pilot.
**New spend: USD0. Independent human DBA/security signoff not obtained.**
