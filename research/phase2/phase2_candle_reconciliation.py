"""Research-only reconciliation of episode-overlapping Bitget candle evidence."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

@dataclass(frozen=True)
class CandleRecord:
    symbol: str
    market: str
    granularity: str
    open_utc: str
    source_exchange: str
    source_endpoint: str
    source_row_id: str
    episode_id: str
    open_price: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    fully_closed: bool

@dataclass(frozen=True)
class Reconciled:
    status: str
    representative: CandleRecord | None
    source_ids: tuple[str, ...]
    episodes: tuple[str, ...]

def reconcile(records: Sequence[CandleRecord]) -> Reconciled:
    """Reconcile one instrument/market/granularity/hour group.
    Retain ALL provenance. Conflicting OHLC stays UNKNOWN; never silently pick.
    """
    if not records:
        return Reconciled("MISSING", None, (), ())
    sources=tuple(sorted({r.source_row_id for r in records}))
    episodes=tuple(sorted({r.episode_id for r in records}))
    key=lambda r:(r.symbol,r.market,r.granularity,r.open_utc)
    if len({key(r) for r in records})!=1:
        return Reconciled("MIXED_KEYS",None,sources,episodes)
    if any(not r.source_row_id or not r.source_endpoint or
           r.source_exchange.upper()!="BITGET" or not r.fully_closed or
           r.low<=0 or not (r.low<=r.open_price<=r.high and r.low<=r.close<=r.high)
           for r in records):
        return Reconciled("INVALID",None,sources,episodes)
    price=lambda r:(r.open_price,r.high,r.low,r.close)
    if len({price(r) for r in records})!=1:
        return Reconciled("CONFLICT",None,sources,episodes)
    chosen=sorted(records,key=lambda r:(r.source_row_id,r.episode_id))[0]
    return Reconciled("UNIQUE" if len(records)==1 else "DEDUPED_IDENTICAL",
                      chosen,sources,episodes)
