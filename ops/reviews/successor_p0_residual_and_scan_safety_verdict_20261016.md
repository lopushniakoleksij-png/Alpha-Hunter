# Alpha Hunter next production priority — P0 paper residual and monitoring integrity
**2026-10-16 06:46:55 UTC, zero-spend read-only checkpoint. DRAFT PR #341 only.**

## Why P0 outranks additional P3 historical cost attribution
P3 has no independently proven decision→manual action→venue-fill link, so
execution-profitability research cannot qualify a real cost model. Meanwhile
the existing *paper* execution ledger still contains an **unmanaged,
unquarantined, partially filled residual** and some canonical parent scans
were committed with missing child and monitoring evidence. Correctness of
position inventory and continuous monitoring is a precondition for scientific
promotion. No new trade or infrastructure can remedy historical evidence.

## Reproducible evidence and strict classification
One SELECT-only forensic SQL:
`ops/reviews/successor_p0_residual_and_scan_gate_readonly_20261016.sql`,
executed against existing Supabase at **06:46:55 UTC**. No private order ID,
API credential, client order ID, email or actor identity is projected.
The live source view and physical ledger are not changed by the query.

**All-cohort ledger, not just managed-only convenience view:**
- 249 historical modeled paper order rows; 32 have strictly positive
  entry-minus-exit quantity, 0 have negative residual quantity.
- Of those 32: **10** appear in the managed protection view and all have
  both recorded STOP/TP leg identifiers; **21** have a quarantine; **one**
  is neither managed nor quarantined.
- Unexplained record: **NMRUSDT LONG**, submitted 2026-10-02 22:04:12 UTC,
  original modeled LIMIT qty **3.2**, later **1.5** filled 2026-10-03
  04:23:18 UTC at model fill price 11.595; state
  **PARTIALLY_FILLED**, remaining entered-minus-exited exposure **1.5**
  paper units, exited **0**.
- **Zero** recorded STOP/TP protective orders, **zero**
  per-position paper exit-monitoring attempts, **zero**
  entry/exit/reconciliation quarantine rows for this exact historical
  order. `paper_only=true`, `trade_permission=false`, exchange
  authority false and `order_path=NONE`: **NOT a real Bitget position**.
- Source view `alpha_hunter_paper_protection_open_v04` requires both
  an existing protection relation (INNER JOIN), aggregate filled
  `quantity >= original requested quantity` and latest event
  `state='FILLED'`. A 1.5-of-3.2 entry with latest
  `PARTIALLY_FILLED` and no protection is mechanically excluded.
  An empty managed view is **not proof of no exposure**. The *other*
  historical NMR paper order from Oct 2 with full entry/exit is separate
  and must not be used to mark this one closed.

**Canonical persistence diagnostic, rolling prior 24h:**
- Exactly **72 RENDER_CRON parents**; **68** have matching full child symbol
  counts; **4** fail the parent→child count equality.
- The same **4** lack recorded paper exit attempt rows. With only
  child-complete parents, there are **4 inter-scan intervals longer than**
  frozen **2,100s**; maximum **2,394s (39m54s)**, an overrun of **294s**.
- **Important:** parent/child scan intervals are not authenticated
  independent per-position quote/protection receipts. They establish
  insufficient necessary evidence and a fail-closed diagnostic, NOT a
  per-position operational continuity pass/fail based on external receipts.
  Also, an interrupted 35m chain is not retroactively repaired by
  subsequent successful scans or by synthetic CI fixtures.

**Independent canonical runtime logs corroborate every missing-child scan:**
Read-only Render app logs were inspected in the exact corresponding time
windows. In every case the same canonical parent is visible but the
symbol-snapshot write reports `Supabase: FAILED: Supabase upsert failed for
alpha_hunter_symbol_snapshots: HTTP 500` with PostgreSQL error
`57014 / canceling statement due to statement timeout`:

