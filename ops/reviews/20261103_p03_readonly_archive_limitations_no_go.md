# P0.3 READ-ONLY HISTORICAL ARCHIVE — PARTIAL SOURCE CENSUS (NO-GO)

Captured 2026-11-03 UTC from connected Alpha Hunter Supabase (PostgreSQL 17.6), while preserving the original protected scanner, database, 3 positions, main and draft PRs #378–#380. **No production writes or secrets.**

## Actually archived (public-safe, reproducible)
- `20261103_p03_readonly_historical_census_no_go.json` contains 31 UTC date rows, 2026-10-04 through partially completed 2026-11-03, counts and per-day SHA-256 commitments. Each day commits to every *observed* canonical `RENDER_CRON` parent run ID, UTC scan timestamp, advertised count, saved child count, parent JSONB SHA256 and sorted child symbol identity SHA256. It does **not** contain raw position, quote or client data.
- `20261103_p03_readonly_historical_census_recheck.sql` is the **exact SELECT-only SQL** for independently rerunning these commitments from the original database, subject to the necessary authorisation.
- `tests/test_p03_readonly_census_archive_no_go_v01.py` proves the archive fails the PR #380 detached-signed *full-row* validator, even if someone signs the incomplete aggregate after capture. Reproducing a DB digest does not authenticate its upstream origin.

Observed source census: **2,160** identified canonical parent runs, **259** parent runs with **zero** persisted children, **129,372** advertised vs **113,846** persisted child rows, and **0** historical `_canonical_publication_state=VERIFIED` markers. These are source-database observations, **not** the complete independently scheduled run census. The packet cannot be promoted to scientific or production proof.

## Independent system observation — LIMITED corroboration only
Render protected cron `crn-d9nmbjbm8hqs73elu6hg` produced these logs on 2026-11-02:
- Log `dbkrkb6c6qcc73b953eg`, 08:02:02.291576604 UTC: cron job started.
- Log `be490bc4-4cec-470a-a398-dd9ab972e552`, 08:06:32.838713717 UTC: scanner reports collection timestamp `2026-11-02T08:05:45.707976+00:00`.
- Log `82e0a775-e01b-4233-9095-a71b745b793d`, 08:06:32.838722917 UTC: scanner reports **61 deep-scanned contracts**.
- Connected Supabase parent run `714535034e77f6e9ea38bbb7d4f7c0ff` at exactly 08:05:45.707976 UTC advertises 61 and has 61 persisted child rows, but **no VERIFIED publication marker**. This is cross-system *one-event* corroboration only. Log messages are application-authored and do not authenticate exchange quotes or prove all database records. Render sampled 2026-10-05, 10-10, 10-20 and 10-26 hourly windows returned no logs; **do not infer scanner downtime from absent historical logs**.

## Why this archive cannot be certified complete
1. The authoritative external clock/run manifest for all required runs and exact original expected symbol universes is not independently signed or proven complete; stored parent rows can themselves be absent.
2. 259 known zero-child parent records cannot be repaired by copying later rows. No retroactive success or snapshot reclassification is allowed.
3. The first quote observations of all three paper positions remain `AMBIGUOUS`; their recorded history includes historical gaps exceeding the frozen 35-minute limit, and market quote provider signatures/source acknowledgements remain unavailable.
4. Original credentialed role verification, independent provider/alert receipts and real production-volume approval remain unsigned. Connected privileged SQL is **not** a genuine per-role HTTP test.

## Next source capture requirements — not auto-authorised
Authorised owner may run a controlled read-only export **in a private secured environment**: all relevant parent/child/position-receipt rows, paginated to exact inventory and time bounds, with the independent scheduler run list and original symbol lists. Seal a canonical manifest and exact row digests with a trusted Ed25519 key whose public verification key is distributed separately. Retain external provider timestamps/source acknowledgements and verify them against source runs; do not upload credentials, raw tokens or private client data to a public repository. Supply to draft #380's isolated validator. Until separately verified, result remains `EVIDENCE_NO_GO`.

**PRODUCTION NO-GO.** No live trades, no merging, no production database changes, no hourly cron changes, no additional spending.
