# P2 monitoring-integrity roadmap — fresh read-only checkpoint and successor-only test handoff
**15 October 2026 ~10:35–10:37 UTC. Draft PR #341 only. $0 new infrastructure. NO production changes.**

## Roadmap transition: P1 isolated regression → P2
P1 historical modeled-paper partial-fill *diagnostic review*, including exact unchanged SQL on disposable PostgreSQL16 and read-only live classifications, has passed in **draft, unmerged PR #337**. P1 historical remediation has NOT been performed: issue #338 remains open, real ledger NMRUSDT LONG 1.5 modeled units positive residual, no exits, no stop/target, no recorded quarantine. The $0 revenue-first funding hold remains binding. Never conflate P1 regression correctness with safety incident closure.

## Latest fresh P2 read-only evidence — NO scientific continuity PASS
Authoritative PostgreSQL SELECTs (not persistent independently authenticated source receipts), performed 2026-10-15 10:35–10:37 UTC:

- Rolling 24h: **72 canonical** `RENDER_CRON` parent snapshots; **70** have symbol children equal to the parent declared count; **2 parent runs show zero symbol children** despite each declaring 60 symbols. **3** parent runs have zero modeled paper exit-monitor attempts, including one 61/61 child-complete run.
- Exact anomalous parents:
  - `60533ed6adddc49c20ec0917641a7581` at **2026-10-14 11:05:03.861431Z**: declared 61 symbols, 61 child symbols, **0** exit attempts;
  - `d0c8a18c50d948e38a7c0e00c5ec13ff` at **2026-10-14 13:23:44.373398Z**: declared 60, **0** children, **0** attempts;
  - `21cc1967e4b4debd549f55f1a2ccbfa0` at **2026-10-15 06:05:06.951196Z**: declared 60, **0** children, **0** attempts.
- Last 24h among the **10 currently managed residual positions**: **770 paper exit attempt rows**, **343 with missing/blank `evidence.quote_source`**; **10 per-position successive raw-attempt intervals >35 minutes**, largest **38.637 minutes**. Missing raw source label means a numeric quote is not an independently authenticated venue receipt.
- The 10 overshoots are the same contemporaneous interval per managed order from **2026-10-14 13:06:20.615394Z** (prior `source_run_id=5a4b09b9722c86b606309087d4e3c2ba`) to **13:44:58.832553Z** (next `source_run_id=d5af9f924ea70c65f5eb08c737cdc220`), with intermediate canonical parent `d0c8a18c50d948e38a7c0e00c5ec13ff` at 13:23:44Z having zero children and zero attempts. The **immediate HTTP persistence failure is now VERIFIED from actual Render logs**: Supabase POST failed after three attempts with `Read timed out. (read timeout=15)`. No evidence establishes whether the underlying delay originated in Supabase, network, PostgREST locking, or a different server-side bottleneck. Never backfill the missing observation or mark the interval `<=35m`.
- At the query instant **10:37:07 UTC** all 10 managed rows retained recorded STOP+TP legs, each had a latest modeled attempt younger than 35m (worst `13.657m`); none was `>35m` stale **at that instant**. This does NOT erase the earlier actual 38.637m gap or prove any prior receipt's quote-source integrity.
- 32 positive-residual historic paper order IDs across all cohorts = **10 managed, 21 quarantined (not verified closed), 1 unprotected NMR** at P1 10:33 UTC source read. Future counts must be recalculated from one independently attested transaction; historic managed-view membership alone is not full universe.
- Canonical `source_run_id`-joined subset within 24h held **690** recorded attempts of which **301** unlabeled (different denominator from 770 all attempts in window); do not mix metrics or imply that all rows have authenticated canonical parent lineage.

## Scientific and system interpretation
1. **P2 scanner-parent presence does NOT imply cycle completeness.** Missing child rows or exit attempts -> INCOMPLETE, not SUCCESS. A complete child set with zero exit attempts is still not position monitoring proof.
2. **P2 every-position raw cadence failed the frozen limit** in the historical 24h window. R10's maximum lag remains **35m (2100 seconds)**, immutable.
3. **P2 independently qualified quote/receipt continuity is UNPROVEN**: raw attempt timestamps, mutable labels, ephemeral CI journal and an inert P2 /healthz are insufficient. Missing provenance is a separate blocker even when a raw timestamp exists.
4. Existing draft PR #341 P0.3 isolated PG16 tests and one-shot Bitget HTTPS prove code/transport paths only, **not** a persistent source-attested monitored deployment or real notification delivery. P0.4 deployment spec is reviewed, but the owner has forbidden paying until verifiable earned revenue, plus a separate explicit charge/deployment permission.
5. **R10 status remains scientific FAIL_CLOSED**, admissions halted, no paper/live authority, no cohort/backfill reset. Main Render hourly scanner and Alpha Hunter Primary Hourly remain untouched.

