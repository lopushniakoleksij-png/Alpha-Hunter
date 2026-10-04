# R9 first-observation repair — NOT FOR LIVE MERGE

Confirmed 2026-10-04 19:53 UTC: R9 has 37 admissions, three integrity-failed
orders, and zero clean completions. AVA, ZEC and PLUME all received a horizon
clock failure at exactly their entry-completion timestamp. AVA subsequently
stopped under continuing protection. ZEC and PLUME also received noncanonical
GitHub observation failures at 19:13:26Z. Evidence is retained, not corrected.

## Root causes

1. The horizon wrapper substitutes entry time for absent previous monitoring and
   rejects observation <= previous. The same scan both establishes the entry
   and visits the new protection worklist. Merely allowing equality is unsafe:
   the underlying protection reconciler returns AMBIGUOUS for the entry run,
   which the horizon wrapper also classifies as a permanent integrity failure.
2. Noncanonical discovery sources call the same storage reconciliation path.
   Successor history aggregates those attempts, so an unrelated GitHub source
   contaminates the Render-only cohort despite not being an intended observation.

## Proposed forward repair

- Do not use a validated entry-completion run as a post-fill observation when
  no monitoring history exists. Emit no attempt/fill/event; do not invent a
  clean baseline. Restrict the exception by source-run ID, canonical identity,
  clock validity and the existing 35-minute time bound.
- The first later canonical observation measures its gap from actual fill time.
- Ignore noncanonical discovery for successor monitoring only. Canonical runs
  with incorrect role/fingerprint still fail closed. Legacy routing is unchanged.
- Reject corrupt prior timestamps rather than treating them as absent history.
- Preserve recorded failures; do not recompute old trades as clean outcomes.

## Deployment decision required

This changes scientific and runtime fingerprints. Do NOT merge into auto-deployed
main while R9 is frozen. No production writes, admission halt, activation reset,
threshold change or history update is part of this PR.

Recommended next release: explicitly close new R9 admission (not discovery or
existing management), preserve the failed cohort and pending orders, prepare a
separately preregistered successor plus management compatibility for existing R9
positions, then deploy/verify before enabling new successor admission. Existing
R9 positions must retain protection even after the runtime fingerprint changes;
the candidate compatibility bridge is now implemented but is not installed or
approved in production. See `r10-preparation.md`. Do not simply overwrite the
immutable R9 fingerprint or clear its failure flags.
