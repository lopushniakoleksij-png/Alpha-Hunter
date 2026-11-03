# Alpha Hunter — P0.3 independent real Supabase role-auth acceptance packet
**Prepared:** 2026-11-03 UTC. **Decision:** PRODUCTION NO-GO. **No human signatures submitted.**

## Verified actual read-only production evidence
- Live PostgreSQL: `anon` and `authenticated` roles `BYPASSRLS=false`; `service_role` `BYPASSRLS=true`.
- Sensitive tables `alpha_hunter_paper_exit_attempts_v04`, `alpha_hunter_open_position_snapshots`, `alpha_hunter_profitability_test_activations_v01`, `alpha_hunter_shadow_decision_quotes_v01` have **RLS ON**, **zero RLS policies**, **no anon/auth SELECT grants**, and **service_role SELECT grants**.
- Parent and child snapshot tables have RLS ON with 0 policies; anon/auth SQL `SELECT` and `INSERT` grants exist, but denied RLS rows are expected for unauthorised identities. **GRANT is not proof of public row visibility; zero policies is not a guarantee about privileged service-role access.**
- Public Alpha Hunter tables lacking RLS: **zero**; selected `SECURITY DEFINER` routines executable by anon: **zero**; private selected definer routines executable by `authenticated`: **zero**. All are catalog evidence only.
- Current Supabase security advisor lists 128 **INFO** findings `rls_enabled_no_policy`; it does not automatically imply data leakage. This is not an independent penetration-test pass.
- Project has **one enabled `sb_publishable_` key and one enabled legacy anonymous JWT key**. Their actual values were deliberately NOT copied to source, GitHub logs or this packet.
- Live unauthenticated/no-key route test previously passed, HTTP 401 on three sensitive routes. Reviewer script replays this bounded negative-only path in CI.

## Exact reviewer-only HTTP checks (actual credentialed tests NOT YET EXECUTED)
Script: `ops/reviews/p03_independent_actual_supabase_role_http_readonly_v01.py`. Only `GET`, fixed real project hostname, verified TLS, redirects forbidden, fixed three table routes, no database writes, no query payload export. It prints role, response status and admission decisions only; never keys, user details or returned data. **Runs with real keys ONLY from an independently controlled reviewer environment.**

1. **Unauthenticated/no API key:** `python ... --role no-key` -> 401/403 on parent, child and exit routes.
2. **Publishable/anon:** Set `AH_P03_EXPLICIT_API_REVIEW=1`, `AH_P03_PUBLISHABLE_KEY` privately (new publishable or legacy anonymous key). Run `python ... --role anon`. Expected parent/child HTTP 200 with exactly `[]` under current no-policy RLS; exit evidence denied HTTP 401/403.
3. **Existing authenticated test user:** Same publishable key plus securely supplied *already issued* `AH_P03_AUTH_USER_ACCESS_TOKEN`. No auth login/user creation performed. `python ... --role authenticated` first verifies `GET /auth/v1/user` 200 then same parent/child `[]`, exit denied. A revoked or expired JWT is BLOCKED, not treated as a passing RLS check.
4. **Independently authorised privileged reviewer ONLY:** Requires `AH_P03_PRIVILEGED_READ_AUTHORIZED=1` and private `AH_P03_PRIVILEGED_REVIEW_KEY` supplied by reviewer via approved secret storage, plus generic opt-in. `python ... --role service_role`. Expected HTTP 200 on all three GETs. This proves read connectivity **only**. It does not test negative writes or validate ownership/secret-storage policy. **Never run privileged route in GitHub Actions, an untrusted computer, an iPhone browser, or ChatGPT.**

Never provide the key/token in GitHub issues, source code, CI input, screenshots, SMS or chat. Run only on an independently owned workstation with secret-safe storage. A user JWT is not the publishable API key; current Supabase requires publishable or secret keys in `apikey` rather than treating them as bearer JWTs.

### Independence and sign-off
| Acceptance authority | External validation required | Status |
|---|---|---|
| Security reviewer | Four actual role profiles, independent credential custody, RLS/API gateway, privileged routines, secret rotation policy | **NOT SIGNED** |
| DBA | Complete trigger/fee cost-floor dependency graph; isolated PG16/17 migration/recovery proof; signed SHA and rollback | **NOT SIGNED** |
| Quote custodian | Prospective authenticated market-source bytes/timestamps/immutable evidence per scan/position | **NOT SIGNED** |
| Alert-delivery custodian | Real provider delivery ID and recipient ACK, durable retry/replay | **NOT SIGNED** |
| Science/risk | No reclassification of three ambiguous same-snapshot first-entry exceptions; paper-only sealed R8/R9/R10 | **NOT SIGNED** |
| Operations/owner | Active protected main, independent release target, reviewed SHA, isolated rollback, separate owner production authorization | **NOT SIGNED** |

### Remaining source lineage and activation parity
Production SELECT-only graph shows activated cost-source trigger `private.alpha_hunter_bind_public_fee_evidence` and R8/R9/R10 guards. Three sealed guards matched archived DDL in earlier audit; **full execution-cost-to-fill lineage and complete actual API / database dependency equivalence are NOT verified**. Do not create database branches with hourly compute costs without independent approval; do not write to production or scan backfill.

As of this audit, most recent rolling 24-hour paper exit receipts: 189, each marked `captured_quote_only=true`, only 79 have a source label and none record a provider signature. This is an *observed field count* and not a proof that no other provider authentication exists. All 3 paper positions remain dual-protection-recorded with `unresolved_protective_evidence=true`.

## Release constraints
GitHub `main` active rule 26434794: PR independent approval and strict `full-suite`, no bypass, deletion/force-push prohibition. P0.3 inert isolated service free/manual-deploy with rollback passed. Production cron `crn-d9nmbjbm8hqs73elu6hg` remains main hourly autoDeploy=yes. Draft PR #378 stays UNMERGED.

**PRODUCTION NO-GO**; successful credential-free CI or a reviewer script with manually asserted success **is not a signed independent review or deployment permission**.
