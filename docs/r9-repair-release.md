# R9 repair release — 2026-10-04

Status: implementation and tests prepared; not deployed or activated.
This branch includes the existing PR #321 containment fix and implements the
successor contract from #323. R8 evidence remains immutable.

## Frozen successor policy

- Entry clock: final complete all-or-none fill, not submission.
- Intended horizon: 24 hours; maximum observation lag: 35 minutes inclusive.
- Entry expiry and monitoring maximum: 35 minutes; ten strategies; >=5R entry.
- Admission window: exactly 30 days after the new activation. At least 100 valid
  completed trades and every admitted order reconciled are required for a readout.
  An insufficient sample at the frozen cut is reported as insufficient; no
  post-result extension or selective exclusion.
- Canonical RENDER_CRON source and role; frozen scientific fingerprint.
- STOP/TP takes precedence. Otherwise use executable bid (LONG) or ask (SHORT),
  full remaining quantity and the existing deterministic paper cost model.
- Timeout event/state: PAPER_HORIZON_EXIT_RECONCILED / HORIZON_CLOSED;
  exit reason HORIZON_24H; protective order ID is null, never fabricated.
- A missing/invalid monitoring observation, a >35-minute gap, unresolved earlier
  protection or an unusable first due observation creates a permanent integrity
  failure. Later protection management remains active but cannot erase failure.
- All admitted orders remain in the denominator, including open, unfilled,
  expired and failed orders. No failed position is silently dropped.
- Existing R8 positions retain their original protective policy. The global R8+
  successor exposure inventory remains intact across activation and admission halt.
- Funding and realistic net-R claims remain blocked until independently validated
  execution-cost evidence exists. This release does not manufacture that evidence.

## Deployment sequence

1. Review final code, CI, SQL behavior and the frozen policy above. Record the final
   commit, scientific fingerprint, runtime fingerprint and migration SHA-256 hashes.
2. Register the corrected deployment target first, so the old entry reconciliation
   worklist fails closed during cutover. Then install
   `ops/sql/r8_reconciliation_required_containment_v01.sql`,
   `ops/sql/paper_horizon_successor_v09.sql`, then
   `ops/sql/paper_successor_activation_v09.sql` transactionally. Installation
   activates nothing. Do not apply the containment worklist alone to old runtime.
3. Register the new spec with the reviewed commit/fingerprint using the owner-only
   `private.alpha_hunter_preregister_r9_v01(commit, fingerprint)`.
4. Deploy the exact reviewed commit to the existing web and
   canonical Render cron services. Do not change cron cadence or disable discovery.
   New paper admission is fail-closed until explicit R9 activation; legacy
   protection monitoring remains active under the repaired runtime.
5. Verify fresh canonical scan, exact git/fingerprint, complete child evidence,
   matched deployment target, legacy protection continuity and DGAI zero-fill
   expiry with no delayed fill. Verify no schema/RPC errors in logs.
6. Call owner-only `private.alpha_hunter_activate_r9_v01(commit, fingerprint)`.
   It rejects pre-preregistration/stale/mismatched runtime and incomplete baseline
   evidence. Execution and profitability identities are inserted atomically.
   Admission starts strictly AFTER verification; no pre-repair rows are reused.
7. Verify R9 admission, global exposure guard, dashboard cohort identity, repaired
   expiry, real first fills and monitoring. Verify first horizon when it matures.
   Do not claim a production 24h exit was verified before it actually occurs.

## Recovery

Before activation, failed deployment remains fail-closed for new paper admission.
After activation, append an owner-only row to
`alpha_hunter_paper_admission_halts_v09` for PAPER_EXECUTION_R9 with the reason.
This permanently closes new cohort admission while preserving its original
activation, open-position protection, reconciliation, hourly discovery and data.
Do not roll back to a pre-horizon runtime while successor exposure exists. Repair
forward or drain exposure under the recorded policy before a new cohort.
Never delete evidence or change the frozen R8/R9 identity to hide drift.

## Validation evidence

- Full Python suite and isolated PostgreSQL behavior tests are run on this branch.
- Live-schema rollback smoke installs both repairs and owner-only activation
  functions, verifies legacy positions remain visible and zero R9 activations,
  then rolls back. No production evidence or settings are changed by that smoke.
- Render workspace confirmation is required by the connector before selecting
  the existing services. The account exposes one workspace named `My Workspace`.