## Additional REAL Render log forensic read — independent source verification
The *existing* canonical Render cron service (`crn-d9nmbjbm8hqs73elu6hg`) application logs were inspected **read-only** in the precise UTC windows. Render records all three affected run headers followed by the same storage error, with no need for a paid service:

| Source run / parent collected | Published parent/child/attempt state | Actual Render error |
|---|---|---|
| `60533ed6adddc49c20ec0917641a7581` / 2026-10-14 11:05:03.861431Z | 61 declared, 61 child, 0 attempts | `Supabase: FAILED: Supabase POST failed after 3 attempts: HTTPSConnectionPool(...): Read timed out. (read timeout=15)` at 11:06:04 UTC |
| `d0c8a18c50d948e38a7c0e00c5ec13ff` / 2026-10-14 13:23:44.373398Z | 60 declared, 0 child, 0 attempts | same exact client-reported POST timeout at 13:24:41 UTC |
| `21cc1967e4b4debd549f55f1a2ccbfa0` / 2026-10-15 06:05:06.951196Z | 60 declared, 0 child, 0 attempts | same exact client-reported POST timeout at 06:06:11 UTC |

All three logs also print a local snapshot file path and `Fast canonical scan complete; hourly auxiliary jobs deferred to the first cycle` after the failure. The main-branch source `alpha_hunter/storage.py` stores **parent before children and downstream paper reconciliation**, and `hourly.py` returns zero after a successful scanner subprocess / deferral. These explain why **a persisted parent and/or a completed cron burst log cannot prove symbol-child or modeled exit reconciliation success**.

**Evidence level: VERIFIED client-side HTTP persistence timeouts at those run times.** The exact failed destination request's table, database-server execution state, Supabase infrastructure cause, retries' database commit ambiguity and whether other request classes also failed are NOT determined from the printed line. The observed 35-minute gap is real for the raw modeled paper-exit attempts and must remain failed. Do not interpret a successful local snapshot as an independently stored position receipt.

**Recommended least-cost next gate:** Review successor-only, off-main atomic parent+children+attempts/receipt failure semantics in existing PR #341 tests, then require accurate `UNKNOWN/INCOMPLETE` classification for a primary HTTP POST timeout under actual contention. The existing isolated PG16/PostgREST evidence is relevant but is not a production fix. Do not increase SQL 12-second, HTTP 15-second or monitoring 35-minute limits or touch the current scanner.

## ONE P2 next zero-spend gate — verified HTTP persistence timeout incident follow-up
**The logged failure class is verified: three exhausted HTTPS Supabase POST retries ending in a 15-second read timeout.** The *next* successor-only task is to inspect existing atomic parent+child+attempt+receipt failure tests and specify the smallest fail-closed response to missing or ambiguous HTTP commit, using only isolated local PostgREST/PG16. The source-side reason for slow responses is not yet proved. Do not infer or assert an exact database table/lock root cause without server evidence. Do NOT increase existing 12s SQL/15s HTTP/35m limits, run duplicate scanners, restart or pay for a worker to conceal this.

### Falsifiable P2 acceptance for a later independent owner-approved forward pilot
- Direct source-transaction all-cohort filled-minus-exit inventory and dispositions are authenticated and independently durable, including NMR/quarantines. No missing or fabricated rows.
- Per-managed-order genuine quote acquisition binds source-run, exact venue instrument, timestamp, raw payload digest, positive book depth, independently sealed predecessor and exact observation. TLS is channel authentication, not exchange-signed quotes.
- Every contemporaneously managed position is prospectively observed continuously with **no interval >2100s**, including under transport, primary, journal, clock, replay and worker-restart faults. None of the observed bad historical cycles can be retroactively redeemed.
- Unverifiable inventory/quote/prior seal and unprotected paper residuals generate durable FAIL/UNKNOWN events, with independently confirmed external alert delivery rather than simulated or queued-only status.
- Full realistic cost/fill/outcome validation and frozen cohort sample/independence remain separate later **P3/P4** gates. Green P2 cannot prove profitability or confer trading permission.

**P2 VERDICT: DIAGNOSTIC RUN COMPLETE; MONITORING-INTEGRITY FAIL_CLOSED; NEXT GATE = SOURCE-RUN STAGE/LOG ROOT-CAUSE REVIEW. NO DEPLOYMENT OR SPEND.**
