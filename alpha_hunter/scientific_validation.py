from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import mean
from typing import Any, Iterable

ENGINE_VERSION = "scientific-validation-shadow-v0.1"
SHADOW_ONLY = True
TRADE_PERMISSION = False
PRODUCTION_PROMOTION_PERMITTED = False


@dataclass(frozen=True)
class HypothesisSpec:
    hypothesis_id: str
    metric: str
    expected_direction: str
    minimum_effect: float
    min_samples_per_group: int
    alpha: float
    family_size: int
    preregistered: bool
    falsification_rule: str
    require_holdout: bool = True

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "HypothesisSpec":
        direction = str(raw.get("expected_direction") or "").strip().upper()
        if direction not in {"GREATER", "LESS"}:
            raise ValueError("expected_direction must be GREATER or LESS")
        hypothesis_id = str(raw.get("hypothesis_id") or "").strip()
        metric = str(raw.get("metric") or "").strip()
        falsification_rule = str(raw.get("falsification_rule") or "").strip()
        if not hypothesis_id or not metric or not falsification_rule:
            raise ValueError("hypothesis_id, metric and falsification_rule are required")
        minimum_effect = float(raw.get("minimum_effect"))
        min_samples = int(raw.get("min_samples_per_group"))
        alpha = float(raw.get("alpha"))
        family_size = int(raw.get("family_size"))
        if minimum_effect < 0:
            raise ValueError("minimum_effect must be >= 0")
        if min_samples < 2:
            raise ValueError("min_samples_per_group must be >= 2")
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        if family_size < 1:
            raise ValueError("family_size must be >= 1")
        return cls(
            hypothesis_id=hypothesis_id,
            metric=metric,
            expected_direction=direction,
            minimum_effect=minimum_effect,
            min_samples_per_group=min_samples,
            alpha=alpha,
            family_size=family_size,
            preregistered=bool(raw.get("preregistered")),
            falsification_rule=falsification_rule,
            require_holdout=bool(raw.get("require_holdout", True)),
        )


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("cannot calculate quantile of empty data")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _normalized_effect(test_mean: float, control_mean: float, expected_direction: str) -> float:
    raw = test_mean - control_mean
    return raw if expected_direction == "GREATER" else -raw


def _bootstrap_effect_interval(
    test: list[float],
    control: list[float],
    expected_direction: str,
    iterations: int,
    rng: random.Random,
) -> tuple[float, float]:
    effects: list[float] = []
    for _ in range(iterations):
        test_sample = [rng.choice(test) for _ in test]
        control_sample = [rng.choice(control) for _ in control]
        effects.append(
            _normalized_effect(mean(test_sample), mean(control_sample), expected_direction)
        )
    return _quantile(effects, 0.025), _quantile(effects, 0.975)


def _permutation_p_value(
    test: list[float],
    control: list[float],
    expected_direction: str,
    iterations: int,
    rng: random.Random,
) -> float:
    observed = _normalized_effect(mean(test), mean(control), expected_direction)
    pooled = list(test) + list(control)
    test_size = len(test)
    extreme = 0
    for _ in range(iterations):
        shuffled = list(pooled)
        rng.shuffle(shuffled)
        perm_test = shuffled[:test_size]
        perm_control = shuffled[test_size:]
        perm_effect = _normalized_effect(
            mean(perm_test), mean(perm_control), expected_direction
        )
        if perm_effect >= observed:
            extreme += 1
    return (extreme + 1) / (iterations + 1)


