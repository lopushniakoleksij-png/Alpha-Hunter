# V1.2 OOS three-regime dates — SELECTED AND LOCKED BEFORE FUTURE-OUTCOME INSPECTION

Fixed prior protocol: `OOS_V12_PREDECLARED_PROTOCOL_20261114.md`, commit `944c347fc8403edb24c0c3cba40a46c22e962d84`.

A single bounded public BTCUSDT Bitget USDT-FUTURES **1Dutc** market candle request for Oct 18–Nov 6 UTC supplied **only prior completed daily close values**. No price outcomes for the three selected days had been examined before this date lock. Read-only existing database was queried only for daily symbol count/complete signal geometry and as-of timestamp availability, not any target/stop outcome. All three instruments had at least one complete as-of signal on each selected day.

| Regime | UTC date | Two days prior BTC close | Previous completed BTC daily close | Pre-day return (pct) | Pre-entry as-of complete candidates (BTC / ETH / SOL) |
|---|---|---:|---:|---:|---|
| SIDEWAYS | 2026-10-20 | 82066 | 81912.5 | -0.187045% | 19 / 18 / 10 |
| RISING | 2026-10-21 | 81912.5 | 82983.9 | 1.307981% | 4 / 2 / 2 |
| FALLING | 2026-10-23 | 84054.9 | 81384.1 | -3.177447% | 17 / 11 / 13 |

**Freeze:** SIDEWAYS **Oct 20**, RISING **Oct 21**, FALLING **Oct 23**, 2026 UTC. This is strictly the earliest date per qualifying prior-day regime within Oct 20–Nov 6, requiring a valid geometry and as-of candidate for each of BTC/ETH/SOL. Do not swap any date based on subsequent outcome, missing P&L, or observed profit. Each day stands as one highly correlated macro exposure episode. No pass-versus-fail comparison is permitted if the relevant filter has no PASS observations.

**Only after committing this file** may we fetch the original signal payload for these dates and 48h of BTC/ETH/SOL 1H price evidence per selected day.
