# Alpha Hunter Cloud Production Control Plane

## Objective

Make the current phone/cloud Alpha Hunter research-production evidence path auditable as one hourly process without enabling live trading.

Each UTC hour gets one canonical control identity:

`AHCLOUD-YYYYMMDDTHH00Z`

The control plane does not replace the existing Big-Mover, parent-direction, Money Entry bridge, or forward scorecard logic. It wraps them with ordering, idempotency, immutable evidence, health checks, and incident records.

## Hourly sequence

1. `:10` ANSWER_KEY — public Bitget USDT-M mover answer key + Big-Mover signature shadow.
2. `:11` PARENT_DIRECTION — isolated public Bitget 12H/1D direction evidence.
3. `:12` MONEY_ENTRY_BRIDGE — fail-closed Big-Mover → Money Entry evaluation handoff.
4. `:14` MONEY_SCORECARD — 1H/4H/12H/24H forward path outcomes using public 3-minute candles.
5. `:20` FINALIZE — stage completeness/order, source-run consistency, data freshness, safety invariants, health event, and incident event.

A stage cannot run successfully before its predecessor has produced PASS or DEGRADED evidence for the same control hour. Re-running a successful/degraded stage in the same hour returns the immutable earlier result and does not rescan the exchange.

## Evidence

- `alpha_hunter_control_plane_runs` — mutable current summary for each canonical hour.
- `alpha_hunter_control_plane_step_events` — append-only per-stage attempts/results.
- `alpha_hunter_control_plane_health_events` — append-only hourly health decisions.
- `alpha_hunter_production_incident_events` — append-only OPEN/RESOLVED health incident stream.

## Health contract

The finalizer verifies:

- all four expected stages exist and are successful enough to continue;
- stage finish order is proven;
- non-null source run IDs agree;
- source feature, answer-key and Big-Mover evidence are not more than 90 minutes old;
- every Big-Mover/parent/Money-Entry/scorecard evidence row still has `shadow_only=true` and `trade_permission=false`.

`FAILED` is used for a broken/missing chain, source-run mismatch, invalid order, or safety violation. `DEGRADED` is used when the chain completed but a stage or freshness condition degraded. Candidate-level missing evidence remains fail-closed and does not become a trade authorization.

## Live validation — 2026-09-13

The first controlled run, `AHCLOUD-20260913T1000Z`, completed all four stages against fresh Bitget data with one consistent source run ID and `safety_status=PASS`.

- ANSWER_KEY: PASS, 787 Bitget USDT-M tickers observed.
- PARENT_DIRECTION: DEGRADED because PONSUSDT had insufficient listing history for 30-candle 12H/1D trend calculation (27 × 12H; 14 × 1D), not because of an HTTP/runtime failure.
- MONEY_ENTRY_BRIDGE: PASS.
- MONEY_SCORECARD: PASS; new scorecard candidates/horizons were seeded and matured outcomes evaluated.
- FINALIZE: DEGRADED solely because one stage reported candidate-level data incompleteness; stage order, source-run consistency, data freshness and the safety boundary all passed.

## Safety boundary

This milestone does **not** add or enable:

- private Bitget credentials;
- order submission;
- automatic trade execution;
- production trade permission;
- leverage or risk-threshold changes;
- inferred T0/T1/T2 thresholds;
- fabricated cost-adjusted net R.

The next production-development gates remain exact immutable T0/T1/T2 single-writer evidence, verified execution-cost evidence, portfolio risk policy, and eventually a separately reviewed order/fill state machine. Those gates must not be bypassed simply because the control plane is healthy.
