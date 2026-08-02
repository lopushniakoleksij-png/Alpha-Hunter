from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "yes", "1", "expanded", "expanding"}:
            return True
        if value in {"false", "no", "0", "contracting", "not_expanding"}:
            return False
    return None


def _signal_id(run_id: str, symbol: str) -> str:
    return hashlib.sha256(f"{run_id}|{symbol}".encode()).hexdigest()[:32]


def _walk(obj: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat[path.lower()] = value
            flat.update(_walk(value, path))
    elif isinstance(obj, list):
        for index, value in enumerate(obj[:20]):
            flat.update(_walk(value, f"{prefix}.{index}" if prefix else str(index)))
    return flat


def _pick(flat: dict[str, Any], *names: str) -> Any:
    names = tuple(name.lower() for name in names)
    for name in names:
        if name in flat:
            return flat[name]
    for path, value in flat.items():
        if path.rsplit(".", 1)[-1] in names:
            return value
    for name in names:
        for path, value in flat.items():
            if path.endswith(name) or name in path:
                return value
    return None


def _session(hour: int) -> str:
    if hour < 7:
        return "ASIA"
    if hour < 13:
        return "LONDON"
    if hour < 21:
        return "NEW_YORK"
    return "LATE_US"


def _text(flat: dict[str, Any], *names: str) -> str | None:
    value = _pick(flat, *names)
    return str(value).upper() if value not in (None, "") else None


def extract_feature_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(snapshot.get("run_id") or "")
    captured_at = snapshot.get("collected_at_utc") or datetime.now(timezone.utc).isoformat()
    dt = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
    snapshot_flat = _walk(snapshot)
    global_regime = _pick(snapshot_flat, "btc_regime", "market_regime")
    rows: list[dict[str, Any]] = []

    for item in snapshot.get("symbols", []):
        if not isinstance(item, dict) or item.get("error"):
            continue

        symbol = str(item.get("symbol") or "")
        if not symbol:
            continue

        flat = _walk(item)
        setup = item.get("execution_setup") or {}
        intel = item.get("intelligence") or {}

        volume_ratio = _float(_pick(flat, "volume_ratio", "relative_volume", "rvol"))
        volume_expansion = _bool(_pick(flat, "volume_expansion", "volume_expanding"))
        if volume_expansion is None and volume_ratio is not None:
            volume_expansion = volume_ratio >= 1.5

        features = {
            "trend_15m": _text(flat, "trend_15m", "15m_trend"),
            "trend_1h": _text(flat, "trend_1h", "1h_trend"),
            "trend_4h": _text(flat, "trend_4h", "4h_trend"),
            "btc_regime": _text(flat, "btc_regime", "market_regime") or (
                str(global_regime).upper() if global_regime not in (None, "") else None
            ),
            "sector": _text(flat, "sector", "category", "narrative"),
            "session": _session(dt.hour),
            "weekday": dt.weekday(),
            "hour_utc": dt.hour,
            "volume_ratio": volume_ratio,
            "volume_expansion": volume_expansion,
            "volatility_pct": _float(_pick(flat, "volatility_pct", "atr_pct", "range_pct")),
            "compression_score": _float(_pick(flat, "compression_score", "compression", "squeeze_score")),
            "funding_rate": _float(_pick(flat, "funding_rate", "funding")),
            "open_interest": _float(_pick(flat, "open_interest", "oi")),
            "open_interest_change_pct": _float(_pick(flat, "open_interest_change_pct", "oi_change_pct")),
            "relative_strength_btc": _float(_pick(flat, "relative_strength_btc", "rs_vs_btc")),
            "rsi_15m": _float(_pick(flat, "rsi_15m", "15m_rsi")),
            "rsi_1h": _float(_pick(flat, "rsi_1h", "1h_rsi")),
            "rsi_4h": _float(_pick(flat, "rsi_4h", "4h_rsi")),
            "distance_to_support_pct": _float(_pick(flat, "distance_to_support_pct", "support_distance_pct")),
            "distance_to_resistance_pct": _float(_pick(flat, "distance_to_resistance_pct", "resistance_distance_pct")),
            "ema_alignment_15m": _text(flat, "ema_alignment_15m", "15m_ema_alignment"),
            "ema_alignment_1h": _text(flat, "ema_alignment_1h", "1h_ema_alignment"),
            "ema_alignment_4h": _text(flat, "ema_alignment_4h", "4h_ema_alignment"),
            "liquidity_state": _text(flat, "liquidity_state", "liquidity_condition"),
        }

        rows.append({
            "signal_id": _signal_id(run_id, symbol),
            "run_id": run_id,
            "symbol": symbol,
            "captured_at_utc": captured_at,
            "state": item.get("state"),
            "direction": setup.get("direction") or _pick(flat, "direction"),
            "trade_permission": bool(item.get("trade_permission")),
            "huge_rr_score": _float(intel.get("huge_rr_score")),
            "confidence_estimate_pct": _float(intel.get("confidence_estimate_pct")),
            "reward_risk": _float(setup.get("rr")),
            **features,
            "features": features,
            "source_payload": item,
        })
    return rows


class FeatureStorage:
    def __init__(self, url: str, key: str, timeout: int = 30) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def save(self, snapshot: dict[str, Any]) -> int:
        rows = extract_feature_rows(snapshot)
        if not rows:
            return 0

        run_id = str(snapshot.get("run_id") or "")
        lookup_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

        lookup = requests.get(
            f"{self.url}/rest/v1/alpha_hunter_signals",
            params={
                "select": "signal_id,symbol",
                "run_id": f"eq.{run_id}",
                "limit": "1000",
            },
            headers=lookup_headers,
            timeout=self.timeout,
        )
        lookup.raise_for_status()

        signal_ids = {
            str(item["symbol"]): str(item["signal_id"])
            for item in lookup.json()
        }

        matched_rows = []
        for row in rows:
            real_signal_id = signal_ids.get(str(row["symbol"]))
            if not real_signal_id:
                print(
                    f"Skipping feature row without matching signal: {row['symbol']}"
                )
                continue
            row["signal_id"] = real_signal_id
            matched_rows.append(row)

        if not matched_rows:
            raise RuntimeError(
                f"No matching Alpha Hunter signals found for run_id={run_id}"
            )

        response = requests.post(
            f"{self.url}/rest/v1/alpha_hunter_signal_features",
            params={"on_conflict": "signal_id"},
            headers=self.headers,
            data=json.dumps(matched_rows, separators=(",", ":")),
            timeout=self.timeout,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                f"Feature save failed: HTTP {response.status_code}: {response.text[:600]}"
            )
        return len(matched_rows)
