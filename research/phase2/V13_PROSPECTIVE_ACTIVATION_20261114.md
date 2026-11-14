# ALPHA HUNTER V1.3 — PROSPECTIVE OBSERVATION ACTIVATION RECORD

**Frozen study start:** 2026-11-15 00:00 UTC. **End:** 2026-12-15 00:00 UTC (30 complete calendar days). **Final 24h outcome maturation:** no sooner than 2026-12-16 00:00 UTC.

## State as of 14 November 2026 (PRE-OBSERVATION)

| Gate | Status | Supporting evidence |
|---|---|---|
| Protocol frozen before the prospective window | PASS | `V13_PROSPECTIVE_PROTOCOL_20261114.md`, source freeze commit `d1c1cca503a3eb68db9700a3d987bb8a52fbd185` |
| Read-only source/schema inspected | PASS | `alpha_hunter_signals`, `alpha_hunter_snapshots`, `alpha_hunter_symbol_snapshots` checked via authorised Supabase SELECT |
| Original scanner producing signal rows | PASS at inspection | Latest signal 2026-11-14 12:43:06Z; 1,786 total rows and 146 symbols for Nov14 as of inspection; may change; not all confirmed fully persisted |
| 30-day prospective source cohort | **NOT STARTED** | First eligible timestamp 2026-11-15 00:00 UTC |
| Hourly outcomes / fee sensitivity | **PENDING FUTURE OBSERVATIONS** | No V1.3 future outcomes known or scored |
| Actual live trading authorisation | **DISABLED / NO-GO** | No orders; paper/research only |
| Full historical-universe / profitability certification | **NO-GO** | Ongoing P0 write-integrity investigation; incomplete venue lineage; V1.3 three symbols cannot produce 100 independent opportunities alone |

## Source and selection controls

- **Only one existing scanner:** Alpha Hunter canonical persisted Bitget USDT-M scanner data. Do not run another exchange full-universe scanner, create Render jobs or change primary hourly tasks.
- **Three fixed symbols:** BTCUSDT/ETHUSDT/SOLUSDT. Forward-only first-as-of-complete candidate per symbol UTC day, 24h cross-day cooldown. Frozen market regime uses previous completed BTC daily close-to-close >+1% rising <-1% falling else sideways. Run a parent-child persistence and as-of content integrity audit before interpreting absence.
- **All existing filters unchanged:** `rr_minimum_met`, `participation_confirmed`, `momentum_confirmed`, etc. Separate PASS, FAIL, MISSING and account-level `trade_permission`; DO NOT treat `trade_permission=false` as a trading outcome.
- **After maturity only:** EP price touch followed by future 1H SL/TP, same-hour ambiguity UNKNOWN, missing/sparse OHLC UNKNOWN, no entry and open at horizon shown separately. Hypothetical 1,000 USDT/reference candidate; 0.06% taker fee per side plus adverse 0/5/10bp slippage; funding excluded until evidenced. Zero executed fills.
- **A new observation task does NOT scan the universe:** `Alpha Hunter V1.3 Evidence Watch`, automation ID `6af85a8f6024819195800a03265febb0`, finite daily 31 checks from **2026-11-16 02:00 Europe/London** to **2026-12-16**; each check reads the previous complete UTC day of signal evidence and assesses matured D−2 outcomes. Research issue #448 is the non-sensitive checkpoint log. Suppress raw private records in public GitHub.
- **End condition:** At least 30 covered UTC days for this stage; at most 90 symbol-day candidates before cooldown suppression. The independent >=100-opportunity criterion for stronger profitability science is **unattainable here**. This stage is descriptive research; require later preregistered expansion. Existing R10 frozen standard remains separate.

## No-change invariants

Do not merge PR #449, change production, scanner, protected P0 database repair PR #445, trading permissions, live orders, R8/R9/R10, privacy/security rules, infrastructure cost, or sealed V1.0/V1.1/V1.2 private evidence.

**Execution state:** protocol and evaluator operational; automated observation scheduled but **no prospective outcome sample has yet elapsed**. Any daily task failure or missing source must be marked `BLOCKED/UNKNOWN`, never inferred PASS.
