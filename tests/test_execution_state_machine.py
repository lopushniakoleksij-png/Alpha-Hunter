import pytest

from alpha_hunter.execution_state_machine import (
    ExecutionAuthorizer,
    ExecutionMode,
    ExecutionSafetyError,
    OrderState,
    PaperExecutionStateMachine,
    TradeIntent,
    live_execution_available,
)


def make_intent(**overrides):
    data = dict(
        symbol="TESTUSDT",
        direction="LONG",
        episode_id="episode-1",
        stage="T1_ACCEPTANCE_CONFIRMED",
        entry_type="LIMIT",
        entry_price=100.0,
        stop_price=98.0,
        target_price=106.0,
        quantity=1.5,
        evidence_version="evidence-v1",
        strategy_version="strategy-v1",
        market_data_fresh=True,
        contract_eligible=True,
        money_entry_validated=True,
        cost_model_validated=True,
        portfolio_risk_eligible=True,
        account_state_verified=True,
        position_conflict=False,
    )
    data.update(overrides)
    return TradeIntent(**data)


def test_live_execution_is_hard_disabled():
    assert live_execution_available() is False
    with pytest.raises(ExecutionSafetyError, match="LIVE_EXECUTION_HARD_DISABLED"):
        ExecutionAuthorizer.authorize(make_intent(), ExecutionMode.LIVE)


def test_authorization_fails_closed_when_any_gate_is_missing():
    record = ExecutionAuthorizer.authorize(
        make_intent(cost_model_validated=False, account_state_verified=False),
        ExecutionMode.PAPER,
    )
    assert record.state is OrderState.REJECTED
    assert "EXECUTION_COST_MODEL_UNVALIDATED" in record.reason
    assert "ACCOUNT_STATE_UNVERIFIED" in record.reason


def test_authorized_intent_gets_deterministic_client_order_id():
    intent = make_intent()
    first = ExecutionAuthorizer.authorize(intent, ExecutionMode.PAPER)
    second = ExecutionAuthorizer.authorize(intent, ExecutionMode.PAPER)
    assert first.state is OrderState.AUTHORIZED
    assert first.client_order_id == second.client_order_id
    assert first.client_order_id == f"AH-{intent.intent_id}"


def test_order_lifecycle_supports_partial_then_full_fill():
    record = ExecutionAuthorizer.authorize(make_intent(), ExecutionMode.PAPER)
    record = PaperExecutionStateMachine.submit(record)
    assert record.state is OrderState.SUBMITTED

    record = PaperExecutionStateMachine.apply_fill(record, 0.5, 100.1)
    assert record.state is OrderState.PARTIALLY_FILLED
    assert record.filled_quantity == pytest.approx(0.5)

    record = PaperExecutionStateMachine.apply_fill(record, 1.0, 100.2)
    assert record.state is OrderState.FILLED
    assert record.filled_quantity == pytest.approx(1.5)
    assert record.average_fill_price == pytest.approx((0.5 * 100.1 + 1.0 * 100.2) / 1.5)


def test_partial_fill_cancel_requires_reconciliation():
    record = ExecutionAuthorizer.authorize(make_intent(), ExecutionMode.PAPER)
    record = PaperExecutionStateMachine.submit(record)
    record = PaperExecutionStateMachine.apply_fill(record, 0.5, 100.1)
    record = PaperExecutionStateMachine.cancel(record)
    assert record.state is OrderState.RECONCILIATION_REQUIRED
    assert record.reason == "PARTIAL_FILL_CANCEL_REQUIRES_POSITION_RECONCILIATION"


def test_overfill_is_rejected():
    record = ExecutionAuthorizer.authorize(make_intent(), ExecutionMode.PAPER)
    record = PaperExecutionStateMachine.submit(record)
    with pytest.raises(ExecutionSafetyError, match="OVERFILL_REQUIRES_RECONCILIATION"):
        PaperExecutionStateMachine.apply_fill(record, 2.0, 100.0)


def test_geometry_is_direction_aware():
    with pytest.raises(ValueError):
        make_intent(stop_price=101.0)

    short = make_intent(direction="SHORT", entry_price=100.0, stop_price=102.0, target_price=94.0)
    assert short.direction == "SHORT"
