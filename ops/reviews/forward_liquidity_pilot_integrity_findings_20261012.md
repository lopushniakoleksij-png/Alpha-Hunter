# P3 — 24-hour exit-liquidity pilot integrity audit (2026-10-12)

**REVIEW-ONLY / DRAFT / NO R10 MERGE / NO TRADING AUTHORITY.**

This report diagnoses the **already-mature** preregistered pilot of 2026-10-08 12:00 UTC through 2026-10-09 12:00 UTC. This post-hoc diagnostic does not change its preregistered criteria, the immutable R10 history, scientific identity, or original failed outcome. Evidence is from SELECT-only queries on Supabase, verified on 2026-10-12.

## Independent measured facts

- 72 canonical frozen-fingerprint scanner snapshots; 70 canonical run IDs had valid observed exit-attempt quotes from legacy monitored paper positions.
- 908 individual exit-attempt rows collapse to 418 independent **(symbol, direction, canonical source-run)** quote observations, on 11 symbol+direction series.
- 140 quote/run groups contain duplicate order-level attempts; none of these groups showed conflicting bid/ask/size evidence or mixed source labels in this window. Never treat orders repeating the same quote as independent market observations.
- 109 of 418 independent quotes have **no explicit source provenance label**; leave them unlabelled, rather than inferring the source from the canonical scanner join. QUSDT LONG generated 490 attempts yet just 70 independent quotes, all 70 missing source labels.
- **0 of 11** have a complete 24h series according to the original duration/boundary/gap specification. **6** have a per-symbol quote gap longer than **35 minutes** (worst ~38m58–38m59). **6** are missing the window's end boundary. These groups overlap: EVAAUSDT LONG has both. **8** have at least one quote without a source label.
- No quote-group book conflicts, invalid top-book pairs, or mixed source labels were observed in the selected historical sample, but this is **not** permission to loosen integrity checks.
- R10 MAGMA and SUPER size failures and WLD/MEGA horizon failures remain **frozen invalid**. Global scanner continuity can be healthy while instrument-specific monitoring samples are incomplete.

Reproducible read-only per-symbol inspection:
`ops/reviews/future_exit_liquidity_pilot_diagnostics_20261012_readonly_v01.sql`.
Keep original `ops/reviews/future_exit_liquidity_24h_readonly_v01.sql` unchanged. This diagnostic is not a second, favorable holdout. A right-censored series is **not** a stable-depth series. The quote-size data do not prove multilevel fill capacity, slippage, queue priority or stop-time liquidity.

## Next successor-only telemetry architecture — not implemented in frozen R10

1. For each managed **paper** symbol/direction on every canonical scan, collect a distinct verified quote or record an explicit `QUOTE_MISSING`/capture failure, with source_run_id and UTC evidence. Scanner heartbeat is not a substitute for per-symbol observation.
2. Write **source identity** (actual captured public endpoint), capture time, optional venue timestamp, symbol, bid/ask price and sizes, quote freshness and error reason. Never synthesize missing time, quote or source tags. Reject future-dated, stale or recycled snapshots in a separately preregistered successor protocol.
3. Aggregate by symbol+direction+canonical run, retaining the original entry-order IDs only for exposure accounting. If the same run has conflicting best quotes, mark `QUOTE_CONFLICT`, not a hand-picked favorable sample.
4. Distinguish an actually ended monitored position, a missing quote, a missing scanner scan and a terminated follow-up. Right-censor actual exits. Do not stitch the last known quote across missing periods or invent additional 24h survivors.
5. Before any future admission or position-sizing threshold, preregister the measurement window, multiple independent UTC-day clusters, sample sufficiency, book participation and cost/slippage/funding assumptions. For eventual full exit capacity, a top-of-book-only quote is insufficient: inspect liquidity at relevant depth, model partial fills and reduce-only residual management, and prove fail-closed behavior.
6. Require separately reviewed permissions, immutable successor fingerprint and legacy-position protection continuity. Do not import research modules into current scanner or merge this PR while R10 protects existing positions.

## Review gates

- **P3 diagnosis:** completed, reproduced from live read-only data.
- **Telemetry repair:** OPEN, not deployed; original collection has known gaps and unlabeled source evidence.
- **Prospective 24h science:** NOT VALIDATED; 0 qualified pilot series.
- **Profitability gate:** BLOCKED by scientific sample and validated execution cost evidence.
- **R10:** admission HALTED; Primary Hourly and current legacy position management unchanged.

See draft PR #335 and frozen failures in issue #334. No restart, backfill, order permission, data mutation or new cron is implied or authorized.
