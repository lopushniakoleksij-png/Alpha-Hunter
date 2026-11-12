# Phase 2 — Bitget USDT-M Big Movers Intelligence V1.0

Status: **research specification only**, not active collection. Tracks #448. No production changes.

## Mission
Observe the real Bitget USDT-M perpetual futures universe over rolling 24h, 48h, 72h and 7d windows. Identify the biggest positive and negative price movers independently of Alpha Hunter's existing signal selection. Compare them to *as-of-time* Alpha Hunter signals and blocks, so we can measure early detection, late detection, missed opportunities and false positives without hindsight leakage.

## Inputs and custody
- Prefer the existing canonical Bitget universe scan and versioned immutable snapshots; do not launch a duplicate full-universe scanner.
- Source must be the real Bitget USDT-M perpetual market, not spot, simulations, or synthetic OHLC. Capture endpoint, instrument identifier, quote currency, product type, source timestamp, observed_at_utc, window boundaries, capture latency and payload hash.
- Check market-data source permissions, freshness, rate limits, retention, gaps and completeness before enabling observation.
- Do not infer missing 24h+ history from a single current ticker. Preserve unavailable data as UNKNOWN.
- Use only closed, source-proven candles for historical price adjudication; 1H OHLC cannot prove ordering within the same hour.

## Versioned cohort and windows
- Rolling 24h, 48h, 72h and 168h, with UTC start/end.
- Rank by signed close-to-close percentage return with a predeclared, versioned top-N rule for gainers and losers; also record absolute return, notional turnover, liquidity and volatility.
- Universe eligibility and thresholds must be established as-of observation time. Preserve instrument additions, delistings, stale and excluded symbols, avoiding survivor bias.
- Store each window's full eligible denominator, ranked cohort and source snapshot ID. Never change selection retrospectively to improve apparent performance.

## Evidence fields
Instrument, window, observed_at, source, reference/open/close/high/low, signed return, volume/turnover, spread/depth, funding, open interest, BTC regime, session, strategy, first signal timestamp, signal state, direction, block reason, EP/SL/TP, hypothetical outcome, ambiguity flag, evidence provenance and missingness codes. Optional fields are NULL rather than invented.

## Attribution
- Join by canonical instrument and timestamps: use only signals known at or before a mover observation cutoff.
- Separate EARLY, LATE, BLOCKED, MISSED, and UNKNOWN using frozen lead-time definitions. Do not label MISSED if scanner completeness, universe membership or source coverage cannot be verified.
- Watch/neutral states count as observations, not executable trade setups. For trade-like outcomes, require validated EP/SL/TP and source evidence.
- Explicitly distinguish retrospective market moves from prospectively observable opportunities; no R10 science, frozen admissions or win-rate updates.

## QA acceptance
1. Reproducible rankings for both sides and each horizon; deterministic tie rules.
2. Test missing/stale source data, symbol aliases, delisted symbols, partial universe, duplicate candles, out-of-order timestamps, gaps, future leakage, daylight-saving boundaries and insufficient liquidity.
3. Match sample cohorts to persisted Alpha Hunter signals and document join coverage, missing features and scan completeness.
4. Compare early/late/blocked/missed cohorts with denominators, costs and uncertainty; do not claim tradable profit from raw return.
5. Build isolated QA-only append-only evidence and test before any release proposal.

## Safety
Read-only research. £0 spend. No new trading authority, no Bitget order API, no canonical scanner duplication, no production migration, no PR merge or deployment without independent approval.
