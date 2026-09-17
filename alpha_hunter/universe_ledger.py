from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import requests

from .analysis import to_float
from .bitget import BitgetClient
from .collector import build_instrument_map, instrument_is_allowed
from .storage import SupabaseConfig

TABLE = "alpha_hunter_universe_hourly"
MODEL_VERSION = "7.9-universe-ledger-v1"


def _bucket(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _observation_id(symbol: str, bucket: datetime) -> str:
    raw = f"{symbol.upper()}|{MODEL_VERSION}|{bucket.isoformat()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


@contextmanager
def capture_existing_universe_calls() -> Iterator[dict[str, list[dict[str, Any]]]]:
    """Capture the scanner's existing public-universe calls without making new calls."""
    captured: dict[str, list[dict[str, Any]]] = {}
    originals = {
        "contracts": BitgetClient.contracts,
        "tickers": BitgetClient.tickers,
        "instruments": BitgetClient.instruments,
    }

    def wrap(name: str):
        original = originals[name]

        def recorder(self: BitgetClient, *args: Any, **kwargs: Any):
            value = original(self, *args, **kwargs)
            if name not in captured and isinstance(value, list):
                captured[name] = value
            return value

        return recorder

    try:
        for name in originals:
            setattr(BitgetClient, name, wrap(name))
        yield captured
    finally:
        for name, original in originals.items():
            setattr(BitgetClient, name, original)


def build_rows_from_existing_scan(
    *,
    contracts: list[dict[str, Any]],
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    selected_symbols: set[str],
    selection_snapshot_at_utc: str,
    selection_run_id: str,
    product_type: str,
    config: dict[str, Any],
    observed_at: datetime,
) -> list[dict[str, Any]]:
    """Bind canonical universe evidence from the already-fetched scanner payload."""
    metadata_map = build_instrument_map(contracts, instruments)
    contract_symbols = set(metadata_map)
    settings = config.get("universe_scan", {})
    minimum_quote_volume = float(settings.get("minimum_quote_volume", 100000))
    maximum_extension = float(settings.get("maximum_24h_extension_pct", 25))
    bucket = _bucket(observed_at)
    rows: list[dict[str, Any]] = []

    for ticker in tickers:
        if not isinstance(ticker, dict):
            continue
        symbol = str(ticker.get("symbol", "")).upper()
        if not symbol or symbol not in contract_symbols:
            continue
        last_price = to_float(ticker.get("lastPr"))
        if last_price is None or last_price <= 0:
            continue
        quote_volume = (
            to_float(ticker.get("quoteVolume"))
            or to_float(ticker.get("usdtVolume"))
            or 0.0
        )
        change_raw = to_float(ticker.get("change24h"))
        change_24h_pct = change_raw * 100.0 if change_raw is not None else None
        metadata = metadata_map.get(symbol, {})
        crypto_allowed = instrument_is_allowed(metadata, config)
        liquidity_pass = quote_volume >= minimum_quote_volume
        extension_pass = (
            change_24h_pct is not None
            and abs(change_24h_pct) <= maximum_extension
        )
        eligible = bool(crypto_allowed and liquidity_pass and extension_pass)
        selected = symbol in selected_symbols
        if not crypto_allowed:
            reason = "NON_CRYPTO"
        elif not liquidity_pass:
            reason = "LOW_LIQUIDITY"
        elif not extension_pass:
            reason = "OVER_EXTENDED"
        elif selected:
            reason = "DEEP_SCAN_SELECTED"
        else:
            reason = "ELIGIBLE_NOT_SELECTED"

        rows.append({
            "observation_id": _observation_id(symbol, bucket),
            "observed_at_utc": observed_at.isoformat(),
            "hour_bucket_utc": bucket.isoformat(),
            "symbol": symbol,
            "product_type": product_type,
            "last_price": last_price,
            "change_24h_pct": change_24h_pct,
            "quote_volume_24h": quote_volume,
            "symbol_type": str(metadata.get("symbolType")) if metadata.get("symbolType") is not None else None,
            "is_rwa": bool(metadata.get("isRwa", False)),
            "is_reality": bool(metadata.get("isReality", False)),
            "crypto_allowed": crypto_allowed,
            "liquidity_pass": liquidity_pass,
            "extension_pass": extension_pass,
            "prefilter_eligible": eligible,
            "deep_scan_selected": selected,
            "rejection_reason": reason,
            "source": "PRIMARY_SCANNER_CACHED_TICKERS",
            "measurement_quality": "HOURLY_TICKER_SNAPSHOT",
            "trade_permission": False,
            "selection_snapshot_at_utc": selection_snapshot_at_utc,
            "selection_run_id": selection_run_id,
            "updated_at": observed_at.isoformat(),
        })
    return rows


def persist_rows(settings: SupabaseConfig, rows: list[dict[str, Any]]) -> int:
    """Append the current hour once; never overwrite prior observations."""
    if not rows:
        raise RuntimeError("Universe persistence refused: scanner payload produced no rows")
    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }
    response = requests.post(
        f"{settings.url}/rest/v1/{TABLE}",
        params={"on_conflict": "observation_id"},
        headers=headers,
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            f"Universe persistence failed: HTTP {response.status_code}: {response.text[:500]}"
        )
    return len(rows)
