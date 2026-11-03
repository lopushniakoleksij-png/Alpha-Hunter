# Alpha Hunter P0.1 — sealed activation guards and real cost-floor evidence
2 November 2026 UTC | ISOLATED RESEARCH | RELEASE NO-GO

## Guard function acceptance
Exact catalog-derived R8, R9, R10 profitability guard functions are in tests/fixtures/p0_r8_r9_r10_sealed_guard_isolated_20261102.sql. Minimal synthetic execution-activation rowtypes are provided, NOT complete production counterpart schemas.

The offline PG16/17 runner ops/reviews/phase2_r8_r9_r10_activation_guard_contract_v01.py tests each recognized cohort: missing exact execution activation prevents a generic activation; wrong timestamp and fingerprint throw; matching synthetic counterparts create only synthetic generic activation rows with shadow_only=true, trade_permission=false, production_promotion_permitted=false and order_path=NONE. Rollback leaves no orphan activation. R10 scientific-role segregation is checked.

PG16+PG17 PASS: GitHub Actions run 41448859530 at SHA 6ad39db7974c35e0d7668cdaf8b289bdbe9337d3, artifacts 13143108874 and 13143562148. The original R8/R9/R10 experiment and production DB were never modified.

## Real cost-floor status from read-only production query
public.alpha_hunter_execution_cost_floor_status_v01 returned five scopes on 2 November 2026:
- ALL: 36,683 recent cost-evidence quote snapshots, 36,683 with valid bid/ask; observed median taker fee 6.00000147449336 bps; descriptive median spread 6.00240096038516 bps; descriptive two-taker-fees-plus-spread floor 18.0024039093719 bps.
- Descriptive median floors: FAIR ~25.876 bps, GOOD ~19.476 bps, HIGH ~13.057 bps, POOR ~41.288 bps.
- Every observed scope reported cost_model_validated=false, cost_model_activation_permitted=false, realistic_net_r_claim_permitted=false, trade_permission=false.

The cost floor is a descriptive lower bound, NOT a validated execution-cost model. It omits a validated slippage/latency/market-impact/adverse-selection/funding chain. It cannot establish profitability or trading authority. Reproducible SELECT: ops/reviews/20261102_p0_r8_r9_r10_cost_gate_READ_ONLY.sql.

## Still BLOCKED
1. Exact complete source-lineage for the live cost-floor view, realized fee provenance and realistic forward-outcome percentile/cost distributions; previous payoff trigger test used an empty synthetic cost-floor view and zero valid historic outcomes.
2. Complete execution activation tables and procedures and scientific interlocks (only exact guard bodies tested with minimal ephemeral row types).
3. Simultaneous full-size, fully authenticated PostgREST 57014, lost-ack, p95/p99, WAL/locks/rollback under realistic mixed load.
4. Effective real Supabase service_role and SECURITY DEFINER permissions, independently authenticated quote and alert receipts.
5. Independent DBA/security/science/operations signoffs plus safe successor-only release isolation.

All three modeled paper positions keep unresolved ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT, with their recorded protective legs unchanged. No live orders, experiment reset, historical backfill, P0 cron or R9/R10 changes, main merge, production migration, deployment or new infrastructure purchase. Production NO-GO, spend £0.
