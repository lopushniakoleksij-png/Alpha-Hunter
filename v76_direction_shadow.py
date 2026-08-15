from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.bitget import (
    BitgetAPIError,
    BitgetClient,
)
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.lifecycle import LifecycleEpisode
from alpha_hunter.storage import SupabaseConfig
from v75_lifecycle_job import (
    load_state,
    load_supabase_state,
)


ROOT = Path(__file__).resolve().parent

TABLE = "alpha_hunter_direction_shadow"
STATE_TABLE = "alpha_hunter_direction_state"

MODEL_VERSION = "7.6-shadow"

CANDLE_LIMIT = 60


def now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


def f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def ema(
    values: list[float],
    period: int,
) -> float | None:
    if len(values) < period:
        return None

    multiplier = (
        2.0
        / (period + 1.0)
    )

    result = sum(
        values[:period]
    ) / period

    for value in values[period:]:
        result = (
            value * multiplier
            + result
            * (1.0 - multiplier)
        )

    return result


def closes(
    candles: list[Any],
) -> list[float]:
    rows = []

    ordered = []

    for candle in candles:
        if not isinstance(
            candle,
            list,
        ):
            continue

        try:
            timestamp = int(
                candle[0]
            )

            close = float(
                candle[4]
            )

        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            continue

        ordered.append(
            (
                timestamp,
                close,
            )
        )

    ordered.sort(
        key=lambda item:
            item[0]
    )

    for _, close in ordered:
        rows.append(
            close
        )

    return rows


def momentum(
    prices: list[float],
    bars: int = 3,
) -> float | None:
    if len(prices) <= bars:
        return None

    previous = prices[
        -(bars + 1)
    ]

    current = prices[-1]

    if previous == 0:
        return None

    return (
        current
        / previous
        - 1.0
    ) * 100.0


def ema_bias(
    prices: list[float],
) -> str:
    fast = ema(
        prices,
        9,
    )

    slow = ema(
        prices,
        21,
    )

    if (
        fast is None
        or slow is None
        or not prices
    ):
        return "UNKNOWN"

    price = prices[-1]

    if (
        price > fast
        and fast > slow
    ):
        return "BULLISH"

    if (
        price < fast
        and fast < slow
    ):
        return "BEARISH"

    return "MIXED"


def structure(
    prices: list[float],
) -> str:
    if len(prices) < 8:
        return "UNKNOWN"

    recent = prices[-4:]
    prior = prices[-8:-4]

    recent_high = max(
        recent
    )

    recent_low = min(
        recent
    )

    prior_high = max(
        prior
    )

    prior_low = min(
        prior
    )

    if (
        recent_high > prior_high
        and recent_low > prior_low
    ):
        return "BULLISH"

    if (
        recent_high < prior_high
        and recent_low < prior_low
    ):
        return "BEARISH"

    return "MIXED"


def score_direction(
    bias_15m: str,
    bias_1h: str,
    momentum_15m: float | None,
    momentum_1h: float | None,
    structure_15m: str,
    structure_1h: str,
) -> tuple[
    float,
    float,
    list[str],
]:
    long_score = 0.0
    short_score = 0.0

    evidence = []

    if bias_15m == "BULLISH":
        long_score += 1.0
        evidence.append(
            "EMA15_BULL"
        )

    elif bias_15m == "BEARISH":
        short_score += 1.0
        evidence.append(
            "EMA15_BEAR"
        )

    if bias_1h == "BULLISH":
        long_score += 2.0
        evidence.append(
            "EMA1H_BULL"
        )

    elif bias_1h == "BEARISH":
        short_score += 2.0
        evidence.append(
            "EMA1H_BEAR"
        )

    if (
        momentum_15m is not None
        and momentum_15m >= 0.6
    ):
        long_score += 1.0
        evidence.append(
            "MOM15_UP"
        )

    elif (
        momentum_15m is not None
        and momentum_15m <= -0.6
    ):
        short_score += 1.0
        evidence.append(
            "MOM15_DOWN"
        )

    if (
        momentum_1h is not None
        and momentum_1h >= 1.0
    ):
        long_score += 1.5
        evidence.append(
            "MOM1H_UP"
        )

    elif (
        momentum_1h is not None
        and momentum_1h <= -1.0
    ):
        short_score += 1.5
        evidence.append(
            "MOM1H_DOWN"
        )

    if structure_15m == "BULLISH":
        long_score += 1.0
        evidence.append(
            "STRUCT15_BULL"
        )

    elif structure_15m == "BEARISH":
        short_score += 1.0
        evidence.append(
            "STRUCT15_BEAR"
        )

    if structure_1h == "BULLISH":
        long_score += 1.5
        evidence.append(
            "STRUCT1H_BULL"
        )

    elif structure_1h == "BEARISH":
        short_score += 1.5
        evidence.append(
            "STRUCT1H_BEAR"
        )

    return (
        long_score,
        short_score,
        evidence,
    )


