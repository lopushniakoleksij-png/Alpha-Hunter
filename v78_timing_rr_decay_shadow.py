from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig
from v75_lifecycle_job import load_state, load_supabase_state
from v76_direction_shadow import load_direction_states
from v76_post_confirmation_tracker import confirmation_shadow
from v77_execution_feasibility_shadow import (
    CANDLE_LIMIT,
    STRUCTURE_WINDOW,
    STOP_BUFFER_ATR_FRACTION,
    atr,
    choose_stop,
    choose_target,
    dt,
    f,
    feasibility_status,
    parse_closed_candles,
    rr,
    stop_distance_pct,
    stop_quality,
    structural_reward_pct,
    swing_levels,
)

ROOT = Path(__file__).resolve().parent
TABLE = "alpha_hunter_timing_rr_shadow"
MODEL_VERSION = "7.8-timing-rr-decay-v1"

PHASES = (
    "DETECTION",
    "EMERGING",
    "CONFIRMED",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def headers(
    settings: SupabaseConfig,
    merge: bool = False,
) -> dict[str, str]:
    result = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }

    if merge:
        result["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=minimal"
        )

    return result


def phase_snapshot_id(
    episode_id: str,
    phase: str,
) -> str:
    raw = (
        f"{episode_id}|"
        f"{MODEL_VERSION}|"
        f"{phase}"
    ).encode("utf-8")

    return hashlib.sha256(raw).hexdigest()[:24]


def minutes_between(
    first: datetime,
    later: datetime,
) -> float:
    return (
        later - first
    ).total_seconds() / 60.0


def rr_decay(
    earlier_rr: float | None,
    later_rr: float | None,
) -> float | None:
    if (
        earlier_rr is None
        or later_rr is None
    ):
        return None

    # Positive = reward-to-risk was lost.
    # Negative = reward-to-risk improved.
    return earlier_rr - later_rr



def load_phase_candles(
    client: BitgetClient,
    symbol: str,
    product_type: str,
    granularity: str,
    phase_at: datetime,
    interval_minutes: int,
    limit: int = CANDLE_LIMIT,
) -> list[Any]:
    """Load historical candles ending at the phase timestamp."""

    if interval_minutes <= 0 or limit <= 0:
        return []

    phase_at = phase_at.astimezone(timezone.utc)

    end_ms = int(
        phase_at.timestamp()
        * 1000
    )

    start_at = (
        phase_at
        - timedelta(
            minutes=(
                interval_minutes
                * int(limit)
            )
        )
    )

    start_ms = int(
        start_at.timestamp()
        * 1000
    )

    return (
        client._get(
            "/api/v2/mix/market/history-candles",
            {
                "symbol": symbol,
                "productType": product_type,
                "granularity": granularity,
                "startTime": str(start_ms),
                "endTime": str(end_ms),
                "limit": str(
                    min(
                        max(int(limit), 1),
                        200,
                    )
                ),
            },
        )
        or []
    )


