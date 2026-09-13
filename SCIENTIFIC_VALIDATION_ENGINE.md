# Alpha Hunter Scientific Validation Engine v0.1

## Purpose

Make Alpha Hunter's development process scientifically testable rather than confidence-driven.

The engine does **not** create trades. It evaluates whether a preregistered trading hypothesis is supported by forward, shadow-only evidence against an explicit control/base rate.

Core sequence:

`Observation -> Hypothesis -> Preregistration -> Forward shadow test -> Control comparison -> Falsification -> Replication -> Separate production review`

## Non-negotiable safety boundary

- `shadow_only=true`
- `trade_permission=false`
- `production_promotion_permitted=false`
- no Bitget private trading endpoint
- no order path
- no leverage/risk relaxation
- no production threshold activation
- scientific support can never bypass Direction / Structure / Entry Location / Remaining R / Portfolio Risk

Even a `SUPPORTED_SHADOW` result only means: **retain the idea for replication**.

## What qualifies as a scientific hypothesis

Every hypothesis must be preregistered before its holdout observations are used and must define:

- unique `hypothesis_id`
- exact outcome metric
- expected direction (`GREATER` or `LESS`)
- minimum economically meaningful effect
- minimum sample size per TEST and CONTROL group
- alpha
- number of simultaneous hypotheses in the family
- explicit falsification rule
- holdout requirement

Example:

```json
{
  "hypothesis_id": "H_T0_NET_R_6H_001",
  "metric": "net_r_6h",
  "expected_direction": "GREATER",
  "minimum_effect": 0.35,
  "min_samples_per_group": 30,
  "alpha": 0.05,
  "family_size": 4,
  "preregistered": true,
  "falsification_rule": "Reject if holdout T0 net-R does not beat matched control by at least 0.35R.",
  "require_holdout": true
}
```

No numerical value in that example is a production trading threshold. The research owner must justify values before use.

## Observation contract

Each observation must contain:

```json
{
  "observation_id": "immutable-unique-id",
  "group": "TEST",
  "value": 1.25,
  "holdout": true,
  "data_quality_ok": true,
  "shadow_only": true,
  "trade_permission": false
}
```

`CONTROL` should represent the correct base rate: for example matched non-movers, later-entry stage, legacy READY path, or another preregistered comparator.

The engine fails closed on duplicate/missing IDs or any observation outside the shadow/no-trade boundary.

## Statistical controls in v0.1

1. **Base-rate comparison** — TEST is evaluated against CONTROL, never in isolation.
2. **Economic effect size** — statistical significance alone is insufficient.
3. **Bootstrap uncertainty** — a 95% bootstrap interval is produced for the direction-normalized effect.
4. **Permutation test** — a one-sided randomization p-value tests whether the observed separation could plausibly arise under exchangeability.
5. **Multiple-testing protection** — family-wise alpha is Bonferroni-adjusted.
6. **Forward holdout requirement** — in-sample observations cannot satisfy a holdout-required hypothesis.
7. **Falsification** — sufficiently strong evidence in the opposite direction marks the hypothesis `FALSIFIED`.
8. **Replication requirement** — `SUPPORTED_SHADOW` is not a production promotion.

## Status meanings

- `SUPPORTED_SHADOW` — effect size, bootstrap interval and multiplicity-adjusted permutation test pass. Retain for replication only.
- `FALSIFIED` — observed effect is materially opposite to the preregistered direction.
- `INCONCLUSIVE` — evidence does not support or strongly falsify the hypothesis.
- `INSUFFICIENT_DATA` — sample requirement not met.
- `DATA_INTEGRITY_FAILURE` — duplicate/missing observation identity.
- `SAFETY_BOUNDARY_VIOLATION` — non-shadow or trade-permitted evidence was supplied.
- `INVALID_HYPOTHESIS` — hypothesis was malformed or not preregistered.

## Alpha Hunter evidence sources

The intended first inputs are the evidence already being produced on `main`:

- Big-Mover Money Scorecard forward outcomes
- post-direction-binding Money Entry calibration cohort
- T0/T1/T2 stage evidence when available
- confirmation-tax measurements
- matched mover vs non-mover/control cohorts
- completed-trade evidence after it is normalized to the same metric and safety contract

Historical evidence may be used for exploration, but it must not be relabeled as holdout evidence.

## First recommended experiments

### H1 — Earlier controlled entry vs later confirmation

TEST: direction-bound, geometry-valid T0 candidates.
CONTROL: matched later T1/T2 or existing READY path on the same/fairly matched future opportunity set.
Primary metric: cost-adjusted net R at a preregistered horizon.
Secondary diagnostics: MAE, MFE, stop survival, remaining R and confirmation tax.

Question: **Does waiting for additional confirmation improve or destroy realized expectancy after costs?**

### H2 — Big-Mover pre-move signature vs matched controls

TEST: candidates above a preregistered signature threshold.
CONTROL: contemporaneous matched futures contracts not satisfying the signature.
Metric: forward direction-adjusted net return/R with liquidity and survivability constraints.

Question: **Does the pre-move signature add information before expansion, beyond the base rate?**

### H3 — Direction-resolution value

TEST: entries aligned with resolved 12H + 1D direction.
CONTROL: otherwise similar opportunities without parent-direction agreement.
Metric: net R, MAE and stop-survival rate.

Question: **Does parent-direction resolution add measurable expectancy rather than merely confidence?**

## Promotion philosophy

Scientific validation is a new evidence gate, not an execution gate.

A future production proposal must still be separately reviewed and must preserve the core Alpha Hunter rule:

**READY = EXECUTABLE CONFLUENCE, NOT CONFIDENCE.**

Scientific support may strengthen evidence for a rule; it must never manufacture READY status or override a failed Direction, Structure, Entry Location, Remaining R, or Portfolio Risk gate.
