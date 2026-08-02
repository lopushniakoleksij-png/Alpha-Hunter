from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import requests

from .bitget import BitgetClient


def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class OutcomeEvaluator:
    def __init__(self, supabase_url: str, supabase_key: str, bitget: BitgetClient, product_type: str, timeout: int = 20) -> None:
        self.url = supabase_url.rstrip("/")
        self.key = supabase_key
        self.bitget = bitget
        self.product_type = product_type
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def _get(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.url}/rest/v1/{table}",
            params=params,
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _upsert(self, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
        if not rows:
            return
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        response = requests.post(
            f"{self.url}/rest/v1/{table}",
            params={"on_conflict": conflict},
            headers=headers,
            data=json.dumps(rows, separators=(",", ":")),
            timeout=self.timeout,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                f"Outcome save failed: HTTP {response.status_code}: {response.text[:500]}"
            )

    def pending_signals(self, horizon_hours: int, limit: int = 500) -> list[dict[str, Any]]:
        cutoff = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - horizon_hours * 3600,
            tz=timezone.utc,
        ).isoformat()

        signals = self._get(
            "alpha_hunter_signals",
            {
                "select": "signal_id,symbol,detected_at_utc,state,direction,reference_price,entry_price,stop_loss,take_profit,payload",
                "detected_at_utc": f"lte.{cutoff}",
                "order": "detected_at_utc.asc",
                "limit": str(limit),
            },
        )
        if not signals:
            return []

        ids = ",".join(row["signal_id"] for row in signals)
        evaluated = self._get(
            "alpha_hunter_signal_outcomes",
            {
                "select": "signal_id",
                "horizon_hours": f"eq.{horizon_hours}",
                "signal_id": f"in.({ids})",
                "limit": str(limit),
            },
        )
        completed = {row["signal_id"] for row in evaluated}
        return [row for row in signals if row["signal_id"] not in completed]

    @staticmethod
    def classify(signal: dict[str, Any], current_price: float) -> dict[str, Any]:
        reference = _f(signal.get("reference_price"))
        if reference is None or reference <= 0:
            raise ValueError("Invalid reference price")

        raw_return = ((current_price / reference) - 1.0) * 100.0
        direction = str(signal.get("direction") or "").upper()
        if not direction:
            state = str(signal.get("state") or "").upper()
            direction = "SHORT" if "SHORT" in state else "LONG" if "LONG" in state else "NONE"

        adjusted = -raw_return if direction == "SHORT" else raw_return
        target = _f(signal.get("take_profit"))
        stop = _f(signal.get("stop_loss"))

        target_hit = False
        stop_hit = False
        if direction == "LONG":
            target_hit = target is not None and current_price >= target
            stop_hit = stop is not None and current_price <= stop
        elif direction == "SHORT":
            target_hit = target is not None and current_price <= target
            stop_hit = stop is not None and current_price >= stop

        if target_hit:
            outcome = "TARGET_HIT"
        elif stop_hit:
            outcome = "STOP_HIT"
        elif adjusted >= 10:
            outcome = "BIG_WIN"
        elif adjusted >= 3:
            outcome = "WIN"
        elif adjusted <= -10:
            outcome = "BIG_LOSS"
        elif adjusted <= -3:
            outcome = "LOSS"
        else:
            outcome = "FLAT"

        return {
            "return_pct": round(raw_return, 6),
            "direction_adjusted_return_pct": round(adjusted, 6),
            "target_hit": target_hit,
            "stop_hit": stop_hit,
            "outcome_class": outcome,
            "direction_used": direction,
        }

    def evaluate_horizon(self, horizon_hours: int) -> tuple[int, int]:
        pending = self.pending_signals(horizon_hours)
        rows = []
        failures = 0
        evaluated_at = datetime.now(timezone.utc).isoformat()
        price_cache: dict[str, float] = {}

        for signal in pending:
            symbol = str(signal["symbol"])
            try:
                if symbol not in price_cache:
                    ticker = self.bitget.ticker(symbol, self.product_type)
                    price = _f(ticker.get("lastPr") or ticker.get("last"))
                    if price is None or price <= 0:
                        raise ValueError("Invalid current price")
                    price_cache[symbol] = price

                current_price = price_cache[symbol]
                result = self.classify(signal, current_price)
                rows.append({
                    "signal_id": signal["signal_id"],
                    "horizon_hours": horizon_hours,
                    "evaluated_at_utc": evaluated_at,
                    "evaluation_price": current_price,
                    "return_pct": result["return_pct"],
                    "direction_adjusted_return_pct": result["direction_adjusted_return_pct"],
                    "target_hit": result["target_hit"],
                    "stop_hit": result["stop_hit"],
                    "outcome_class": result["outcome_class"],
                    "payload": {
                        "direction_used": result["direction_used"],
                        "reference_price": signal.get("reference_price"),
                        "state": signal.get("state"),
                    },
                })
            except Exception as exc:
                failures += 1
                print(f"Outcome evaluation failed for {symbol} at {horizon_hours}h: {exc}")

        self._upsert("alpha_hunter_signal_outcomes", rows, "signal_id,horizon_hours")
        return len(rows), failures
