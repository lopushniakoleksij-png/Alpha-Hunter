# Alpha Hunter Phase 2 — Scientific Pilot V1.0 (BTC, ETH, SOL)

**Execution:** 14 November 2026, offline research adjudication based on READ-ONLY Supabase evidence and a bounded public Bitget historical candle retrieval. **Production unchanged; no orders; no broad backfill; no profitability certification.**

## Frozen pilot cohort and inputs
- Signal detection cohort **2026-11-08 00:00 UTC (inclusive)–2026-11-09 00:00 UTC (exclusive)**.
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT. Bitget USDT-FUTURES **market candles**, not mark or index prices; granularity 1H.
- Read-only SQL: `public.alpha_hunter_signals` filtered on `symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')` and `detected_at_utc` within cohort. The cohort contains 175 distinct signal rows (BTC 59, ETH 57, SOL 59); all 175 have `trade_permission=false`, and there are **zero authorized trades** in this sample.
- Directional: 47 (BTC 10 / ETH 20 / SOL 17), all SHORT; 43 complete positive, directionally coherent EP, SL, TP (BTC 9 / ETH 19 / SOL 15). Four directional rows lack stop and/or target. The other 128 are not directional setups. These are signal **instances**; many refer to repeatedly updated/overlapping levels.
- Source historical market candles read directly from Bitget `GET https://api.bitget.com/api/v2/mix/market/history-candles` with `productType=USDT-FUTURES&granularity=1H&startTime=1794096000000&endTime=1794268800000&limit=48`, per symbol. Source interval **Nov 8 00:00 to Nov 10 00:00 UTC**, 48 bars × 3 = 144 candles. Three responses code `00000`; 48/48 exact chronological hour opens, valid finite OHLC for each.
  - BTC requestTime 1794652927683
  - ETH requestTime 1794652927681
  - SOL requestTime 1794652927733
- Prior privately archived 24h samples (Nov 8) and 7d ETH/SOL were QA-validated in Codespace. **The additional Nov 9 raw 48h responses retrieved in this pilot were validated in-session but have NOT yet been deposited with immutable SHA-256 manifests in private QA**. The `phase2_scientific_pilot_replay.py` tool supports offline SHA-256 source validation once a private snapshot is available. Do not call this pilot fully reproducible until source bytes + filtered signal snapshot are privately archived and replayed.

## Outcome method — conservative hourly OHLC
1. For a signal detected at e.g. 02:04 UTC, begin only at the first *complete hourly bar starting after detection* (03:00 UTC). **Exclude the signal's unfinished 02:00–03:00 candle** so its full high/low cannot leak into an as-of judgment. Require 24 complete consecutive hourly candles (03:00 to next-day 03:00).
2. Validate direction, positive EP/SL/TP and geometry: for SHORT, `TP < EP < SL`. No null, NaN, wrong geometry or missing bars are counted as an outcome.
3. Entry screen: a later hour with `low <= EP <= high` is a *price-touch assumption*, **not a fill**; when no such hour occurs, label `NO_ENTRY`.
4. If an entry-touch hour also touches the stop or target, label `AMBIGUOUS`: the 1H bar does not reveal intrabar order. After an unambiguous entry-touch bar, the first future bar touching TP or SL gives `TP_FIRST` or `SL_FIRST`; both in one bar also `AMBIGUOUS`. No 24h touch -> `OPEN_AT_HORIZON`.
5. Separately, a *barrier-only* price-level diagnostic asks whether TP or SL was touched first from the first complete post-detection hour **without requiring entry**. Do **not** translate these auxiliary counts into wins, fills or profits.
6. Date-level 8 Nov instrument eligibility has NOT been scientifically certified; this is **market-evidence research-evaluable**, not historically trade-authorized. No future knowledge is used for signal selection.

## Observed 24-hour first-touch results
| Category | BTCUSDT | ETHUSDT | SOLUSDT | Total |
|---|---:|---:|---:|---:|
| All signal rows | 59 | 57 | 59 | **175** |
| Directional (all SHORT, blocked permission) | 10 | 20 | 17 | **47** |
| Complete EP/SL/TP | 9 | 19 | 15 | **43** |
| Barrier-only: TP level before SL (ignores entry) | 9 | 19 | 15 | **43** |
| Entry touched then later-hour TP, **hypothetical** | 6 | 11 | 12 | **29** |
| Entry/exit sequencing unknown within entry hour | 3 | 0 | 0 | **3** |
| No EP touch in eligible 24h hour sequence | 0 | 8 | 3 | **11** |
| Missing EP/SL/TP (directional) | 1 | 1 | 2 | **4** |
| SL after unambiguous entry | 0 | 0 | 0 | 0 |

