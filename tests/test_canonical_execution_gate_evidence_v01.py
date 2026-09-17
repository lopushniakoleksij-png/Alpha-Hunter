from pathlib import Path

SQL = Path("canonical_execution_gate_evidence_v01.sql").read_text()


def test_contract_binds_canonical_evidence_ids_and_runs():
    required = [
        "alpha_hunter_execution_gate_evidence_v01",
        "ce.stage_snapshot_id=s.stage_snapshot_id",
        "pr.stage_snapshot_id=s.stage_snapshot_id",
        "a.account_snapshot_id=pr.account_snapshot_id",
        "ux.selection_run_id=s.source_run_id",
        "ce2.control_run_id=b.control_run_id",
        "ce2.source_run_id=b.source_run_id",
        "pr2.cost_evidence_id=b.cost_evidence_id",
        "cp2.source_run_id=b.source_run_id",
        "account_evidence->>'canonical_run_id'",
        "source_binding_valid",
    ]
    for marker in required:
        assert marker in SQL


def test_each_authorization_gate_requires_active_validated_registry_evidence():
    required = [
        "threshold_registry_status='ACTIVE'",
        "threshold_validated_at_utc is not null",
        "threshold_activated_at_utc is not null",
        "cost_model_status='ACTIVE_VALIDATED_COST_MODEL'",
        "cost_model_registry_status='ACTIVE'",
        "realistic_net_r_status in ('VERIFIED_FULL_COST_PATH','VERIFIED_NET_R')",
        "risk_policy_status='ACTIVE_VALIDATED_RISK_POLICY'",
        "risk_policy_registry_status='ACTIVE'",
        "risk_decision='ELIGIBLE_FOR_RISK_REVIEW'",
        "account_state_status='CONNECTED_READ_ONLY_COMPLETE'",
        "position_ledger_status='VERIFIED_SNAPSHOT'",
        "account_connection_status='CONNECTED_READ_ONLY'",
        "lower(coalesce(b.product_type,''))='usdt-futures'",
        "safety_status='PASS'",
        "data_freshness_status='FRESH'",
    ]
    for marker in required:
        assert marker in SQL


def test_fail_closed_blockers_are_explicit():
    blockers = [
        "CANONICAL_SOURCE_BINDING_INVALID",
        "MONEY_ENTRY_GATE_NOT_VALIDATED",
        "EXECUTION_COST_GATE_NOT_VALIDATED",
        "PORTFOLIO_RISK_GATE_NOT_VALIDATED",
        "ACCOUNT_STATE_NOT_CANONICAL_VERIFIED",
        "FUTURES_UNIVERSE_GATE_NOT_VERIFIED",
        "CONTROL_PLANE_SAFETY_OR_FRESHNESS_BLOCK",
        "SHADOW_SAFETY_BOUNDARY_INVALID",
    ]
    for blocker in blockers:
        assert blocker in SQL
    assert "jsonb_array_length(e.authorization_blockers)=0" in SQL


def test_paper_contract_cannot_enable_live_or_trade_permission():
    required = [
        "false as live_authorization_eligible",
        "true as shadow_only",
        "false as trade_permission",
        "'NONE'::text as order_path",
        "production_execution_enabled is false",
        "research_trade_permission is false",
        "revoke all on public.alpha_hunter_execution_gate_evidence_v01 from public,anon,authenticated",
        "grant select on public.alpha_hunter_execution_gate_evidence_v01 to service_role",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "/api/v2/mix/order/place-order",
        "/api/v3/trade/place-order",
        "insert into public.alpha_hunter_money_entry_threshold_sets",
        "insert into public.alpha_hunter_execution_cost_model_versions",
        "insert into public.alpha_hunter_risk_policy_versions",
        "update public.alpha_hunter_",
        "delete from public.alpha_hunter_",
        "production_execution_enabled=true",
        "trade_permission=true",
    ]
    lowered = SQL.lower()
    for marker in forbidden:
        assert marker.lower() not in lowered


def test_view_is_security_invoker_read_only_surface():
    assert "with (security_invoker=true)" in SQL
    assert "create or replace view public.alpha_hunter_execution_gate_evidence_v01" in SQL
    assert "paper_authorization_eligible" in SQL
