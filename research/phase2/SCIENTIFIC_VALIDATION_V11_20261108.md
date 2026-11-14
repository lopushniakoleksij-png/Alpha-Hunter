# Alpha Hunter — Phase 2 Scientific Validation V1.1

**Research date:** 14 November 2026. **Cohort:** 8 November 2026 00:00–9 November 2026 00:00 UTC, three USDT-M perpetual futures contracts (BTCUSDT / ETHUSDT / SOLUSDT). **Status:** live read-only research calculation performed; the separate V1.1 private replay against the immutable Codespace archive remains an additional acceptance gate. No DB writes, trading, deployment, broad backfill, modified certificates or raw evidence.

## Evidence and integrity boundary

1. **Exact inputs.** The existing private QA V1.0 recapture contains three SHA-256-verified, 48-hour public Bitget `USDT-FUTURES` **market-price** 1H candle responses (144 hours collectively); a private CSV of 175 historical Supabase `alpha_hunter_signals` records (BTC 59, ETH 57, SOL 59); and a certificate `REPLAY_MATCH_PRELIMINARY_COUNTS` reporting TP_FIRST 29, AMBIGUOUS 3, NO_ENTRY 11, NOT_EVALUABLE 132. Evidence remains unchanged in the existing private Codespace. The user screenshot attests to the previous private replay, but its original bytes have not been uploaded to this report.
2. **V1.1 analysis:** additional **read-only** Supabase queries examined source payload `trade_permission_reason`, `execution_setup.checks`, and `decision_trace.blocking_gate`; a bounded three-symbol public candle GET rechecked the selected candidate outcomes. No raw, identifying or private signal rows are committed into the repo.
3. **No hindsight in selection calculation:** first complete as-of directional setup for **each symbol**, ordered by signal timestamp and immutable ID. No target/stop/outcome is consulted to choose the record. Once selected, all later records from the symbol within the frozen UTC day are suppressed; no pyramiding or reopening. This was **designed retrospectively after V1.0 results had been inspected**, so it is NOT prospectively preregistered evidence. Use it as the frozen rule on a separate future test period.
4. **Economic and statistical independence are distinct.** This rule collapses 43 complete directional *instances* (12 distinct stop/target groups) to **3 symbol-level candidate opportunities** (40 suppressed repeats). All three have the **same timestamp 02:04:51 UTC** and arise in a single correlated crypto-market episode; they are **not 3 independent macro observations**.

## Observed rejection reasons (read-only Supabase evidence)

Frozen population: **175** records; all `trade_permission=false`. Of these, **128 lack a direction**, and their stored reason is `Direction is not fully aligned across 15m, 1H and 4H`. Only the 47 directional SHORT records are considered hypothetical directional setups.

| Execution check failed, 47 directional SHORT records | Count | Notes |
|---|---:|---|
| `rr_minimum_met` | **47/47** | Each below its configured signal gate; no permission override |
| `participation_confirmed` | **39/47** | Can overlap with momentum/R:R |
| `momentum_confirmed` | **19/47** | Can overlap with participation/R:R |
| `direction_aligned` | 0/47 | This particular check passed for the directed group |
| `structure_valid` | 0/47 | This particular check passed |
| `funding_not_extreme` | 0/47 | This particular check passed |
| `data_integrity_min_88` | 0/47 | This particular check passed |

Exact stored `trade_permission_reason` frequency among 47 directed records: **25** failed participation+R:R; **14** failed momentum+participation+R:R; **5** failed momentum+R:R; **3** failed R:R only. `decision_trace.blocking_gate`: **37** `DISCOVERY_SCORE`, **10** `DIRECTION_PROOF`. Those stages describe separate discovery/decision gates; the execution checks are the direct reasons stored for the proposed setup. **A later market target touch does not prove the original gate was incorrect.** Historical observations alone cannot isolate the causal benefit of removing any filter.

All three retrospectively selected candidates have `rr_minimum_met=false` and `participation_confirmed=false`; BTC and ETH also have `momentum_confirmed=false`. Their `trade_permission` was explicitly false. **No blocked-signal trading permission is changed.**

## Independent candidate results, frozen first-hour timing

Every selected row was detected at **2026-11-08 02:04:51.975942 UTC**. The post-detection 24-hour evaluation begins at the next full 1H market candle, 03:00 UTC. Market OHLC is not an executable fill. If an entry and exit share one hour, classify `AMBIGUOUS`; price-touch/fee model does not turn touches into fills.

| Symbol | Entry | Stop | Target | Nominal reward/risk | First observed entry-touch hour UTC | First later target-touch hour UTC | 24h status |
|---|---:|---:|---:|---:|---|---|---|
| BTCUSDT SHORT | 75693.4 | 76344.1 | 74800 | 1.373 | 2026-11-08 17:00 | 2026-11-08 21:00 | TP_FIRST |
| ETHUSDT SHORT | 2232.27 | 2253.28 | 2208.22 | 1.145 | 2026-11-08 06:00 | 2026-11-08 21:00 | TP_FIRST |
| SOLUSDT SHORT | 88.991 | 91.55 | 88.657 | 0.131 | 2026-11-08 04:00 | 2026-11-08 21:00 | TP_FIRST |

