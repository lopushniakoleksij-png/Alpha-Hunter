# P2 successor isolation release gate — 2026-10-12

## Scope

**NEVER MERGE** the isolated P2 branch into auto-deploying main during active R10 paper testing. This *inert deployment proof* is intentionally **not** a strategy scanner, live Bitget collector, quote-history service, paper execution engine or real-order handler. It must never be counted as successful trading/monitoring. The only route is public GET /healthz, with explicitly FALSE scientific, source-authentication, paper and exchange flags.

## Production boundary verified in Render

| Runtime | ID | Actual deployment boundary |
|---|---|---|
| Primary hourly Render cron | crn-d9nmbjbm8hqs73elu6hg | branch **main**, autoDeploy **yes**, schedule **0 * * * *** |
| Existing web UI | srv-d9notmtaeets73cdrbc0 | branch **main**, autoDeploy **no** |
| Proposed successor inert web probe | new service | branch **p2-isolated-shadow-guard-20261012**, autoDeploy **no** |

**Required exact Render configuration for new isolated service:**
- repo: https://github.com/lopushniakoleksij-png/Alpha-Hunter
- branch: p2-isolated-shadow-guard-20261012
- autoDeploy: no
- runtime: python
- plan: free
- region: frankfurt
- buildCommand: python -m py_compile ops/reviews/p2_shadow_health_service_v01.py
- startCommand: python3 ops/reviews/p2_shadow_health_service_v01.py
- env: AH_P2_SHADOW_ISOLATION=ONLY_HEALTH_NO_TRADE
- env: AH_P2_SHADOW_PRODUCTION_ACCESS=DENIED
- Explicitly **NO** Supabase URL/role, Bitget API keys, shared service environment group, DATABASE_URL, scheduler settings, monitoring permission or order permission.
- This service may expose only /healthz, and must deny any mutating HTTP method. No public market/trade data or private customer data.

**Release gates and expected evidence:**
1. Tested branch + draft review PR exists, no main merge and no alteration of main scanner service configuration.
2. Unit CI passes, including forbidden secret env values, no app imports, deny trade routes, GET /healthz only.
3. New service created with the exact branch, no auto-deploy, free plan, no keys.
4. Health returns inert flags and false authority; record the exact service ID/branch/URL. Verify original cron ID, branch, last deployed SHA and configured 0 * * * * schedule remain unchanged.
5. NEXT research gate, not satisfied by this deployment: a separate trusted source collector and persistent key custody with real Bitget TLS quote captures, independently verified as-of fill-minus-exit all-cohort snapshots (including quarantined/unprotected residuals), and prospective per-order quote/stop observation within frozen 35m under failing Supabase/PostgREST. Any future web service code addition requires new review/approval, and must not silently inherit live credentials.

**Hard restrictions:** no DB schema mutation, no historical backfill, no R10 restart/reopen, no stopping Primary Hourly, no real exchange order authority, no scanner schedule change, no changing fixed 12s SQL/15s HTTP/35m monitoring limits, no payment beyond free plan.

The existing P2 research proof remains isolated and DRAFT in [PR #341](https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/341); the live incident remains [#340](https://github.com/lopushniakoleksij-png/Alpha-Hunter/issues/340).