| Failed parent UTC | Supabase failure logged UTC | Child rows / declared symbols | Exit-attempt rows |
|---|---|---|---|
| 2026-10-15 17:23:31 | 17:24:30 | 0 / 61 | 0 |
| 2026-10-16 04:23:20 | 04:24:24 | 0 / 61 | 0 |
| 2026-10-16 05:23:27 | 05:24:25 | 0 / 61 | 0 |
| 2026-10-16 06:05:06 | 06:06:11 | 0 / 61 | 0 |

The **immediate failure stage** is now verified: source parent persisted
without completed child write and associated exit-attempt evidence. This
is strong evidence of **statement-timeout cancellation on the child upsert**.
It does **not** independently identify the deepest cause of excessive query
duration (e.g. a particular trigger, lock contention, source workload or
network/retry interaction), nor demonstrate transaction atomicity or
per-position monitoring safety. Do not declare persistence fixed by
the next successful scan. Preserve original 12s DB and 15s HTTP ceilings.

**SQL verdict:** `FAIL_CLOSED_RESIDUAL_OR_SCAN_EVIDENCE_INCOMPLETE`,
`all_cohort_continuous_monitoring_proven=false`,
`scientific_pass_or_admissions_permitted=false`.
Queries repeated at a different time can produce different rolling-24h
scan counts; historic failures must stay preserved.

## Root-cause boundary / next smallest safe repair
**Source-based cause of one blind spot is verified:** a fully-filled-only
managed view excludes positive partially filled order balances, so it
cannot be the primary all-cohort safety census. This is a diagnostic of
what the view includes/excludes, not proof the execution writer has one
simple fix, nor authority to change a production view.

1. In isolated synthetic PG16, model cumulative partial entry and exit,
   order state progression, quarantine and the entire all-cohort census.
   Require **every positive entry-minus-exit residual** to have a verified
   managed-monitor disposition or an explicit fail-visible quarantine/
   incident. Partial orders cannot silently disappear from the expected
   monitor inventory. Synthetic PASS remains separate from actual source
   proof.
2. Treat an incomplete parent-child commit or missing per-position
   receipt as **UNKNOWN/INCIDENT**, never as a complete monitor cycle.
   Preserve dual-source, independent-journal and critical-alert design
   previously proven *only offline*. Neither ongoing source reads nor
   paper protective **records** prove actual continuous venue liquidity
   / stop-fill safety.
3. Compare the exact source run evidence and logs behind the four
   incomplete parents using existing read-only records. Review a
   successor-only fail-closed acceptance contract; do not change current
   R10 production schema, triggers, role grants, job cadence, timeouts,
   paper history or active management while the financial and operational
   release gates remain blocked.
4. Operational response/remediation affecting R10 orders, quarantine
   classification or source roles **requires separate explicit owner
   approval**, read-back, rollback plan and formal safety gate. Do not
   silently insert an old quarantine row or protective stop, backfill old
   receipt chains or claim historical 35m repair. No Bitget trade
   authority is implied or approved.

## Immutable safety and cost boundaries
- Original Primary Hourly cron on main enabled; R10 37 admitted,
  1 completed, **4 original horizon-integrity failures** and halted
  admissions. Currently 10 managed paper positions have recorded both
  STOP/TP legs, while the 1 NMR paper partial remains unexplained.
- Frozen max **35 minutes = 2,100 seconds**. No relaxation or reset.
- P2 live observer/independent recipient alerts and genuinely prospective
  72-hour pilot blocked. P3 no real verified execution-attribution or net-R
  validation. Paper/live trading authority remains false.
- Earn-first, **USD $0 new spending**; USD25/mo future planning ceiling
  is not approval. No vendor account, paid trial, service, email, new
  infrastructure, production role, database migration, cron modification,
  GitHub merge or live order.
- This branch remains DRAFT. An offline green test never makes
  `source_authenticated`, `monitoring_qualified` or
  `scientific_pass` true.

**Next safety decision: P0 incomplete paper position inventory + scanner child
evidence — FAIL / INVESTIGATION ACTIVE. Production mutation — NO-GO.**
