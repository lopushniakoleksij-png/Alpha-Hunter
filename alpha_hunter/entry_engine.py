from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from math import isfinite
from typing import Any


ENTRY_ENGINE_VERSION = "8.0-shadow"
MINIMUM_NET_RR = 2.20
MAXIMUM_STOP_ATR = 0.90
MAXIMUM_COST_R = 0.15
ENTRY_BAND_ATR = 0.20
MAXIMUM_CHASE_R = 0.25


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class EntryState(str, Enum):
    DISCOVERED = "DISCOVERED"
    IMPULSE_CONFIRMED = "IMPULSE_CONFIRMED"
    PULLBACK = "PULLBACK"
    ARMED = "ARMED"
    READY = "READY"
    ENTERED = "ENTERED"
    CLOSED = "CLOSED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class EntryStatus(str, Enum):
    NO = "NO"
    WATCH = "WATCH"
    READY = "READY"


TERMINAL_STATES = {
    EntryState.CLOSED,
    EntryState.INVALIDATED,
    EntryState.EXPIRED,
}


_FORWARD_TRANSITIONS = {
    (EntryState.DISCOVERED, "impulse_confirmed"): EntryState.IMPULSE_CONFIRMED,
    (EntryState.IMPULSE_CONFIRMED, "pullback_started"): EntryState.PULLBACK,
    (EntryState.PULLBACK, "geometry_armed"): EntryState.ARMED,
    (EntryState.ARMED, "trigger_ready"): EntryState.READY,
    (EntryState.READY, "entered"): EntryState.ENTERED,
    (EntryState.ENTERED, "closed"): EntryState.CLOSED,
}


@dataclass(frozen=True)
class EntryInputs:
    symbol: str
    side: Side
    anchor: float
    trigger_extreme: float
    pullback_extreme: float
    atr_5m: float
    spread: float
    tick_size: float
    current_price: float
    structural_target: float
    estimated_round_trip_cost: float
    data_fresh: bool
    direction_eligible: bool
    direction_change_clear: bool
    conflict_firewall_clear: bool
    liquidity_executable: bool
    price_accepted: bool
    aggressive_flow_confirmed: bool
    open_interest_confirmed: bool
    order_book_confirmed: bool


@dataclass(frozen=True)
class EntryDecision:
    version: str
    symbol: str
    side: str
    status: str
    state: str
    entry: float | None
    stop: float | None
    target: float | None
    risk: float | None
    net_rr: float | None
    stop_atr: float | None
    cost_r: float | None
    confirmation_count: int
    hard_vetoes: tuple[str, ...]
    missing_confirmations: tuple[str, ...]
    reason: str
    shadow_only: bool = True
    trade_permission: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def transition_entry_state(current: EntryState, event: str) -> EntryState:
    """Advance the deterministic V8 state machine without skipping stages."""
    if current in TERMINAL_STATES:
        return current
    if event == "invalidated":
        return EntryState.INVALIDATED
    if event == "expired" and current is not EntryState.ENTERED:
        return EntryState.EXPIRED
    try:
        return _FORWARD_TRANSITIONS[(current, event)]
    except KeyError as exc:
        raise ValueError(f"Invalid V8 transition: {current.value} + {event}") from exc


def _valid_number(value: float, *, allow_zero: bool = False) -> bool:
    if not isfinite(value):
        return False
    return value >= 0 if allow_zero else value > 0


def _empty_decision(inputs: EntryInputs, *reasons: str) -> EntryDecision:
    return EntryDecision(
        version=ENTRY_ENGINE_VERSION,
        symbol=inputs.symbol.upper(),
        side=inputs.side.value,
        status=EntryStatus.NO.value,
        state=EntryState.INVALIDATED.value,
        entry=None,
        stop=None,
        target=None,
        risk=None,
        net_rr=None,
        stop_atr=None,
        cost_r=None,
        confirmation_count=0,
        hard_vetoes=tuple(reasons),
        missing_confirmations=(),
        reason="; ".join(reasons),
    )


