# Alpha Hunter P0 — Hourly scoring-only successor and persistence compatibility
**Date:** 2026-11-04. **Status:** ISOLATED RESEARCH ONLY / NO PRODUCTION DEPLOYMENT.

## The defects this separates

1. Canonical `RENDER_CRON` parent/children/feature persistence occasionally fails during Supabase PostgREST timeouts, while cron may still report success. Real failure on 4 November 19:23 UTC: **61 declared, 0 children, 0 feature rows**; 19:43 UTC recovery: **61/61/61**. Neither a parent commit nor scheduler success proves usable evidence.
2. `private.alpha_hunter_collect_big_mover_parent_direction()` rejects sources older than **90 minutes**, but expensive `public.alpha_hunter_run_big_mover_shadow()` training runs only at `11 2,8,14,20 * * *`. The hourly consumer at `16 * * * *` fails between training cycles. PR #408 independently proves the cadence mismatch.

## New successor implementation

- `alpha_hunter/hourly_shadow_score.py`: small deterministic engine using **previously learned, digest-checked LONG and SHORT Python research signature profiles**, exact canonical `RENDER_CRON` parent, all persisted child symbols, and the *same run's* complete signal feature rows. It calls existing `build_live_candidates` and `rank_candidates` without training or contacting Bitget/Render/Supabase.
- `alpha_hunter/hourly_shadow_readback.py`: injectable **GET-only stable-latest** query contract, exact run ID and bounded child/feature reads; rereads newest canonical parent after fetching to reject concurrent head changes. No fallback to an older complete run, no database credentials or network logic in the module. Actual runtime reader authentication remains untested.
- `ops/reviews/p0_hourly_shadow_score_cli_v01.py`: read a local JSON fixture and write a research-only output **only after** every source-evidence gate succeeds. Does not read environment keys or call network.
- `tests/test_hourly_shadow_score_persistence_v01.py`: synthetic failure injection for zero/partial/duplicate child writes, cross-run data, incomplete features, stale source, scientific identity drift, training maturity, artifact tampering and no trading permission.

**Hard constraints:** source runtime and role exact `RENDER_CRON`; source fingerprint pinned; `snapshot-parent-v0.2` and exact run ID; parent count == 1:1 unique parent stubs == child rows == feature rows; scanner error_count=0; feature timestamps match the canonical parent; source freshness <=90m; pretrained profiles <=8h and training outcomes at least 24h mature; no source fabrication, filtering around failed symbols, or stale fallback. Any breach raises `HourlyScoringBlocked` before producing scores.

**Always:** `shadow_only=true`, `trade_permission=false`, `exchange_authority=false`, `production_promotion_permitted=false`, `order_path=NONE`. Candidate names such as `SHADOW_QUEUE` are research states, **not real-money or R10 admission permissions**.

## Reconciliation with existing persistence repair

This PR is intentionally **stacked on research PR #407** (itself stacked on #406/#378) to test compatibility with fail-closed canonical publish, child-readback and nonzero scanner-exit fixes. No change to the upstream protected scanner, frozen science, live orders, paper cohort, RLS, migrations, credentials, Render services or pg_cron.

**Why no production auto-wiring:** The current deployed six-hour SQL model uses `big-mover-signature-shadow-v0.2-db-forward`, while this isolated Python scorer consumes a `big-mover-signature-shadow-v0.1` training artifact. The existing SQL job does **not** persist validated reusable model profiles for that Python consumer. A real hourly successor therefore still needs an independently reviewed and version-pinned trained-profile export or a separate provably equivalent SQL-score-only artifact; no unproven algorithm swap is authorized.

The artifact's SHA-256 digest catches accidental corruption but does not authenticate ownership or scientific validity. A separate source-custody signing strategy is necessary if the artifact is to be trusted. The pure function assumes the caller has selected the **newest** canonical run; an eventual read-only adapter must prove that and must never substitute an older complete run without explicitly reporting the freshness gap.

## How to test without production or paid services

```bash
python -m pytest -q tests/test_hourly_shadow_score_persistence_v01.py
# With a SYNTHETIC test fixture containing all six required keys:
python -m ops.reviews.p0_hourly_shadow_score_cli_v01 \
  --input /tmp/alpha-hourly-synthetic.json \
  --output /tmp/alpha-hourly-research.json \
  --as-of-utc 2026-11-04T19:47:00Z
```

The CLI intentionally has no public/live credentials, automatic hourly schedule, network adapter or data writer. Do **not** schedule it on production yet.

## Release gate — remains NO-GO

- [ ] Full exact-commit GitHub Actions and offline test pass, with reproducible fixtures and no network.
- [ ] Real six-hour SQL-v0.2 profile export/custody provenance, or separately preregistered non-equivalent research model approval; version/fingerprint matching; no look-ahead.
- [x] Offline read-only exact latest-source query contract and synthetic head-change/failure tests; parent/children/features retrieval is GET-only and no old-run fallback.
- [ ] Independently authenticated production read-only adapter, real PostgREST pagination/roles and exact-source runtime validation under load; 0/61 failures and ambiguous ACK fail-closed in real isolated HTTP integration.
- [ ] Full paired PG16/PG17 + PostgREST fault, contention and latency tests from isolated #378/#406/#407; verify baseline alerts and <=35-minute monitoring continuity.
- [ ] Test scoring against independently archived forward/out-of-sample observations; check source timestamp, feature availability, LONG/SHORT direction, net execution costs, no hindsight and no claimed profit until sealed evidence.
- [ ] DBA, security, source-custody approvals; rollback tested on separate deployment; user approval for exact non-main release; NEVER merge to main while Render cron auto-deploy is on.
- [ ] No real orders, no exchange authority, no R10 admissions or scientific promotion.
