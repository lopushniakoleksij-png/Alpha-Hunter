"""Research-only Bitget USDT-M mover ranking; no exchange/network/trading I/O."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

WINDOWS_HOURS = (24, 48, 72, 168)

@dataclass(frozen=True)
class Snapshot:
    symbol: str
    at_utc: str
    close: Decimal
    source_id: str
    market: str = "USDT-M"
    complete: bool = True

@dataclass(frozen=True)
class Mover:
    symbol: str
    window_hours: int
    start_utc: str
    end_utc: str
    return_pct: Decimal
    start_source_id: str
    end_source_id: str

def rank_movers(start: Sequence[Snapshot], end: Sequence[Snapshot],
                window_hours: int, top_n: int = 10):
    """Snapshots must be exact UTC window endpoints from source-proven observations.
    Returns (gainers, losers, exclusion reasons). No nearest-timestamp substitution.
    """
    if window_hours not in WINDOWS_HOURS or top_n < 1:
        raise ValueError("unsupported window or rank")
    from datetime import datetime, timezone, timedelta
    def parse(t):
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        if d.tzinfo is None or d.utcoffset() != timedelta(0):
            raise ValueError("timestamps must be UTC aware")
        return d
    def index(items):
        found, duplicates = {}, set()
        for s in items:
            if s.symbol in found:
                duplicates.add(s.symbol)
            found[s.symbol] = s
        return found, duplicates
    a, da = index(start)
    b, db = index(end)
    excluded, movers = {}, []
    for symbol in sorted(set(a) | set(b)):
        if symbol in da | db:
            excluded[symbol] = "DUPLICATE_SNAPSHOT"
            continue
        if symbol not in a or symbol not in b:
            excluded[symbol] = "MISSING_ENDPOINT"
            continue
        x, y = a[symbol], b[symbol]
        if not x.complete or not y.complete or not x.source_id or not y.source_id:
            excluded[symbol] = "INCOMPLETE_PROVENANCE"
            continue
        if x.market != "USDT-M" or y.market != "USDT-M":
            excluded[symbol] = "WRONG_MARKET"
            continue
        if x.close <= 0 or y.close <= 0:
            excluded[symbol] = "INVALID_PRICE"
            continue
        if parse(y.at_utc) - parse(x.at_utc) != timedelta(hours=window_hours):
            excluded[symbol] = "WINDOW_MISMATCH"
            continue
        pct = (y.close / x.close - 1) * Decimal("100")
        movers.append(Mover(symbol, window_hours, x.at_utc, y.at_utc,
                            pct, x.source_id, y.source_id))
    gainers = sorted((m for m in movers if m.return_pct > 0),
                     key=lambda m: (-m.return_pct, m.symbol))[:top_n]
    losers = sorted((m for m in movers if m.return_pct < 0),
                    key=lambda m: (m.return_pct, m.symbol))[:top_n]
    return gainers, losers, excluded
