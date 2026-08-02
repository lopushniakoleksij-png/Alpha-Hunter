from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean, median
from typing import Any

import requests

NOISE_THRESHOLD_PCT = 0.10
BIG_MOVE_THRESHOLD_PCT = 3.0
MIN_RECOMMENDATION_SAMPLES = 30
PROMOTION_SAMPLES = 100


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + (z * z / total)
    centre = p + (z * z / (2 * total))
    margin = z * sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    low = (centre - margin) / denominator
    high = (centre + margin) / denominator
    return max(0.0, low), min(1.0, high)


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
                "select": (
                    "signal_id,horizon_hours,evaluated_at_utc,evaluation_price,"
                    "return_pct,direction_adjusted_return_pct,target_hit,stop_hit,"
                    "outcome_class,payload"
                ),
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
                "select": (
                    "signal_id,run_id,symbol,detected_at_utc,state,direction,"
                    "trade_permission,huge_rr_score,confidence_estimate_pct,"
                    "reward_risk,reference_price,payload"
                ),
                "signal_id": f"in.({ids})",
                "limit": str(limit),
            },
        )
        signal_map = {row["signal_id"]: row for row in signals}
        return [
            {**signal_map[outcome["signal_id"]], "outcome": outcome}
            for outcome in outcomes
            if outcome["signal_id"] in signal_map
        ]

    @staticmethod
    def _summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
        returns = [
            _f(sample["outcome"].get("direction_adjusted_return_pct"))
            for sample in samples
        ]
        total = len(returns)
        positive = [r for r in returns if r > NOISE_THRESHOLD_PCT]
        negative = [r for r in returns if r < -NOISE_THRESHOLD_PCT]
        flat = total - len(positive) - len(negative)
        decisive = len(positive) + len(negative)

        gross_profit = sum(positive)
        gross_loss = abs(sum(negative))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        expectancy = mean(returns) if returns else 0.0
        avg_win = mean(positive) if positive else 0.0
        avg_loss = abs(mean(negative)) if negative else 0.0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

        low, high = _wilson_interval(len(positive), decisive)
        directional_accuracy = len(positive) / decisive * 100 if decisive else 0.0
        coverage = decisive / total * 100 if total else 0.0

        return {
            "samples": total,
            "correct": len(positive),
            "wrong": len(negative),
            "flat": flat,
            "directional_accuracy": round(directional_accuracy, 2),
            "accuracy_ci_low": round(low * 100, 2),
            "accuracy_ci_high": round(high * 100, 2),
            "coverage_pct": round(coverage, 2),
            "expected_value_pct": round(expectancy, 4),
            "average_return_pct": round(expectancy, 4),
            "median_return_pct": round(median(returns), 4) if returns else 0.0,
            "profit_factor": round(profit_factor, 3),
            "payoff_ratio": round(payoff_ratio, 3),
            "average_win_pct": round(avg_win, 4),
            "average_loss_pct": round(avg_loss, 4),
            "big_move_rate": round(sum(r >= BIG_MOVE_THRESHOLD_PCT for r in returns) / total * 100, 2) if total else 0.0,
            "big_loss_rate": round(sum(r <= -BIG_MOVE_THRESHOLD_PCT for r in returns) / total * 100, 2) if total else 0.0,
            "best_return_pct": round(max(returns), 4) if returns else 0.0,
            "worst_return_pct": round(min(returns), 4) if returns else 0.0,
            "sample_sufficiency_pct": round(min(total / PROMOTION_SAMPLES, 1.0) * 100, 1),
        }

    @classmethod
    def _group(cls, samples: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in samples:
            grouped[str(sample.get(key_name) or "UNKNOWN")].append(sample)

        rows = [{"name": name, **cls._summary(group)} for name, group in grouped.items()]
        rows.sort(
            key=lambda row: (
                row["expected_value_pct"],
                row["directional_accuracy"],
                row["profit_factor"],
                row["samples"],
            ),
            reverse=True,
        )
        return rows

    @classmethod
    def _buckets(
        cls,
        samples: list[dict[str, Any]],
        field: str,
        step: int,
        suffix: str = "",
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in samples:
            value = _f(sample.get(field))
            lower = int(value // step) * step
            label = f"{lower}-{lower + step - 1}{suffix}"
            grouped[label].append(sample)

        rows = [{"name": name, **cls._summary(group)} for name, group in grouped.items()]
        rows.sort(key=lambda row: int(row["name"].split("-")[0]))
        return rows

    @staticmethod
    def recommendations(strategy_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        recommendations = []
        for row in strategy_rows:
            samples = row["samples"]
            ev = row["expected_value_pct"]
            accuracy = row["directional_accuracy"]
            ci_low = row["accuracy_ci_low"]
            profit_factor = row["profit_factor"]
            coverage = row["coverage_pct"]

            if samples < MIN_RECOMMENDATION_SAMPLES:
                action = "COLLECT MORE DATA"
                reason = f"{samples}/{MIN_RECOMMENDATION_SAMPLES} minimum samples"
            elif coverage < 35:
                action = "NO CHANGE"
                reason = f"Only {coverage}% decisive outcomes"
            elif samples < PROMOTION_SAMPLES:
                action = "KEEP TESTING"
                reason = f"{samples}/{PROMOTION_SAMPLES} promotion samples; EV {ev}%"
            elif ev > 0 and ci_low >= 52 and profit_factor >= 1.20:
                action = "PROMOTE"
                reason = (
                    f"EV {ev}%, CI floor {ci_low}%, PF {profit_factor}"
                )
            elif ev < 0 and accuracy < 45 and profit_factor < 0.90:
                action = "REDUCE WEIGHT"
                reason = (
                    f"EV {ev}%, accuracy {accuracy}%, PF {profit_factor}"
                )
            else:
                action = "KEEP"
                reason = (
                    f"EV {ev}%, accuracy {accuracy}% "
                    f"[{row['accuracy_ci_low']}–{row['accuracy_ci_high']}]"
                )

            recommendations.append({
                "strategy": row["name"],
                "action": action,
                "reason": reason,
            })
        return recommendations

    def report(self, horizon_hours: int = 1) -> dict[str, Any]:
        samples = self.load_samples(horizon_hours)
        strategies = self._group(samples, "state")
        return {
            "horizon_hours": horizon_hours,
            "overall": self._summary(samples),
            "strategies": strategies,
            "directions": self._group(samples, "direction"),
            "score_buckets": self._buckets(samples, "huge_rr_score", 1),
            "confidence_buckets": self._buckets(
                samples,
                "confidence_estimate_pct",
                5,
                "%",
            ),
            "recommendations": self.recommendations(strategies),
            "methodology": {
                "noise_threshold_pct": NOISE_THRESHOLD_PCT,
                "big_move_threshold_pct": BIG_MOVE_THRESHOLD_PCT,
                "minimum_recommendation_samples": MIN_RECOMMENDATION_SAMPLES,
                "promotion_samples": PROMOTION_SAMPLES,
            },
        }
