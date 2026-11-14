"""Phase 2 prospective signal investigator. Pure functions; no I/O or trading authority."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

D = Decimal

@dataclass(frozen=True)
class Setup:
    signal_id: str
    direction: str
    entry: Optional[Decimal]
    stop: Optional[Decimal]
    target: Optional[Decimal]
    disposition: str
    strategy: Optional[str] = None

@dataclass(frozen=True)
class Bar:
    timestamp_utc: str
    high: Decimal
    low: Decimal

@dataclass(frozen=True)
class Investigation:
    signal_id: str
    status: str
    entry_at: Optional[str]
    exit_at: Optional[str]
    reason: str
    hypothetical: bool

def investigate(setup: Setup, bars: Sequence[Bar]) -> Investigation:
    """Conservative OHLC adjudication. Bars MUST be chronological and strictly post-signal.
    A candle that crosses entry and an exit threshold is ambiguous; no fabricated ordering.
    No claim of executable fills or net P&L from OHLC alone.
    """
    hypothetical = setup.disposition.upper() in {"BLOCKED", "REJECTED", "WATCH"}
    def result(status, entry_at=None, exit_at=None, reason=""):
        return Investigation(setup.signal_id, status, entry_at, exit_at, reason, hypothetical)
    if setup.direction not in {"LONG", "SHORT"}:
        return result("NOT_EVALUABLE", reason="NO_DIRECTION")
    if any(v is None for v in (setup.entry, setup.stop, setup.target)):
        return result("NOT_EVALUABLE", reason="MISSING_EP_SL_TP")
    ep, sl, tp = setup.entry, setup.stop, setup.target
    if not ((sl < ep < tp) if setup.direction == "LONG" else (tp < ep < sl)):
        return result("NOT_EVALUABLE", reason="INVALID_PRICE_GEOMETRY")
    if not bars:
        return result("UNKNOWN", reason="NO_PRICE_EVIDENCE")
    if any(b.low > b.high for b in bars):
        return result("UNKNOWN", reason="INVALID_OHLC")
    if any(bars[i].timestamp_utc >= bars[i+1].timestamp_utc for i in range(len(bars)-1)):
        return result("UNKNOWN", reason="NON_MONOTONIC_TIMESTAMPS")
    entry_at = None
    for b in bars:
        if entry_at is None:
            if not b.low <= ep <= b.high:
                continue
            entry_at = b.timestamp_utc
            entry_bar_exit = (b.low <= sl or b.high >= tp) if setup.direction == "LONG" else (b.high >= sl or b.low <= tp)
            if entry_bar_exit:
                return result("AMBIGUOUS", entry_at, b.timestamp_utc, "ENTRY_AND_EXIT_SAME_BAR")
            continue
        hit_sl = b.low <= sl if setup.direction == "LONG" else b.high >= sl
        hit_tp = b.high >= tp if setup.direction == "LONG" else b.low <= tp
        if hit_sl and hit_tp:
            return result("AMBIGUOUS", entry_at, b.timestamp_utc, "SL_TP_SAME_BAR")
        if hit_sl:
            return result("SL_FIRST", entry_at, b.timestamp_utc, "OHLC_TOUCH_NOT_EXECUTION")
        if hit_tp:
            return result("TP_FIRST", entry_at, b.timestamp_utc, "OHLC_TOUCH_NOT_EXECUTION")
    return result("NO_ENTRY" if entry_at is None else "OPEN_AT_HORIZON", entry_at, reason="OBSERVATION_WINDOW_ENDED")
