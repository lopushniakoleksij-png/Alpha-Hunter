from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


MODEL_VERSION = "7.10-early-execution-rr-v1"
MIN_HUGE_RR = 5.0

VALID_PHASES = {
    "DETECTION",
    "EMERGING",
    "CONFIRMED",
}

CLASS_EARLY_EXECUTABLE = "EARLY_EXECUTABLE"
CLASS_CONFIRMATION_TOO_LATE = "CONFIRMATION_TOO_LATE"
CLASS_RIGHT_DIRECTION_BAD_RR = "RIGHT_DIRECTION_BAD_RR"
CLASS_GOOD_RR_WRONG_DIRECTION = "GOOD_RR_WRONG_DIRECTION"
CLASS_WRONG_DIRECTION_BAD_RR = "WRONG_DIRECTION_BAD_RR"
CLASS_NO_EXECUTABLE_STRUCTURE = "NO_EXECUTABLE_STRUCTURE"
CLASS_NO_LIVE_DIRECTION = "NO_LIVE_DIRECTION"
CLASS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def float_or_none(
    value: Any,
) -> Optional[float]:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def bool_or_none(
    value: Any,
) -> Optional[bool]:
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    text = str(value).strip().lower()

    if text in {
        "true",
        "1",
        "yes",
    }:
        return True

    if text in {
        "false",
        "0",
        "no",
    }:
        return False

    return None


def evidence_dict(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}

        if isinstance(parsed, dict):
            return parsed

    return {}


@dataclass(frozen=True)
class PhaseEvidence:
    phase: str

    direction_available: bool
    direction_consistent_with_confirmed: Optional[bool]

    structure_valid: bool
    rr_to_structure: Optional[float]

    phase_price: Optional[float] = None
    confidence: Optional[float] = None
    minutes_from_detection: Optional[float] = None
    move_consumed_pct: Optional[float] = None

    observed_direction: Optional[str] = None
    measurement_quality: Optional[str] = None

    def __post_init__(self) -> None:
        if self.phase not in VALID_PHASES:
            raise ValueError(
                f"Invalid phase: {self.phase}"
            )

    @property
    def measurement_complete(self) -> bool:
        return (
            self.measurement_quality
            in {
                None,
                "",
                "COMPLETE",
            }
        )

    @property
    def has_executable_structure(self) -> bool:
        return (
            self.measurement_complete
            and self.structure_valid
            and self.rr_to_structure is not None
            and self.rr_to_structure > 0
        )

    @property
    def huge_rr_available(self) -> bool:
        return (
            self.has_executable_structure
            and self.rr_to_structure is not None
            and self.rr_to_structure >= MIN_HUGE_RR
        )


@dataclass(frozen=True)
class EarlyExecutionResult:
    classification: str

    earliest_live_phase: Optional[str]

    emerging_rr: Optional[float]
    confirmed_rr: Optional[float]

    rr_lost_emerging_to_confirmed: Optional[float]

    emerging_direction_available: bool
    emerging_direction_consistent: Optional[bool]

    emerging_structure_valid: bool
    confirmed_structure_valid: bool

    emerging_huge_rr_available: bool
    confirmed_huge_rr_available: bool

    trade_permission: bool = False


def rr_lost(
    earlier_rr: Optional[float],
    later_rr: Optional[float],
) -> Optional[float]:
    if (
        earlier_rr is None
        or later_rr is None
    ):
        return None

    return earlier_rr - later_rr


def earliest_live_phase(
    emerging: PhaseEvidence,
    confirmed: PhaseEvidence,
) -> Optional[str]:
    if emerging.direction_available:
        return "EMERGING"

    if confirmed.direction_available:
        return "CONFIRMED"

    return None


