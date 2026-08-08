from __future__ import annotations

from typing import Any


TRACE_VERSION = "7.2.1"


STAGE_ORDER = {
    "NORMAL": 0,
    "ANOMALY_DETECTED": 1,
    "UNDER_SURVEILLANCE": 2,
    "BEHAVIOUR_ACCELERATING": 3,
    "DIRECTION_EMERGING": 4,
    "EXECUTION_TEST": 5,
    "TRADE_READY": 6,
    "REJECTED": -1,
}


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_list(
    values: Any,
) -> list[str]:
    if not values:
        return []

    if isinstance(values, str):
        return [values]

    if not isinstance(values, list):
        return [str(values)]

    output: list[str] = []

    for value in values:
        text = str(value).strip()

        if text and text not in output:
            output.append(text)

    return output


def _normalize_stage(
    value: Any,
) -> str | None:
    if value is None:
        return None

    stage = (
        str(value)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )

    aliases = {
        "WATCH_LONG":
            "UNDER_SURVEILLANCE",

        "WATCH_SHORT":
            "UNDER_SURVEILLANCE",

        "DIRECTION_EMERGING_LONG":
            "DIRECTION_EMERGING",

        "DIRECTION_EMERGING_SHORT":
            "DIRECTION_EMERGING",

        "EXECUTION_WATCH":
            "EXECUTION_TEST",

        "LONG_READY":
            "TRADE_READY",

        "SHORT_READY":
            "TRADE_READY",
    }

    return aliases.get(
        stage,
        stage,
    )


def _quality_rejections(
    record: dict[str, Any],
) -> list[str]:
    return _clean_list(
        record.get(
            "rejection_reasons"
        )
    )


def _minimum_discovery_score(
    config: dict[str, Any],
) -> float:
    return _safe_float(
        config.get(
            "candidate_quality",
            {},
        ).get(
            "minimum_discovery_score",
            5.0,
        ),
        5.0,
    )


def _trace_stage(
    record: dict[str, Any],
    config: dict[str, Any],
) -> str:

    behaviour_config = config.get(
        "behaviour_engine",
        {},
    )

    score = _safe_float(
        record.get(
            "behaviour_score"
        )
    )

    discovery = bool(
        record.get(
            "discovery_permission"
        )
    )

    trade_ready = bool(
        record.get(
            "v7_trade_ready"
        )
    )

    hard_rejections = _quality_rejections(
        record
    )

    if trade_ready:
        return "TRADE_READY"

    # Critical V7.2.1 distinction:
    # Only explicit structural/quality failures are REJECTED.
    # A candidate below discovery score is still developing.
    if hard_rejections:
        return "REJECTED"

    execution_threshold = _safe_float(
        behaviour_config.get(
            "execution_test_threshold",
            7.5,
        ),
        7.5,
    )

    direction_threshold = _safe_float(
        behaviour_config.get(
            "direction_emerging_threshold",
            6.5,
        ),
        6.5,
    )

    accelerating_threshold = _safe_float(
        behaviour_config.get(
            "behaviour_accelerating_threshold",
            5.5,
        ),
        5.5,
    )

    surveillance_threshold = _safe_float(
        behaviour_config.get(
            "under_surveillance_threshold",
            4.5,
        ),
        4.5,
    )

    anomaly_threshold = _safe_float(
        behaviour_config.get(
            "early_anomaly_threshold",
            3.5,
        ),
        3.5,
    )

    if (
        discovery
        and score >= execution_threshold
    ):
        return "EXECUTION_TEST"

    if score >= direction_threshold:
        return "DIRECTION_EMERGING"

    if score >= accelerating_threshold:
        return "BEHAVIOUR_ACCELERATING"

    if score >= surveillance_threshold:
        return "UNDER_SURVEILLANCE"

    if score >= anomaly_threshold:
        return "ANOMALY_DETECTED"

    return "NORMAL"


