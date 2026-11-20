# Future successor liquidity-sizing prototype — review only

**Status: NOT ACTIVATED · NOT DEPLOYED · NOT ADMISSION-ENABLING**

## Evidence and defect

R10 historical entries were sized at fixed virtual risk but did not include a hard cap based on the exit side of the contemporaneous top-of-book quote:

- MAGMAUSDT LONG: entry 143 units, bid 46 / ask 848 units at entry; at the first 24h horizon attempt bid only 40, so a complete 143-unit SELL could not be modeled. A capped entry could still face lower later depth.
- SUPERUSDT SHORT: entry 892 units, bid 2157 / ask 266 at entry; at the earlier protective stop ask only 13, so full 892-unit BUY could not be modeled. Even a 266-unit entry-time cap **would not** have been executable as a whole at the later stop.

These are historic failures. **Do not backfill, revise, reclassify or count either trade as valid.** WLDUSDT/MEGAUSDT gap failures are a separate cadence issue, not a liquidity sizing issue.

## Shadow-only function

`alpha_hunter.successor_liquidity.assess_successor_liquidity(candidate, quote, policy)` provides a deterministic **hypothetical** pre-entry decision, not a submission or fill. Only future `PAPER_EXECUTION_*` cohort labels can be assessed; R9/R10 are rejected. No code imports it from `storage.py`, `run.py`, `hourly.py`, `paper_execution.py`, `paper_exit.py`, or `paper_horizon.py`.

1. Validate contemporaneous quote identity, side prices, positive sizes and bounded age, without later quotes or lookahead.
2. Compute risk-only size: `budget / abs(entry - stop)`, which must have valid LONG or SHORT geometry.
3. LONG entry consumes **ask**, but eventual SELL consumes **bid**; SHORT entry consumes **bid**, but eventual BUY consumes **ask**. Cap quantity to the **minimum** of risk-only quantity, entry-side size times explicit participation cap, and exit-side size times the same cap.
4. Quantize **down** by contract size multiplier. Never round up to hit minimum size or notional. Reject missing metadata, bad clocks, zero depth or out-of-policy requests.
5. Return `SHADOW_FEASIBLE_AT_ENTRY_SNAPSHOT_ONLY` or `BLOCKED`, with `paper_authority=false`, `trade_permission=false`, `exchange_authority=false`, `production_promotion_permitted=false`, `order_path=NONE`. Return **no order, fill, or write action**.

The parameters `maximum_book_participation` and `max_quote_age_seconds` have **no defaults** and MUST be independently preregistered and validated on forward/out-of-sample evidence. Test examples `1` / `0.25` participation and 30 seconds are not an adopted trading rule, optimized threshold or performance claim.

## Explicit limitations

* Top-of-book at entry is not future stop/horizon depth; sizes may shrink discontinuously (SUPER is real evidence). No one-shot best-quote model, partial exit, future order-book depth, venue fill, fill probability, or net expectancy is established. A suggested quantity is **never** an executable trade verdict.
* The quote-side constraint alone cannot repair the pre-existing four R10 irreversible integrity failures, including the two monitoring gaps.
* Even if a later partial execution model is developed, it needs separately preregistered remainder management, fee/slippage/depth assumptions, deterministic idempotency, and tests for full 24h evidence; it must never manufacture closes from absent depth.

## Release boundary (hard stop)

1. This PR remains **draft** and **unmerged/undeployed**. Any `alpha_hunter/*.py` addition changes the frozen scientific fingerprint, even if unimported. Do **not** deploy this file to the current R10 runtime; keep existing filled positions managed by existing frozen runtime.
2. Review the tests, synthetic and historical admission-time fixtures, and separately measure book-side feasibility on held-out **future** cohorts without altering R10 evidence. Freeze thresholds and deterministic exit handling **before** holdout.
3. Any future live execution requires a separate real-order authorization; this prototype does not enable one. No extra scanner or cron; P0 Alpha Hunter Primary Hourly continues.
4. A future successor needs explicit owner-reviewed activation, a new frozen fingerprint/approval for management of legacy positions, and an append-only audit ledger. Until then, `NO_NEW_PAPER_ADMISSIONS` in R10 remains enforced.
