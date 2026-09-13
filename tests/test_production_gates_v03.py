from pathlib import Path

STAGE = Path('money_entry_stage_single_writer.sql').read_text()
GATES = Path('production_cost_risk_gates.sql').read_text()
CONTROL = Path('production_gates_v03_control_plane.sql').read_text()
ALL = '\n'.join([STAGE, GATES, CONTROL])


def test_stage_thresholds_are_evidence_gated_not_seeded():
    assert 'NO_ACTIVE_VALIDATED_THRESHOLD_SET' in STAGE
    assert "status='ACTIVE' and t.validated_at_utc is not null and t.activated_at_utc is not null" in STAGE
    assert "'thresholds_invented',false" in STAGE
    assert 'insert into public.alpha_hunter_money_entry_threshold_sets' not in STAGE.lower()
    for stage in ['T0_CONTROLLED_ENTRY', 'T1_ACCEPTANCE_CONFIRMED', 'T2_EXPANSION_CONFIRMED']:
        assert stage in STAGE


def test_stage_writer_is_append_only_and_fail_closed():
    assert 'trg_ah_money_entry_stage_snapshots_append_only' in STAGE
    assert 'trg_ah_money_entry_threshold_sets_append_only' in STAGE
    assert 'OPEN_POSITION_CONFLICT_NOT_CAPTURED' in STAGE
    assert 'LIQUIDITY_PASS_NOT_CAPTURED' in STAGE
    assert 'PARTICIPATION_EMERGING_NOT_CAPTURED' in STAGE
    assert "security definer\nset search_path = ''" in STAGE


def test_cost_model_is_not_seeded_and_net_r_is_withheld():
    assert 'NO_ACTIVE_VALIDATED_COST_MODEL' in GATES
    assert 'WITHHELD_UNTIL_VERIFIED_FULL_COST_PATH' in GATES
    assert "'realistic_net_r_claim_permitted',false" in GATES
    assert "'no_fee_or_slippage_values_invented',true" in GATES
    assert 'insert into public.alpha_hunter_execution_cost_model_versions' not in GATES.lower()
    assert "null,\n      case\n        when v_cost_model_id is null" in GATES


def test_risk_policy_is_not_seeded_and_is_veto_only():
    assert 'NO_ACTIVE_VALIDATED_RISK_POLICY' in GATES
    assert "risk_decision in ('BLOCK','ELIGIBLE_FOR_RISK_REVIEW')" in GATES
    assert "'execution_authorized',false" in GATES
    assert "'risk_is_veto_only',true" in GATES
    assert "'leverage_selected',false" in GATES
    assert 'insert into public.alpha_hunter_risk_policy_versions' not in GATES.lower()


def test_account_and_position_inputs_are_read_only_evidence_contracts():
    assert "connection_status in ('CONNECTED_READ_ONLY','DISCONNECTED','DATA_INSUFFICIENT')" in GATES
    assert 'schema_validated boolean not null default false' in GATES
    assert 'complete boolean not null default false' in GATES
    assert 'planned_risk_usdt double precision' in GATES
    assert 'POSITION_LEDGER_NOT_CONNECTED' in GATES


def test_seven_stage_control_plane_order_and_schedule():
    order = [
        "when 'ANSWER_KEY' then 1",
        "when 'PARENT_DIRECTION' then 2",
        "when 'MONEY_ENTRY_BRIDGE' then 3",
        "when 'MONEY_ENTRY_STAGE' then 4",
        "when 'MONEY_SCORECARD' then 5",
        "when 'COST_EVIDENCE' then 6",
        "when 'PORTFOLIO_RISK' then 7",
    ]
    for token in order:
        assert token in CONTROL
    for minute in ['10 * * * *', '11 * * * *', '12 * * * *', '13 * * * *', '14 * * * *', '15 * * * *', '16 * * * *', '20 * * * *']:
        assert minute in CONTROL
    assert 'expected_stage_count in (4,5,7)' in CONTROL


def test_readiness_gaps_do_not_become_execution_permission():
    for warning in [
        'READINESS_NO_ACTIVE_MONEY_ENTRY_THRESHOLDS',
        'READINESS_NO_ACTIVE_COST_MODEL',
        'READINESS_NO_ACTIVE_RISK_POLICY',
        'READINESS_NO_VERIFIED_ACCOUNT_STATE',
    ]:
        assert warning in CONTROL
    assert "v_should_incident:=v_status='FAILED'" in CONTROL
    assert 'RISK_ENGINE_AUTHORIZATION_BOUNDARY_VIOLATION' in CONTROL


def test_all_new_evidence_is_service_role_only_and_rls_protected():
    for table in [
        'alpha_hunter_money_entry_threshold_sets',
        'alpha_hunter_money_entry_stage_snapshots',
        'alpha_hunter_execution_cost_model_versions',
        'alpha_hunter_execution_cost_evidence',
        'alpha_hunter_risk_policy_versions',
        'alpha_hunter_account_state_snapshots',
        'alpha_hunter_open_position_snapshots',
        'alpha_hunter_portfolio_risk_assessments',
    ]:
        assert f'alter table public.{table} enable row level security' in ALL
        assert f'revoke all on table public.{table} from public,anon,authenticated' in ALL


def test_no_live_order_or_trade_permission_path_added():
    lowered = ALL.lower()
    forbidden = [
        'trade_permission=true',
        'trade_permission = true',
        'automatic_trade_execution=true',
        'place_order',
        'place-order',
        '/api/v2/mix/order/',
        '/api/v3/trade/',
    ]
    for token in forbidden:
        assert token not in lowered
    assert ALL.count('check (trade_permission=false)') >= 8
    assert ALL.count('check (shadow_only=true)') >= 8


def test_security_definers_pin_empty_search_path_and_old_warning_is_hardened():
    assert ALL.count("security definer\nset search_path = ''") >= 5
    assert "alter function public.alpha_hunter_block_direction_transition_mutation() set search_path = '';" in CONTROL