def classify_episode(
    emerging: PhaseEvidence,
    confirmed: PhaseEvidence,
) -> EarlyExecutionResult:
    if emerging.phase != "EMERGING":
        raise ValueError(
            "emerging evidence must have phase=EMERGING"
        )

    if confirmed.phase != "CONFIRMED":
        raise ValueError(
            "confirmed evidence must have phase=CONFIRMED"
        )

    early_phase = earliest_live_phase(
        emerging,
        confirmed,
    )

    emerging_rr = emerging.rr_to_structure
    confirmed_rr = confirmed.rr_to_structure

    lost = rr_lost(
        emerging_rr,
        confirmed_rr,
    )

    emerging_huge_rr = (
        emerging.huge_rr_available
    )

    confirmed_huge_rr = (
        confirmed.huge_rr_available
    )

    if (
        not emerging.measurement_complete
        or not confirmed.measurement_complete
    ):
        classification = (
            CLASS_INSUFFICIENT_EVIDENCE
        )

    elif early_phase is None:
        classification = (
            CLASS_NO_LIVE_DIRECTION
        )

    elif (
        emerging.direction_available
        and
        emerging.direction_consistent_with_confirmed
        is False
        and
        emerging_huge_rr
    ):
        classification = (
            CLASS_GOOD_RR_WRONG_DIRECTION
        )

    elif (
        emerging.direction_available
        and
        emerging.direction_consistent_with_confirmed
        is False
        and
        emerging.has_executable_structure
        and
        not emerging_huge_rr
    ):
        classification = (
            CLASS_WRONG_DIRECTION_BAD_RR
        )

    elif (
        emerging.direction_available
        and
        emerging.direction_consistent_with_confirmed
        is True
        and
        emerging_huge_rr
    ):
        if not confirmed_huge_rr:
            classification = (
                CLASS_CONFIRMATION_TOO_LATE
            )
        else:
            classification = (
                CLASS_EARLY_EXECUTABLE
            )

    elif (
        emerging.direction_available
        and
        emerging.direction_consistent_with_confirmed
        is True
        and
        emerging.has_executable_structure
        and
        not emerging_huge_rr
    ):
        classification = (
            CLASS_RIGHT_DIRECTION_BAD_RR
        )

    elif (
        not emerging.has_executable_structure
        and
        not confirmed.has_executable_structure
    ):
        classification = (
            CLASS_NO_EXECUTABLE_STRUCTURE
        )

    elif (
        emerging.direction_consistent_with_confirmed
        is None
    ):
        classification = (
            CLASS_INSUFFICIENT_EVIDENCE
        )

    else:
        classification = (
            CLASS_RIGHT_DIRECTION_BAD_RR
        )

    return EarlyExecutionResult(
        classification=classification,

        earliest_live_phase=early_phase,

        emerging_rr=emerging_rr,
        confirmed_rr=confirmed_rr,

        rr_lost_emerging_to_confirmed=lost,

        emerging_direction_available=(
            emerging.direction_available
        ),

        emerging_direction_consistent=(
            emerging
            .direction_consistent_with_confirmed
        ),

        emerging_structure_valid=(
            emerging.structure_valid
        ),

        confirmed_structure_valid=(
            confirmed.structure_valid
        ),

        emerging_huge_rr_available=(
            emerging_huge_rr
        ),

        confirmed_huge_rr_available=(
            confirmed_huge_rr
        ),

        trade_permission=False,
    )


def phase_evidence_from_v78_row(
    row: dict[str, Any],
    expected_phase: str,
) -> PhaseEvidence:
    phase = str(
        row.get("phase")
        or ""
    ).upper()

    if phase != expected_phase:
        raise ValueError(
            f"Expected {expected_phase}, got {phase}"
        )

    evidence = evidence_dict(
        row.get("evidence")
    )

    observed_direction = str(
        evidence.get(
            "observed_direction_at_phase"
        )
        or (
            row.get("direction")
            if phase == "CONFIRMED"
            else ""
        )
        or ""
    ).upper()

    live_direction_available = (
        observed_direction
        in {
            "LONG",
            "SHORT",
        }
    )

    return PhaseEvidence(
        phase=phase,

        direction_available=(
            live_direction_available
        ),

        direction_consistent_with_confirmed=(
            bool_or_none(
                row.get(
                    "direction_consistent_with_confirmed"
                )
            )
        ),

        structure_valid=(
            bool_or_none(
                row.get(
                    "structure_valid"
                )
            )
            is True
        ),

        rr_to_structure=(
            float_or_none(
                row.get(
                    "rr_to_structure"
                )
            )
        ),

        phase_price=(
            float_or_none(
                row.get(
                    "phase_price"
                )
            )
        ),

        confidence=(
            float_or_none(
                row.get(
                    "confidence"
                )
            )
        ),

        minutes_from_detection=(
            float_or_none(
                row.get(
                    "minutes_from_detection"
                )
            )
        ),

        move_consumed_pct=(
            float_or_none(
                row.get(
                    "move_consumed_pct"
                )
            )
        ),

        observed_direction=(
            observed_direction
            or None
        ),

        measurement_quality=(
            str(
                row.get(
                    "measurement_quality"
                )
                or ""
            ).upper()
            or None
        ),
    )


