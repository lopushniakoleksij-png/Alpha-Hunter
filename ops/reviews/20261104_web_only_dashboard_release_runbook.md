# ALPHA HUNTER — WEB-ONLY DASHBOARD REPAIR RELEASE RUNBOOK (2026-11-04)

**Purpose:** Restore mobile browser availability during invalid canonical source persistence, without altering the protected Render cron scanner, database, R10 or trading permissions.

## Release scope and tested evidence
- Change only the Flask web application and tests from [draft PR #410](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/410).
- Isolated HEAD at initial verification: `af9d84c81af277763f9be61c3c641d62f803f06c`.
- Full application suite: PASS (1,310 tests). Dashboard resilience: PASS (13 tests). Other 7 reported targeted/GitHub checks: PASS. Verify these **again on any later HEAD** before deploying.
- Last read-only production observation 20:15 UTC: 20:05 canonical scan declared 61 symbols with **zero** stored children and zero feature rows, following a complete 19:43 scan. This proves the data producer still needs a separate repair. No claims that this web patch restores scanner integrity or a profitable trade signal.

## Deployment constraints
- Existing web service: **Render Alpha-Hunter**, `srv-d9notmtaeets73cdrbc0`, URL `https://alpha-hunter-j5i3.onrender.com`; web `autoDeploy=no`.
- Protected canonical cron service: `crn-d9nmbjbm8hqs73elu6hg`; `autoDeploy=yes`; both currently track **main**.
- Source `main` **must not be merged or pushed** as a side effect, as that could redeploy the cron scanner. No new services, paid capacity, secrets or migrations.
- The connected Render action `trigger_deploy` deploys the web service's **configured branch** and does **not** accept an arbitrary commit SHA or branch. Calling it while web still tracks `main` would deploy the **old code**, not this fix.

## Owner-controlled web-only branch selection (requires current release authorization)
1. Open the **existing web service** dashboard only: `https://dashboard.render.com/web/srv-d9notmtaeets73cdrbc0`.
2. In **Settings → Build & Deploy**, edit **Branch** from `main` to `repair/web-only-canonical-integrity-availability-20261104`. Keep **Auto-Deploy OFF**. Confirm that the selected service type is **Web Service**, **not** the Cron Job.
3. Only after independently verifying the branch and latest passing CI, use Render **Manual Deploy** for that web service (or the connected web-only `trigger_deploy`). Do not change the cron job or its branch.
4. Monitor Render deploy/build logs. Verify live `/api/build` returns the exact repair commit short SHA.
5. In case of an incomplete latest canonical source, `/` should serve a clear non-trading status page (HTML 200, `X-Alpha-Hunter-Evidence-State: INCOMPLETE`); `/api/latest` must serve **503**, `error=canonical_scan_incomplete`, `signals_available=false`, `trade_permission=false`.
6. When a complete, verified latest canonical source arrives, `/api/latest` may return 200 as before, but never infer proof of profitability or trading readiness. `/api/public-market` is a separate public-quote reference feed only.
7. Check no cron deployment event, no new trading permission, no scanner change, no source hash drift, and no evidence history rewrite.

## Rollback if web smoke fails
1. Do **not** touch the cron job. Restore the web service branch to the previously verified `main` source or redeploy known-good web commit `b71c87d0b5963a5ca10c23d82b67a0edd47f120c` using a supported web-only rollback.
2. Verify `/api/build` matches the rolled-back commit and `/api/latest` fails closed on incomplete evidence.
3. Preserve error logs and page status for forensic analysis; do not cover up invalid signals by showing stale research scores as live.

**Decision:** Code quality CI passed. **Actual web deployment not performed** until correct web-only branch is selected and a controlled rollout is authorised; complete trading-signal integrity still depends on persistence repair handled separately by the automated engineering process.
