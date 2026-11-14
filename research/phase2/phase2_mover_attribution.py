"""Phase 2 research-only, as-of mover-to-signal attribution. No I/O."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

@dataclass(frozen=True)
class SignalObservation:
    signal_id: str
    symbol: str
    detected_at_utc: str
    state: str
    direction: Optional[str]
    trade_permission: Optional[bool]
    blocked: bool
    scan_complete: bool = True

@dataclass(frozen=True)
class Attribution:
    symbol: str
    category: str
    first_signal_id: Optional[str]
    first_signal_at_utc: Optional[str]
    reason: str

def _utc(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() != timedelta(0):
        raise ValueError("UTC timestamp required")
    return d

def attribute_mover(symbol: str, direction: str, window_start_utc: str,
                    cutoff_utc: str, signals: Sequence[SignalObservation],
                    *, universe_complete: bool, scan_persistence_complete: bool,
                    lead_hours: int = 6) -> Attribution:
    """Only evidence known by cutoff is eligible. EARLY means a directional signal
    within the first lead_hours of the specified observation window, not a
    proven tradable entry or a prediction of the eventual mover ranking.
    """
    start, cutoff = _utc(window_start_utc), _utc(cutoff_utc)
    if start >= cutoff or lead_hours < 0:
        raise ValueError("invalid window or lead hours")
    if direction not in {"LONG", "SHORT"}:
        return Attribution(symbol, "UNKNOWN", None, None, "INVALID_DIRECTION")
    if not universe_complete or not scan_persistence_complete:
        return Attribution(symbol, "UNKNOWN", None, None, "INCOMPLETE_COVERAGE")
    observations = [s for s in signals if s.symbol == symbol and
                    start <= _utc(s.detected_at_utc) <= cutoff]
    if any(not s.scan_complete for s in observations):
        return Attribution(symbol, "UNKNOWN", None, None, "INCOMPLETE_SCAN")
    directional = [s for s in observations if s.direction == direction]
    directional.sort(key=lambda s: (_utc(s.detected_at_utc), s.signal_id))
    if not directional:
        return Attribution(symbol, "MISSED", None, None, "NO_MATCHING_DIRECTIONAL_SIGNAL")
    first = directional[0]
    if first.blocked or first.trade_permission is False:
        category, reason = "BLOCKED", "FIRST_DIRECTIONAL_SIGNAL_BLOCKED"
    elif _utc(first.detected_at_utc) <= start + timedelta(hours=lead_hours):
        category, reason = "EARLY", "WITHIN_PREDECLARED_LEAD_WINDOW"
    else:
        category, reason = "LATE", "AFTER_PREDECLARED_LEAD_WINDOW"
    return Attribution(symbol, category, first.signal_id, first.detected_at_utc, reason)