def classify_v78_phase_rows(
    rows: list[dict[str, Any]],
) -> Optional[EarlyExecutionResult]:
    by_phase: dict[
        str,
        dict[str, Any],
    ] = {}

    for row in rows:
        phase = str(
            row.get("phase")
            or ""
        ).upper()

        if phase in VALID_PHASES:
            by_phase[phase] = row

    emerging_row = by_phase.get(
        "EMERGING"
    )

    confirmed_row = by_phase.get(
        "CONFIRMED"
    )

    if (
        emerging_row is None
        or confirmed_row is None
    ):
        return None

    emerging = (
        phase_evidence_from_v78_row(
            emerging_row,
            "EMERGING",
        )
    )

    confirmed = (
        phase_evidence_from_v78_row(
            confirmed_row,
            "CONFIRMED",
        )
    )

    return classify_episode(
        emerging,
        confirmed,
    )


ROOT = Path(__file__).resolve().parent
V78_TABLE = "alpha_hunter_timing_rr_shadow"


def readonly_headers(
    settings: SupabaseConfig,
) -> dict[str, str]:
    return {
        "apikey": settings.key,
        "Authorization": (
            f"Bearer {settings.key}"
        ),
    }


def load_v78_rows(
    settings: SupabaseConfig,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = requests.get(
            (
                f"{settings.url}"
                f"/rest/v1/{V78_TABLE}"
            ),
            params={
                "select": "*",
                "order": (
                    "episode_id.asc,"
                    "phase_at_utc.asc"
                ),
                "limit": str(page_size),
                "offset": str(offset),
            },
            headers=readonly_headers(
                settings
            ),
            timeout=settings.timeout_seconds,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "V7.10 V7.8 evidence load failed: "
                f"HTTP {response.status_code}: "
                f"{response.text[:800]}"
            )

        payload = response.json()

        if not isinstance(
            payload,
            list,
        ):
            raise RuntimeError(
                "V7.10 V7.8 evidence response "
                "is not a list"
            )

        valid = [
            row
            for row in payload
            if isinstance(row, dict)
        ]

        rows.extend(valid)

        if len(payload) < page_size:
            break

        offset += page_size

    return rows


def group_v78_rows(
    rows: list[dict[str, Any]],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for row in rows:
        episode_id = str(
            row.get("episode_id")
            or ""
        )

        if not episode_id:
            continue

        grouped.setdefault(
            episode_id,
            [],
        ).append(row)

    return grouped


def analyze_v78_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped = group_v78_rows(
        rows
    )

    classifications: list[
        dict[str, Any]
    ] = []

    skipped_missing_phase = 0

    counts: dict[str, int] = {}

    for episode_id, phase_rows in grouped.items():
        result = classify_v78_phase_rows(
            phase_rows
        )

        if result is None:
            skipped_missing_phase += 1
            continue

        by_phase = {
            str(
                row.get("phase")
                or ""
            ).upper(): row
            for row in phase_rows
        }

        emerging_row = by_phase[
            "EMERGING"
        ]

        confirmed_row = by_phase[
            "CONFIRMED"
        ]

        emerging = (
            phase_evidence_from_v78_row(
                emerging_row,
                "EMERGING",
            )
        )

        confirmed = (
            phase_evidence_from_v78_row(
                confirmed_row,
                "CONFIRMED",
            )
        )

        symbol = str(
            emerging_row.get("symbol")
            or confirmed_row.get("symbol")
            or ""
        )

        path = str(
            emerging_row.get("path")
            or confirmed_row.get("path")
            or ""
        )

        row = {
            "episode_id":
                episode_id,

            "symbol":
                symbol,

            "path":
                path,

            "classification":
                result.classification,

            "emerging_direction":
                emerging.observed_direction,

            "emerging_direction_consistent":
                (
                    emerging
                    .direction_consistent_with_confirmed
                ),

            "emerging_confidence":
                emerging.confidence,

            "emerging_price":
                emerging.phase_price,

            "emerging_minutes":
                emerging.minutes_from_detection,

            "emerging_move_consumed_pct":
                emerging.move_consumed_pct,

            "emerging_rr":
                result.emerging_rr,

            "confirmed_rr":
                result.confirmed_rr,

            "rr_lost":
                (
                    result
                    .rr_lost_emerging_to_confirmed
                ),

            "emerging_structure_valid":
                (
                    result
                    .emerging_structure_valid
                ),

            "confirmed_structure_valid":
                (
                    result
                    .confirmed_structure_valid
                ),

            "emerging_huge_rr":
                (
                    result
                    .emerging_huge_rr_available
                ),

            "confirmed_huge_rr":
                (
                    result
                    .confirmed_huge_rr_available
                ),

            "emerging_measurement_quality":
                (
                    emerging
                    .measurement_quality
                ),

            "confirmed_measurement_quality":
                (
                    confirmed
                    .measurement_quality
                ),

            "trade_permission":
                False,
        }

        classifications.append(
            row
        )

        classification = (
            result.classification
        )

        counts[classification] = (
            counts.get(
                classification,
                0,
            )
            + 1
        )

    classifications.sort(
        key=lambda row: (
            -(
                float(
                    row["rr_lost"]
                )
                if row.get(
                    "rr_lost"
                ) is not None
                else -999999.0
            ),
            str(
                row.get("symbol")
                or ""
            ),
        )
    )

    return {
        "v78_rows":
            len(rows),

        "episodes":
            len(grouped),

        "classified":
            len(classifications),

        "skipped_missing_phase":
            skipped_missing_phase,

        "classification_counts":
            counts,

        "classifications":
            classifications,

        "trade_permission":
            False,
    }


def value_text(
    value: Any,
) -> str:
    number = float_or_none(
        value
    )

    if number is None:
        return "—"

    return f"{number:.2f}"


def print_analysis(
    report: dict[str, Any],
) -> None:
    print()
    print("=" * 118)
    print(
        "ALPHA HUNTER V7.10 "
        "EARLY EXECUTION & RR PRESERVATION — "
        "READ-ONLY SHADOW"
    )
    print("=" * 118)

    print(
        "V7.8 rows loaded:",
        report["v78_rows"],
    )

    print(
        "Episodes found:",
        report["episodes"],
    )

    print(
        "Episodes classified:",
        report["classified"],
    )

    print(
        "Skipped missing "
        "EMERGING/CONFIRMED:",
        report[
            "skipped_missing_phase"
        ],
    )

    print()
    print("CLASSIFICATION COUNTS")

    counts = report[
        "classification_counts"
    ]

    if not counts:
        print("None")
    else:
        for name in sorted(counts):
            print(
                f"{name:<32}"
                f"{counts[name]}"
            )

    important = {
        CLASS_CONFIRMATION_TOO_LATE,
        CLASS_EARLY_EXECUTABLE,
        CLASS_GOOD_RR_WRONG_DIRECTION,
        CLASS_WRONG_DIRECTION_BAD_RR,
    }

    rows = [
        row
        for row in report[
            "classifications"
        ]
        if row["classification"]
        in important
    ]

    print()
    print("=" * 118)
    print(
        "EARLY-EXECUTION DIAGNOSTIC CASES"
    )
    print("=" * 118)

    print(
        f"{'SYMBOL':<15}"
        f"{'CLASS':<30}"
        f"{'DIR':<8}"
        f"{'OK?':<6}"
        f"{'E_RR':>7}"
        f"{'C_RR':>7}"
        f"{'LOST':>8}"
        f"{'MIN':>8}"
        f"{'MOVE':>8}"
    )

    print("-" * 118)

    if not rows:
        print(
            "No qualifying diagnostic "
            "cases in current evidence."
        )

    for row in rows[:50]:
        consistent = (
            "Y"
            if row[
                "emerging_direction_consistent"
            ] is True
            else (
                "N"
                if row[
                    "emerging_direction_consistent"
                ] is False
                else "—"
            )
        )

        print(
            f"{row['symbol']:<15}"
            f"{row['classification']:<30}"
            f"{str(row['emerging_direction'] or '—'):<8}"
            f"{consistent:<6}"
            f"{value_text(row['emerging_rr']):>7}"
            f"{value_text(row['confirmed_rr']):>7}"
            f"{value_text(row['rr_lost']):>8}"
            f"{value_text(row['emerging_minutes']):>8}"
            f"{value_text(row['emerging_move_consumed_pct']):>8}"
        )

    print()
    print(
        "IMPORTANT: V7.10 IS READ-ONLY "
        "SHADOW RESEARCH."
    )

    print(
        "No Supabase rows were written."
    )

    print(
        "No trade permission was generated."
    )

    print("=" * 118)


def main() -> int:
    load_env_file(
        ROOT / ".env"
    )

    config = load_config(
        ROOT / "config.json"
    )

    settings = (
        SupabaseConfig
        .from_environment(
            config
        )
    )

    if settings is None:
        raise SystemExit(
            "Supabase is not configured"
        )

    rows = load_v78_rows(
        settings
    )

    report = analyze_v78_rows(
        rows
    )

    print_analysis(
        report
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
