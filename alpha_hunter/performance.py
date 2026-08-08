from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_signal_id(run_id: str, symbol: str) -> str:
    raw = f"{run_id}|{symbol}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def extract_signal_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    run_id = str(snapshot.get("run_id") or "")
    detected_at = snapshot.get("collected_at_utc")
    rows: list[dict[str, Any]] = []

    for item in snapshot.get("symbols", []):
        if "error" in item:
            continue
        setup = item.get("execution_setup", {})
        intel = item.get("intelligence", {})
        reference_price = _f(item.get("last_price"))
        if reference_price is None:
            continue

        rows.append({
            "signal_id": build_signal_id(run_id, str(item.get("symbol"))),
            "run_id": run_id,
            "symbol": item.get("symbol"),
            "detected_at_utc": detected_at,
            "state": item.get("state"),
            "direction": setup.get("direction"),
            "trade_permission": bool(item.get("trade_permission")),
            "huge_rr_score": _f(intel.get("huge_rr_score")),
            "confidence_estimate_pct": _f(intel.get("confidence_estimate_pct")),
            "reward_risk": _f(setup.get("rr")),
            "entry_price": _f(setup.get("entry")),
            "stop_loss": _f(setup.get("stop_loss")),
            "take_profit": _f(setup.get("take_profit")),
            "reference_price": reference_price,
            "payload": item,
        })
    return rows


class PerformanceStorage:
    def __init__(self, url: str, key: str, timeout: int = 20) -> None:
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

    def save_signals(self, snapshot: dict[str, Any]) -> int:
        rows = extract_signal_rows(snapshot)
        if not rows:
            return 0
        response = requests.post(
            f"{self.url}/rest/v1/alpha_hunter_signals",
            params={"on_conflict": "signal_id"},
            headers=self.headers,
            data=json.dumps(rows, separators=(",", ":")),
            timeout=self.timeout,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                f"Performance signal save failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        return len(rows)
