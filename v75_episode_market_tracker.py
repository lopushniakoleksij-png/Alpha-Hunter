from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.lifecycle import LifecycleEpisode
from alpha_hunter.storage import SupabaseConfig
from v75_lifecycle_job import (
    load_state,
    load_supabase_state,
    save_state,
    upsert_supabase,
)

ROOT = Path(__file__).resolve().parent
LOOKBACK_CANDLES = 120


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

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


def candle_time(candle: list[Any]) -> datetime | None:
    try:
        timestamp_ms = int(candle[0])
    except (TypeError, ValueError, IndexError):
        return None

    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    )


def percentage_move(
    reference: float,
    price: float,
) -> float:
    return (
        price / reference - 1.0
    ) * 100.0


def mark_threshold(
    episode: LifecycleEpisode,
    move: float,
    observed_at: datetime,
) -> None:
    absolute_move = abs(move)

    direction = (
        "UP"
        if move >= 0
        else "DOWN"
    )

    timestamp = observed_at.isoformat()

    if (
        absolute_move >= 3
        and not episode.expansion_3_hit
    ):
        episode.expansion_3_hit = True
        episode.first_3pct_at_utc = timestamp

        if episode.expansion_direction is None:
            episode.expansion_direction = direction

    if (
        absolute_move >= 5
        and not episode.expansion_5_hit
    ):
        episode.expansion_5_hit = True
        episode.first_5pct_at_utc = timestamp

    if (
        absolute_move >= 10
        and not episode.expansion_10_hit
    ):
        episode.expansion_10_hit = True
        episode.first_10pct_at_utc = timestamp


def inspect_price(
    episode: LifecycleEpisode,
    price: float,
    observed_at: datetime,
) -> None:
    reference = episode.first_detection_price

    if reference in (None, 0):
        return

    move = percentage_move(
        reference,
        price,
    )

    episode.latest_price = price

    episode.max_up_excursion_pct = max(
        episode.max_up_excursion_pct,
        move,
    )

    episode.max_down_excursion_pct = min(
        episode.max_down_excursion_pct,
        move,
    )

    episode.max_favorable_excursion_pct = max(
        episode.max_favorable_excursion_pct,
        move,
    )

    episode.max_adverse_excursion_pct = min(
        episode.max_adverse_excursion_pct,
        move,
    )

    mark_threshold(
        episode,
        move,
        observed_at,
    )


def inspect_candle(
    episode: LifecycleEpisode,
    candle: list[Any],
) -> None:
    observed_at = candle_time(candle)

    if observed_at is None:
        return

    first_detected = dt(
        episode.first_detected_at_utc
    )

    if (
        first_detected is not None
        and observed_at < first_detected
    ):
        return

    last_check = dt(
        episode.last_market_check_at_utc
    )

    if (
        last_check is not None
        and observed_at <= last_check
    ):
        return

    try:
        high = f(candle[2])
        low = f(candle[3])
    except IndexError:
        return

    if high is not None:
        inspect_price(
            episode,
            high,
            observed_at,
        )

    if low is not None:
        inspect_price(
            episode,
            low,
            observed_at,
        )


def cached_1m_candles(
    client: BitgetClient,
    cache: dict[str, list[Any]],
    symbol: str,
    product_type: str,
) -> list[Any]:
    if symbol not in cache:
        cache[symbol] = (
            client.candles(
                symbol,
                product_type,
                "1m",
                LOOKBACK_CANDLES,
            )
            or []
        )

    return cache[symbol]


def cached_ticker(
    client: BitgetClient,
    cache: dict[str, dict[str, Any]],
    symbol: str,
    product_type: str,
) -> dict[str, Any]:
    if symbol not in cache:
        cache[symbol] = client.ticker(
            symbol,
            product_type,
        )

    return cache[symbol]