def evaluate_hypothesis(
    spec_raw: dict[str, Any],
    observations: Iterable[dict[str, Any]],
    *,
    bootstrap_iterations: int = 2000,
    permutation_iterations: int = 2000,
    seed: int = 17,
) -> dict[str, Any]:
    """Evaluate a preregistered shadow hypothesis against matched control evidence.

    Evidence may be classified as scientifically supported in shadow, but this module
    can never grant trade permission or production promotion.
    """
    try:
        spec = HypothesisSpec.from_dict(spec_raw)
    except (TypeError, ValueError) as exc:
        return {
            "engine_version": ENGINE_VERSION,
            "status": "INVALID_HYPOTHESIS",
            "reason": str(exc),
            "shadow_only": SHADOW_ONLY,
            "trade_permission": TRADE_PERMISSION,
            "production_promotion_permitted": PRODUCTION_PROMOTION_PERMITTED,
        }

    if not spec.preregistered:
        return {
            "engine_version": ENGINE_VERSION,
            "hypothesis_id": spec.hypothesis_id,
            "status": "INVALID_HYPOTHESIS",
            "reason": "HYPOTHESIS_NOT_PREREGISTERED",
            "shadow_only": SHADOW_ONLY,
            "trade_permission": TRADE_PERMISSION,
            "production_promotion_permitted": PRODUCTION_PROMOTION_PERMITTED,
        }

    rows = list(observations)
    seen_ids: set[str] = set()
    usable: list[tuple[str, float]] = []
    excluded_non_holdout = 0
    excluded_bad_quality = 0

    for row in rows:
        observation_id = str(row.get("observation_id") or "").strip()
        if not observation_id or observation_id in seen_ids:
            return {
                "engine_version": ENGINE_VERSION,
                "hypothesis_id": spec.hypothesis_id,
                "status": "DATA_INTEGRITY_FAILURE",
                "reason": "MISSING_OR_DUPLICATE_OBSERVATION_ID",
                "shadow_only": SHADOW_ONLY,
                "trade_permission": TRADE_PERMISSION,
                "production_promotion_permitted": PRODUCTION_PROMOTION_PERMITTED,
            }
        seen_ids.add(observation_id)

        if row.get("shadow_only") is not True or row.get("trade_permission") is not False:
            return {
                "engine_version": ENGINE_VERSION,
                "hypothesis_id": spec.hypothesis_id,
                "status": "SAFETY_BOUNDARY_VIOLATION",
                "reason": "OBSERVATION_OUTSIDE_SHADOW_NO_TRADE_BOUNDARY",
                "shadow_only": SHADOW_ONLY,
                "trade_permission": TRADE_PERMISSION,
                "production_promotion_permitted": PRODUCTION_PROMOTION_PERMITTED,
            }

        if row.get("data_quality_ok") is not True:
            excluded_bad_quality += 1
            continue

        if spec.require_holdout and row.get("holdout") is not True:
            excluded_non_holdout += 1
            continue

        group = str(row.get("group") or "").strip().upper()
        if group not in {"TEST", "CONTROL"}:
            continue
        value = _float(row.get("value"))
        if value is None:
            continue
        usable.append((group, value))

    test = [value for group, value in usable if group == "TEST"]
    control = [value for group, value in usable if group == "CONTROL"]

    common = {
        "engine_version": ENGINE_VERSION,
        "hypothesis_id": spec.hypothesis_id,
        "metric": spec.metric,
        "expected_direction": spec.expected_direction,
        "minimum_effect": spec.minimum_effect,
        "alpha": spec.alpha,
        "family_size": spec.family_size,
        "multiple_testing_method": "BONFERRONI",
        "adjusted_alpha": spec.alpha / spec.family_size,
        "test_n": len(test),
        "control_n": len(control),
        "excluded_non_holdout": excluded_non_holdout,
        "excluded_bad_quality": excluded_bad_quality,
        "falsification_rule": spec.falsification_rule,
        "replication_required": True,
        "shadow_only": SHADOW_ONLY,
        "trade_permission": TRADE_PERMISSION,
        "production_promotion_permitted": PRODUCTION_PROMOTION_PERMITTED,
    }

    if len(test) < spec.min_samples_per_group or len(control) < spec.min_samples_per_group:
        return {
            **common,
            "status": "INSUFFICIENT_DATA",
            "decision": "COLLECT_MORE_EVIDENCE",
            "reason": "MIN_SAMPLE_NOT_MET",
            "scientific_support": False,
        }

    if bootstrap_iterations < 200 or permutation_iterations < 200:
        return {
            **common,
            "status": "INVALID_ANALYSIS_CONFIG",
            "decision": "DO_NOT_EVALUATE",
            "reason": "RESAMPLING_ITERATIONS_TOO_LOW",
            "scientific_support": False,
        }

    rng = random.Random(seed)
    test_mean = mean(test)
    control_mean = mean(control)
    normalized_effect = _normalized_effect(
        test_mean, control_mean, spec.expected_direction
    )
    raw_effect = test_mean - control_mean

    ci_low, ci_high = _bootstrap_effect_interval(
        test, control, spec.expected_direction, bootstrap_iterations, rng
    )
    p_value = _permutation_p_value(
        test, control, spec.expected_direction, permutation_iterations, rng
    )

    effect_pass = normalized_effect >= spec.minimum_effect
    confidence_pass = ci_low > 0
    multiplicity_pass = p_value <= (spec.alpha / spec.family_size)
    supported = effect_pass and confidence_pass and multiplicity_pass

    falsified = normalized_effect <= -spec.minimum_effect
    if supported:
        status = "SUPPORTED_SHADOW"
        decision = "RETAIN_FOR_REPLICATION"
    elif falsified:
        status = "FALSIFIED"
        decision = "REJECT_HYPOTHESIS"
    else:
        status = "INCONCLUSIVE"
        decision = "COLLECT_MORE_EVIDENCE"

    return {
        **common,
        "status": status,
        "decision": decision,
        "scientific_support": supported,
        "test_mean": test_mean,
        "control_mean": control_mean,
        "raw_effect": raw_effect,
        "direction_normalized_effect": normalized_effect,
        "bootstrap_95_ci_normalized_effect": [ci_low, ci_high],
        "permutation_p_value_one_sided": p_value,
        "effect_size_pass": effect_pass,
        "confidence_interval_pass": confidence_pass,
        "multiple_testing_pass": multiplicity_pass,
    }