def direction_verdict(
    long_score: float,
    short_score: float,
) -> tuple[str, float]:

    best = max(
        long_score,
        short_score,
    )

    difference = abs(
        long_score
        - short_score
    )

    if (
        best < 4.0
        or difference < 2.0
    ):
        return (
            "UNKNOWN",
            0.0,
        )

    direction = (
        "LONG"
        if long_score
        > short_score
        else "SHORT"
    )

    confidence = min(
        100.0,
        (
            best / 8.0 * 70.0
            + difference / 8.0 * 30.0
        ),
    )

    return (
        direction,
        confidence,
    )


def shadow_id(
    episode_id: str,
    timestamp: datetime,
) -> str:

    hour_bucket = timestamp.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    raw = (
        f"{episode_id}|"
        f"{MODEL_VERSION}|"
        f"{hour_bucket.isoformat()}"
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()[:24]


def headers(
    settings: SupabaseConfig,
) -> dict[str, str]:
    return {
        "apikey":
            settings.key,

        "Authorization":
            f"Bearer {settings.key}",

        "Content-Type":
            "application/json",

        "Prefer":
            (
                "resolution=merge-duplicates,"
                "return=minimal"
            ),
    }


def save_rows(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> int:

    if not rows:
        return 0

    response = requests.post(
        (
            f"{settings.url}"
            f"/rest/v1/{TABLE}"
        ),
        params={
            "on_conflict":
                "shadow_id",
        },
        headers=headers(
            settings
        ),
        data=json.dumps(
            rows,
            separators=(
                ",",
                ":",
            ),
        ),
        timeout=settings.timeout_seconds,
    )

    if response.status_code not in {
        200,
        201,
        204,
    }:
        raise RuntimeError(
            "V7.6 shadow save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(rows)


def load_direction_states(
    settings: SupabaseConfig,
) -> dict[str, dict[str, Any]]:

    response = requests.get(
        (
            f"{settings.url}"
            f"/rest/v1/{STATE_TABLE}"
        ),
        params={
            "select": "*",
            "limit": "10000",
        },
        headers={
            "apikey":
                settings.key,

            "Authorization":
                f"Bearer {settings.key}",
        },
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "V7.6 direction-state load failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if not isinstance(
        payload,
        list,
    ):
        return {}

    return {
        str(row["episode_id"]):
            row
        for row in payload
        if isinstance(row, dict)
        and row.get("episode_id")
    }


def save_direction_states(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> int:

    if not rows:
        return 0

    response = requests.post(
        (
            f"{settings.url}"
            f"/rest/v1/{STATE_TABLE}"
        ),
        params={
            "on_conflict":
                "episode_id",
        },
        headers=headers(
            settings
        ),
        data=json.dumps(
            rows,
            separators=(
                ",",
                ":",
            ),
        ),
        timeout=settings.timeout_seconds,
    )

    if response.status_code not in {
        200,
        201,
        204,
    }:
        raise RuntimeError(
            "V7.6 direction-state save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(rows)


def directional_move_pct(
    episode: LifecycleEpisode,
    direction: str,
    price: float | None,
) -> float | None:

    reference = episode.first_detection_price

    if (
        reference in (None, 0)
        or price is None
        or direction not in {
            "LONG",
            "SHORT",
        }
    ):
        return None

    raw_move = (
        price / reference - 1.0
    ) * 100.0

    if direction == "LONG":
        return raw_move

    return -raw_move


def update_direction_state(
    episode: LifecycleEpisode,
    previous: dict[str, Any] | None,
    direction: str,
    confidence: float,
    market_price: float | None,
    evaluated_at: datetime,
) -> dict[str, Any]:

    previous = (
        previous
        or {}
    )

    previous_direction = str(
        previous.get(
            "last_direction"
        )
        or "UNKNOWN"
    )

    previous_state = str(
        previous.get(
            "direction_state"
        )
        or "UNKNOWN"
    )

    previous_count = int(
        previous.get(
            "consecutive_direction_count"
        )
        or 0
    )

    previous_bucket_text = previous.get(
        "last_counted_bucket_utc"
    )

    current_bucket = evaluated_at.replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    previous_bucket = None

    if previous_bucket_text:
        try:
            previous_bucket = datetime.fromisoformat(
                str(previous_bucket_text)
                .replace("Z", "+00:00")
            )

            if previous_bucket.tzinfo is None:
                previous_bucket = previous_bucket.replace(
                    tzinfo=timezone.utc
                )

            previous_bucket = previous_bucket.astimezone(
                timezone.utc
            ).replace(
                minute=0,
                second=0,
                microsecond=0,
            )

        except ValueError:
            previous_bucket = None

    new_time_bucket = (
        previous_bucket is None
        or current_bucket > previous_bucket
    )

    confirmation_count = int(
        previous.get(
            "confirmation_count"
        )
        or 0
    )

    lost_count = int(
        previous.get(
            "lost_confirmation_count"
        )
        or 0
    )

    highest_confidence = max(
        float(
            previous.get(
                "highest_confidence"
            )
            or 0
        ),
        confidence,
    )

    first_emerging_at = previous.get(
        "first_emerging_at_utc"
    )

    first_confirmed_at = previous.get(
        "first_confirmed_at_utc"
    )

    price_at_emerging = previous.get(
        "price_at_emerging"
    )

    price_at_confirmed = previous.get(
        "price_at_confirmed"
    )

    move_at_emerging_pct = previous.get(
        "move_at_emerging_pct"
    )

    move_at_confirmed_pct = previous.get(
        "move_at_confirmed_pct"
    )

    # Safe recovery for pre-existing V7.6 rows:
    # derive timing metrics only from already-frozen prices.
    if (
        move_at_emerging_pct is None
        and price_at_emerging is not None
        and previous_direction in {"LONG", "SHORT"}
    ):
        move_at_emerging_pct = directional_move_pct(
            episode,
            previous_direction,
            float(price_at_emerging),
        )

    if (
        move_at_confirmed_pct is None
        and price_at_confirmed is not None
        and previous_direction in {"LONG", "SHORT"}
    ):
        move_at_confirmed_pct = directional_move_pct(
            episode,
            previous_direction,
            float(price_at_confirmed),
        )

    # ----------------------------------------------
    # CONSECUTIVE DIRECTION COUNT
    # ----------------------------------------------

    if not new_time_bucket:
        # Same hourly observation bucket.
        # Refresh evidence but never manufacture
        # another persistence confirmation.
        consecutive = previous_count

    elif direction == "UNKNOWN":
        consecutive = 0

    elif (
        direction
        == previous_direction
    ):
        consecutive = (
            previous_count + 1
        )

    else:
        consecutive = 1

    # ----------------------------------------------
    # STATE MACHINE
    # ----------------------------------------------

    state = "UNKNOWN"

    if direction != "UNKNOWN":
        state = "DIRECTION_EMERGING"

        if first_emerging_at is None:
            first_emerging_at = (
                evaluated_at.isoformat()
            )

            price_at_emerging = (
                market_price
            )

            move_at_emerging_pct = (
                directional_move_pct(
                    episode,
                    direction,
                    market_price,
                )
            )

        if (
            consecutive >= 2
            and confidence >= 55.0
        ):
            state = "DIRECTION_CONFIRMED"

            if first_confirmed_at is None:
                first_confirmed_at = (
                    evaluated_at.isoformat()
                )

                price_at_confirmed = (
                    market_price
                )

                move_at_confirmed_pct = (
                    directional_move_pct(
                        episode,
                        direction,
                        market_price,
                    )
                )

                confirmation_count += 1

    # ----------------------------------------------
    # LOST CONFIRMATION
    # ----------------------------------------------

    if (
        previous_state
        == "DIRECTION_CONFIRMED"
        and (
            direction == "UNKNOWN"
            or direction
            != previous_direction
        )
    ):
        state = "LOST_CONFIRMATION"
        lost_count += 1

    return {
        "episode_id":
            episode.episode_id,

        "symbol":
            episode.symbol,

        "path":
            episode.path,

        "current_direction":
            direction,

        "direction_state":
            state,

        "first_emerging_at_utc":
            first_emerging_at,

        "first_confirmed_at_utc":
            first_confirmed_at,

        "price_at_emerging":
            price_at_emerging,

        "price_at_confirmed":
            price_at_confirmed,

        "move_at_emerging_pct":
            move_at_emerging_pct,

        "move_at_confirmed_pct":
            move_at_confirmed_pct,

        "highest_confidence":
            highest_confidence,

        "consecutive_direction_count":
            consecutive,

        "last_direction":
            direction,

        "last_confidence":
            confidence,

        "last_evaluated_at_utc":
            evaluated_at.isoformat(),

        "last_counted_bucket_utc":
            (
                current_bucket.isoformat()
                if new_time_bucket
                else previous_bucket_text
            ),

        "confirmation_count":
            confirmation_count,

        "lost_confirmation_count":
            lost_count,

        "model_version":
            MODEL_VERSION,

        "updated_at":
            evaluated_at.isoformat(),
    }


def eligible(
    episode: LifecycleEpisode,
) -> bool:

    if episode.is_finalized:
        return False

    if (
        episode.measurement_quality
        != "FORWARD_COMPLETE"
    ):
        return False

    return True


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

    candidates = [
        episode
        for episode in episodes
        if eligible(
            episode
        )
    ]

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

    evaluated_at = now_utc()

    previous_states = load_direction_states(
        settings
    )

    rows = []
    state_rows = []

    failures = 0

    print()
    print(
        "=" * 118
    )

    print(
        "ALPHA HUNTER V7.6 "
        "DIRECTION-PROOF ENGINE — SHADOW"
    )

    print(
        "=" * 118
    )

    print(
        "Eligible forward episodes:",
        len(
            candidates
        ),
    )

    print()

    print(
        f"{'SYMBOL':<15}"
        f"{'PATH':<14}"
        f"{'DIR':<9}"
        f"{'CONF':>7}"
        f"{'LONG':>7}"
        f"{'SHORT':>8}"
        f"{'15M':>10}"
        f"{'1H':>10}"
    )

    print(
        "-" * 118
    )

    for episode in candidates:

        try:
            candles_15m = client.candles(
                episode.symbol,
                product_type,
                "15m",
                CANDLE_LIMIT,
            ) or []

            candles_1h = client.candles(
                episode.symbol,
                product_type,
                "1H",
                CANDLE_LIMIT,
            ) or []

            prices_15m = closes(
                candles_15m
            )

            prices_1h = closes(
                candles_1h
            )

            if (
                len(prices_15m) < 21
                or len(prices_1h) < 21
            ):
                raise RuntimeError(
                    "insufficient candle history"
                )

            bias_15m = ema_bias(
                prices_15m
            )

            bias_1h = ema_bias(
                prices_1h
            )

            mom_15m = momentum(
                prices_15m,
                3,
            )

            mom_1h = momentum(
                prices_1h,
                3,
            )

            struct_15m = structure(
                prices_15m
            )

            struct_1h = structure(
                prices_1h
            )

            (
                long_score,
                short_score,
                evidence,
            ) = score_direction(
                bias_15m,
                bias_1h,
                mom_15m,
                mom_1h,
                struct_15m,
                struct_1h,
            )

            (
                direction,
                confidence,
            ) = direction_verdict(
                long_score,
                short_score,
            )

            ticker = client.ticker(
                episode.symbol,
                product_type,
            )

            price = f(
                ticker.get(
                    "lastPr"
                )
                or ticker.get(
                    "last"
                )
                or ticker.get(
                    "close"
                )
            )

            row = {
                "shadow_id":
                    shadow_id(
                        episode.episode_id,
                        evaluated_at,
                    ),

                "episode_id":
                    episode.episode_id,

                "symbol":
                    episode.symbol,

                "path":
                    episode.path,

                "evaluated_at_utc":
                    evaluated_at.isoformat(),

                "market_price":
                    price,

                "direction":
                    direction,

                "confidence":
                    confidence,

                "long_score":
                    long_score,

                "short_score":
                    short_score,

                "ema_15m_bias":
                    bias_15m,

                "ema_1h_bias":
                    bias_1h,

                "momentum_15m":
                    mom_15m,

                "momentum_1h":
                    mom_1h,

                "structure_15m":
                    struct_15m,

                "structure_1h":
                    struct_1h,

                "evidence": {
                    "signals":
                        evidence,

                    "lifecycle_state":
                        episode.lifecycle_state,

                    "v74_rank":
                        episode.v74_rank,

                    "v74_score":
                        episode.v74_score,

                    "v741_shadow_score":
                        episode.v741_shadow_score,

                    "first_detection_price":
                        episode.first_detection_price,

                    "max_up_excursion_pct":
                        episode.max_up_excursion_pct,

                    "max_down_excursion_pct":
                        episode.max_down_excursion_pct,
                },

                "model_version":
                    MODEL_VERSION,
            }

            rows.append(
                row
            )

            state_row = update_direction_state(
                episode,
                previous_states.get(
                    episode.episode_id
                ),
                direction,
                confidence,
                price,
                evaluated_at,
            )

            state_rows.append(
                state_row
            )

            print(
                f"{episode.symbol:<15}"
                f"{episode.path:<14}"
                f"{direction:<9}"
                f"{confidence:>6.1f}%"
                f"{long_score:>7.2f}"
                f"{short_score:>8.2f}"
                f"{bias_15m:>10}"
                f"{bias_1h:>10}"
            )

        except (
            BitgetAPIError,
            RuntimeError,
            ValueError,
        ) as exc:

            failures += 1

            print(
                f"{episode.symbol:<15}"
                f"FAILED: {exc}"
            )

    saved = save_rows(
        settings,
        rows,
    )

    states_saved = save_direction_states(
        settings,
        state_rows,
    )

    longs = sum(
        row["direction"]
        == "LONG"
        for row in rows
    )

    shorts = sum(
        row["direction"]
        == "SHORT"
        for row in rows
    )

    unknown = sum(
        row["direction"]
        == "UNKNOWN"
        for row in rows
    )

    print()
    print(
        "=" * 118
    )

    print(
        "V7.6 SHADOW SUMMARY"
    )

    print(
        "=" * 118
    )

    print(
        "Evaluated:",
        len(rows),
    )

    print(
        "LONG:",
        longs,
    )

    print(
        "SHORT:",
        shorts,
    )

    print(
        "UNKNOWN:",
        unknown,
    )

    print(
        "Failures:",
        failures,
    )

    print(
        "Supabase shadow rows saved:",
        saved,
    )

    print(
        "Direction state rows saved:",
        states_saved,
    )

    emerging = sum(
        row["direction_state"]
        == "DIRECTION_EMERGING"
        for row in state_rows
    )

    confirmed = sum(
        row["direction_state"]
        == "DIRECTION_CONFIRMED"
        for row in state_rows
    )

    lost = sum(
        row["direction_state"]
        == "LOST_CONFIRMATION"
        for row in state_rows
    )

    print(
        "Direction emerging:",
        emerging,
    )

    print(
        "Direction confirmed:",
        confirmed,
    )

    print(
        "Lost confirmation:",
        lost,
    )

    print()

    print(
        "IMPORTANT: V7.6 IS SHADOW ONLY."
    )

    print(
        "No trade permission was generated."
    )

    if failures:
        raise SystemExit(
            f"V7.6 DIRECTION SHADOW FAILED "
            f"FOR {failures} EPISODES"
        )

    print()
    print(
        "V7.6 DIRECTION SHADOW: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
