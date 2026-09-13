# Alpha Hunter Money Entry Stage Single Writer

## Purpose

Create one contemporaneous, append-only source of truth for Money Entry T0/T1/T2 stage evidence without inventing production thresholds or granting trade permission.

The writer runs after the Big-Mover → Money Entry bridge and before the forward scorecard:

`:10 ANSWER_KEY → :11 PARENT_DIRECTION → :12 MONEY_ENTRY_BRIDGE → :13 MONEY_ENTRY_STAGE → :14 MONEY_SCORECARD → :20 FINALIZE`

## Threshold policy

PR #6 contained test-fixture threshold values. They are **not** production policy and are not copied here.

`alpha_hunter_money_entry_threshold_sets` exists only as a reviewed evidence registry. This milestone inserts no ACTIVE threshold set. Therefore current stage records fail closed with `DATA_INSUFFICIENT` + `NO_ACTIVE_VALIDATED_THRESHOLD_SET` until forward evidence supports a separately reviewed activation.

An ACTIVE threshold set must have all four numeric fields, a validation timestamp, activation timestamp, and a non-empty evidence reference. Only one ACTIVE set may exist.

## Exact evidence binding

The stage writer freezes the current bridge row plus the exact scanner fields available at that time, including:

- 1H / 12H / 1D direction
- lifecycle / research / bridge state
- entry / stop / target / R geometry
- scanner execution direction
- scanner `structure_valid`
- scanner `direction_aligned`
- scanner `momentum_confirmed`
- scanner `participation_confirmed`
- scanner data-integrity pass
- market phase / scanner state / decision stage
- explicit live fields for liquidity pass, participation emerging, acceptance, trigger, expansion and open-position conflict when they exist

Missing fields remain `NULL` and create explicit blockers. They are never inferred from nearby labels.

## Current expected blockers

The current source payload does not consistently expose explicit Money Entry booleans for liquidity pass, participation-emerging, acceptance, trigger, expansion, or open-position conflict. These are preserved as named evidence gaps such as:

- `LIQUIDITY_PASS_NOT_CAPTURED`
- `PARTICIPATION_EMERGING_NOT_CAPTURED`
- `T1_ACCEPTANCE_NOT_CAPTURED`
- `T1_TRIGGER_NOT_CAPTURED`
- `T2_EXPANSION_NOT_CAPTURED`
- `OPEN_POSITION_CONFLICT_NOT_CAPTURED`

The writer also rejects a scanner execution setup whose direction conflicts with the independent Big-Mover research direction.

## Stage semantics

- `DATA_INSUFFICIENT`: threshold set or required evidence is unavailable.
- `NO_T0`: validated thresholds exist but the candidate fails the controlled-entry requirements.
- `T0_CONTROLLED_ENTRY`: earliest current snapshot satisfying the evidence-backed T0 contract.
- `T1_ACCEPTANCE_CONFIRMED`: T0 plus confirmed participation, acceptance and trigger.
- `T2_EXPANSION_CONFIRMED`: T1 plus expansion confirmation while remaining-R still meets the validated threshold.

Every snapshot is immutable and keyed to its exact bridge row. A snapshot never rewrites another hour with later market information.

A stable cross-hour Money Entry episode identity is not yet claimed. Until a trustworthy episode binding exists, snapshots explicitly record `stable_episode_id_status=NOT_BOUND_TO_STABLE_EPISODE` rather than grouping events by hindsight.

## Forward scorecard linkage

Future scorecard candidate rows link to the immutable `money_entry_stage_snapshot_id` when present. This creates provenance from discovery → bridge → exact stage snapshot → forward path measurement.

The scorecard still withholds `realistic_net_r` until execution-cost evidence is verified. A stage snapshot also does not grant order permission.

## Safety

- `shadow_only=true`
- `trade_permission=false`
- threshold registry and stage snapshots are service-role-only with RLS
- threshold and stage evidence tables are append-only
- no private Bitget credentials
- no order path
- no leverage/risk expansion
- no production threshold activation in this milestone
