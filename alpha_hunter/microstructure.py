from __future__ import annotations

from typing import Any


MICROSTRUCTURE_VERSION = "0.1"


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _levels(rows: Any, limit: int = 15) -> list[tuple[float, float]]:
    output: list[tuple[float, float]] = []
    if not isinstance(rows, list):
        return output
    for row in rows[:limit]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        price = _float(row[0])
        size = _float(row[1])
        if price is None or size is None or price <= 0 or size < 0:
            continue
        output.append((price, size))
    return output


def _notional(levels: list[tuple[float, float]]) -> float:
    return sum(price * size for price, size in levels)


def _imbalance(left: float, right: float) -> float | None:
    total = left + right
    if total <= 0:
        return None
    return (left - right) / total


def summarize_order_book(
    depth: dict[str, Any],
    *,
    level_limit: int = 15,
    keep_levels: int = 5,
) -> dict[str, Any]:
    bids = _levels(depth.get("bids"), level_limit)
    asks = _levels(depth.get("asks"), level_limit)
    bid_notional = _notional(bids)
    ask_notional = _notional(asks)
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    midpoint = (
        (best_bid + best_ask) / 2
        if best_bid is not None and best_ask is not None
        else None
    )
    spread_pct = (
        (best_ask - best_bid) / midpoint * 100
        if midpoint and best_ask is not None and best_bid is not None
        else None
    )
    return {
        "version": MICROSTRUCTURE_VERSION,
        "status": "COMPLETE" if bids and asks else "DATA_INSUFFICIENT",
        "source": "BITGET_PUBLIC_MERGE_DEPTH",
        "exchange_timestamp_ms": _int(depth.get("ts")),
        "precision": depth.get("precision"),
        "scale": depth.get("scale"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "midpoint": midpoint,
        "spread_pct": spread_pct,
        "bid_notional": bid_notional,
        "ask_notional": ask_notional,
        "depth_imbalance": _imbalance(bid_notional, ask_notional),
        "level_count_bid": len(bids),
        "level_count_ask": len(asks),
        "top_bids": [[price, size] for price, size in bids[:keep_levels]],
        "top_asks": [[price, size] for price, size in asks[:keep_levels]],
    }


def summarize_recent_trades(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    buy_notional = 0.0
    sell_notional = 0.0
    buy_size = 0.0
    sell_size = 0.0
    timestamps: list[int] = []
    trade_ids: list[str] = []
    valid = 0

    for row in rows:
        price = _float(row.get("price"))
        size = _float(row.get("size"))
        side = str(row.get("side") or "").lower()
        timestamp = _int(row.get("ts"))
        trade_id = row.get("tradeId")
        if price is None or size is None or price <= 0 or size < 0:
            continue
        if side not in {"buy", "sell"}:
            continue
        notional = price * size
        if side == "buy":
            buy_notional += notional
            buy_size += size
        else:
            sell_notional += notional
            sell_size += size
        valid += 1
        if timestamp is not None:
            timestamps.append(timestamp)
        if trade_id is not None:
            trade_ids.append(str(trade_id))

    newest = max(timestamps) if timestamps else None
    oldest = min(timestamps) if timestamps else None
    return {
        "version": MICROSTRUCTURE_VERSION,
        "status": "COMPLETE" if valid > 0 else "DATA_INSUFFICIENT",
        "source": "BITGET_PUBLIC_RECENT_TRANSACTIONS",
        "trade_count": valid,
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "buy_size": buy_size,
        "sell_size": sell_size,
        "trade_imbalance": _imbalance(buy_notional, sell_notional),
        "newest_trade_timestamp_ms": newest,
        "oldest_trade_timestamp_ms": oldest,
        "window_ms": (newest - oldest) if newest is not None and oldest is not None else None,
        "first_trade_id": trade_ids[0] if trade_ids else None,
        "last_trade_id": trade_ids[-1] if trade_ids else None,
    }


def build_microstructure_snapshot(
    depth: dict[str, Any] | None,
    trades: list[dict[str, Any]] | None,
    *,
    ticker_timestamp_ms: int | None = None,
) -> dict[str, Any]:
    book = summarize_order_book(depth or {})
    flow = summarize_recent_trades(trades or [])
    timestamps = [
        value
        for value in (
            book.get("exchange_timestamp_ms"),
            flow.get("newest_trade_timestamp_ms"),
        )
        if isinstance(value, int)
    ]
    newest_source_timestamp = max(timestamps) if timestamps else None
    source_skew_ms = None
    if ticker_timestamp_ms is not None and newest_source_timestamp is not None:
        source_skew_ms = abs(ticker_timestamp_ms - newest_source_timestamp)

    complete = book["status"] == "COMPLETE" and flow["status"] == "COMPLETE"
    return {
        "version": MICROSTRUCTURE_VERSION,
        "status": "COMPLETE" if complete else "DATA_INSUFFICIENT",
        "read_only": True,
        "sources": [
            "GET /api/v2/mix/market/merge-depth",
            "GET /api/v2/mix/market/fills",
        ],
        "ticker_timestamp_ms": ticker_timestamp_ms,
        "newest_source_timestamp_ms": newest_source_timestamp,
        "source_skew_ms": source_skew_ms,
        "order_book": book,
        "recent_trades": flow,
    }


def build_microstructure_coverage(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible = [
        record
        for record in records
        if isinstance(record, dict)
        and "error" not in record
    ]
    complete = 0
    insufficient = 0
    for record in eligible:
        micro = record.get("microstructure")
        status = (
            str(micro.get("status") or "")
            if isinstance(micro, dict)
            else "MISSING"
        )
        if status == "COMPLETE":
            complete += 1
        else:
            insufficient += 1
    coverage_pct = (
        complete / len(eligible) * 100
        if eligible
        else 0.0
    )
    return {
        "version": MICROSTRUCTURE_VERSION,
        "source": "BITGET_PUBLIC_READ_ONLY",
        "eligible_symbol_count": len(eligible),
        "complete_count": complete,
        "data_insufficient_count": insufficient,
        "coverage_pct": round(coverage_pct, 2),
        "trade_permission": False,
    }