**No outcome claims for the other 128 non-directional state records.** The barrier-only 43/43 TP-first observation is NOT a 100% hit rate for trades: 11 setups had no observed entry-touch; 3 were ambiguous, all were permission-blocked, and the 29 remaining instances do not prove execution.

## Dependence, quality and limits
- The 43 complete directional records occupy just **12 unique (symbol, stop_loss, take_profit) groups** (BTC 2, ETH 4, SOL 6). Repeated signal instances are **correlated**, not 43 independent trading opportunities.
- Of the 43 complete rows, **36 have nominal reward/risk below 1.0** (BTC 7/9, ETH 14/19, SOL 15/15). Observed median RR: BTC 0.769, ETH 0.503, SOL 0.261. This calculation comes from stored signal EP/SL/TP ratio field, not an independently filled trade. Signal score and confidence percentages are not calibrated empirical win probabilities.
- All 47 directional signals and all 175 records have `trade_permission=false`. Do not assume this field alone proves a specific strategy filter rejected the signal; it may also reflect paper-only system constraints.
- **Not measured**: time-priority execution, maker/taker fills, spread, liquidity/order-book depth, partial fills, commissions, funding, slippage, realistic simultaneous positions, risk limits, longitudinal out-of-sample performance, truly independent trade opportunities or reproducible net £1,000 returns.
- An hourly market candle's TP/SL touches cannot prove exact order execution, and the first post-detection hour method excludes potentially important earlier partial-hour movements.
- This is **one historical day**, one directional regime (all SHORT), and three selected symbols; it is not a forecast, trustworthy profit rate, statistically representative comparison, or authorization to weaken blocked-signal safeguards.

## Private QA capture and certification implementation (subsequent stage)
- `phase2_pilot_private_capture.py`: manually run, *only in existing private Codespace*, to re-fetch **exactly three** public V2 Bitget 48h market-candle responses and atomically create new raw-response files plus SHA-256 manifests in a new private directory. Public GET only; no trading, Supabase credentials or database writes.
- `PILOT_SIGNALS_READ_ONLY_EXPORT.sql`: fixed-cohort read-only query for all 175 stored signal records including `created_at`, EP/SL/TP and state. Private export must be performed using an authorized read-only connection. Do not commit private CSVs.
- `phase2_pilot_offline_certify.py`: accepts a newly captured 3-response raw archive and a user-supplied private CSV of the exact 175-row signal cohort. Verifies all SHA-256 fingerprints, exact symbol/product/horizon URL parameters, unique IDs, symbol counts BTC59/ETH57/SOL59, trade_permission=false, post-detection hour timing, and reconciles status totals. It writes a **private** certificate and per-signal findings only if all gates pass.
- `test_phase2_pilot_private_capture.py`, `test_phase2_pilot_offline_certify.py`: mocked offline QA covering valid scope, tampering, missing/duplicate records, and fail-closed certifications.
- **Status:** code committed and tested; live recapture and local 175-row cohort export into the existing private Codespace have **not** been performed through these scripts. This stage is ready for manual run in Codespace; do not mark the full private-data replay as PASS until actual evidence output is inspected.
- **Provenance distinction:** a newly captured raw 48h response will have a new exchange requestTime and SHA-256, even if candle OHLC matches the earlier pilot's in-session fetch. This is a *recapture*, not proof that identical original response bytes were preserved.

## Reproduction and next QA gate
- Code: `research/phase2/phase2_scientific_pilot_replay.py` (pure offline deterministic replay using `phase2_signal_investigator.py` and `phase2_bitget_response_verifier.py`).
- Tests: `research/phase2/test_phase2_scientific_pilot_replay.py` (source-boundary, no-permission and ambiguity checks).
- Archive exact 3 raw 48h Bitget responses and a read-only filtered 175-row Supabase signal snapshot **outside the repository, in the existing private QA environment**, with URI/response time/UTC window/hash and export time; then run the offline replay and reconcile the 29/3/11/4 counts.
- Next: assess same-hour outcomes using smaller trusted 1m bars where permitted, reduce correlated duplicate setups using a predeclared rule, review regime / filter provenance, and independently certify historical instrument availability.
- **Broad backfill and real trading remain NO-GO.** No PR merge, production write, scanner restarts or deployment.
