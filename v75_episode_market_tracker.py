from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

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
UNIVERSE_TABLE = "alpha_hunter_universe_hourly"
MAX_UNIVERSE_AGE_HOURS = 2.0


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



def load_latest_universe_symbols(
    settings: SupabaseConfig,
    now: datetime,
) -> tuple[set[str], datetime]:
    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
    }

    latest_response = requests.get(
        f"{settings.url}/rest/v1/{UNIVERSE_TABLE}",
        params={
            "select": "hour_bucket_utc",
            "order": "hour_bucket_utc.desc",
            "limit": "1",
        },
        headers=headers,
        timeout=settings.timeout_seconds,
    )

    if latest_response.status_code != 200:
        raise RuntimeError(
            "V7.5 universe freshness lookup failed: "
            f"HTTP {latest_response.status_code}: "
            f"{latest_response.text[:500]}"
        )

    latest_payload = latest_response.json()

    if (
        not isinstance(latest_payload, list)
        or not latest_payload
        or not isinstance(latest_payload[0], dict)
    ):
        raise RuntimeError(
            "V7.5 current canonical universe is unavailable"
        )

    hour_bucket = dt(
        latest_payload[0].get("hour_bucket_utc")
    )

    if hour_bucket is None:
        raise RuntimeError(
            "V7.5 current canonical universe timestamp is invalid"
        )

    age_hours = (
        now - hour_bucket
    ).total_seconds() / 3600.0

    if age_hours < -0.1 or age_hours > MAX_UNIVERSE_AGE_HOURS:
        raise RuntimeError(
            "V7.5 canonical universe is stale: "
            f"age_hours={age_hours:.2f}"
        )

    symbols_response = requests.get(
        f"{settings.url}/rest/v1/{UNIVERSE_TABLE}",
        params={
            "select": "symbol",
            "hour_bucket_utc": f"eq.{hour_bucket.isoformat()}",
            "limit": "2000",
        },
        headers=headers,
        timeout=settings.timeout_seconds,
    )

    if symbols_response.status_code != 200:
        raise RuntimeError(
            "V7.5 current canonical universe load failed: "
            f"HTTP {symbols_response.status_code}: "
            f"{symbols_response.text[:500]}"
        )

    symbols_payload = symbols_response.json()

    if not isinstance(symbols_payload, list):
        raise RuntimeError(
            "V7.5 canonical universe payload is not a list"
        )

    symbols = {
        str(row.get("symbol") or "").upper()
        for row in symbols_payload
        if isinstance(row, dict)
        and str(row.get("symbol") or "").strip()
    }

    if not symbols:
        raise RuntimeError(
            "V7.5 current canonical universe is empty"
        )

    return symbols, hour_bucket


def finalize_venue_ineligible_episode(
    episode: LifecycleEpisode,
    observed_at: datetime,
) -> None:
    episode.previous_state = episode.lifecycle_state
    episode.lifecycle_state = "FINALIZED"
    episode.measurement_quality = (
        "VENUE_INELIGIBLE_UNOBSERVABLE"
    )
    episode.final_classification = (
        "VENUE_INELIGIBLE_UNOBSERVABLE"
    )
    episode.finalized_at_utc = observed_at.isoformat()
    episode.is_finalized = True


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

    current_universe, universe_hour = (
        load_latest_universe_symbols(
            settings,
            now,
        )
    )

    checked = 0
    failed = 0
    venue_ineligible = 0

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

    print(
        "Canonical universe hour:",
        universe_hour.isoformat(),
    )

    print(
        "Canonical universe symbols:",
        len(current_universe),
    )

    print()

    for episode in active:
        if episode.symbol.upper() not in current_universe:
            finalize_venue_ineligible_episode(
                episode,
                now,
            )

            venue_ineligible += 1

            print(
                f"{episode.symbol:<15}"
                f"{episode.path:<14}"
                "VENUE_INELIGIBLE_UNOBSERVABLE"
            )

            continue

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

            candles = client.candles(
                episode.symbol,
                product_type,
                "1m",
                LOOKBACK_CANDLES,
            ) or []

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

            ticker = client.ticker(
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
    print(
        "Venue ineligible finalized:",
        venue_ineligible,
    )
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
