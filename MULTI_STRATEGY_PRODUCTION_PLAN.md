# Alpha Hunter — Multi-Strategy Production Architecture Plan v0.1

## Mission

Move Alpha Hunter from one generic execution geometry to a strategy-portfolio architecture in which every canonical Bitget USDT-M scan evaluates the full S1-S10 set, LONG and SHORT symmetrically, while preserving the existing fail-closed execution contract.

The architecture must answer:

1. Which strategy sees an opportunity?
2. Which side does it see?
3. What evidence produced the signal?
4. What entry, stop/invalidation and target belong to that strategy?
5. What is the remaining R:R?
6. Which data, liquidity, participation and regime gates pass or fail?
7. What is the best shadow candidate across all symbols and strategies?
8. Has that strategy earned production permission from forward evidence?

## Non-negotiable safety contract

- The multi-strategy engine starts 'shadow_only=true'.
- It cannot set or mutate legacy 'trade_permission'.
- It cannot set or mutate 'v7_trade_ready'.
- It cannot submit, simulate-as-live, or route an exchange order.
- Existing minimum execution R:R remains 5.0R.
- Missing strategy-specific evidence fails closed as 'DATA_INSUFFICIENT'.
- No strategy may manufacture a target when no defensible structural target exists.
- Existing canonical universe and canonical market scan remain the source of truth.
- No second exchange-universe scanner is introduced.

## Strategy portfolio

| ID | Strategy | Initial evidence path |
| --- | --- | --- |
| S1 | Early Momentum / Expansion | phase + timing + trend + MACD + participation |
| S2 | Breakout + Retest | breakout/breakdown trigger + ATR invalidation + structural target |
| S3 | Trend Pullback | 1H/4H trend + EMA21 pullback + structural invalidation |
| S4 | Relative Strength / Weakness | relative strength vs BTC + acceleration + trend |
| S5 | Volatility Compression | compression + direction + participation-confirmed trigger |
| S6 | Liquidity Sweep / Reclaim | current 1H candle + previous canonical support/resistance + participation |
| S7 | Acceptance / Absorption | fail closed until order-book/trade-flow absorption evidence is canonical |
| S8 | Mean-Reversion Edge | Bollinger + RSI + StochRSI + higher-timeframe countertrend guard |
| S9 | Catalyst / News Momentum | fail closed until validated timestamped catalyst evidence is bound to scan |
| S10 | Risk-Regime / Beta | BTC regime + relative-strength proxy + symbol trend; no calibrated beta claim |

## Production phases

### P0 — Architecture + safety boundary

Deliver:
- versioned 'multi_strategy_engine'
- ten deterministic strategy evaluators
- explicit 'SHADOW_CANDIDATE / WATCH / NO_SETUP / DATA_INSUFFICIENT'
- explicit 'EXECUTE_NOW / PLACE_LIMIT / WAIT_FOR_TRIGGER / NO_SAFE_TRADE'
- strategy-specific entry/stop/target/R:R where defensible
- invariant 'trade_permission=false' inside the engine
- focused CI

Exit gate:
- exactly ten evaluations per scanned symbol
- zero mutation of legacy execution permission
- all tests green

### P1 — Canonical persistence

Deliver:
- strategy matrix persisted in every immutable scanner snapshot
- snapshot-level strategy coverage summary
- strategy ID, version, evidence, geometry and fail reasons persisted
- previous canonical snapshot used only where strategy design requires it

Exit gate:
- every production scan proves S1-S10 coverage
- missing evidence is distinguishable from no signal

### P2 — Dashboard visibility

Deliver:
- phone-first S1-S10 shadow matrix
- top shadow candidates separated from the live Money Action block
- clear 'SHADOW — NOT TRADE PERMISSION' label
- per-strategy side, action, score, entry, stop, target, R:R and reason

Exit gate:
- user can see whether HYPEUSDT, for example, is being evaluated by all ten strategies rather than only the retest path

### P3 — Missing-data production capture

Add canonical evidence streams for strategies that currently fail closed:
- S7: order-book/trade-flow acceptance/absorption evidence
- S9: validated timestamped catalyst/news evidence
- improved S2 short breakdown trigger
- persistent strategy-signal lifecycle across scans