def _discovery_reasons(
    record: dict[str, Any],
) -> list[str]:

    reasons: list[str] = []

    phase = str(
        record.get(
            "market_phase",
            "",
        )
    ).upper()

    timing = str(
        record.get(
            "opportunity_timing",
            "",
        )
    ).upper()

    behaviour_score = _safe_float(
        record.get(
            "behaviour_score"
        )
    )

    behaviour = record.get(
        "behaviour",
        {},
    )

    components = (
        behaviour.get(
            "components",
            {},
        )
        if isinstance(
            behaviour,
            dict,
        )
        else {}
    )

    if phase:
        reasons.append(
            f"MARKET_PHASE_{phase}"
        )

    if timing:
        reasons.append(
            f"TIMING_{timing}"
        )

    reasons.append(
        f"BEHAVIOUR_SCORE_{behaviour_score:.2f}"
    )

    if isinstance(
        components,
        dict,
    ):
        ranked_components = sorted(
            components.items(),
            key=lambda item:
                _safe_float(
                    item[1]
                ),
            reverse=True,
        )

        for name, value in ranked_components[:3]:

            component_value = _safe_float(
                value
            )

            if component_value > 0:
                reasons.append(
                    (
                        "BEHAVIOUR_"
                        f"{str(name).upper()}_"
                        f"{component_value:.2f}"
                    )
                )

    if record.get(
        "discovery_permission"
    ):
        reasons.append(
            "DISCOVERY_GATE_PASSED"
        )

    return reasons


def _promotion_reasons(
    record: dict[str, Any],
    current_stage: str,
    previous_stage: str | None,
    previous: dict[str, Any],
) -> list[str]:

    reasons: list[str] = []

    current_rank = STAGE_ORDER.get(
        current_stage,
        0,
    )

    previous_rank = STAGE_ORDER.get(
        previous_stage or "NORMAL",
        0,
    )

    if current_rank > previous_rank:
        reasons.append(
            (
                f"STAGE_ADVANCED_"
                f"{previous_stage or 'NORMAL'}"
                f"_TO_{current_stage}"
            )
        )

    previous_score = _safe_float(
        previous.get(
            "behaviour_score"
        )
    )

    current_score = _safe_float(
        record.get(
            "behaviour_score"
        )
    )

    if current_score > previous_score:
        reasons.append(
            (
                "BEHAVIOUR_SCORE_INCREASED_"
                f"{previous_score:.2f}_TO_"
                f"{current_score:.2f}"
            )
        )

    previous_phase = str(
        previous.get(
            "market_phase",
            "",
        )
    ).upper()

    current_phase = str(
        record.get(
            "market_phase",
            "",
        )
    ).upper()

    if (
        previous_phase
        and current_phase
        and previous_phase != current_phase
    ):
        reasons.append(
            (
                "PHASE_CHANGED_"
                f"{previous_phase}_TO_"
                f"{current_phase}"
            )
        )

    if record.get(
        "discovery_permission"
    ):
        reasons.append(
            "DISCOVERY_PERMISSION_ACTIVE"
        )

    if record.get(
        "v7_trade_ready"
    ):
        reasons.append(
            "EXECUTION_PERMISSION_ACTIVE"
        )

    return reasons


def _blocking_gate(
    record: dict[str, Any],
    stage: str,
    config: dict[str, Any],
) -> str | None:

    rejections = _quality_rejections(
        record
    )

    if rejections:
        return rejections[0]

    score = _safe_float(
        record.get(
            "behaviour_score"
        )
    )

    discovery_minimum = _minimum_discovery_score(
        config
    )

    if score < discovery_minimum:
        return "DISCOVERY_SCORE"

    if not record.get(
        "discovery_permission"
    ):
        return "DISCOVERY_GATE"

    if stage in {
        "NORMAL",
        "ANOMALY_DETECTED",
        "UNDER_SURVEILLANCE",
        "BEHAVIOUR_ACCELERATING",
    }:
        return "DIRECTION_PROOF"

    if stage == "DIRECTION_EMERGING":
        return "EXECUTION_TEST"

    if stage == "EXECUTION_TEST":
        return "TRADE_PERMISSION"

    return None


