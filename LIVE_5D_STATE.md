# ALPHA HUNTER — 5-DAY CLOUD LIVE CONTINUITY

Start:
2026-08-16 22:45 Europe/London

End:
2026-08-21 22:45 Europe/London

Source checkpoint:
e636c07df2bc56b5477b7fb32b3e2be84ae024e3

Purpose:
Keep the live evidence-collection and forward-measurement processes running while the development MacBook is offline.

This branch is DATA / LIVE-EVIDENCE ONLY.

SAFE LIVE CHAIN

1. run.py
   - live Bitget market scan
   - candidate discovery
   - snapshot/state-history collection

2. v79_universe_hourly_collector.py
   - full Bitget futures universe hourly ledger

3. production_guardrails.py
   - data-integrity verification

4. v74_tracking_job.py
   - performance tracking

5. v75_lifecycle_job.py
   - opportunity lifecycle

6. v75_episode_market_tracker.py
   - episode market tracking

7. v75_episode_finalizer.py
   - matured episode finalization

8. v76_direction_shadow.py
   - direction shadow
   - V7.10 immutable direction-transition capture

9. v76_post_confirmation_tracker.py
   - post-confirmation outcome tracking

10. v77_execution_feasibility_shadow.py
    - Huge-RR feasibility shadow

11. v79_missed_mover_recall_auditor.py
    - independent missed-mover audit

MANDATORY BLOCKS

DO NOT RUN:
- production_runner.py
- v78_timing_rr_decay_shadow.py
- v710_early_execution_rr_shadow.py
- V7.10 replay/promotion diagnostics
- historical reconstruction
- real order execution

Reason:
V7.8 evidence-integrity repair is not complete.

Trade Permission remains FALSE.

Cloud execution must preserve:
- immutable timestamps
- anti-hindsight evidence
- hourly raw Bitget evidence
- state history
- task logs
- failures and skipped steps

No silent production-rule changes are permitted.

This five-day branch must not be merged wholesale into Production.
Research/data findings must be audited first.
