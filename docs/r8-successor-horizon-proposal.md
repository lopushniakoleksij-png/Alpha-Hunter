# Successor executed-paper horizon — review proposal

Status: DRAFT, NOT PREREGISTERED, NOT ACTIVATED.
Prepared 2026-10-03 for Issues #318 and #322; dependent on PR #321.
This document creates no database identity, activation, order or runtime policy.

## Proposed treatment

Use a 24-hour maximum intended holding period measured from the final all-or-none
entry fill timestamp, with a prospective paper timeout exit. This makes the
holding-period policy explicit rather than treating a later SL/TP result as a
24-hour result. It is a NEW protocol, not an interpretation of active R8.

Freeze both the 24-hour target and a separate 35-minute maximum observation lag
before admitting any successor candidate. The 35-minute lag is a proposed
observation tolerance, not an extension that turns a late observation into an
exact 24-hour price. Report actual holding duration and lag on every trade.
These numerical choices require scientific review and implementation before
they can become a registered contract.

1. `entry_completed_at_utc` is the authoritative clock origin. Preserve submission
   time separately. Missing/invalid entry time blocks confirmatory admission.
2. Before the deadline, retain the preregistered stop/target monitoring rules.
3. At the first valid canonical observation at or after entry + 24 hours, apply
   protective-exit precedence using the same frozen protective rules. If no
   protective exit applies, attempt a paper timeout exit at the executable side
   of that observation: bid for a LONG sell, ask for a SHORT buy. Do not use a
   midpoint, interpolate the deadline price, or manufacture an earlier fill.
4. The timeout route requires full-position capacity and all existing integrity
   checks. It must never fabricate a fill when liquidity/price evidence is
   missing. Ambiguous protective-path evidence keeps its frozen conservative
   treatment; a timeout must not overwrite an unresolved earlier trigger.
5. A missing/invalid observation, insufficient exit capacity, or a monitoring gap
   must remain visible as unresolved execution. Keep the position protected and
   monitored; do not silently mark it closed or recycle its exposure key.
6. If no admissible exit evidence exists by deadline + 35 minutes, append a
   horizon-integrity failure. Retain later management and terminal events, but
   never label that trade a compliant 24-hour outcome. Record the failure in the
   all-admitted cohort denominator; it cannot be dropped to improve win rate.
7. Any horizon failure blocks the proposed cohort's confirmatory profitability
   pass pending a separately registered successor/review. Do not compensate by
   collecting extra winners or excluding adverse outcomes after seeing results.

## Cohort and claim boundaries

- Register a new immutable spec/activation only after corrected runtime and SQL
  are deployed and verified. Bind exact commits, scientific fingerprint, SQL
  contract hashes, timeout rules, source authority and new activation timestamp.
- Successor admission must begin strictly after verification. Reuse no R8 trade
  or pre-repair completion as successor confirmatory evidence.
- Continue managing legacy open paper positions under their original rules.
  Preserve global exposure/risk containment across the cutover so old positions
  cannot disappear when the successor activation changes. Report cohorts separately.
- Preserve all-or-none entry, 35-minute entry age, 35-minute monitoring ceiling,
  ten strategies and >=5R entry rule unless separately preregistered. The new
  timeout can close below the planned target; report this honestly.
- Preserve at least 30 test days and 100 compliant completed trades as minimum
  evidence gates, not sufficient proof. Freeze admission/data-cut and pending
  position treatment so a completed-only subset cannot silently omit open losses.
- A confirmatory readout requires all admitted orders through the preregistered
  data cut to be terminal and reconciled, with horizon failures absent. Otherwise
  report RUNNING/INCOMPLETE, including all pending and failed cases.
- Require validated entry/exit costs and funding evidence before realistic
  net-R claims. Endpoint positivity and gross paper returns are not profitability.
- Paper only: no exchange authority, live orders, threshold activation or
  production promotion is granted by this proposal.

## Required tests and deployment gates

Test the clock origin, exact 24h and 24h+35m boundaries, delayed LIMIT fill,
LONG/SHORT timeout prices, SL/TP precedence, missing quotes, insufficient depth,
monitoring gaps, no delayed profitable relabeling, duplicate/replayed observations,
and legacy exposure across activation. The six gate-visibility tests in this PR
do not establish any of these future timeout-execution behaviors.

Resolve the scientific review first. Then implement and test the timeout model,
evaluator denominator and successor activation transaction; verify the final
fingerprint; prepare rollback and monitoring; and obtain the required deployment
authorization. Do not merge/deploy/activate merely because this draft exists.
