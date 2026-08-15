from __future__ import annotations

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

ROOT = Path(__file__).resolve().parent

OUTCOME_TABLE = "alpha_hunter_direction_outcomes"
SHADOW_TABLE = "alpha_hunter_direction_shadow"
LOOKBACK_CANDLES = 120
HORIZONS = (
    (1, "h1"),
    (4, "h4"),
    (12, "h12"),
    (24, "h24"),
)
THRESHOLDS = (1, 2, 3, 5, 10)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def headers(
    settings: SupabaseConfig,
    *,
    merge: bool = False,
) -> dict[str, str]:
    result = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }

    if merge:
        result["Prefer"] = (
            "resolution=merge-duplicates,return=minimal"
        )

    return result


def load_outcomes(
    settings: SupabaseConfig,
) -> dict[str, dict[str, Any]]:
    response = requests.get(
        f"{settings.url}/rest/v1/{OUTCOME_TABLE}",
        params={
            "select": "*",
            "limit": "10000",
        },
        headers=headers(settings),
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "Direction outcome load failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if not isinstance(payload, list):
        return {}

    return {
        str(row["episode_id"]): row
        for row in payload
        if isinstance(row, dict)
        and row.get("episode_id")
    }


def upsert_outcomes(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    response = requests.post(
        f"{settings.url}/rest/v1/{OUTCOME_TABLE}",
        params={"on_conflict": "episode_id"},
        headers=headers(settings, merge=True),
        data=json.dumps(
            rows,
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
            "Direction outcome save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(rows)


def confirmation_shadow(
    settings: SupabaseConfig,
    episode_id: str,
    confirmed_at: datetime,
) -> dict[str, Any] | None:
    response = requests.get(
        f"{settings.url}/rest/v1/{SHADOW_TABLE}",
        params={
            "select": (
                "direction,confidence,"
                "evaluated_at_utc,market_price"
            ),
            "episode_id": f"eq.{episode_id}",
            "order": "evaluated_at_utc.asc",
            "limit": "100",
        },
        headers=headers(settings),
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "Direction shadow lookup failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    rows = response.json()

    if not isinstance(rows, list):
        return None

    valid: list[
        tuple[float, dict[str, Any]]
    ] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        direction = str(
            row.get("direction") or ""
        ).upper()

        when = dt(
            row.get("evaluated_at_utc")
        )

        if (
            direction not in {"LONG", "SHORT"}
            or when is None
        ):
            continue

        distance = abs(
            (
                when - confirmed_at
            ).total_seconds()
        )

        valid.append(
            (distance, row)
        )

    if not valid:
        return None

    valid.sort(
        key=lambda item: item[0]
    )

    return valid[0][1]


def make_outcome_row(
    settings: SupabaseConfig,
    state: dict[str, Any],
    episode: Any,
    now: datetime,
) -> dict[str, Any] | None:
    confirmed_at = dt(
        state.get("first_confirmed_at_utc")
    )

    confirmation_price = f(
        state.get("price_at_confirmed")
    )

    if (
        confirmed_at is None
        or confirmation_price in (None, 0)
    ):
        return None

    shadow = confirmation_shadow(
        settings,
        str(state["episode_id"]),
        confirmed_at,
    )

    direction = ""

    if shadow:
        direction = str(
            shadow.get("direction") or ""
        ).upper()

    if direction not in {
        "LONG",
        "SHORT",
    }:
        current_direction = str(
            state.get("current_direction")
            or ""
        ).upper()

        if (
            state.get("direction_state")
            == "DIRECTION_CONFIRMED"
            and current_direction
            in {"LONG", "SHORT"}
        ):
            direction = current_direction

    if direction not in {
        "LONG",
        "SHORT",
    }:
        return None

    confidence = (
        f(shadow.get("confidence"))
        if shadow
        else None
    )

    if confidence is None:
        confidence = f(
            state.get("last_confidence")
        )

    delay_hours = (
        now - confirmed_at
    ).total_seconds() / 3600.0

    quality = (
        "FORWARD_COMPLETE"
        if 0.0 <= delay_hours <= 1.5
        else "LEGACY_PARTIAL"
    )

    return {
        "episode_id": str(
            state["episode_id"]
        ),
        "symbol": str(
            state.get("symbol")
            or episode.symbol
        ),
        "path": str(
            state.get("path")
            or episode.path
        ),
        "model_version": str(
            state.get("model_version")
            or "V7.6"
        ),
        "confirmed_direction": direction,
        "confirmed_at_utc": (
            confirmed_at.isoformat()
        ),
        "confirmation_price": (
            confirmation_price
        ),
        "confirmation_confidence": (
            confidence
        ),
        "move_consumed_pct": f(
            state.get(
                "move_at_confirmed_pct"
            )
        ),
        "tracking_started_at_utc": (
            now.isoformat()
        ),
        "measurement_quality": quality,
        "last_market_check_at_utc": None,
        "market_checks": 0,
        "current_directional_move_pct": 0.0,
        "max_favorable_after_confirm_pct": 0.0,
        "max_adverse_after_confirm_pct": 0.0,
        "hit_1pct": False,
        "hit_2pct": False,
        "hit_3pct": False,
        "hit_5pct": False,
        "hit_10pct": False,
        "first_1pct_at_utc": None,
        "first_2pct_at_utc": None,
        "first_3pct_at_utc": None,
        "first_5pct_at_utc": None,
        "first_10pct_at_utc": None,
        "h1_mfe_pct": None,
        "h1_mae_pct": None,
        "h1_frozen_at_utc": None,
        "h4_mfe_pct": None,
        "h4_mae_pct": None,
        "h4_frozen_at_utc": None,
        "h12_mfe_pct": None,
        "h12_mae_pct": None,
        "h12_frozen_at_utc": None,
        "h24_mfe_pct": None,
        "h24_mae_pct": None,
        "h24_frozen_at_utc": None,
        "confirmation_lost": False,
        "first_lost_confirmation_at_utc": None,
        "lifecycle_final_classification": None,
        "direction_correct": None,
        "is_complete": False,
        "completed_at_utc": None,
        "trade_permission": False,
        "updated_at": now.isoformat(),
    }


def directional_move(
    direction: str,
    reference: float,
    price: float,
) -> float:
    raw = (
        price / reference - 1.0
    ) * 100.0

    if direction == "LONG":
        return raw

    return -raw


def mark_thresholds(
    row: dict[str, Any],
    move: float,
    observed_at: datetime,
) -> None:
    if move <= 0:
        return

    timestamp = (
        observed_at.isoformat()
    )

    for threshold in THRESHOLDS:
        hit_key = (
            f"hit_{threshold}pct"
        )
        time_key = (
            f"first_{threshold}pct_at_utc"
        )

        if (
            move >= threshold
            and not bool(row.get(hit_key))
        ):
            row[hit_key] = True
            row[time_key] = timestamp


def inspect_price(
    row: dict[str, Any],
    price: float,
    observed_at: datetime,
) -> None:
    reference = f(
        row.get("confirmation_price")
    )

    direction = str(
        row.get("confirmed_direction")
        or ""
    ).upper()

    if (
        reference in (None, 0)
        or direction
        not in {"LONG", "SHORT"}
    ):
        return

    move = directional_move(
        direction,
        reference,
        price,
    )

    row[
        "max_favorable_after_confirm_pct"
    ] = max(
        float(
            row.get(
                "max_favorable_after_confirm_pct"
            )
            or 0.0
        ),
        move,
        0.0,
    )

    row[
        "max_adverse_after_confirm_pct"
    ] = min(
        float(
            row.get(
                "max_adverse_after_confirm_pct"
            )
            or 0.0
        ),
        move,
        0.0,
    )

    mark_thresholds(
        row,
        move,
        observed_at,
    )


def freeze_due_horizons(
    row: dict[str, Any],
    before_or_at: datetime,
) -> None:
    confirmed_at = dt(
        row.get("confirmed_at_utc")
    )

    if confirmed_at is None:
        return

    for hours, prefix in HORIZONS:
        frozen_key = (
            f"{prefix}_frozen_at_utc"
        )

        if row.get(frozen_key):
            continue

        boundary = (
            confirmed_at
            + timedelta(hours=hours)
        )

        if before_or_at < boundary:
            continue

        row[f"{prefix}_mfe_pct"] = float(
            row.get(
                "max_favorable_after_confirm_pct"
            )
            or 0.0
        )

        row[f"{prefix}_mae_pct"] = float(
            row.get(
                "max_adverse_after_confirm_pct"
            )
            or 0.0
        )

        row[frozen_key] = (
            boundary.isoformat()
        )

        if hours == 24:
            row["is_complete"] = True
            row["completed_at_utc"] = (
                boundary.isoformat()
            )


def candle_time(
    candle: list[Any],
) -> datetime | None:
    try:
        timestamp_ms = int(
            candle[0]
        )
    except (
        TypeError,
        ValueError,
        IndexError,
    ):
        return None

    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    )


def inspect_candle(
    row: dict[str, Any],
    candle: list[Any],
) -> None:
    observed_at = candle_time(
        candle
    )

    confirmed_at = dt(
        row.get("confirmed_at_utc")
    )

    last_check = dt(
        row.get("last_market_check_at_utc")
    )

    if (
        observed_at is None
        or confirmed_at is None
        or observed_at < confirmed_at
    ):
        return

    if (
        last_check is not None
        and observed_at <= last_check
    ):
        return

    freeze_due_horizons(
        row,
        observed_at,
    )

    h24 = (
        confirmed_at
        + timedelta(hours=24)
    )

    if observed_at > h24:
        return

    try:
        high = f(candle[2])
        low = f(candle[3])
    except IndexError:
        return

    if high is not None:
        inspect_price(
            row,
            high,
            observed_at,
        )

    if low is not None:
        inspect_price(
            row,
            low,
            observed_at,
        )


def apply_direction_state(
    row: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if (
        not row.get("confirmation_lost")
        and (
            str(
                state.get(
                    "direction_state"
                )
                or ""
            )
            == "LOST_CONFIRMATION"
            or int(
                state.get(
                    "lost_confirmation_count"
                )
                or 0
            )
            > 0
        )
    ):
        row["confirmation_lost"] = True
        row[
            "first_lost_confirmation_at_utc"
        ] = (
            state.get(
                "last_evaluated_at_utc"
            )
            or state.get(
                "updated_at"
            )
        )


def apply_lifecycle_truth(
    row: dict[str, Any],
    episode: Any,
) -> None:
    if not episode.is_finalized:
        return

    classification = (
        episode.final_classification
    )

    row[
        "lifecycle_final_classification"
    ] = classification

    if not classification:
        return

    expected = (
        "UP"
        if row["confirmed_direction"]
        == "LONG"
        else "DOWN"
    )

    if classification.endswith(
        "_UP"
    ):
        row["direction_correct"] = (
            expected == "UP"
        )

    elif classification.endswith(
        "_DOWN"
    ):
        row["direction_correct"] = (
            expected == "DOWN"
        )

    elif classification == "NO_EXPANSION":
        row["direction_correct"] = None


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

    product_type = str(
        config.get(
            "product_type",
            "usdt-futures",
        )
    )

    episodes = load_state()

    if not episodes:
        episodes = load_supabase_state(
            settings
        )

    episode_map = {
        episode.episode_id: episode
        for episode in episodes
    }

    states = load_direction_states(
        settings
    )

    outcomes = load_outcomes(
        settings
    )

    now = utc_now()

    created = 0
    tracked = 0
    failed = 0

    for episode_id, state in states.items():
        if not state.get(
            "first_confirmed_at_utc"
        ):
            continue

        episode = episode_map.get(
            episode_id
        )

        if episode is None:
            continue

        if episode_id not in outcomes:
            row = make_outcome_row(
                settings,
                state,
                episode,
                now,
            )

            if row is None:
                continue

            outcomes[episode_id] = row
            created += 1

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

    print()
    print("=" * 118)
    print(
        "ALPHA HUNTER V7.6 "
        "POST-CONFIRMATION OUTCOME TRACKER — SHADOW"
    )
    print("=" * 118)

    print(
        "Confirmed outcome rows:",
        len(outcomes),
    )

    print(
        "Created this run:",
        created,
    )

    print()

    for episode_id, row in outcomes.items():
        episode = episode_map.get(
            episode_id
        )

        state = states.get(
            episode_id
        )

        if (
            episode is None
            or state is None
        ):
            continue

        apply_direction_state(
            row,
            state,
        )

        apply_lifecycle_truth(
            row,
            episode,
        )

        if row.get("is_complete"):
            row["trade_permission"] = False
            row["updated_at"] = (
                now.isoformat()
            )
            continue

        try:
            candles = (
                client.candles(
                    row["symbol"],
                    product_type,
                    "1m",
                    LOOKBACK_CANDLES,
                )
                or []
            )

            ordered = []

            for candle in candles:
                if not isinstance(
                    candle,
                    list,
                ):
                    continue

                when = candle_time(
                    candle
                )

                if when is not None:
                    ordered.append(
                        (when, candle)
                    )

            ordered.sort(
                key=lambda item: item[0]
            )

            for _, candle in ordered:
                inspect_candle(
                    row,
                    candle,
                )

            freeze_due_horizons(
                row,
                now,
            )

            ticker = client.ticker(
                row["symbol"],
                product_type,
            )

            current_price = f(
                ticker.get("lastPr")
                or ticker.get("last")
                or ticker.get("close")
            )

            if current_price is None:
                raise RuntimeError(
                    "ticker has no usable price"
                )

            reference = f(
                row.get(
                    "confirmation_price"
                )
            )

            if reference in (None, 0):
                raise RuntimeError(
                    "confirmation price missing"
                )

            row[
                "current_directional_move_pct"
            ] = directional_move(
                row["confirmed_direction"],
                reference,
                current_price,
            )

            confirmed_at = dt(
                row.get(
                    "confirmed_at_utc"
                )
            )

            if (
                confirmed_at is not None
                and now
                <= confirmed_at
                + timedelta(hours=24)
            ):
                inspect_price(
                    row,
                    current_price,
                    now,
                )

            row[
                "last_market_check_at_utc"
            ] = now.isoformat()

            row["market_checks"] = (
                int(
                    row.get(
                        "market_checks"
                    )
                    or 0
                )
                + 1
            )

            row["trade_permission"] = False
            row["updated_at"] = (
                now.isoformat()
            )

            tracked += 1

            print(
                f"{row['symbol']:<15}"
                f"{row['confirmed_direction']:<7}"
                f"quality="
                f"{row.get('measurement_quality'):<16} "
                f"now="
                f"{row['current_directional_move_pct']:>7.2f}% "
                f"MFE="
                f"{row['max_favorable_after_confirm_pct']:>7.2f}% "
                f"MAE="
                f"{row['max_adverse_after_confirm_pct']:>7.2f}% "
                f"lost="
                f"{'Y' if row.get('confirmation_lost') else '-'} "
                f"done="
                f"{'Y' if row.get('is_complete') else '-'}"
            )

        except (
            BitgetAPIError,
            RuntimeError,
            ValueError,
        ) as exc:
            failed += 1

            print(
                f"{row.get('symbol', episode_id):<15}"
                f"FAILED: {exc}"
            )

    rows = list(
        outcomes.values()
    )

    saved = upsert_outcomes(
        settings,
        rows,
    )

    print()
    print("=" * 118)
    print(
        "POST-CONFIRMATION TRACKER SUMMARY"
    )
    print("=" * 118)

    print(
        "Outcome rows:",
        len(rows),
    )
    print(
        "Created this run:",
        created,
    )
    print(
        "Tracked this run:",
        tracked,
    )
    print(
        "Failed:",
        failed,
    )
    print(
        "Supabase rows upserted:",
        saved,
    )
    print(
        "Forward complete:",
        sum(
            row.get(
                "measurement_quality"
            )
            == "FORWARD_COMPLETE"
            for row in rows
        ),
    )
    print(
        "Completed 24H:",
        sum(
            bool(
                row.get(
                    "is_complete"
                )
            )
            for row in rows
        ),
    )

    print()
    print(
        "IMPORTANT: OUTCOME TRACKER "
        "IS MEASUREMENT ONLY."
    )
    print(
        "No trade permission was generated."
    )

    if failed:
        raise SystemExit(
            "V7.6 POST-CONFIRMATION "
            f"TRACKER FAILED FOR {failed} ROWS"
        )

    print()
    print(
        "V7.6 POST-CONFIRMATION "
        "OUTCOME TRACKER: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
