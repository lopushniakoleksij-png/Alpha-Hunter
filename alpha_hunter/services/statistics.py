from __future__ import annotations
from collections import defaultdict
from statistics import mean
from typing import Any
import requests

WIN_CLASSES = {"WIN", "BIG_WIN", "TARGET_HIT"}
LOSS_CLASSES = {"LOSS", "BIG_LOSS", "STOP_HIT"}

def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

class StatisticsService:
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

    def load_samples(self, horizon_hours: int = 1, limit: int = 5000) -> list[dict[str, Any]]:
        outcomes = self._get(
            "alpha_hunter_signal_outcomes",
            {
                "select": "signal_id,horizon_hours,evaluated_at_utc,evaluation_price,return_pct,direction_adjusted_return_pct,target_hit,stop_hit,outcome_class,payload",
                "horizon_hours": f"eq.{horizon_hours}",
                "order": "evaluated_at_utc.desc",
                "limit": str(limit),
            },
        )
        if not outcomes:
            return []
        ids = ",".join(row["signal_id"] for row in outcomes)
        signals = self._get(
            "alpha_hunter_signals",
            {
                "select": "signal_id,run_id,symbol,detected_at_utc,state,direction,trade_permission,huge_rr_score,confidence_estimate_pct,reward_risk,reference_price,payload",
                "signal_id": f"in.({ids})",
                "limit": str(limit),
            },
        )
        signal_map = {row["signal_id"]: row for row in signals}
        return [{**signal_map[o["signal_id"]], "outcome": o} for o in outcomes if o["signal_id"] in signal_map]

    @staticmethod
    def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(samples)
        wins = sum(1 for s in samples if s["outcome"].get("outcome_class") in WIN_CLASSES)
        losses = sum(1 for s in samples if s["outcome"].get("outcome_class") in LOSS_CLASSES)
        returns = [_f(s["outcome"].get("direction_adjusted_return_pct")) for s in samples]
        return {
            "samples": total,
            "wins": wins,
            "losses": losses,
            "flat": total - wins - losses,
            "win_rate": round(wins / total * 100, 2) if total else 0.0,
            "average_return_pct": round(mean(returns), 4) if returns else 0.0,
            "best_return_pct": round(max(returns), 4) if returns else 0.0,
            "worst_return_pct": round(min(returns), 4) if returns else 0.0,
        }

    @classmethod
    def _group(cls, samples: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        grouped = defaultdict(list)
        for sample in samples:
            grouped[str(sample.get(key_name) or "UNKNOWN")].append(sample)
        rows = [{"name": name, **cls._summary(group)} for name, group in grouped.items()]
        rows.sort(key=lambda r: (r["win_rate"], r["average_return_pct"], r["samples"]), reverse=True)
        return rows

    @classmethod
    def _buckets(cls, samples: list[dict[str, Any]], field: str, step: int, suffix: str = "") -> list[dict[str, Any]]:
        grouped = defaultdict(list)
        for sample in samples:
            value = _f(sample.get(field))
            lower = int(value // step) * step
            label = f"{lower}-{lower + step - 1}{suffix}"
            grouped[label].append(sample)
        rows = [{"name": name, **cls._summary(group)} for name, group in grouped.items()]
        rows.sort(key=lambda r: int(r["name"].split("-")[0]))
        return rows

    @staticmethod
    def recommendations(strategy_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        out = []
        for row in strategy_rows:
            if row["samples"] < 10:
                action = "COLLECT MORE DATA"
                reason = f"Only {row['samples']} samples"
            elif row["win_rate"] >= 60 and row["average_return_pct"] > 0:
                action = "INCREASE WEIGHT"
                reason = f"{row['win_rate']}% wins, {row['average_return_pct']}% average return"
            elif row["win_rate"] < 40 or row["average_return_pct"] < 0:
                action = "REDUCE / DISABLE"
                reason = f"{row['win_rate']}% wins, {row['average_return_pct']}% average return"
            else:
                action = "KEEP"
                reason = f"{row['win_rate']}% wins across {row['samples']} samples"
            out.append({"strategy": row["name"], "action": action, "reason": reason})
        return out

    def report(self, horizon_hours: int = 1) -> dict[str, Any]:
        samples = self.load_samples(horizon_hours)
        strategies = self._group(samples, "state")
        return {
            "horizon_hours": horizon_hours,
            "overall": self._summary(samples),
            "strategies": strategies,
            "directions": self._group(samples, "direction"),
            "score_buckets": self._buckets(samples, "huge_rr_score", 1),
            "confidence_buckets": self._buckets(samples, "confidence_estimate_pct", 5, "%"),
            "recommendations": self.recommendations(strategies),
        }
