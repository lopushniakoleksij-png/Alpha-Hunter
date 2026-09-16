# Scientific Forward Holdout v0.1

## Decision

Start a prospective, capture-only matched-holdout clock from clean `main`.
Do not merge or depend on draft PR #18, quarantine the now-merged unsafe PR #19
recorder, and do not use the current scientific evaluator for a support claim.

The migration also closes a prerequisite evidence-integrity gap: inherited
`service_role` grants currently include `TRUNCATE`, `UPDATE`, and `DELETE` on
tables described as append-only. The ACL quarantine reduces the immutable
research ledgers to `SELECT` and disables PR #19's unsafe progression trigger
while preserving its empty live tables.

## Frozen hypothesis

`H_EARLY_OPERATIONAL_BUNDLE_DISCRIMINATION_12H_V1` asks whether the complete
contemporaneous direction-and-geometry qualification bundle discriminates
12-hour predictive returns among otherwise-safe EARLY candidates in the
absolute 0–5% move window. It does not identify a causal effect of geometry or
direction separately.

- TEST: scanner direction equals candidate direction; geometry is valid;
  `geometry_source=SCANNER_EXECUTION_SETUP`; direction binding is explicitly
  true.
- CONTROL_POOL: the same prospective, EARLY, lifecycle, source-version, safety,
  and non-promotion contract, with at least one direction/geometry qualification
  absent. Gap reasons remain separate; blanket `not eligible` is prohibited.
- EXCLUDED: every other post-registration source row, retained with an explicit
  reason for attrition accounting.

The FAIR-timing comparison is not preregistered because the current live FAIR
population has no candidates satisfying the common direction-and-geometry
contract. Capturing an empty control by design would not be a scientific test.

## Prospective boundary

The database creates `registered_at_utc` with `clock_timestamp()` during
migration. There is no historical `INSERT ... SELECT` and no backfill. A source
row is eligible only when both its candidate timestamp and database creation
timestamp are strictly later than registration.

`collection_ends_at_utc` is immutably fixed at registration plus 60 days. Rows
after that boundary remain visible only as `AFTER_COLLECTION_WINDOW`; they can
never enter TEST or CONTROL_POOL. If all gates are met earlier, the future pair
ledger must freeze at the first scheduled UTC-day close and use only bindings
available at that close.

Assignment is frozen in an append-only binding row using candidate-time fields
only. Outcomes are not read by the capture function. A 24-hour symbol/direction
cooldown prevents overlapping hourly observations from being counted as
independent candidates.

## Measurement contract (future work, not implemented here)

The primary endpoint is a pre-cost predictive market return, not an executable
or fill-conditioned return:

1. `decision_available_at_utc` is recorded by the database after the candidate
   row is inserted.
2. Reference price is the open of the first fully complete public Bitget 3-minute
   candle whose `open_time >= ceil_3m(decision_available_at_utc)`.
3. Endpoint price is the close of the last fully complete candle at or before
   decision time plus 12 hours.
4. The 24-hour endpoint is a separately reported secondary sensitivity horizon,
   not an independent replication.

Exact return equations are `100 × (endpoint_close/reference_open − 1)` for LONG
and `100 × (1 − endpoint_close/reference_open)` for SHORT.

`path_r_pre_cost`, `candidate_path_outcome`, and `realistic_net_r` are prohibited
for this experiment. The current scorecard path scan can observe a target or stop
before a passive entry would have filled.

## Frozen analysis gate

- 100 matched pairs minimum
- 30 symbols minimum
- 20 UTC days minimum
- 25 pairs per direction minimum
- 60 collection days maximum
- greedy 1:1 matching without replacement within source run, direction,
  lifecycle, bridge status, liquidity state, and candidate-quality status
- exclude missing liquidity, candidate quality, similarity, or feature coverage
  before the 24-hour cooldown can consume the symbol/direction slot
- similarity must be finite 0–100 and feature coverage finite 0–1
- standardized L1 distance: absolute-move difference divided by 5, plus absolute
  similarity difference divided by 100, plus absolute feature-coverage difference
- process TEST rows by decision timestamp then scorecard ID
- deterministic tie-break: control candidate timestamp, then scorecard ID
- pairs freeze once all gates are first met in a scheduled UTC-day close, or at
  day 60; pairing is completed before primary outcomes are read
- primary statistic: paired mean TEST-minus-CONTROL return, one-sided alpha 0.025
- support additionally requires effect at least +0.50 percentage points and the
  95% paired block-bootstrap confidence-interval lower bound above zero
- differential missing-outcome attrition above 10 percentage points, any mixed
  metric/source, or failure to meet gates by day 60 yields INCONCLUSIVE
- 24H is a secondary sensitivity horizon on the same cohort, not replication
- clustered paired label-swap randomization: cluster is UTC decision date plus
  source run; draw one sign per cluster, multiply every pair difference in that
  cluster by it, then compute the pair-weighted mean over all frozen pairs;
  observed statistic uses all +1 signs; 100,000 draws; seed 2026091602;
  one-sided p-value uses the +1 correction
- percentile paired cluster bootstrap: resample the observed count of UTC-day/run
  clusters with replacement, including all fixed pairs in each sampled cluster;
  pair-weighted mean; 100,000 draws; seed 2026091601; empirical 2.5%/97.5% bounds
- no peeking and no use of the existing unpaired evaluator

Unmatched rows remain visible. Any safety violation, source drift, capture error,
registration breach, or assignment leakage prevents a support claim.

## Claim ceiling and safety

The v0.1 status is always `COLLECTING - NOT YET EVALUABLE`. Even after the frozen
gate, a valid result may say only `SUPPORTED IN SHADOW - INDEPENDENT REPLICATION
REQUIRED`; it may not say READY, profitable, executable, or production-safe.

Every persistent row enforces:

- `shadow_only=true`
- `trade_permission=false`
- `production_promotion_permitted=false`
- `order_path=NONE`

This change adds no exchange client, authenticated endpoint, order method,
threshold activation, scheduler, or production promotion path.
