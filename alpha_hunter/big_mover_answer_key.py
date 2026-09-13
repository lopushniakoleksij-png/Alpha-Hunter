from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from alpha_hunter.collector import build_instrument_map, instrument_is_allowed


ANSWER_KEY_VERSION = "big-mover-answer-key-v0.1"
THRESHOLDS = (5.0, 10.0, 20.0)


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _hour_bucket(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def _event_id(
    symbol: str,
    bucket: datetime,
    direction: str,
    threshold: float,
) -> str:
    raw = (
        f"{ANSWER_KEY_VERSION}|{symbol.upper()}|{bucket.isoformat()}|"
        f"{direction}|{threshold:.2f}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def build_answer_key_rows(
    *,
    contracts: list[dict[str, Any]],
    instruments: list[dict[str, Any]],
    tickers: Iterable[dict[str, Any]],
    product_type: str,
    config: dict[str, Any],
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create immutable answer-key rows from the complete Bitget futures ticker set.

    This is ground truth, not a trade signal. It records current mover threshold
    membership before any Alpha Hunter discovery/ranking decision is considered.
    """
    metadata_map = build_instrument_map(contracts, instruments)
    contract_symbols = set(metadata_map)
    scan_config = config.get("universe_scan", {})
    if not isinstance(scan_config, dict):
        scan_config = {}
    minimum_quote_volume = float(scan_config.get("minimum_quote_volume", 100000))
    bucket = _hour_bucket(observed_at)

    rows: list[dict[str, Any]] = []
    symbols_seen = 0
    threshold_symbols: dict[str, set[str]] = {
        "UP_5": set(),
        "UP_10": set(),
        "UP_20": set(),
        "DOWN_5": set(),
        "DOWN_10": set(),
        "DOWN_20": set(),
    }

    for ticker in tickers:
        if not isinstance(ticker, dict):
            continue
        symbol = str(ticker.get("symbol") or "").strip().upper()
        if not symbol or symbol not in contract_symbols:
            continue

        last_price = _float(ticker.get("lastPr"))
        change_raw = _float(ticker.get("change24h"))
        if last_price is None or last_price <= 0 or change_raw is None:
            continue

        symbols_seen += 1
        change_pct = change_raw * 100.0
        absolute_move = abs(change_pct)
        direction = "UP" if change_pct >= 0 else "DOWN"
        quote_volume = (
            _float(ticker.get("quoteVolume"))
            or _float(ticker.get("usdtVolume"))
            or 0.0
        )
        metadata = metadata_map.get(symbol, {})
        strategy_eligible = bool(instrument_is_allowed(metadata, config))
        liquidity_pass = quote_volume >= minimum_quote_volume

        for threshold in THRESHOLDS:
            if absolute_move < threshold:
                continue
            threshold_symbols[f"{direction}_{int(threshold)}"].add(symbol)
            rows.append(
                {
                    "event_id": _event_id(
                        symbol,
                        bucket,
                        direction,
                        threshold,
                    ),
                    "observed_at_utc": observed_at.isoformat(),
                    "hour_bucket_utc": bucket.isoformat(),
                    "symbol": symbol,
                    "product_type": product_type,
                    "direction": direction,
                    "threshold_pct": threshold,
                    "current_24h_move_pct": change_pct,
                    "last_price": last_price,
                    "quote_volume_24h": quote_volume,
                    "strategy_eligible": strategy_eligible,
                    "liquidity_pass": liquidity_pass,
                    "source": "BITGET_PUBLIC_ALL_TICKERS",
                    "model_version": ANSWER_KEY_VERSION,
                    "shadow_only": True,
                    "trade_permission": False,
                }
            )

    summary = {
        "observed_at_utc": observed_at.isoformat(),
        "hour_bucket_utc": bucket.isoformat(),
        "contract_symbols_observed": symbols_seen,
        "rows": len(rows),
        "threshold_symbol_counts": {
            key: len(value)
            for key, value in threshold_symbols.items()
        },
        "shadow_only": True,
        "trade_permission": False,
    }
    return rows, summary