Exit gate:
- no strategy relies on an unverifiable proxy for production promotion

### P4 — Forward science ledger

For every strategy episode persist:
- signal timestamp
- first objectively identifiable entry
- action state
- entry/stop/targets
- MAE/MFE
- confirmation tax
- remaining-R
- time-to-trigger
- outcome at fixed horizons
- execution-cost-adjusted outcome
- found/traded/missed state

Controls:
- preregister strategy/version before evidence collection
- no in-sample threshold tuning after outcomes are known
- compare with strategy-appropriate controls
- preserve losing and missed episodes

### P5 — Strategy ranking

Rank surviving shadow candidates by:
- strategy evidence quality
- liquidity/spread
- participation
- direction/regime compatibility
- R:R and remaining-R
- entry distance / chase risk
- lifecycle freshness
- historical forward evidence for that exact strategy version

Output:
- MOST TRADABLE SHADOW CANDIDATE
- BEST LIMIT SHADOW CANDIDATE
- strategy-specific reasons and cancel conditions

No production permission is granted at this phase.

### P6 — One-strategy-at-a-time promotion review

A strategy can move from shadow to production review only after:
- sufficient prospective sample
- reproducible positive economic effect net of costs
- no unresolved data-integrity defect
- no look-ahead leakage
- stable performance across relevant regimes
- explicit engineering + scientific review

Promotion is strategy-version-specific. Promotion of S3 does not promote S1-S10.

### P7 — Execution integration

Only after a strategy passes P6:
- bind its strategy contract to the existing execution authorization gates
- preserve portfolio/account/open-position/cost/freshness controls
- keep LIVE exchange routing separately disabled until its own review

## Current implementation boundary

v0.1 intentionally starts with canonical scanner evidence already available on main.

S7 and S9 fail closed when their required evidence is absent. This is deliberate: Alpha Hunter must record that it cannot know something rather than convert missing data into a false signal.

The existing Money Action / V7 execution path remains unchanged until forward evidence justifies a separate promotion decision.


## P3 execution increment — v0.1 microstructure + persistence

Implemented as the next production-development increment:

- read-only Bitget futures merge-depth capture
- read-only Bitget recent public transaction capture
- compact canonical order-book depth imbalance
- compact canonical recent-trade notional imbalance
- source timestamp/skew evidence
- snapshot-level microstructure coverage accounting
- S7 acceptance evidence path using previous canonical levels + price acceptance + order-book/trade-flow alignment
- S7 explicitly records `absorption_confirmed=false`; snapshot evidence is not mislabeled as true absorption
- persistent per-strategy signal lifecycle across canonical scans:
  - NEW
  - CONTINUING
  - CHANGED
  - INACTIVE
  - first seen
  - consecutive scans
  - prior status/action/direction/score/R:R
  - deterministic strategy instance ID
- dashboard microstructure coverage + persistence visibility

Still required before P3 is complete:

- higher-frequency evidence if true absorption is to be claimed
- validated timestamped catalyst/news evidence binding for S9
- forward outcome ledger for strategy instances


## P3 execution increment — v0.1 official catalyst evidence

Implemented:

- read-only official Bitget announcement ingestion from the public announcements API
- canonical announcement ID/title/type/subtype/timestamp/URL evidence
- conservative symbol binding using exact futures symbol/pair forms or whole-token base-coin matching
- freshness window and future-timestamp tolerance
- S9 no longer invents sentiment direction from an announcement
- when an official catalyst is fresh, S9 requires market-confirmed LONG/SHORT direction plus participation before becoming a shadow candidate
- snapshot-level catalyst fetch/binding summary
- mobile dashboard count of fresh official catalyst matches

Still fail-closed:

- no unofficial/social-media catalyst source is trusted
- no announcement alone grants trade permission
- stale or unmatched announcements cannot create an S9 shadow candidate
- all S9 results remain shadow-only until forward evidence supports promotion


## P4 execution increment — v0.1 prospective strategy forward outcomes

Implemented in this increment:

