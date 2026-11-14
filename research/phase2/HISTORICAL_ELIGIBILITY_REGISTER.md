# Alpha Hunter Phase 2 — historical USDT-futures eligibility register v0.1

**Research-only, 14 November 2026. Production and full-universe backfill: NO-GO.**

## Scope
- Target: **2026-11-08 00:00 UTC inclusive to 2026-11-09 00:00 UTC exclusive**.
- Product: Bitget **USDT-FUTURES** perpetual contracts only (no spot, USDC, coin-margined, mark/index interchange).
- File: `HISTORICAL_ELIGIBILITY_20261108.csv`.
- Initial source: Bitget public GET `/api/v2/mix/market/contracts?productType=USDT-FUTURES` snapshot, response `requestTime=1794628383976`, **885** unique currently normal symbols.
- Also includes 8 independently documented pre-window futures delistings absent from current catalogue, plus FCHUSDT which was previously inspected and is absent now. **894 total symbol rows.**
- **Not** a complete historical universe. Other delisted and re-listed instruments may be missing. The catalogue response has not been preserved in this repository as immutable raw API bytes.

## Classification: separate facts, never conflate them
1. `listing_event_evidence=VERIFIED`: official *dated* Bitget listing announcement is identifiable. This proves a **listing announcement event only**, not uninterrupted eligibility on Nov 8.
2. `window_eligibility=UNKNOWN`: insufficient independent historical evidence of actual tradeability throughout the requested window. Includes today's normal contracts, contracts with historical candles, stale/blank time fields and FCHUSDT.
3. `window_eligibility=EXCLUDED`: official **futures** delisting with stated effective UTC time before target, and the symbol is absent from current catalogue. A verified re-listing or contradictory evidence forces manual reconsideration. This excludes the contract from this proposed **Nov 8 trading universe**, not from all historical dates.
4. `window_eligibility=VERIFIED`: reserved for independently corroborated tradability for the exact target window, including suspension/relisting review and sign-off. **No rows qualify currently.** This class cannot be assigned automatically by the offline validator.

All rows: `backfill_allowed=NO`. Unknown is **not** counted as inactive or a losing signal. Futures prices/candles are not proof of order permission, fees, market depth or fills.

## Important official API documentation correction
Bitget's futures API contract endpoint documents:
- `launchTime` = listing time, but returned empty for representative BTCUSDT/ETHUSDT/SOLUSDT.
- `openTime` = **deprecated**. Its earlier 764/1/120 division MUST NOT be used to infer Nov 8 instrument eligibility.
- `symbolStatus=normal` is a *current* property, not a dated historical state.

Docs: https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market

## First dated exchange evidence
- **DASHUSDT** listing announcement Nov 4, 2025 (UTC+8): https://www.bitget.com/support/articles/12560603841543 — dated **listing event VERIFIED**, Nov 8 target **UNKNOWN**. A separate 2021 DASHUSDT futures launch article demonstrates that one announcement does not prove uninterrupted listing history: https://www.bitget.com/support/articles/4410379824665
- **WBDUSDT** futures termination effective **Oct 7, 2026 13:30 UTC**: https://www.bitget.com/support/articles/12560603896801
- **EPICUSDT** futures termination effective **Oct 20, 2026 07:00 UTC**: https://www.bitget.com/support/articles/12560603897724
- **AINUSDT, RCATUSDT** futures termination effective **Sep 22, 2026 07:00 UTC**: https://www.bitget.com/support/articles/12560603895497
- **STGUSDT** futures termination effective **Sep 28, 2026 07:00 UTC**: https://www.bitget.com/support/articles/12560603895978
- **4USDT, GOATUSDT, ESPORTSUSDT** futures termination effective **Sep 8, 2026 07:00 UTC**: https://www.bitget.com/support/articles/12560603894224

All eight excluded contracts were absent from the current 885-symbol catalogue at the time of this snapshot. These exclusion decisions would need reversal if new authenticated relisting evidence is discovered.

## Earlier bounded historical market-data findings
BTC, ETH, XRP, BCH, LTC and DASH Nov 8 official API 24/24 hourly candle checks passed; SOL also passed private Codespace historical capture. This supports **market data availability only**. FCHUSDT returned HTTP 400 in public fetch and is not currently listed; its prior historical eligibility is UNKNOWN. Do not equate HTTP 400 or missing candles with historical nonexistence.

## Acceptance gates still open
- Search official dated listings, delistings, suspension/maintenance and relistings across the target window, including contracts absent today.
- Preserve source snapshots/hashes in an approved private QA location; record source publication times and audit limitations.
- Independently verify trading-permission intervals and catalogue history. Avoid survivorship bias.
- Confirm historical data licensing/retention and rate limits for any wider activity.
- Independent scientific, DBA and security review for any promotion.
- No merge, production write, real orders, duplicate scanner, new infrastructure or spend.

Run offline structural gate:
`python research/phase2/phase2_eligibility_gate.py`