def main() -> int:
    load_env_file(
        ROOT / ".env"
    )

    config = load_config(
        ROOT / "config.json"
    )

    product_type = str(
        config.get(
            "product_type",
            "usdt-futures",
        )
    )

    settings = SupabaseConfig.from_environment(
        config
    )

    if settings is None:
        raise SystemExit(
            "Supabase is not configured"
        )

    episodes = load_state()

    if not episodes:
        episodes = load_supabase_state(
            settings
        )

    active = [
        episode
        for episode in episodes
        if not episode.is_finalized
    ]

    client = BitgetClient.from_environment(
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

    now = utc_now()

    checked = 0
    failed = 0

    candle_cache: dict[
        str,
        list[Any],
    ] = {}

    ticker_cache: dict[
        str,
        dict[str, Any],
    ] = {}

    print()
    print("=" * 110)
    print(
        "ALPHA HUNTER V7.5 "
        "INDEPENDENT EPISODE MARKET TRACKER"
    )
    print("=" * 110)

    print(
        "Episodes stored:",
        len(episodes),
    )

    print(
        "Active episodes:",
        len(active),
    )

    print()

    for episode in active:
        try:
            if (
                episode.market_tracking_started_at_utc
                is None
            ):
                first_detected = dt(
                    episode.first_detected_at_utc
                )

                episode.market_tracking_started_at_utc = (
                    now.isoformat()
                )

                if first_detected is None:
                    episode.measurement_quality = (
                        "LEGACY_PARTIAL"
                    )

                else:
                    age_at_tracker_start = (
                        now - first_detected
                    ).total_seconds() / 3600.0

                    if age_at_tracker_start <= 2.0:
                        episode.measurement_quality = (
                            "FORWARD_COMPLETE"
                        )
                    else:
                        episode.measurement_quality = (
                            "LEGACY_PARTIAL"
                        )

            candles = cached_1m_candles(
                client,
                candle_cache,
                episode.symbol,
                product_type,
            )

            ordered = []

            for candle in candles:
                if not isinstance(
                    candle,
                    list,
                ):
                    continue

                timestamp = candle_time(
                    candle
                )

                if timestamp is None:
                    continue

                ordered.append(
                    (timestamp, candle)
                )

            ordered.sort(
                key=lambda item:
                    item[0]
            )

            for _, candle in ordered:
                inspect_candle(
                    episode,
                    candle,
                )

            ticker = cached_ticker(
                client,
                ticker_cache,
                episode.symbol,
                product_type,
            )

            price = f(
                ticker.get("lastPr")
                or ticker.get("last")
                or ticker.get("close")
            )

            if price is None:
                raise RuntimeError(
                    "ticker has no usable price"
                )

            inspect_price(
                episode,
                price,
                now,
            )

            episode.last_market_check_at_utc = (
                now.isoformat()
            )

            episode.market_checks += 1

            checked += 1

            current_move = (
                percentage_move(
                    episode.first_detection_price,
                    price,
                )
                if episode.first_detection_price
                not in (None, 0)
                else 0.0
            )

            print(
                f"{episode.symbol:<15}"
                f"{episode.path:<14}"
                f"now={current_move:>8.2f}% "
                f"UP={episode.max_up_excursion_pct:>8.2f}% "
                f"DOWN={episode.max_down_excursion_pct:>8.2f}% "
                f"3={'Y' if episode.expansion_3_hit else '-'} "
                f"5={'Y' if episode.expansion_5_hit else '-'} "
                f"10={'Y' if episode.expansion_10_hit else '-'} "
                f"checks={episode.market_checks}"
            )

        except (
            BitgetAPIError,
            RuntimeError,
            ValueError,
        ) as exc:
            failed += 1

            print(
                f"{episode.symbol:<15}"
                f"FAILED: {exc}"
            )

    save_state(
        episodes
    )

    saved = upsert_supabase(
        episodes,
        settings,
    )

    print()
    print("=" * 110)
    print("TRACKER SUMMARY")
    print("=" * 110)

    print("Checked:", checked)
    print("Failed:", failed)
    print(
        "Supabase rows upserted:",
        saved,
    )

    print(
        "3% episodes:",
        sum(
            episode.expansion_3_hit
            for episode in episodes
        ),
    )

    print(
        "5% episodes:",
        sum(
            episode.expansion_5_hit
            for episode in episodes
        ),
    )

    print(
        "10% episodes:",
        sum(
            episode.expansion_10_hit
            for episode in episodes
        ),
    )

    if failed:
        raise SystemExit(
            f"V7.5 MARKET TRACKER FAILED "
            f"FOR {failed} EPISODES"
        )

    print()
    print(
        "V7.5 EPISODE MARKET TRACKER: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