- persist the most recent fully closed candle separately from the currently forming candle
- normalize every S1-S10 canonical observation from the immutable symbol snapshot stream
- create immutable persistent strategy episodes from strategy_instance_id
- freeze 1H / 4H / 12H / 24H forward horizons
- quantify first SHADOW_CANDIDATE time and price
- quantify confirmation tax in reference-price %, planned-entry %, and first-risk R units
- preserve remaining R at first candidate and its change from first observation
- detect PLACE_LIMIT touches only from future fully closed canonical 1H candles
- calculate conservative post-trigger MAE, MFE and direction-adjusted endpoint return
- classify target-first / stop-first / same-candle ambiguity without inventing intrabar ordering
- explicitly exclude the trigger candle and partial signal hour from path measurements
- record path coverage and incomplete-data quality
- expose a non-ranking per-strategy forward scorecard
- schedule the database evaluator hourly using only canonical persisted evidence

Scientific fail-closed boundary:

- no second universe scanner is used
- no additional exchange market query is needed for the outcome evaluator
- incomplete candle coverage remains incomplete rather than imputed
- net-of-cost return remains NULL until canonical cost evidence is bound
- outcomes cannot change thresholds, grant READY, grant trade permission, or promote a strategy


## Continuity hardening — canonical previous snapshot v0.1

Implemented after the first live S1-S10 production scan exposed that a redeploy can start without a project-local previous snapshot:

- scanner now loads both project-local latest.json and the latest canonical Supabase parent snapshot when configured
- the newest valid snapshot wins
- cloud canonical context is therefore available after process restart/redeploy instead of resetting S6/S7 and persistence history to no previous evidence
- every new snapshot records previous_snapshot_context source/run/time for auditability
- dashboard exposes whether previous context came from LOCAL_LATEST, SUPABASE_CANONICAL or NONE
- WATCH strategies can no longer display EXECUTE_NOW or PLACE_LIMIT as their gate action when execution gates fail
- raw strategy intent is preserved separately as proposed_action for research analysis
- SHADOW_CANDIDATE remains the only strategy status permitted to expose EXECUTE_NOW or PLACE_LIMIT inside the shadow matrix

This does not relax any R:R, safety, liquidity, integrity or production-permission gate.


## P4 execution increment — v0.1 first-observation opportunity path

Implemented as a descriptive companion to the execution-forward ledger:

- measures what happened after the FIRST persistent S1-S10 observation even if the setup never became a SHADOW_CANDIDATE
- freezes 1H / 4H / 12H / 24H horizons
- starts path measurement at the next fully closed 1H candle, excluding the partial signal hour
- records direction-adjusted opportunity MFE, MAE and endpoint return from the first observed reference price
- records opportunity excursion in the initial geometry's R unit when a valid initial risk amount exists
- records first candidate time, candidate conversion delay and confirmation tax when a later SHADOW_CANDIDATE appears
- records whether the originally proposed PLACE_LIMIT entry was touched after first observation
- preserves path coverage and incomplete-data quality
- exposes a descriptive per-strategy scorecard only
- explicitly labels this evidence DESCRIPTIVE_ONLY_NOT_EDGE_PROOF

This table is intended to answer:
"Did Alpha Hunter identify the move early enough before confirmation?"

It cannot establish:
- executable edge
- profitability
- production readiness
- a best strategy ranking

Those claims still require controlled prospective evidence and net-of-cost validation.


## Live evidence correction — catalyst symbol-boundary v0.2

The first live multi-strategy scan exposed a matcher defect in catalyst v0.1:
a short futures symbol could be found as an alphanumeric substring inside a
different, longer contract symbol (for example LSKUSDT inside CLSKUSDT).

Corrective action:

- catalyst evidence version bumped to v0.2
- full symbols and pair forms now require alphanumeric token boundaries
- whole-base fallback also requires token boundaries
- short base coins remain in fail-closed mode for base-only matching
- S9 persists catalyst_version and match_rule for auditability
- regression cases explicitly reject LSKUSDT/CLSKUSDT, MUSDT/CRMUSDT and SUSDT/GFSUSDT collisions

Historical canonical snapshots remain immutable. Catalyst v0.1 evidence can be
distinguished from v0.2 and must not be treated as equivalent evidence in future
S9 scientific analysis.