def load_existing_snapshot_rows(
    settings: SupabaseConfig,
    snapshot_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Read existing V7.8 evidence before deciding what may be written."""

    ids = sorted(
        {
            str(value)
            for value in snapshot_ids
            if value
        }
    )

    if not ids:
        return {}

    response = requests.get(
        f"{settings.url}/rest/v1/{TABLE}",
        params={
            "select":
                "snapshot_id,measurement_quality",
            "snapshot_id":
                "in.("
                + ",".join(ids)
                + ")",
        },
        headers=headers(settings),
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "V7.8 existing snapshot load failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if not isinstance(payload, list):
        raise RuntimeError(
            "V7.8 existing snapshot response "
            "is not a list"
        )

    result = {}

    for row in payload:
        if not isinstance(row, dict):
            continue

        snapshot_id = str(
            row.get("snapshot_id")
            or ""
        )

        if snapshot_id:
            result[snapshot_id] = row

    return result


def build_phase_row(
    *,
    episode: Any,
    state: dict[str, Any],
    phase: str,
    phase_at: datetime,
    phase_price: float,
    confirmed_direction: str,
    confirmed_confidence: float | None,
    observed_direction_at_phase: str | None,
    observed_confidence_at_phase: float | None,
    move_consumed_pct: float | None,
    candles_15m_raw: list[Any],
    candles_1h_raw: list[Any],
    processed_at: datetime,
) -> dict[str, Any] | None:

    if phase not in PHASES:
        return None

    episode_id = str(
        state.get("episode_id")
        or episode.episode_id
        or ""
    )

    symbol = str(
        state.get("symbol")
        or episode.symbol
        or ""
    )

    direction = str(
        confirmed_direction
        or ""
    ).upper()

    if (
        not episode_id
        or not symbol
        or phase_price <= 0
        or direction not in {"LONG", "SHORT"}
    ):
        return None

    detection_at = dt(
        episode.first_detected_at_utc
    )

    if detection_at is None:
        return None

    c15 = parse_closed_candles(
        candles_15m_raw,
        phase_at,
        15,
    )

    c1h = parse_closed_candles(
        candles_1h_raw,
        phase_at,
        60,
    )

    history_complete = (
        len(c15) >= 15
        and len(c1h) >= 15
    )

    atr15 = None
    atr1h = None

    low15 = None
    high15 = None
    low1h = None
    high1h = None

    stop = None
    stop_source = None
    target = None

    risk_pct = None
    reward_pct = None
    structure_rr = None
    distance_atr = None

    stop_valid = False
    structure_valid = False

    if history_complete:
        atr15 = atr(c15)
        atr1h = atr(c1h)

        low15, high15 = swing_levels(c15)
        low1h, high1h = swing_levels(c1h)

        stop, stop_source = choose_stop(
            direction,
            phase_price,
            low15,
            high15,
            low1h,
            high1h,
            atr15,
        )

        target = choose_target(
            direction,
            phase_price,
            low15,
            high15,
            low1h,
            high1h,
        )

        risk_pct = stop_distance_pct(
            phase_price,
            stop,
        )

        reward_pct = structural_reward_pct(
            direction,
            phase_price,
            target,
        )

        structure_rr = rr(
            reward_pct,
            risk_pct,
        )

        risk_abs = (
            abs(phase_price - stop)
            if stop is not None
            else None
        )

        distance_atr = (
            risk_abs / atr15
            if (
                risk_abs is not None
                and atr15 not in (None, 0)
            )
            else None
        )

        stop_valid = bool(
            stop is not None
            and risk_pct not in (None, 0)
            and (
                (
                    direction == "LONG"
                    and stop < phase_price
                )
                or (
                    direction == "SHORT"
                    and stop > phase_price
                )
            )
        )

        structure_valid = bool(
            stop_valid
            and target is not None
            and reward_pct not in (None, 0)
            and (
                (
                    direction == "LONG"
                    and target > phase_price
                )
                or (
                    direction == "SHORT"
                    and target < phase_price
                )
            )
        )

    if not history_complete:
        status = "INSUFFICIENT_HISTORY"
        measurement_quality = (
            "INSUFFICIENT_CANDLE_HISTORY"
        )
    else:
        status = feasibility_status(
            stop_valid,
            structure_valid,
            structure_rr,
        )
        measurement_quality = "COMPLETE"

    observed = str(
        observed_direction_at_phase
        or ""
    ).upper()

    if phase == "DETECTION":
        direction_source = (
            "RETROSPECTIVE_FIRST_CONFIRMED"
        )
        direction_available = False
        direction_consistent = None
        confidence = None

    elif phase == "EMERGING":
        direction_source = (
            "FIRST_CONFIRMED_FOR_COMPARABLE_RR"
        )
        direction_available = (
            observed in {"LONG", "SHORT"}
            and observed == direction
        )
        direction_consistent = (
            observed == direction
            if observed in {"LONG", "SHORT"}
            else None
        )
        confidence = observed_confidence_at_phase

    else:
        direction_source = "FIRST_CONFIRMED"
        direction_available = True
        direction_consistent = True
        confidence = confirmed_confidence

    return {
        "snapshot_id": phase_snapshot_id(
            episode_id,
            phase,
        ),
        "episode_id": episode_id,
        "symbol": symbol,
        "path": (
            state.get("path")
            or episode.path
        ),
        "model_version": MODEL_VERSION,

        "phase": phase,
        "phase_at_utc": phase_at.isoformat(),
        "phase_price": phase_price,

        "direction": direction,
        "direction_source": direction_source,
        "direction_available_at_phase":
            direction_available,
        "direction_consistent_with_confirmed":
            direction_consistent,

        "confidence": confidence,

        "move_consumed_pct":
            move_consumed_pct,
        "minutes_from_detection":
            minutes_between(
                detection_at,
                phase_at,
            ),

        "stop_price": stop,
        "stop_source": stop_source,
        "stop_distance_pct": risk_pct,

        "atr_15m": atr15,
        "atr_1h": atr1h,
        "stop_distance_atr": distance_atr,

        "swing_low_15m": low15,
        "swing_high_15m": high15,
        "swing_low_1h": low1h,
        "swing_high_1h": high1h,

        "structural_target": target,
        "structural_reward_pct": reward_pct,
        "rr_to_structure": structure_rr,

        "rr_to_3pct": rr(
            3.0,
            risk_pct,
        ),
        "rr_to_5pct": rr(
            5.0,
            risk_pct,
        ),
        "rr_to_10pct": rr(
            10.0,
            risk_pct,
        ),

        "rr3_possible": bool(
            structure_valid
            and structure_rr is not None
            and structure_rr >= 3
        ),
        "rr5_possible": bool(
            structure_valid
            and structure_rr is not None
            and structure_rr >= 5
        ),
        "rr10_possible": bool(
            structure_valid
            and structure_rr is not None
            and structure_rr >= 10
        ),

        "previous_phase": None,
        "previous_phase_rr": None,
        "rr_decay_from_previous": None,
        "rr_decay_from_detection": None,

        "structure_valid": structure_valid,
        "stop_valid": stop_valid,
        "feasibility_status": status,
        "measurement_quality":
            measurement_quality,

        "evidence": {
            "audit_type":
                "TIMING_AND_RR_DECAY",
            "comparison_direction":
                "FIRST_CONFIRMED_DIRECTION",
            "observed_direction_at_phase":
                observed or None,
            "observed_confidence_at_phase":
                observed_confidence_at_phase,
            "future_candle_leakage_blocked":
                True,
            "closed_15m_bars_used":
                len(c15),
            "closed_1h_bars_used":
                len(c1h),
            "structure_window_bars":
                STRUCTURE_WINDOW,
            "stop_buffer_atr_fraction":
                STOP_BUFFER_ATR_FRACTION,
            "stop_distance_quality":
                stop_quality(distance_atr),
            "scenario_note":
                (
                    "3pct/5pct/10pct are "
                    "reward-distance scenarios, "
                    "not predicted targets"
                ),
            "processed_at_utc":
                processed_at.isoformat(),
        },

        "trade_permission": False,
        "updated_at": processed_at.isoformat(),
    }


def apply_rr_decay(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    order = {
        "DETECTION": 0,
        "EMERGING": 1,
        "CONFIRMED": 2,
    }

    rows.sort(
        key=lambda row:
            order.get(
                str(row.get("phase")),
                99,
            )
    )

    detection_rr = None
    previous = None

    for row in rows:
        current_rr = f(
            row.get("rr_to_structure")
        )

        if row.get("phase") == "DETECTION":
            detection_rr = current_rr

        if previous is not None:
            previous_rr = f(
                previous.get(
                    "rr_to_structure"
                )
            )

            row["previous_phase"] = (
                previous.get("phase")
            )

            row["previous_phase_rr"] = (
                previous_rr
            )

            row[
                "rr_decay_from_previous"
            ] = rr_decay(
                previous_rr,
                current_rr,
            )

        row[
            "rr_decay_from_detection"
        ] = rr_decay(
            detection_rr,
            current_rr,
        )

        previous = row

    return rows



def upsert_rows(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> int:

    if not rows:
        return 0

    existing = load_existing_snapshot_rows(
        settings,
        [
            str(
                row.get("snapshot_id")
                or ""
            )
            for row in rows
        ],
    )

    writable_rows = []

    for row in rows:
        snapshot_id = str(
            row.get("snapshot_id")
            or ""
        )

        previous = existing.get(
            snapshot_id
        )

        previous_quality = str(
            (
                previous
                or {}
            ).get(
                "measurement_quality"
            )
            or ""
        ).upper()

        # COMPLETE historical evidence is immutable.
        if (
            previous is not None
            and previous_quality == "COMPLETE"
        ):
            continue

        writable_rows.append(row)

    if not writable_rows:
        return 0

    response = requests.post(
        f"{settings.url}/rest/v1/{TABLE}",
        params={
            "on_conflict": "snapshot_id",
        },
        headers=headers(
            settings,
            merge=True,
        ),
        data=json.dumps(
            writable_rows,
            separators=(",", ":"),
        ),
        timeout=settings.timeout_seconds,
    )

    if response.status_code not in {
        200,
        201,
        204,
    }:
        raise RuntimeError(
            "V7.8 timing/RR save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(writable_rows)


def rr_text(
    value: Any,
) -> str:
    number = f(value)

    return (
        f"{number:.2f}"
        if number is not None
        else "—"
    )


def main() -> int:

    load_env_file(ROOT / ".env")

    config = load_config(
        ROOT / "config.json"
    )

    settings = (
        SupabaseConfig
        .from_environment(config)
    )

    if settings is None:
        raise SystemExit(
            "Supabase is not configured"
        )

    product_type = str(
        config.get(
            "product_type",
            "usdt-futures",
        )
    )

    states = load_direction_states(
        settings
    )

    episodes = load_state()

    if not episodes:
        episodes = load_supabase_state(
            settings
        )

    episodes_by_id = {
        str(episode.episode_id): episode
        for episode in episodes
    }

    confirmed_states = [
        state
        for state in states.values()
        if state.get(
            "first_confirmed_at_utc"
        )
        and f(
            state.get("price_at_confirmed")
        ) not in (None, 0)
    ]

    confirmed_states.sort(
        key=lambda state: (
            str(
                state.get(
                    "first_confirmed_at_utc"
                )
                or ""
            ),
            str(
                state.get("symbol")
                or ""
            ),
        )
    )

    client = (
        BitgetClient
        .from_environment(
            timeout=int(
                config.get(
                    "request_timeout_seconds",
                    12,
                )
            ),
            max_retries=int(
                config.get(
                    "max_retries",
                    3,
                )
            ),
        )
    )

    processed_at = utc_now()

    all_rows: list[
        dict[str, Any]
    ] = []

    failures = 0
    skipped = 0

    print()
    print("=" * 124)
    print(
        "ALPHA HUNTER V7.8 "
        "TIMING & RR DECAY AUDITOR — SHADOW"
    )
    print("=" * 124)
    print(
        "Confirmed direction states:",
        len(confirmed_states),
    )
    print()

    for state in confirmed_states:

        episode_id = str(
            state.get("episode_id")
            or ""
        )

        symbol = str(
            state.get("symbol")
            or ""
        )

        episode = episodes_by_id.get(
            episode_id
        )

        try:
            if episode is None:
                print(
                    f"SKIP   {symbol:<15}"
                    "lifecycle episode unavailable"
                )
                skipped += 1
                continue

            confirmed_at = dt(
                state.get(
                    "first_confirmed_at_utc"
                )
            )

            confirmed_price = f(
                state.get(
                    "price_at_confirmed"
                )
            )

            emerging_at = dt(
                state.get(
                    "first_emerging_at_utc"
                )
            )

            emerging_price = f(
                state.get(
                    "price_at_emerging"
                )
            )

            detection_at = dt(
                episode.first_detected_at_utc
            )

            detection_price = f(
                episode.first_detection_price
            )

            if (
                confirmed_at is None
                or confirmed_price in (None, 0)
                or detection_at is None
                or detection_price in (None, 0)
            ):
                skipped += 1
                continue

            confirmed_shadow = (
                confirmation_shadow(
                    settings,
                    episode_id,
                    confirmed_at,
                )
            )

            if not confirmed_shadow:
                print(
                    f"SKIP   {symbol:<15}"
                    "confirmation shadow unavailable"
                )
                skipped += 1
                continue

            confirmed_direction = str(
                confirmed_shadow.get(
                    "direction"
                )
                or ""
            ).upper()

            confirmed_confidence = f(
                confirmed_shadow.get(
                    "confidence"
                )
            )

            if confirmed_direction not in {
                "LONG",
                "SHORT",
            }:
                skipped += 1
                continue

            emerging_shadow = None

            if emerging_at is not None:
                emerging_shadow = (
                    confirmation_shadow(
                        settings,
                        episode_id,
                        emerging_at,
                    )
                )

            emerging_direction = (
                str(
                    emerging_shadow.get(
                        "direction"
                    )
                    or ""
                ).upper()
                if emerging_shadow
                else None
            )

            emerging_confidence = (
                f(
                    emerging_shadow.get(
                        "confidence"
                    )
                )
                if emerging_shadow
                else None
            )

            episode_rows = []

            detection_candles_15m = (
                load_phase_candles(
                    client,
                    symbol,
                    product_type,
                    "15m",
                    detection_at,
                    15,
                    CANDLE_LIMIT,
                )
            )

            detection_candles_1h = (
                load_phase_candles(
                    client,
                    symbol,
                    product_type,
                    "1H",
                    detection_at,
                    60,
                    CANDLE_LIMIT,
                )
            )

            detection_row = build_phase_row(
                episode=episode,
                state=state,
                phase="DETECTION",
                phase_at=detection_at,
                phase_price=detection_price,
                confirmed_direction=
                    confirmed_direction,
                confirmed_confidence=
                    confirmed_confidence,
                observed_direction_at_phase=None,
                observed_confidence_at_phase=None,
                move_consumed_pct=0.0,
                candles_15m_raw=
                    detection_candles_15m,
                candles_1h_raw=
                    detection_candles_1h,
                processed_at=processed_at,
            )

            if detection_row:
                episode_rows.append(
                    detection_row
                )

            if (
                emerging_at is not None
                and emerging_price
                not in (None, 0)
            ):
                emerging_candles_15m = (
                    load_phase_candles(
                        client,
                        symbol,
                        product_type,
                        "15m",
                        emerging_at,
                        15,
                        CANDLE_LIMIT,
                    )
                )

                emerging_candles_1h = (
                    load_phase_candles(
                        client,
                        symbol,
                        product_type,
                        "1H",
                        emerging_at,
                        60,
                        CANDLE_LIMIT,
                    )
                )

                emerging_row = build_phase_row(
                    episode=episode,
                    state=state,
                    phase="EMERGING",
                    phase_at=emerging_at,
                    phase_price=emerging_price,
                    confirmed_direction=
                        confirmed_direction,
                    confirmed_confidence=
                        confirmed_confidence,
                    observed_direction_at_phase=
                        emerging_direction,
                    observed_confidence_at_phase=
                        emerging_confidence,
                    move_consumed_pct=f(
                        state.get(
                            "move_at_emerging_pct"
                        )
                    ),
                    candles_15m_raw=
                        emerging_candles_15m,
                    candles_1h_raw=
                        emerging_candles_1h,
                    processed_at=processed_at,
                )

                if emerging_row:
                    episode_rows.append(
                        emerging_row
                    )

            confirmed_candles_15m = (
                load_phase_candles(
                    client,
                    symbol,
                    product_type,
                    "15m",
                    confirmed_at,
                    15,
                    CANDLE_LIMIT,
                )
            )

            confirmed_candles_1h = (
                load_phase_candles(
                    client,
                    symbol,
                    product_type,
                    "1H",
                    confirmed_at,
                    60,
                    CANDLE_LIMIT,
                )
            )

            confirmed_row = build_phase_row(
                episode=episode,
                state=state,
                phase="CONFIRMED",
                phase_at=confirmed_at,
                phase_price=confirmed_price,
                confirmed_direction=
                    confirmed_direction,
                confirmed_confidence=
                    confirmed_confidence,
                observed_direction_at_phase=
                    confirmed_direction,
                observed_confidence_at_phase=
                    confirmed_confidence,
                move_consumed_pct=f(
                    state.get(
                        "move_at_confirmed_pct"
                    )
                ),
                candles_15m_raw=
                    confirmed_candles_15m,
                candles_1h_raw=
                    confirmed_candles_1h,
                processed_at=processed_at,
            )

            if confirmed_row:
                episode_rows.append(
                    confirmed_row
                )

            apply_rr_decay(
                episode_rows
            )

            all_rows.extend(
                episode_rows
            )

            by_phase = {
                row["phase"]: row
                for row in episode_rows
            }

            d = by_phase.get(
                "DETECTION"
            )

            e = by_phase.get(
                "EMERGING"
            )

            c = by_phase.get(
                "CONFIRMED"
            )

            emerging_known = (
                "Y"
                if e
                and e.get(
                    "direction_available_at_phase"
                )
                else "N"
            )

            decay = (
                f(
                    c.get(
                        "rr_decay_from_detection"
                    )
                )
                if c
                else None
            )

            decay_text = (
                f"{decay:+.2f}"
                if decay is not None
                else "—"
            )

            print(
                f"{symbol:<15}"
                f"{confirmed_direction:<7}"
                f"D={rr_text(d.get('rr_to_structure') if d else None):<6} "
                f"E={rr_text(e.get('rr_to_structure') if e else None):<6} "
                f"C={rr_text(c.get('rr_to_structure') if c else None):<6} "
                f"RR_LOST={decay_text:<7} "
                f"DIR@E={emerging_known}"
            )

        except (
            BitgetAPIError,
            RuntimeError,
            ValueError,
            TypeError,
        ) as exc:
            failures += 1
            print(
                f"FAILED {symbol:<15}{exc}"
            )

    saved = upsert_rows(
        settings,
        all_rows,
    )

    counts = {
        phase: 0
        for phase in PHASES
    }

    rr3 = {
        phase: 0
        for phase in PHASES
    }

    rr5 = {
        phase: 0
        for phase in PHASES
    }

    rr10 = {
        phase: 0
        for phase in PHASES
    }

    for row in all_rows:
        phase = str(row["phase"])

        counts[phase] += 1
        rr3[phase] += int(
            bool(row["rr3_possible"])
        )
        rr5[phase] += int(
            bool(row["rr5_possible"])
        )
        rr10[phase] += int(
            bool(row["rr10_possible"])
        )

    print()
    print("=" * 124)
    print(
        "V7.8 TIMING & RR DECAY SUMMARY"
    )
    print("=" * 124)

    print(
        "Confirmed direction states:",
        len(confirmed_states),
    )
    print(
        "Phase snapshots:",
        len(all_rows),
    )
    print("Skipped:", skipped)
    print("Failures:", failures)
    print(
        "Supabase rows upserted:",
        saved,
    )

    for phase in PHASES:
        print(
            f"{phase:<10}"
            f" rows={counts[phase]:<3}"
            f" RR>=3={rr3[phase]:<3}"
            f" RR>=5={rr5[phase]:<3}"
            f" RR>=10={rr10[phase]:<3}"
        )

    print()
    print(
        "IMPORTANT: V7.8 IS TIMING/RR "
        "DIAGNOSTIC SHADOW ONLY."
    )
    print(
        "Detection direction is retrospective "
        "and is never a live trade signal."
    )
    print(
        "Positive RR_LOST means execution "
        "quality deteriorated before confirmation."
    )
    print(
        "No trade permission was generated."
    )
    print()
    print(
        "V7.8 TIMING & RR DECAY AUDITOR: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
