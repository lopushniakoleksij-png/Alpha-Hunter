from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from typing import Optional


class ExecutionMode(str, Enum):
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderState(str, Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


TERMINAL_STATES = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}


class ExecutionSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    direction: str
    episode_id: str
    stage: str
    entry_type: str
    entry_price: float
    stop_price: float
    target_price: float
    quantity: float
    evidence_version: str
    strategy_version: str
    market_data_fresh: bool
    contract_eligible: bool
    money_entry_validated: bool
    cost_model_validated: bool
    portfolio_risk_eligible: bool
    account_state_verified: bool
    position_conflict: bool = False
    expires_at_utc: Optional[str] = None

    def __post_init__(self) -> None:
        direction = self.direction.upper()
        entry_type = self.entry_type.upper()
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")
        if entry_type not in {"LIMIT", "MARKET"}:
            raise ValueError("entry_type must be LIMIT or MARKET")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if min(self.entry_price, self.stop_price, self.target_price) <= 0:
            raise ValueError("prices must be positive")
        if direction == "LONG" and not (self.stop_price < self.entry_price < self.target_price):
            raise ValueError("LONG geometry must satisfy stop < entry < target")
        if direction == "SHORT" and not (self.target_price < self.entry_price < self.stop_price):
            raise ValueError("SHORT geometry must satisfy target < entry < stop")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "entry_type", entry_type)

    @property
    def intent_id(self) -> str:
        raw = "|".join(
            [
                self.symbol,
                self.direction,
                self.episode_id,
                self.stage,
                self.entry_type,
                f"{self.entry_price:.12g}",
                f"{self.stop_price:.12g}",
                f"{self.target_price:.12g}",
                f"{self.quantity:.12g}",
                self.evidence_version,
                self.strategy_version,
            ]
        )
        return sha256(raw.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True)
class ExecutionRecord:
    intent: TradeIntent
    mode: ExecutionMode
    state: OrderState = OrderState.CREATED
    client_order_id: Optional[str] = None
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    reason: Optional[str] = None


class ExecutionAuthorizer:
    """Fail-closed authorization boundary.

    LIVE is deliberately unavailable in this increment. PAPER/SHADOW must satisfy
    the same upstream evidence gates that future live execution will require.
    """

    REQUIRED_STAGES = {"T0_CONTROLLED_ENTRY", "T1_ACCEPTANCE_CONFIRMED", "T2_EXPANSION_CONFIRMED"}

    @classmethod
    def blockers(cls, intent: TradeIntent) -> list[str]:
        blockers: list[str] = []
        if intent.stage not in cls.REQUIRED_STAGES:
            blockers.append("MONEY_ENTRY_STAGE_NOT_EXECUTABLE")
        if not intent.market_data_fresh:
            blockers.append("STALE_MARKET_DATA")
        if not intent.contract_eligible:
            blockers.append("CONTRACT_NOT_ELIGIBLE")
        if not intent.money_entry_validated:
            blockers.append("MONEY_ENTRY_THRESHOLDS_UNVALIDATED")
        if not intent.cost_model_validated:
            blockers.append("EXECUTION_COST_MODEL_UNVALIDATED")
        if not intent.portfolio_risk_eligible:
            blockers.append("PORTFOLIO_RISK_BLOCK")
        if not intent.account_state_verified:
            blockers.append("ACCOUNT_STATE_UNVERIFIED")
        if intent.position_conflict:
            blockers.append("OPEN_POSITION_CONFLICT")
        return blockers

    @classmethod
    def authorize(cls, intent: TradeIntent, mode: ExecutionMode) -> ExecutionRecord:
        if mode is ExecutionMode.LIVE:
            raise ExecutionSafetyError("LIVE_EXECUTION_HARD_DISABLED_PENDING_PRODUCTION_GATES")
        blockers = cls.blockers(intent)
        if blockers:
            return ExecutionRecord(
                intent=intent,
                mode=mode,
                state=OrderState.REJECTED,
                reason="|".join(blockers),
            )
        return ExecutionRecord(
            intent=intent,
            mode=mode,
            state=OrderState.AUTHORIZED,
            client_order_id=f"AH-{intent.intent_id}",
        )


class PaperExecutionStateMachine:
    """Deterministic execution lifecycle with no exchange write path."""

    @staticmethod
    def submit(record: ExecutionRecord) -> ExecutionRecord:
        if record.mode is ExecutionMode.LIVE:
            raise ExecutionSafetyError("LIVE_EXECUTION_HARD_DISABLED_PENDING_PRODUCTION_GATES")
        if record.state is not OrderState.AUTHORIZED:
            raise ExecutionSafetyError("ONLY_AUTHORIZED_INTENTS_CAN_BE_SUBMITTED")
        if not record.client_order_id:
            raise ExecutionSafetyError("CLIENT_ORDER_ID_REQUIRED")
        return replace(record, state=OrderState.SUBMITTED)

    @staticmethod
    def apply_fill(record: ExecutionRecord, fill_quantity: float, fill_price: float) -> ExecutionRecord:
        if record.state not in {OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED}:
            raise ExecutionSafetyError("FILL_NOT_ALLOWED_IN_CURRENT_STATE")
        if fill_quantity <= 0 or fill_price <= 0:
            raise ValueError("fill quantity and price must be positive")
        remaining = record.intent.quantity - record.filled_quantity
        if fill_quantity > remaining + 1e-12:
            raise ExecutionSafetyError("OVERFILL_REQUIRES_RECONCILIATION")

        old_notional = (record.average_fill_price or 0.0) * record.filled_quantity
        new_filled = record.filled_quantity + fill_quantity
        new_average = (old_notional + fill_price * fill_quantity) / new_filled
        new_state = OrderState.FILLED if abs(new_filled - record.intent.quantity) <= 1e-12 else OrderState.PARTIALLY_FILLED
        return replace(
            record,
            state=new_state,
            filled_quantity=new_filled,
            average_fill_price=new_average,
        )

    @staticmethod
    def cancel(record: ExecutionRecord, reason: str = "CANCELLED_BY_POLICY") -> ExecutionRecord:
        if record.state in TERMINAL_STATES:
            raise ExecutionSafetyError("TERMINAL_ORDER_CANNOT_BE_CANCELLED")
        if record.filled_quantity > 0:
            return replace(record, state=OrderState.RECONCILIATION_REQUIRED, reason="PARTIAL_FILL_CANCEL_REQUIRES_POSITION_RECONCILIATION")
        return replace(record, state=OrderState.CANCELLED, reason=reason)

    @staticmethod
    def expire(record: ExecutionRecord) -> ExecutionRecord:
        if record.state in TERMINAL_STATES:
            return record
        if record.filled_quantity > 0:
            return replace(record, state=OrderState.RECONCILIATION_REQUIRED, reason="PARTIAL_FILL_EXPIRED_REQUIRES_POSITION_RECONCILIATION")
        return replace(record, state=OrderState.EXPIRED, reason="INTENT_EXPIRED")


def live_execution_available() -> bool:
    """Explicit safety contract for this increment."""
    return False