def _next_required_condition(
    record: dict[str, Any],
    stage: str,
    config: dict[str, Any],
) -> str:

    quality = config.get(
        "candidate_quality",
        {},
    )

    behaviour_config = config.get(
        "behaviour_engine",
        {},
    )

    rejections = _quality_rejections(
        record
    )

    if rejections:
        return (
            "CLEAR_REJECTION: "
            + rejections[0]
        )

    score = _safe_float(
        record.get(
            "behaviour_score"
        )
    )

    discovery_minimum = _minimum_discovery_score(
        config
    )

    if score < discovery_minimum:
        return (
            "BEHAVIOUR_SCORE >= "
            f"{discovery_minimum}"
        )

    if stage == "NORMAL":
        threshold = behaviour_config.get(
            "early_anomaly_threshold",
            3.5,
        )

        return (
            "BEHAVIOUR_SCORE >= "
            f"{threshold}"
        )

    if stage == "ANOMALY_DETECTED":
        threshold = behaviour_config.get(
            "under_surveillance_threshold",
            4.5,
        )

        return (
            "BEHAVIOUR_SCORE >= "
            f"{threshold}"
        )

    if stage == "UNDER_SURVEILLANCE":
        threshold = behaviour_config.get(
            "behaviour_accelerating_threshold",
            5.5,
        )

        return (
            "BEHAVIOUR_SCORE >= "
            f"{threshold}"
        )

    if stage == "BEHAVIOUR_ACCELERATING":
        threshold = behaviour_config.get(
            "direction_emerging_threshold",
            6.5,
        )

        return (
            "BEHAVIOUR_SCORE >= "
            f"{threshold}"
            " WITH DIRECTIONAL CONFIRMATION"
        )

    if stage == "DIRECTION_EMERGING":
        threshold = behaviour_config.get(
            "execution_test_threshold",
            7.5,
        )

        return (
            "BEHAVIOUR_SCORE >= "
            f"{threshold}"
            " AND DISCOVERY GATE PASS"
        )

    if stage == "EXECUTION_TEST":

        minimum_rr = quality.get(
            "minimum_execution_reward_risk",
            5.0,
        )

        minimum_execution = quality.get(
            "minimum_execution_score",
            7.5,
        )

        return (
            "EXECUTION_SCORE >= "
            f"{minimum_execution}"
            " AND RR >= 1:"
            f"{minimum_rr}"
            " WITH VALID TRIGGER"
        )

    if stage == "TRADE_READY":
        return (
            "MAINTAIN EXECUTION VALIDITY "
            "AND MANAGE OPEN TRADE"
        )

    if stage == "REJECTED":
        return (
            "CLEAR STRUCTURAL QUALITY REJECTION"
        )

    return "CONTINUE SURVEILLANCE"


def build_decision_trace(
    record: dict[str, Any],
    previous: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:

    previous = previous or {}

    stage = _trace_stage(
        record,
        config,
    )

    previous_trace = previous.get(
        "decision_trace",
        {},
    )

    previous_stage = _normalize_stage(
        previous_trace.get(
            "decision_stage"
        )
        or previous.get(
            "decision_stage"
        )
        or previous.get(
            "state"
        )
    )

    stage_changed = (
        previous_stage is not None
        and previous_stage != stage
    )

    rejection_reasons = _quality_rejections(
        record
    )

    return {
        "version":
            TRACE_VERSION,

        "decision_stage":
            stage,

        "previous_stage":
            previous_stage,

        "stage_changed":
            stage_changed,

        "discovery_reasons":
            _discovery_reasons(
                record
            ),

        "promotion_reasons":
            _promotion_reasons(
                record,
                stage,
                previous_stage,
                previous,
            ),

        "rejection_reasons":
            rejection_reasons,

        "blocking_gate":
            _blocking_gate(
                record,
                stage,
                config,
            ),

        "next_required_condition":
            _next_required_condition(
                record,
                stage,
                config,
            ),

        "behaviour_score":
            _safe_float(
                record.get(
                    "behaviour_score"
                )
            ),

        "previous_behaviour_score":
            _safe_float(
                previous.get(
                    "behaviour_score"
                )
            ),

        "market_phase":
            record.get(
                "market_phase"
            ),

        "previous_market_phase":
            previous.get(
                "market_phase"
            ),

        "opportunity_timing":
            record.get(
                "opportunity_timing"
            ),

        "discovery_permission":
            bool(
                record.get(
                    "discovery_permission"
                )
            ),

        "execution_permission":
            bool(
                record.get(
                    "v7_trade_ready"
                )
            ),

        "candidate_quality_status":
            record.get(
                "candidate_quality_status"
            ),
    }
