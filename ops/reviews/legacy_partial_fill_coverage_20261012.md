# Legacy partial-fill coverage defect — 12 October 2026

Status: verified diagnosis; monitoring-only correction. NMR lifecycle/protection repair NOT deployed.

## Evidence
NMRUSDT LONG order 9975630880b549753d81aa4708eea321:
- Submitted 2026-10-02T22:04:12.523274Z, LIMIT quantity 3.2.
- Fill 92bd3329f4c6e19f3ea3d93a60780a22 modeled 1.5 at 11.595 on 2026-10-03T04:23:18.759325Z.
- Captured ask quantity was 1.5. Remaining entry quantity 1.7; only one fill exists.
- Last reconciliation observation 2026-10-03T05:04:35.141705Z, NO_CROSS.
- Latest lifecycle remains PARTIALLY_FILLED; no exit fills, protective orders, exit attempts or inspected entry/exit/reconciliation quarantine.
- No R10 membership. This is a historical paper record, not an exchange order.

## Verified exclusion mechanism
The live reconciliation_inventory_v08 joins orders on submission >= R8 activation, 2026-10-03T06:23:09.434421Z. NMR predates it. Even though the current reconciliation gate is permitted, NMR has zero inventory/open reconciliation rows.
The live protection_open_v04 requires fully filled quantity, lifecycle FILLED, and existing protective records. NMR fails all three.
These combined predicates explain its current invisibility. Exact historic deployment causality has not been reconstructed; the current exclusion is verified directly from view definitions and data.

## Smallest non-disruptive correction
The adjacent SQL starts from ALL fill quantities less recorded exit quantities, without cohort/date/state exclusion. It LEFT JOINs protection and quarantine evidence so missing records remain visible. It performs SELECT only and creates no view or migration.
Live read-only validation on 2026-10-12 returned 33 residual orders:
- 11 managed protection records present;
- 21 explicitly quarantined residuals (19 full, 2 partial);
- 1 UNPROTECTED_RESIDUAL_REVIEW_REQUIRED: exact NMR order, residual 1.5.
Quarantined residuals remain visible and are never labeled safely closed. Protection records present is not a guarantee of executable exit liquidity.

Production Safety Watch received an instruction-only addendum to perform this all-history cross-check, keep NMR OPEN, and distinguish paper evidence from live exchange positions. Its existing enabled hourly schedule was preserved; Primary Hourly was not edited. This repairs monitoring coverage, not NMR execution.

## Repair boundary
Do not restore this legacy order to ordinary reconciliation: that could manufacture a new fill years/hours after the original decision. Do not infer a historical stop or horizon exit from future prices, apply R10 membership/horizon retrospectively, erase the fill, or add a quarantine merely to make metrics pass.
Any actual lifecycle disposition needs a separately specified append-only historical incident path, explicit accounting for 1.5 already modeled and 1.7 unfilled, preservation of original records and exclusion from valid cohort profitability. Do not implement it by changing the frozen running scanner.
Future execution must choose preregistered all-or-none admission or genuine partial-fill lifecycle protection with correct residual sizing and cancellations, independently tested in a successor boundary.

## Acceptance / falsification
- Historical NMR must appear with 1.5 residual, zero STOP/TP, no managed membership.
- Known 11 managed rows remain visible and distinct from the 21 quarantined rows.
- A terminal lifecycle label alone must not erase positive residual quantity.
- Closed R10 fills with matching exit quantity must not appear as residual.
- No new scanner, migration, cron, engine import, threshold, authority or cohort mutation.
- Any missing relation/access produces UNKNOWN in monitoring, never PASS.

DRAFT ONLY. Do not merge/deploy as part of active-test repair: main auto-deploys the scanner. SQL is run manually read-only from this draft. Existing R10 admission halt, original activation/cutoff, four failures, 35-minute bound and protected legacy management remain intact.
