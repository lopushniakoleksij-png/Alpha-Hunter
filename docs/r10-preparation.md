# R10 preparation — inactive, not a final preregistration

Recorded 2026-10-04 UTC. This record prepares a corrected successor; it does
not register or activate one, authorize orders, or change R9 evidence.

## Controlled R9 closure

New PAPER_EXECUTION_R9 admissions were halted at
2026-10-04T20:02:43.628791Z by the user-approved append-only admission halt.
The reason records first-fill observation-clock and noncanonical-source defects.
The immutable activation, original fingerprint, failures and history remain intact.

Post-halt verification found zero admission-view rows and zero subsequently
submitted orders. Canonical discovery continued at 20:04:02.023997Z and protection
observations continued at 20:04:10.522633Z; 19 positions remained in the protection
worklist. These are point-in-time observations, not a guarantee of future health.
Six R9 orders were unresolved immediately before the halt.

## Candidate correction

Draft PR #326: https://github.com/lopushniakoleksij-png/Alpha-Hunter/pull/326

- Tested candidate commit: `18a2754e2261a41434810de8ebeb5eef3b6b9e30`.
- Candidate tree: `6da83528a37c3c783e9bee1931e14f2bf21ea7b8`.
- CI Python 3.14.3 scientific fingerprint:
  `8aecbc85b3895a81a49f33407e52c2651f90829a44dd1ffdeb2cbf708c08ba33`.
- Four CI workflows passed, including 1,257 Python tests and PostgreSQL contracts.
- The correction skips the entry-establishing observation, retains the first
  subsequent observation's gap from actual fill time, isolates noncanonical
  sources, and fails closed for malformed prior timestamps.

This is a candidate fingerprint, not the final R10 freeze. A management bridge
or further scientific changes require a new fingerprint and fresh validation.
The corrected code has not been deployed.

## Required handover work

1. Preserve existing R9 position management across a runtime fingerprint change.
   Either verify that all R9 orders have resolved before deployment or implement
   and test explicit management compatibility. Do not overwrite the frozen R9
   fingerprint or admit new orders under it. A compatibility path must not turn
   failed R9 observations into clean scientific outcomes.
2. Define immutable, explicit successor membership. Current v09 cohort and
   protection views associate orders after R9 activation with R9 without a
   successor boundary. Test disjoint R9/R10 membership, including R9 pending
   orders filled after the handover. Membership must follow original admission,
   not subsequent fill time. Preserve the original audit history.
3. Add an owner-only R10 registration and activation interlock before inserting
   a successor spec. The generic profitability activator can otherwise activate
   newly inserted eligible specs automatically. An absent or incomplete R10
   activation must yield zero new admissions.
4. Freeze the final validated code and scientific fingerprint in a separate
   preregistration. Carry forward 30 days, 100 clean completed trades, all admitted
   orders reconciled, zero integrity failures, 10 strategies, minimum 5R, a
   24-hour horizon from completed fill, and existing 35-minute bounds. Preserve
   full-size executable-side evidence and SL/TP precedence. Do not infer validated
   execution costs or realistic net profitability from these repairs.
5. Deploy with new admissions closed; verify matching canonical deployment
   identity, fresh complete source evidence, continued discovery and existing
   protections. Then activate the separately registered successor atomically.

Acceptance cases include same-entry-run observations, first later observations
at and beyond the 35-minute limit, noncanonical scans, malformed/replayed clocks,
failed R9 positions receiving valid protection, and no cross-cohort admission or
outcome counting. None of these gates may be satisfied by deleting old failures.

## Timing

Engineering and preparation can proceed today. Genuine 24-hour observations
require elapsed time after each completed fill. A 24-hour wait alone does not
satisfy the separate 30-day and 100-clean-trade requirements. R10's clock has not
started. No historical replay or R9 evidence will be relabeled as R10 evidence.
