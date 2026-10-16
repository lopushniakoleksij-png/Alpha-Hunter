"""Successor-only *synthetic* residual exit accounting contract.

No market data collection, database or exchange access. This module cannot
create a real fill and cannot supply scientific profitability evidence.
Inputs represent isolated test fixtures, NEVER authenticated provider receipts.
The sealed R9 engine does not import or call this module.

A proposed partial fill plus verified residual guard acknowledgements are
applied as ONE isolated state transition. If a synthetic fill could have
occurred but residual protection cannot be proved, state is HALTED_UNRESOLVED;
it is never silently reported as safely open or profitably closed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

MODEL = "SUCCESSOR_SYNTHETIC_EXIT_RESIDUAL_V0"
# RESEARCH-only limits, not approved risk parameters and not R9 configuration.
MAX_RESEARCH_TAKER_FEE_BPS = Decimal("20")
MAX_RESEARCH_SLIPPAGE_BPS = Decimal("25")


class RejectedTransition(ValueError):
    """Cannot accept the supplied synthetic evidence as a valid transition."""


def dec(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise RejectedTransition("BOOLEAN_NUMERIC_INVALID")
    try:
        d = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise RejectedTransition("INVALID_DECIMAL") from None
    if not d.is_finite():
        raise RejectedTransition("NONFINITE_DECIMAL")
    return d


def utc(value: str) -> datetime:
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        raise RejectedTransition("INVALID_TIMESTAMP") from None
    if d.tzinfo is None or d.utcoffset() is None:
        raise RejectedTransition("TIMEZONE_REQUIRED")
    return d.astimezone(timezone.utc)


def digest(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class Guard:
    quantity: Decimal
    stop_price: Decimal
    target_price: Decimal
    stop_id: str
    target_id: str
    oco_group: str
    stop_ack: str
    target_ack: str
    revision: int
    observed_at_utc: str
    status: str = "ARMED"  # ARMED for nonzero; CANCELLED for terminal


@dataclass(frozen=True)
class Fill:
    event_id: str
    receipt_sha256: str
    quote_id: str
    time_utc: str
    quantity: Decimal
    exit_price: Decimal
    best_bid: Decimal
    best_ask: Decimal
    visible_exit_size: Decimal
    fee_bps: Decimal
    # Only isolated synthetic receipts accepted by this test state machine.
    evidence_kind: str = "ISOLATED_SYNTHETIC_RECEIPT"
    receipt_status: str = "SIMULATED_CONFIRMED"


@dataclass(frozen=True)
class Position:
    position_id: str
    symbol: str
    direction: str
    entry_quantity: Decimal
    remaining: Decimal
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    original_entry_fee: Decimal
    allocated_entry_fee: Decimal
    realized_gross: Decimal
    realized_exit_fee: Decimal
    diagnostic_spread: Decimal
    diagnostic_slippage: Decimal
    guard: Guard
    fills: tuple[Fill, ...]
    revision: int
    last_event_at_utc: str
    integrity_state: str = "PROTECTED"
    incident: str | None = None
    # Not a provider confirmation and not execution/reporting authorization.
    paper_only: bool = True
    trade_permission: bool = False
    exchange_authority: bool = False
    production_promotion_permitted: bool = False
    profitability_claim_permitted: bool = False


@dataclass(frozen=True)
class Result:
    status: str
    position: Position
    gross_realized: Decimal
    fees_deducted: Decimal
    net_realized_ex_funding: Decimal
    execution_price_verified: bool = False
    source_authentication: str = "ISOLATED_SYNTHETIC_ONLY"
    counterfactual_only: bool = True
    trade_permission: bool = False
    production_promotion_permitted: bool = False
    profitability_claim_permitted: bool = False


def _result(status: str, p: Position) -> Result:
    return Result(status, p, p.realized_gross,
                  p.allocated_entry_fee + p.realized_exit_fee,
                  p.realized_gross - p.allocated_entry_fee - p.realized_exit_fee)


def initial_position(
    *, position_id: str, symbol: str, direction: str,
    quantity: Any, entry_price: Any, stop: Any, target: Any,
    entry_fee: Any, initial_guard: Guard, opened_at_utc: str,
) -> Position:
    q, ep, sl, tp, fee = map(dec, (quantity,entry_price,stop,target,entry_fee))
    if not position_id or not symbol or direction not in ("LONG","SHORT"):
        raise RejectedTransition("INVALID_POSITION_IDENTITY")
    if not (q > 0 and ep > 0 and sl > 0 and tp > 0 and fee >= 0):
        raise RejectedTransition("INVALID_OPEN_POSITION")
    if not ((sl < ep < tp) if direction=="LONG" else (tp < ep < sl)):
        raise RejectedTransition("INVALID_OPEN_PROTECTIVE_GEOMETRY")
    utc(opened_at_utc)
    _validate_guard(initial_guard, q, sl, tp, expected_revision=0, after=opened_at_utc)
    return Position(
        position_id=position_id, symbol=symbol, direction=direction,
        entry_quantity=q, remaining=q,entry_price=ep,stop_price=sl,target_price=tp,
        original_entry_fee=fee,allocated_entry_fee=Decimal(0),
        realized_gross=Decimal(0),realized_exit_fee=Decimal(0),
        diagnostic_spread=Decimal(0),diagnostic_slippage=Decimal(0),
        guard=initial_guard,fills=(),revision=0,last_event_at_utc=opened_at_utc,
    )


def _validate_guard(
    guard: Guard, remaining: Decimal, sl: Decimal, tp: Decimal,
    *, expected_revision: int, after: str,
) -> None:
    if guard.revision != expected_revision:
        raise RejectedTransition("GUARD_REVISION_NOT_MATCHED")
    if not guard.stop_id or not guard.target_id or guard.stop_id == guard.target_id:
        raise RejectedTransition("GUARD_IDS_MISSING_OR_DUPLICATED")
    if not guard.oco_group or not guard.stop_ack or not guard.target_ack:
        raise RejectedTransition("GUARD_OCO_OR_ACK_MISSING")
    if guard.stop_ack == guard.target_ack:
        raise RejectedTransition("GUARD_ACKS_NOT_INDEPENDENT")
    if utc(guard.observed_at_utc) < utc(after):
        raise RejectedTransition("PROTECTIVE_ACK_PRECEDES_FILL")
    if dec(guard.quantity) != remaining:
        raise RejectedTransition("UNPROTECTED_RESIDUAL_OR_OVERSIZED_GUARD")
    if dec(guard.stop_price) != sl or dec(guard.target_price) != tp:
        raise RejectedTransition("PROTECTIVE_RISK_GEOMETRY_CHANGED")
    if guard.status != ("ARMED" if remaining > 0 else "CANCELLED"):
        raise RejectedTransition("GUARD_STATUS_NOT_ACKNOWLEDGED")


def apply_synthetic_exit(
    position: Position, fill: Fill, *, next_guard: Guard | None,
    expected_revision: int,
) -> Result:
    """Single-event, sequential isolated state transition; never actual trading.

    Quote size and modeled receipts alone cannot attest exchange execution.
    Caller must separately retain authenticated provider event and guard
    custody before any possible future real-world implementation.
    """
    p = position
    if p.integrity_state != "PROTECTED":
        raise RejectedTransition("INTEGRITY_HALT_STAYS_HALTED")
    if not p.paper_only or p.trade_permission or p.exchange_authority or p.production_promotion_permitted:
        raise RejectedTransition("NO_AUTHORITY_CONTRACT_VIOLATION")
    if not fill.event_id or not digest(fill.receipt_sha256) or not fill.quote_id:
        raise RejectedTransition("SYNTHETIC_RECEIPT_IDENTITY_MISSING")
    existing = {x.event_id: x for x in p.fills}
    if fill.event_id in existing:
        if existing[fill.event_id] == fill:
            return _result("DUPLICATE_NOOP", p)
        # A contradictory event ID makes book-state custody untrustworthy.
        halted = replace(p, integrity_state="HALTED_UNRESOLVED",
                         incident="CONFLICTING_EVENT_ID")
        return _result("HALTED_UNRESOLVED", halted)
    if expected_revision != p.revision:
        raise RejectedTransition("STALE_EXPECTED_REVISION")
    if any(x.quote_id == fill.quote_id for x in p.fills):
        raise RejectedTransition("REUSED_MARKET_OBSERVATION_NOT_EXECUTION_CUSTODY")
    if fill.evidence_kind != "ISOLATED_SYNTHETIC_RECEIPT" or fill.receipt_status != "SIMULATED_CONFIRMED":
        raise RejectedTransition("PROVIDER_FILL_EVIDENCE_NOT_SUPPORTED_BY_RESEARCH")
    if utc(fill.time_utc) <= utc(p.last_event_at_utc):
        raise RejectedTransition("NONMONOTONE_OR_PRE_ENTRY_EVENT")
    q, price, bid, ask, visible, fee_bps = map(
        dec, (fill.quantity,fill.exit_price,fill.best_bid,fill.best_ask,
              fill.visible_exit_size,fill.fee_bps)
    )
    if not (q > 0 and q <= p.remaining):
        raise RejectedTransition("OVERFILL_ZERO_OR_NEGATIVE_FILL")
    if not (0 < bid <= ask and price > 0 and visible > 0):
        raise RejectedTransition("INVALID_QUOTE_OR_FILL_PRICE")
    if q > visible:
        raise RejectedTransition("FILL_EXCEEDS_SINGLE_OBSERVED_LEVEL")
    if not (0 <= fee_bps <= MAX_RESEARCH_TAKER_FEE_BPS):
        raise RejectedTransition("UNAPPROVED_FEE_BOUND")
    exit_side_cross = bid if p.direction=="LONG" else ask
    # No bonus from optimistic market-price improvement in this model.
    adverse_bps = (
        (exit_side_cross - price) / exit_side_cross
        if p.direction=="LONG" else (price - exit_side_cross)/exit_side_cross
    ) * Decimal(10000)
    if not (0 <= adverse_bps <= MAX_RESEARCH_SLIPPAGE_BPS):
        raise RejectedTransition("UNAPPROVED_SLIPPAGE_OR_PRICE_IMPROVEMENT")
    new_remaining = p.remaining - q
    # The accepted synthetic event must be accompanied by contemporaneous
    # stop AND target OCO acknowledgments on the entire new residual, or
    # terminal cancellations acknowledged for BOTH legs.
    try:
        if next_guard is None:
            raise RejectedTransition("RESIDUAL_GUARD_ACK_MISSING")
        _validate_guard(next_guard, new_remaining,p.stop_price,p.target_price,
                        expected_revision=p.revision+1,after=fill.time_utc)
        if next_guard.oco_group != p.guard.oco_group:
            raise RejectedTransition("OCO_GROUP_CHANGED_WITHOUT_APPROVAL")
        if new_remaining and (next_guard.stop_id == p.guard.stop_id and
                              next_guard.stop_ack == p.guard.stop_ack):
            raise RejectedTransition("RESIDUAL_PROTECTION_NOT_REACKNOWLEDGED")
    except RejectedTransition as exc:
        halted = replace(p,integrity_state="HALTED_UNRESOLVED",
                         incident=str(exc))
        return _result("HALTED_UNRESOLVED",halted)

    ratio = q/p.entry_quantity
    allocated = (p.original_entry_fee-p.allocated_entry_fee
                 if new_remaining==0 else p.original_entry_fee*ratio)
    signed = Decimal(1) if p.direction=="LONG" else Decimal(-1)
    gross = signed*(price-p.entry_price)*q
    exit_fee = price*q*fee_bps/Decimal(10000)
    # Spread/slippage are already reflected in price; diagnostics only.
    spread = (ask-bid)*q/Decimal(2)
    slippage = abs(price-exit_side_cross)*q
    new_state = replace(
        p, remaining=new_remaining,
        allocated_entry_fee=p.allocated_entry_fee+allocated,
        realized_gross=p.realized_gross+gross,
        realized_exit_fee=p.realized_exit_fee+exit_fee,
        diagnostic_spread=p.diagnostic_spread+spread,
        diagnostic_slippage=p.diagnostic_slippage+slippage,
        guard=next_guard, fills=p.fills+(fill,),revision=p.revision+1,
        last_event_at_utc=fill.time_utc,
        integrity_state="CLOSED" if new_remaining==0 else "PROTECTED",
    )
    return _result("SIMULATED_CLOSED" if new_remaining==0
                   else "SIMULATED_PARTIAL_PROTECTED",new_state)
