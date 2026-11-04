# P0 read-only analysis — big-mover model cadence is incompatible with hourly freshness

**Observed 2026-11-04, UTC; research only. No production mutations.**

## Proven from actual database catalog and stage ledger

- `cron.job`: `alpha-hunter-big-mover-shadow-model-research-v01` active at `11 2,8,14,20 * * *` (four times/day), running `public.alpha_hunter_run_big_mover_shadow()`.
- `cron.job`: `alpha-hunter-big-mover-parent-direction-hourly` active at `16 * * * *`, calling the controlled stage `PARENT_DIRECTION`.
- `private.alpha_hunter_collect_big_mover_parent_direction()` has a **hard 90-minute** source freshness guard; it must not be widened merely to mask a stale pipeline.
- Latest `alpha_hunter_big_mover_shadow` `captured_at_utc` at 18:50 UTC was **14:04:55.821677**, although the 14:11 model job succeeded. Its underlying feature timestamp predates the model job.
- The 16:16, 17:16 and 18:16 parent-direction stages all recorded `FAILED` and the *same* stale-shadow exception; downstream money-entry stages were skipped as designed.
- PostgreSQL cron reports `succeeded` for these *wrapper* invocations because they record a failed controlled-stage result rather than raising a SQL exception; do not confuse cron scheduler success with business-stage success.

## Isolated simulation (not a production remedy)

Run the zero-dependency simulation from the repository root:

```bash
python ops/reviews/p0_big_mover_freshness_cadence_audit_v01.py \
  --producer-cron "11 2,8,14,20 * * *" \
  --consumer-cron "16 * * * *" \
  --max-age-minutes 90 --producer-runtime-minutes 3 \
  --source-timestamp-lag-minutes 7 --day-utc 2026-11-04
```

With the observed schedule, an assumed 3-minute producer runtime and 7-minute feature-timestamp lag, the model forecasts **8/24 fresh** hourly stages and **16/24 stale**. This explains the *structural impossibility*, not the exact historical success count; actual runtime and upstream feature capture vary. The result includes `trade_permission=false` and `production_change_permitted=false`.

## Engineering recommendation, not applied

**Do not** weaken the 90-minute source gate, fabricate backfilled model timestamps, refresh an old row's `captured_at_utc`, launch a duplicate Bitget full-universe scanner or convert WATCH states into executable signals.

The candidate solution is a **low-cost hourly *scoring-only* successor** that consumes exact-source freshly persisted feature evidence and previously validated training profiles. Keep expensive full retraining at its separate six-hour cadence. It must use truthful per-run source timestamps; fail closed if fresh source/profiles are missing; remain paper-only, and never admit R10 orders. Alternative isolated tests can compare a different permitted cadence before any production scheduling change.

Before even proposing release:
1. Independently verify provenance and completeness of producer profiles, exact RENDER_CRON source run, feature rows, model version and signature.
2. Test producer worst-case runtime and database contention under representative load; adding hourly expensive full retraining could worsen the active PostgREST timeouts.
3. Run isolated PostgreSQL 16/17 and PostgREST tests for stale-source, missing source, source mismatch, post-commit uncertainty and downstream fail-closed behavior.
4. Require fresh consumer evidence each hour, all control-plane stages to finalize truthfully and no unapproved live or paper trade permission.
5. Obtain separate source-custody/DBA/security and owner release approval, with an independently proven rollback. Keep R9/R10 fingerprints and histories immutable.

**Current status:** Diagnostic and regression contract only. Production and `main` are unchanged. This work must not be represented as a completed reliability repair or evidence of trading profitability.
