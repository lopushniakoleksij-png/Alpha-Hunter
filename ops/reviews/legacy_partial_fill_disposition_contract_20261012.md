# P1 legacy paper partial-fill disposition — review contract v0.1 (2026-10-12)

**STATUS: DESIGN + READ-ONLY EVIDENCE ONLY. No applied repair.** This document accompanies draft PR #337, issue #338, and immutable frozen R10 incident #334. It is not an instruction to run a trade, close a position, insert a quarantine record, merge, migrate, restart a cron, or change a scientific test.

## P1 verified evidence (12 October 2026, UTC)

- Order `9975630880b549753d81aa4708eea321`, `NMRUSDT LONG`: submitted 2026-10-02 22:04:12.523274 UTC; **ordered 3.2; modeled fill 1.5** at 11.595 on 2026-10-03 04:23:18.759325 UTC; **remaining unfilled order quantity 1.7**. This unfilled amount is NOT a filled position.
- **Unexited modeled fill residual 1.5**: zero recorded exits, zero STOP/TP protective records, zero exit attempts, zero managed-protection membership, zero inspected entry/reconciliation quarantine, and no R10 successor identity. Model quality is `DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION`. No assertion about live Bitget exchange exposure follows.
- Today's all-history coverage SQL (the other file in PR #337) classified **33 positive residual orders: 11 managed protection records, 21 quarantined, 1 unprotected/unquarantined NMR**. Managed protection records do NOT prove future exit liquidity; quarantined is not closed. No all-history protection PASS is allowed.
- The independent all-history balance SQL in this PR was **executed read-only in Supabase on 12 October**: 249 orders, 216 `BALANCED_OR_UNFILLED`, 33 `POSITIVE_RESIDUAL_REQUIRES_COVERAGE_AUDIT`, and zero observed orphan/overfill/over-exit categories. This does NOT prove missing protection resolved.
- Existing R10 admission-open = 0 (explicit halt), admitted orders = 37, existing managed filled paper positions = 11 with two protective records each. Keep the separate known four R10 integrity failures immutable.

## Verified structural exclusion; causal limits

Current R8 reconciliation inventory joins only submissions at or after R8 activation, and NMR was submitted earlier. Current full-fill protection view requires fully filled order and existing protective records; NMR is partial with zero such records. These current predicates explain **why the record is invisible now**. They do not reconstruct historical deployment causality.

## Proposed successor-only historical incident disposition contract — NOT IMPLEMENTED

1. First append an *incident observation*, if separately approved, in an independently owned append-only review ledger (prefer a protected private schema, not the frozen `alpha_hunter_*` engine namespace). Stable unique identity: `(source='PAPER_LEDGER', order_id, finding_type='UNPROTECTED_POSITIVE_RESIDUAL')`. Reference original immutable order/fill IDs and source timestamps; do not rewrite original evidence.
2. Record `ordered_quantity=3.2`, `filled_quantity=1.5`, `exited_quantity=0`, `unfilled_entry_quantity=1.7`, `residual_exposure_quantity=1.5`, `protection_count=0`, paper-only provenance, and a UTC `observed_at` distinct from original economic event times. Pin a reviewed snapshot of source identities, audit version and reason. Reject negative, non-finite, or contradictory quantities.
3. Allow operational review state `OPEN_REVIEW` while the positive residual has no legitimate documented terminal exit. An append-only later review decision **cannot itself count as an exit fill, booked PnL, stop/target hit, horizon success, R10 membership, quarantine protection, or scientific-valid sample**.
4. Require explicit documented resolution criteria before a later review state may be marked resolved: exact original fill-vs-exit ledger reconciled, a genuine eligible forward event if any, independently verified evidence, no retroactive quote/fill creation, no silent loss of positive residual exposure. Where no defensible resolution is possible, keep the incident **OPEN / NOT_AUDITABLE**.
5. Preserve the 1.7 unfilled entry remainder as a separate concern; no future normal reconciliation/replay of that stale entry is allowed, and no synthetic cancellation with a backdated event. New successor engine design must explicitly define partial-fill protection vs strict all-or-none, sizing, reconciliation expiry, and marketable executable exit liquidity.
6. Review DDL, permissions, RLS/least privilege, idempotency, uniqueness, append-only immutability and separation from main deployment *later*. No DB migration or scanner code in this PR; do not activate via existing legacy quarantine tables solely to make the count look healthy.

## Falsifiable acceptance checklist for later authorized implementation

- Baseline direct read: NMR order = 3.2, sum fills = 1.5, sum exits = 0, positive residual = 1.5; no fabricated fees, PnL or stop.
- No cohort/date/lifecycle filter hides a positive residual, even a terminal-marked or partly filled row.
- Distinguish 11 managed vs 21 quarantined vs one NMR open exception; unknown source access => UNKNOWN, never PASS.
- Orphan fills/exits, filled > ordered and exited > filled fail explicitly. Do not infer a negative residual as a closed trade.
- Idempotency keyed to original source IDs; incident observations cannot modify orders, fills, exits, events, protection records or R9/R10 profitability denominators.
- Zero deployment/import of new logic under frozen `alpha_hunter/*.py` / `hourly.py`; R10 fingerprint, 24h/35m/5R thresholds, original 4 failed rows and halt unchanged.
- All already managed paper positions still receive forward canonical exit attempts and remain observed (do not infer executable protection from record presence alone). No exchange live authority.

## Stage gate

**P1 diagnosis + read-only measurement: PASS. P1 historical lifecycle remediation: OPEN / REVIEW_REQUIRED.**
Only a separately reviewed successor design and explicit owner-approved deployment boundary can advance remediation. Existing scanner and paper test continue without interruption. References: #338, #334, PR #337.
