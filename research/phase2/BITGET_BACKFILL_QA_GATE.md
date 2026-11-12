# Phase 2 — controlled Bitget historical QA backfill gate

Status: **plan and bounded external sample evidence only**. No backfill has been executed, no database writes authorised. Owner budget £0; paper/research only.

## Verified bounded external evidence (2026-11-12)
Official public Bitget V2 `/api/v2/mix/market/history-candles` with `productType=USDT-FUTURES`, `granularity=1H`:
- UTC Nov 8 00:00–Nov 9 00:00: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT: 24/24 each; valid ordered UTC hours and OHLC.
- UTC Nov 9 00:00 endpoint: BTCUSDT, ETHUSDT, SOLUSDT each passed 48/48, 72/72 and 168/168 hour windows; 7d split into two 84-hour requests.
- 8/8 BTCUSDT Nov 8 16:00–23:00 source OHLC values exactly matched existing Supabase audit-only shadow candles.
- 984 checked observations in total, **overlapping**, not unique observations. This does not establish full-universe completeness.
- Previous 7–8 Nov shadow sample: 198 duplicate symbol-hour groups, all identical OHLC, 356 extra rows. These are episode-specific records, not whole-market candles.

## Request manifest specification
For each bounded request retain: exact URL and query parameters, UTC requested start/end (end-exclusive), symbol, product type, candle type (market), granularity, source response code/requestTime, fetch UTC, response byte SHA-256, returned row count, ordered first/last candle timestamps, continuity/OHLC status, source endpoint/version, instrument-catalogue status, request batch ID, QA dataset version and immutable raw payload location. **Do not commit raw proprietary payloads or secrets to public GitHub.** No API credentials or order endpoints.

## QA-only execution acceptance
1. Obtain documented public data-use/retention approval and current futures instrument catalogue; do not assume availability of delisted instruments.
2. Isolated local QA file store or existing approved private PostgreSQL QA only. No Supabase production writes, migrations or triggers.
3. Execute only pre-approved bounded symbol/window manifests; enforce rate limiting, retries with backoff, request ceilings, stop on errors. No duplicate full-universe scanner.
4. Require exact timestamp continuity and source-proven closed candles; keep missing, stale and conflicted periods UNKNOWN.
5. Reconcile identical duplicate OHLC while retaining every original source ID/episode ID; quarantine conflicts.
6. Independently compare a sample to existing historical audit candles, report discrepancies and source provenance.
7. Freeze cohort/threshold definitions before mover rankings and as-of signal joins; separate retrospective results from frozen R10 paper science.
8. Independent DBA/security/scientific approval before broader historical backfill or release.

## Current blockers
- Full-universe historical availability and delisting coverage unverified.
- Public API usage/retention terms and instrument catalogue not yet signed off.
- Isolated QA backfill storage and end-to-end source manifest execution not yet certified.
- The Python request planner only **generates URLs**; it does not fetch, trade, persist, or deploy.