def evaluate_entry(inputs: EntryInputs) -> EntryDecision:
    """Evaluate one V8 first-pullback reclaim candidate in shadow mode.

    This function calculates exact entry geometry and emits READY/WATCH/NO.
    It deliberately cannot grant production trade permission.
    """
    if not inputs.symbol.strip():
        return _empty_decision(inputs, "symbol_missing")

    numeric_fields = {
        "anchor_invalid": inputs.anchor,
        "trigger_invalid": inputs.trigger_extreme,
        "pullback_invalid": inputs.pullback_extreme,
        "atr_invalid": inputs.atr_5m,
        "spread_invalid": inputs.spread,
        "tick_invalid": inputs.tick_size,
        "price_invalid": inputs.current_price,
        "target_invalid": inputs.structural_target,
    }
    invalid = [name for name, value in numeric_fields.items() if not _valid_number(value)]
    if not _valid_number(inputs.estimated_round_trip_cost, allow_zero=True):
        invalid.append("cost_invalid")
    if invalid:
        return _empty_decision(inputs, *invalid)

    buffer = max(2.0 * inputs.spread, 0.10 * inputs.atr_5m)
    if inputs.side is Side.LONG:
        entry = inputs.trigger_extreme + inputs.tick_size
        stop = inputs.pullback_extreme - buffer
        gross_reward = inputs.structural_target - entry
        band_low = inputs.anchor
        band_high = inputs.anchor + ENTRY_BAND_ATR * inputs.atr_5m
        geometry_valid = stop < entry < inputs.structural_target
    else:
        entry = inputs.trigger_extreme - inputs.tick_size
        stop = inputs.pullback_extreme + buffer
        gross_reward = entry - inputs.structural_target
        band_low = inputs.anchor - ENTRY_BAND_ATR * inputs.atr_5m
        band_high = inputs.anchor
        geometry_valid = inputs.structural_target < entry < stop

    risk = abs(entry - stop)
    if not geometry_valid or risk <= 0:
        return _empty_decision(inputs, "invalid_entry_stop_target_geometry")

    stop_atr = risk / inputs.atr_5m
    cost_r = inputs.estimated_round_trip_cost / risk
    net_reward = gross_reward - inputs.estimated_round_trip_cost
    net_rr = net_reward / risk
    inside_entry_band = band_low <= entry <= band_high
    current_inside_band = band_low <= inputs.current_price <= band_high
    if inputs.side is Side.LONG:
        not_chased = inputs.current_price <= entry + MAXIMUM_CHASE_R * risk
    else:
        not_chased = inputs.current_price >= entry - MAXIMUM_CHASE_R * risk

    vetoes: list[str] = []
    checks = (
        (inputs.data_fresh, "stale_or_incomplete_data"),
        (inputs.direction_eligible, "direction_not_eligible"),
        (inputs.direction_change_clear, "direction_change_unresolved"),
        (inputs.conflict_firewall_clear, "position_conflict"),
        (inputs.liquidity_executable, "liquidity_not_executable"),
        (inside_entry_band and current_inside_band and not_chased, "outside_entry_band_or_chased"),
        (stop_atr <= MAXIMUM_STOP_ATR, "stop_too_wide"),
        (cost_r <= MAXIMUM_COST_R, "cost_exceeds_0.15R"),
        (net_rr >= MINIMUM_NET_RR, "net_rr_below_2.20"),
    )
    vetoes.extend(reason for passed, reason in checks if not passed)

    confirmation_map = {
        "aggressive_flow": inputs.aggressive_flow_confirmed,
        "open_interest": inputs.open_interest_confirmed,
        "order_book": inputs.order_book_confirmed,
    }
    confirmation_count = sum(confirmation_map.values())
    missing = tuple(name for name, passed in confirmation_map.items() if not passed)

    if vetoes:
        status = EntryStatus.NO
        state = EntryState.INVALIDATED
        reason = "Hard veto: " + ", ".join(vetoes)
    elif not inputs.price_accepted:
        status = EntryStatus.WATCH
        state = EntryState.ARMED
        reason = "Awaiting price acceptance above/below the reclaim anchor"
    elif confirmation_count < 2:
        status = EntryStatus.WATCH
        state = EntryState.ARMED
        reason = "Awaiting at least two independent confirmation families"
    else:
        status = EntryStatus.READY
        state = EntryState.READY
        reason = "V8 shadow READY: geometry, PLA and confirmation passed"

    return EntryDecision(
        version=ENTRY_ENGINE_VERSION,
        symbol=inputs.symbol.upper(),
        side=inputs.side.value,
        status=status.value,
        state=state.value,
        entry=round(entry, 12),
        stop=round(stop, 12),
        target=round(inputs.structural_target, 12),
        risk=round(risk, 12),
        net_rr=round(net_rr, 6),
        stop_atr=round(stop_atr, 6),
        cost_r=round(cost_r, 6),
        confirmation_count=confirmation_count,
        hard_vetoes=tuple(vetoes),
        missing_confirmations=missing,
        reason=reason,
    )