**Three counterfactual target-touch episodes, zero verified fills or executions.** All three belong to a common one-day SHORT price regime. Do not claim 3/3 as an empirical win rate.

## Transaction cost sensitivity — model, not realized P&L

**Public exchange assumption:** Bitget's standard USDT-perpetual **taker fee 0.06% each side**, maker fee 0.02% each side (not assumed). Sources:
- https://www.bitget.com/asia/support/articles/12560603892733 (published Aug 20, 2026)
- https://www.bitget.com/support/articles/12560603828198 (USDT-M perpetual futures fee and funding explanation)
- Current V3 public `/api/v3/market/instruments?category=USDT-FUTURES` independently reports BTCUSDT `takerFeeRate=0.0006`, `makerFeeRate=0.0002` (live value, not guaranteed historical account tier).

**Execution assumptions:** SHORT quantity = 1000 USDT reference notional / recorded entry; adverse fill at entry `entry × (1 - slippage)`, exit at target `target × (1 + slippage)`. Fees apply to each adverse executed notional; fundings are excluded from primary results. No leverage, reinvestment, tax, order depth or FX conversion.

| Hypothetical, per 1,000 USDT position | 0 bp slippage each side | 5 bp each side (baseline) | 10 bp each side |
|---|---:|---:|---:|
| BTC SHORT | +10.61 USDT | **+9.62 USDT** | +8.62 USDT |
| ETH SHORT | +9.58 USDT | **+8.59 USDT** | +7.59 USDT |
| SOL SHORT | +2.56 USDT | **+1.56 USDT** | +0.56 USDT |
| **Sum of three hypothetical positions** | +22.75 USDT | **+19.76 USDT** | +16.77 USDT |

**This sum is not verified portfolio net profit or a return on a real account.** It is a scenario conditioned on three hypothetical EP and TP fills. Positions may overlap and share systematic risk; the market could fail to provide those prices at adequate order depth. Fee tier, historical order type, actual entry/exit spread/slippage and mark/index triggers are not independently certified.

### Funding sensitivity from bounded historical Bitget public data

Read-only `GET https://api.bitget.com/api/v3/market/history-fund-rate?category=USDT-FUTURES&symbol=...&limit=100&cursor=1` for these three symbols returned dated records for **8 November 2026**:
- BTC: 08:00 +0.000070, 16:00 +0.000025; the selected model's 17:00–21:00 BTC interval spans neither.
- ETH: 08:00 +0.000088, 16:00 +0.000067. A short held through both would **receive** approximate +0.0155% of mark notional, ~**+0.155 USDT** for 1000 notional.
- SOL: 08:00 +0.000100, 16:00 +0.000100. A short held through both would **receive** approximate +0.0200%, ~**+0.200 USDT** for 1000 notional.

The 1H entry/target touch periods (ETH 06:00 and 21:00, SOL 04:00 and 21:00) straddle those settlements, but **fill timing and position persistence remain hypothetical**, and the exact historical mark notional is not established by market OHLC. The approximate combined funding sensitivity is **+0.355 USDT**, not included in the baseline net model. The funding responses have not yet been privately archived and hash certified. Official API docs: https://www.bitget.com/docs/catalog/market/derivatives

## Interpretation and scientific gates

- Filtering **prevented trade authorization** as intended by the recorded checks; later favourable movement is a useful filter-analysis hypothesis, not justification to disable gates.
- The most concerning structural issue is **weak R:R**: among 43 complete signal instances, 36 have nominal R:R < 1, and the first SOL candidate offers only 0.131 nominal R:R. Low R:R means a target-touch-heavy cohort can still have poor expectancy over multiple markets and losing periods.
- The 24-hour OHLC procedure, frozen episode choice, fee/slippage scenarios and historical funding observations are explainable, but they do not settle signal as-of feature provenance, spread, quote executable depth, nonfilled orders, independent exposure, fees actually paid, or reliable long-run profitability.
- **No sample win rate, calibrated confidence, Sharpe ratio or £1,000 profit projection is certified from this one-day single-regime cohort.**
- **Private evidence protection:** original `pilot-48h-20261108-recapture/`, `pilot_signals_20261108_verified.csv`, and `pilot-certificate-20261108/` are **read-only inputs**. New script `phase2_scientific_v11.py` checks source SHA-256 and the original certificate, then writes only to a **new** separate private directory; it refuses overwrites. These original bytes have not been read from this chat's runtime, so a **separate private V1.1 replay remains pending** after this code review.
- **Next acceptance:** execute that offline V1.1 replay against the original sealed evidence; verify expected 3 selected signals and reported cost scenarios; pre-register selection for new dates; review true filter counterfactuals without relaxing production safeguards; obtain historic instrument-universe and exchange-execution evidence before expanding.
- **No PR merge, production scanner/data changes, new trade permissions, live trading, spending or broad backfill.**
