# GitHub MAIN release protection — exact administrator configuration (NO-GO)

**Source of truth inspected 2026-11-02 UTC**
- Repo: `lopushniakoleksij-png/Alpha-Hunter`, public personal repository, default `main`.
- Main exact head at inspection: `b71c87d0b5963a5ca10c23d82b67a0edd47f120c`.
- GitHub branch API: `protected=false`. Repository rulesets GET: `[]`.
- Protected scanner Render cron `crn-d9nmbjbm8hqs73elu6hg` tracks `main`, autoDeploy=yes, schedule `0 * * * *`.
- Draft PR #378 is stacked on unmerged #371. **DO NOT MERGE #378 OR #371** on the basis of this document.

## Actions for the authorised repository administrator — not executed by automation

1. Open [Repository Settings → Rules → Rulesets](https://github.com/lopushniakoleksij-png/Alpha-Hunter/settings/rules) on GitHub with administrator credentials. Create **New branch ruleset**.
2. Name `AH-P0-Protect-main-No-Scanner-Autodeploy`. Enforcement: **ACTIVE**, not Evaluate or Disabled. Target **exact branch `main` only** (or "default branch" with explicit verification). Use an empty bypass list. Restrict branch deletions and block force pushes.
3. Require a pull request before merging; require **at least one independent approving review** (author must not self-approve), dismiss stale reviews on new commits, require approval of the most recent reviewable push if offered, and resolve all conversations before merging. Apply rules to repository administrators, without a self-bypass.
4. Require status checks to pass. First **exact verified eligible job/check name**: `full-suite` from workflow `Full Production Test Suite v0.1`. Its definition on current `main`: `.github/workflows/full-production-test-suite-v01.yml`, with unconditional `on: pull_request` (no path or branch filter). This check **passed** on research PR latest inspected head. Select GitHub Actions as expected source when supported.
5. Optionally include additional unconditional required job checks ONLY after verifying that they run on every PR targeting main and produce the correct check context. **Do not require path-filtered jobs** such as `fingerprint`, P0 catalog/PG checks or P0.3 research jobs without making their workflows universally runnable first. GitHub may hold skipped path-filtered checks PENDING indefinitely, blocking merges. Do not require `sync-production-target`: it runs on push to main and writes a release target to production rather than gating a PR.
6. Save/Create the active ruleset, then independently verify `GET /repos/lopushniakoleksij-png/Alpha-Hunter/rulesets` has an ACTIVE main-targeted rule and `GET /repos/lopushniakoleksij-png/Alpha-Hunter/branches/main` reports `protected=true`. Verify a contributor (including a repository admin) cannot directly push, force-push, delete or merge without review and CI. No production branch push required for this verification.
7. **Important:** This ruleset protects source changes but does not disable Render's auto-deployment from main and does not authorise future merges. A separate change-control decision and signed release plan are mandatory.

## Independent review remaining, not self-certifiable

- **DBA:** full exact trigger/fee and cost-floor/source graph, isolated PG16/17 independent reproduction and rollback with exact tested SHA/signature.
- **Security:** actual independently managed Supabase anon/auth/service_role API identities, RLS and SECURITY DEFINER end-to-end least-privilege review. Never paste real service_role credentials in GitHub or ChatGPT.
- **External provenance and delivery:** prospective independent provider quote source/time/raw-byte custody; durable alert provider ID and recipient acknowledgment, not app-only assertions.
- **Science/ops:** three first-entry ordering ambiguities remain unresolved; protect R8/R9/R10, locked paper positions, scanner cron and rollback. Signatures from named independent reviewers and final separate owner authorization.

**Release decision: PRODUCTION NO-GO.**
No GitHub ruleset was enabled by this document. No scanner, production database, position, deploy, branch main, R9/R10 or paid infrastructure changes authorised.
