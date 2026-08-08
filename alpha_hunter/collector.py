from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .analysis import (
    build_intelligence_score,
    calculate_indicators,
    compression_score,
    classify_state,
    funding_summary,
    integrity_score,
    parse_candles,
    percentage_change,
    support_resistance,
    to_float,
    trend_state,
    validate_trade_setup,
)
from .bitget import BitgetAPIError, BitgetClient
from .env import load_env_file
from .decision_trace import build_decision_trace
from .pre_move import apply_pre_move_engine
from .private_account import collect_private_account_snapshot
from .storage import (
    SupabaseConfig,
    SupabaseStorage,
    SupabaseStorageError,
    build_run_id,
)


# =========================================================
# BASIC HELPERS
# =========================================================

def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    return bool(value)


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def safe_intelligence_score(
    row: dict[str, Any],
) -> float:
    try:
        return float(
            row.get(
                "intelligence",
                {},
            ).get(
                "huge_rr_score",
                0,
            )
            or 0
        )
    except (TypeError, ValueError):
        return 0.0


# =========================================================
# TECHNICAL HELPERS
# =========================================================

def percent_change(
    current: float | None,
    previous: float | None,
) -> float | None:
    if current is None or previous in (None, 0):
        return None

    return (
        (current - previous)
        / previous
        * 100
    )


def average_close(
    candles: list[dict[str, float | int]],
    lookback: int,
) -> float | None:
    if len(candles) < lookback:
        return None

    closes = [
        float(candle["close"])
        for candle in candles[-lookback:]
    ]

    if not closes:
        return None

    return mean(closes)


def change_over_candles(
    candles: list[dict[str, float | int]],
    lookback: int,
) -> float | None:
    if len(candles) <= lookback:
        return None

    current = float(
        candles[-1]["close"]
    )

    previous = float(
        candles[-(lookback + 1)]["close"]
    )

    return percent_change(
        current,
        previous,
    )


def compression_base(
    candles: list[dict[str, float | int]],
    lookback: int = 40,
) -> float | None:
    if not candles:
        return None

    sample = candles[-lookback:]

    return min(
        float(candle["low"])
        for candle in sample
    )


def breakout_trigger(
    candles: list[dict[str, float | int]],
    lookback: int = 20,
) -> float | None:
    if len(candles) < lookback + 1:
        return None

    sample = candles[
        -(lookback + 1):-1
    ]

    return max(
        float(candle["high"])
        for candle in sample
    )


def rsi_series(
    values: list[float],
    period: int = 14,
) -> list[float]:
    if len(values) <= period:
        return []

    deltas = [
        values[index]
        - values[index - 1]
        for index in range(
            1,
            len(values),
        )
    ]

    gains = [
        max(delta, 0.0)
        for delta in deltas
    ]

    losses = [
        max(-delta, 0.0)
        for delta in deltas
    ]

    avg_gain = mean(
        gains[:period]
    )

    avg_loss = mean(
        losses[:period]
    )

    output: list[float] = []

    if avg_loss == 0:
        output.append(100.0)
    else:
        rs = avg_gain / avg_loss

        output.append(
            100
            - (
                100
                / (1 + rs)
            )
        )

    for gain, loss in zip(
        gains[period:],
        losses[period:],
    ):
        avg_gain = (
            (
                avg_gain
                * (period - 1)
            )
            + gain
        ) / period

        avg_loss = (
            (
                avg_loss
                * (period - 1)
            )
            + loss
        ) / period

        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss

            current_rsi = (
                100
                - (
                    100
                    / (1 + rs)
                )
            )

        output.append(
            current_rsi
        )

    return output


def stochastic_rsi(
    candles: list[dict[str, float | int]],
    rsi_period: int = 14,
    stoch_period: int = 14,
) -> float | None:
    closes = [
        float(candle["close"])
        for candle in candles
    ]

    values = rsi_series(
        closes,
        rsi_period,
    )

    if len(values) < stoch_period:
        return None

    sample = values[
        -stoch_period:
    ]

    minimum = min(sample)
    maximum = max(sample)
    current = sample[-1]

    if maximum == minimum:
        return 50.0

    return (
        (current - minimum)
        / (maximum - minimum)
        * 100
    )


# =========================================================
# SYMBOL COLLECTION
# =========================================================

def collect_symbol(
    client: BitgetClient,
    symbol: str,
    config: dict[str, Any],
) -> dict[str, Any]:

    product_type = config[
        "product_type"
    ]

    ticker = client.ticker(
        symbol,
        product_type,
    )

    prices = client.symbol_price(
        symbol,
        product_type,
    )

    oi_payload = client.open_interest(
        symbol,
        product_type,
    )

    funding = client.current_funding(
        symbol,
        product_type,
    )

    funding_rows = client.funding_history(
        symbol,
        product_type,
        config.get(
            "funding_history_limit",
            30,
        ),
    )

    timeframes: dict[str, Any] = {}

    combined_levels: dict[
        str,
        float | None,
    ] = {
        "support": None,
        "resistance": None,
    }

    raw_candles: dict[
        str,
        list[dict[str, float | int]],
    ] = {}

    for timeframe in config[
        "timeframes"
    ]:

        candles = parse_candles(
            client.candles(
                symbol,
                product_type,
                timeframe,
                config[
                    "candle_limit"
                ],
            )
        )

        raw_candles[
            timeframe
        ] = candles

        levels = support_resistance(
            candles
        )

        indicators = calculate_indicators(
            candles
        )

        indicators[
            "stoch_rsi"
        ] = stochastic_rsi(
            candles
        )

        timeframes[
            timeframe
        ] = {
            "trend":
                trend_state(candles),

            "candle_count":
                len(candles),

            "latest_candle":
                (
                    candles[-1]
                    if candles
                    else None
                ),

            "indicators":
                indicators,

            "compression":
                compression_score(
                    candles
                ),

            **levels,
        }

        if timeframe == "1H":
            combined_levels = levels

    oi_list = (
        oi_payload.get(
            "openInterestList",
            [],
        )
        if isinstance(
            oi_payload,
            dict,
        )
        else []
    )

    oi = (
        to_float(
            oi_list[0].get(
                "size"
            )
        )
        if oi_list
        else None
    )

    last_price = to_float(
        prices.get(
            "price"
        )
        or ticker.get(
            "lastPr"
        )
    )

    trends = {
        timeframe:
            values["trend"]
        for timeframe, values
        in timeframes.items()
    }

    (
        state,
        permission,
        permission_reason,
    ) = classify_state(
        trends,
        last_price,
        combined_levels,
    )

    current_funding = to_float(
        funding.get(
            "fundingRate"
        )
    )

    one_hour_candles = (
        raw_candles.get(
            "1H",
            [],
        )
    )

    change_3d = change_over_candles(
        one_hour_candles,
        72,
    )

    average_7d = average_close(
        one_hour_candles,
        168,
    )

    base = compression_base(
        one_hour_candles,
        40,
    )

    trigger = breakout_trigger(
        one_hour_candles,
        20,
    )

    distance_from_base = (
        percent_change(
            last_price,
            base,
        )
    )

    distance_above_trigger = (
        percent_change(
            last_price,
            trigger,
        )
    )

    distance_from_7d_average = (
        percent_change(
            last_price,
            average_7d,
        )
    )

    record = {
        "symbol":
            symbol,

        "collected_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "exchange_timestamp_ms":
            int(
                prices.get(
                    "ts"
                )
                or ticker.get(
                    "ts"
                )
                or 0
            ),

        "last_price":
            last_price,

        "mark_price":
            to_float(
                prices.get(
                    "markPrice"
                )
                or ticker.get(
                    "markPrice"
                )
            ),

        "index_price":
            to_float(
                prices.get(
                    "indexPrice"
                )
                or ticker.get(
                    "indexPrice"
                )
            ),

        "bid_price":
            to_float(
                ticker.get(
                    "bidPr"
                )
            ),

        "ask_price":
            to_float(
                ticker.get(
                    "askPr"
                )
            ),

        "change_24h_pct":
            (
                (
                    to_float(
                        ticker.get(
                            "change24h"
                        )
                    )
                    or 0.0
                )
                * 100
            ),

        "change_3d_pct":
            change_3d,

        "quote_volume_24h":
            to_float(
                ticker.get(
                    "quoteVolume"
                )
                or ticker.get(
                    "usdtVolume"
                )
            ),

        "open_interest":
            oi,

        "open_interest_change_pct":
            None,

        "funding_rate":
            current_funding,

        "funding_history":
            funding_summary(
                funding_rows,
                current_funding,
            ),

        "funding_interval_hours":
            int(
                funding.get(
                    "fundingRateInterval"
                )
                or 0
            ),

        "next_funding_time_ms":
            int(
                funding.get(
                    "nextUpdate"
                )
                or 0
            ),

        "timeframes":
            timeframes,

        "support":
            combined_levels.get(
                "support"
            ),

        "resistance":
            combined_levels.get(
                "resistance"
            ),

        "compression_base":
            base,

        "breakout_trigger":
            trigger,

        "average_7d":
            average_7d,

        "distance_from_compression_base_pct":
            distance_from_base,

        "distance_above_breakout_trigger_pct":
            distance_above_trigger,

        "distance_from_7d_average_pct":
            distance_from_7d_average,

        "state":
            state,

        "trade_permission":
            permission,

        "trade_permission_reason":
            permission_reason,
    }

    record[
        "data_integrity_score"
    ] = integrity_score(
        record
    )

    setup = validate_trade_setup(
        record,
        config.get(
            "minimum_reward_risk",
            5.0,
        ),
    )

    record[
        "execution_setup"
    ] = setup

    record[
        "trade_permission"
    ] = setup[
        "permission"
    ]

    record[
        "trade_permission_reason"
    ] = setup[
        "reason"
    ]

    record[
        "intelligence"
    ] = build_intelligence_score(
        record,
        config.get(
            "minimum_reward_risk",
            5.0,
        ),
    )

    return record


# =========================================================
# PREVIOUS SNAPSHOT
# =========================================================

def load_previous_snapshot(
    config_path: Path,
    config: dict[str, Any],
) -> dict[str, Any] | None:

    path = (
        config_path.parent
        / config[
            "snapshot_directory"
        ]
        / "latest.json"
    )

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


# =========================================================
# FULL MARKET UNIVERSE FILTER
# =========================================================

def build_instrument_map(
    contracts: list[
        dict[str, Any]
    ],
    instruments: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    dict[str, Any],
]:

    output: dict[
        str,
        dict[str, Any],
    ] = {}

    for row in contracts:
        symbol = str(
            row.get(
                "symbol",
                "",
            )
        ).upper()

        if symbol:
            output[
                symbol
            ] = dict(row)

    for row in instruments:
        symbol = str(
            row.get(
                "symbol",
                "",
            )
        ).upper()

        if not symbol:
            continue

        if symbol not in output:
            output[
                symbol
            ] = {}

        output[
            symbol
        ].update(row)

    return output


def instrument_is_allowed(
    metadata: dict[
        str,
        Any,
    ],
    config: dict[
        str,
        Any,
    ],
) -> bool:

    settings = config.get(
        "universe_scan",
        {},
    )

    symbol_type = str(
        metadata.get(
            "symbolType",
            "",
        )
    ).lower()

    is_rwa = safe_bool(
        metadata.get(
            "isRwa",
            False,
        )
    )

    is_reality = safe_bool(
        metadata.get(
            "isReality",
            False,
        )
    )

    if (
        settings.get(
            "reject_rwa",
            True,
        )
        and is_rwa
    ):
        return False

    if (
        settings.get(
            "reject_reality",
            True,
        )
        and is_reality
    ):
        return False

    if (
        settings.get(
            "crypto_only",
            True,
        )
        and symbol_type
        and symbol_type
        not in {
            "crypto",
            "coin",
        }
    ):
        return False

    return True


def select_market_universe(
    contracts: list[
        dict[str, Any]
    ],
    instruments: list[
        dict[str, Any]
    ],
    tickers: list[
        dict[str, Any]
    ],
    previous_snapshot:
        dict[str, Any] | None,
    config: dict[str, Any],
) -> tuple[
    list[str],
    dict[str, Any],
]:

    settings = config.get(
        "universe_scan",
        {},
    )

    metadata_map = (
        build_instrument_map(
            contracts,
            instruments,
        )
    )

    contract_symbols = set(
        metadata_map.keys()
    )

    deep_scan_limit = int(
        settings.get(
            "deep_scan_limit",
            30,
        )
    )

    minimum_quote_volume = float(
        settings.get(
            "minimum_quote_volume",
            100000,
        )
    )

    maximum_extension = float(
        settings.get(
            "maximum_24h_extension_pct",
            25,
        )
    )

    preferred_min = float(
        settings.get(
            "preferred_24h_move_min_pct",
            -8,
        )
    )

    preferred_max = float(
        settings.get(
            "preferred_24h_move_max_pct",
            15,
        )
    )

    candidates: list[
        dict[str, Any]
    ] = []

    rejected_non_crypto = 0
    rejected_liquidity = 0
    rejected_extension = 0

    for ticker in tickers:

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
        ).upper()

        if not symbol:
            continue

        if symbol not in contract_symbols:
            continue

        metadata = metadata_map.get(
            symbol,
            {},
        )

        if not instrument_is_allowed(
            metadata,
            config,
        ):
            rejected_non_crypto += 1
            continue

        last_price = to_float(
            ticker.get(
                "lastPr"
            )
        )

        quote_volume = (
            to_float(
                ticker.get(
                    "quoteVolume"
                )
            )
            or to_float(
                ticker.get(
                    "usdtVolume"
                )
            )
            or 0.0
        )

        change_24h_pct = (
            (
                to_float(
                    ticker.get(
                        "change24h"
                    )
                )
                or 0.0
            )
            * 100
        )

        if (
            last_price is None
            or last_price <= 0
        ):
            continue

        if (
            quote_volume
            < minimum_quote_volume
        ):
            rejected_liquidity += 1
            continue

        if (
            abs(
                change_24h_pct
            )
            > maximum_extension
        ):
            rejected_extension += 1
            continue

        candidates.append({
            "symbol":
                symbol,

            "last_price":
                last_price,

            "quote_volume":
                quote_volume,

            "change_24h_pct":
                change_24h_pct,

            "preferred_move":
                (
                    preferred_min
                    <= change_24h_pct
                    <= preferred_max
                ),
        })

    selected: list[str] = []

    def add_symbol(
        symbol: str,
    ) -> None:

        if (
            symbol
            and symbol
            in contract_symbols
            and symbol
            not in selected
        ):
            selected.append(
                symbol
            )

    if (
        settings.get(
            "preserve_previous_candidates",
            True,
        )
        and previous_snapshot
    ):

        previous_limit = int(
            settings.get(
                "previous_candidate_limit",
                10,
            )
        )

        previous_rows = [
            row
            for row
            in previous_snapshot.get(
                "symbols",
                [],
            )
            if "error"
            not in row
        ]

        previous_rows = sorted(
            previous_rows,
            key=
                safe_intelligence_score,
            reverse=True,
        )

        for row in previous_rows[
            :previous_limit
        ]:

            symbol = str(
                row.get(
                    "symbol",
                    "",
                )
            ).upper()

            metadata = metadata_map.get(
                symbol,
                {},
            )

            if instrument_is_allowed(
                metadata,
                config,
            ):
                add_symbol(
                    symbol
                )

    quiet_limit = int(
        settings.get(
            "quiet_bucket_size",
            12,
        )
    )

    quiet_max = float(
        settings.get(
            "quiet_24h_abs_change_max_pct",
            3,
        )
    )

    quiet = [
        row
        for row
        in candidates
        if abs(
            row[
                "change_24h_pct"
            ]
        )
        <= quiet_max
    ]

    quiet.sort(
        key=lambda row:
            row[
                "quote_volume"
            ],
        reverse=True,
    )

    for row in quiet[
        :quiet_limit
    ]:
        add_symbol(
            row[
                "symbol"
            ]
        )

    movement_limit = int(
        settings.get(
            "movement_bucket_size",
            10,
        )
    )

    early_min = float(
        settings.get(
            "early_ignition_min_abs_change_pct",
            1,
        )
    )

    early_max = float(
        settings.get(
            "early_ignition_max_abs_change_pct",
            15,
        )
    )

    movement = [
        row
        for row
        in candidates
        if (
            early_min
            <= abs(
                row[
                    "change_24h_pct"
                ]
            )
            <= early_max
        )
    ]

    movement.sort(
        key=lambda row:
            abs(
                row[
                    "change_24h_pct"
                ]
            ),
        reverse=True,
    )

    for row in movement[
        :movement_limit
    ]:
        add_symbol(
            row[
                "symbol"
            ]
        )

    liquidity_limit = int(
        settings.get(
            "liquidity_bucket_size",
            8,
        )
    )

    liquid = sorted(
        candidates,
        key=lambda row:
            row[
                "quote_volume"
            ],
        reverse=True,
    )

    for row in liquid[
        :liquidity_limit
    ]:
        add_symbol(
            row[
                "symbol"
            ]
        )

    selected = selected[
        :deep_scan_limit
    ]

    universe = {
        "total_contracts":
            len(
                contract_symbols
            ),

        "ticker_count":
            len(tickers),

        "eligible_count":
            len(candidates),

        "selected_count":
            len(selected),

        "selection_method":
            (
                "v7.1-crypto-"
                "behaviour-prefilter"
            ),

        "selected_symbols":
            selected,

        "rejected_non_crypto":
            rejected_non_crypto,

        "rejected_liquidity":
            rejected_liquidity,

        "rejected_extension":
            rejected_extension,

        "minimum_quote_volume":
            minimum_quote_volume,

        "maximum_24h_extension_pct":
            maximum_extension,
    }

    return (
        selected,
        universe,
    )


# =========================================================
# SNAPSHOT COMPARISON
# =========================================================

def apply_snapshot_comparisons(
    results: list[
        dict[str, Any]
    ],
    previous:
        dict[str, Any] | None,
    minimum_rr: float = 5.0,
) -> None:

    previous_by_symbol: dict[
        str,
        dict[str, Any],
    ] = {}

    if previous:
        previous_by_symbol = {
            str(
                item.get(
                    "symbol",
                    ""
                )
            ):
                item
            for item
            in previous.get(
                "symbols",
                [],
            )
        }

    for item in results:

        if "error" in item:
            continue

        old = previous_by_symbol.get(
            item["symbol"],
            {},
        )

        item[
            "open_interest_change_pct"
        ] = percentage_change(
            item.get(
                "open_interest"
            ),
            old.get(
                "open_interest"
            ),
        )

        item[
            "price_change_since_snapshot_pct"
        ] = percentage_change(
            item.get(
                "last_price"
            ),
            old.get(
                "last_price"
            ),
        )

        previous_state = old.get(
            "state"
        )

        item[
            "previous_state"
        ] = previous_state

        item[
            "state_changed"
        ] = bool(
            previous_state
            and previous_state
            != item.get(
                "state"
            )
        )

        item[
            "previous_behaviour_score"
        ] = old.get(
            "behaviour_score"
        )

        setup = validate_trade_setup(
            item,
            minimum_rr,
        )

        item[
            "execution_setup"
        ] = setup

        item[
            "trade_permission"
        ] = setup[
            "permission"
        ]

        item[
            "trade_permission_reason"
        ] = setup[
            "reason"
        ]

        item[
            "intelligence"
        ] = build_intelligence_score(
            item,
            minimum_rr,
        )


# =========================================================
# MARKET PHASE
# =========================================================

def classify_market_phase(
    record: dict[str, Any],
    config: dict[str, Any],
) -> str:

    change_24h = safe_float(
        record.get(
            "change_24h_pct"
        )
    )

    change_3d = safe_float(
        record.get(
            "change_3d_pct"
        )
    )

    from_base = safe_float(
        record.get(
            "distance_from_compression_base_pct"
        )
    )

    above_trigger = safe_float(
        record.get(
            "distance_above_breakout_trigger_pct"
        )
    )

    above_average = safe_float(
        record.get(
            "distance_from_7d_average_pct"
        )
    )

    one_hour = (
        record.get(
            "timeframes",
            {},
        ).get(
            "1H",
            {},
        )
    )

    four_hour = (
        record.get(
            "timeframes",
            {},
        ).get(
            "4H",
            {},
        )
    )

    fifteen = (
        record.get(
            "timeframes",
            {},
        ).get(
            "15m",
            {},
        )
    )

    compression = one_hour.get(
        "compression",
        {},
    )

    compression_state = compression.get(
        "state"
    )

    volume_ratio = safe_float(
        one_hour.get(
            "indicators",
            {},
        ).get(
            "volume_anomaly",
            {},
        ).get(
            "ratio"
        )
    )

    stoch_1h = safe_float(
        one_hour.get(
            "indicators",
            {},
        ).get(
            "stoch_rsi"
        )
    )

    stoch_4h = safe_float(
        four_hour.get(
            "indicators",
            {},
        ).get(
            "stoch_rsi"
        )
    )

    bb_upper = (
        one_hour.get(
            "indicators",
            {},
        ).get(
            "bollinger",
            {},
        ).get(
            "upper"
        )
    )

    price = record.get(
        "last_price"
    )

    trends = {
        "15m":
            fifteen.get(
                "trend"
            ),

        "1H":
            one_hour.get(
                "trend"
            ),

        "4H":
            four_hour.get(
                "trend"
            ),
    }

    thresholds = config.get(
        "universe_scan",
        {},
    )

    max_24h = float(
        thresholds.get(
            "maximum_24h_extension_pct",
            25,
        )
    )

    max_3d = float(
        thresholds.get(
            "maximum_3d_extension_pct",
            40,
        )
    )

    max_base = float(
        thresholds.get(
            "maximum_from_compression_base_pct",
            30,
        )
    )

    max_trigger = float(
        thresholds.get(
            "maximum_above_breakout_trigger_pct",
            20,
        )
    )

    max_average = float(
        thresholds.get(
            "maximum_above_7d_average_pct",
            50,
        )
    )

    if (
        abs(change_24h) > max_24h
        or abs(change_3d) > max_3d
        or from_base > max_base
        or above_trigger > max_trigger
        or above_average > max_average
    ):
        return "EXPANSION"

    if (
        stoch_1h > 90
        and stoch_4h > 85
        and change_24h > 5
    ):
        return "DISTRIBUTION_RISK"

    if (
        bb_upper
        and price
        and price
        > bb_upper * 1.02
        and change_24h > 5
    ):
        return "DISTRIBUTION_RISK"

    if (
        volume_ratio >= 4
        and abs(
            change_24h
        )
        >= 10
    ):
        return "EXPANSION_MANAGEMENT"

    if (
        trends.get(
            "15m"
        )
        == "BEARISH"
        and trends.get(
            "1H"
        )
        == "BEARISH"
        and change_24h < -5
    ):
        return "BREAKDOWN"

    if (
        compression_state
        in {
            "STRONG",
            "MODERATE",
        }
        and abs(
            change_24h
        )
        <= 5
    ):
        return "COMPRESSION"

    if (
        compression_state
        in {
            "STRONG",
            "MODERATE",
        }
        and trends.get(
            "4H"
        )
        in {
            "NEUTRAL",
            "BULLISH",
        }
        and abs(
            change_24h
        )
        <= 3
    ):
        return "ACCUMULATION"

    if (
        trends.get(
            "15m"
        )
        == "BULLISH"
        and trends.get(
            "1H"
        )
        == "BULLISH"
        and trends.get(
            "4H"
        )
        in {
            "BEARISH",
            "NEUTRAL",
        }
        and change_24h
        < 15
    ):
        return "RECOVERY"

    if (
        trends.get(
            "15m"
        )
        == trends.get(
            "1H"
        )
        and trends.get(
            "15m"
        )
        in {
            "BULLISH",
            "BEARISH",
        }
        and volume_ratio
        >= 1.25
        and abs(
            change_24h
        )
        <= 15
    ):
        return "IGNITION"

    return "ACCUMULATION"


# =========================================================
# OPPORTUNITY TIMING
# =========================================================

def classify_opportunity_timing(
    record: dict[str, Any],
) -> str:

    change_24h = abs(
        safe_float(
            record.get(
                "change_24h_pct"
            )
        )
    )

    from_base = abs(
        safe_float(
            record.get(
                "distance_from_compression_base_pct"
            )
        )
    )

    above_trigger = safe_float(
        record.get(
            "distance_above_breakout_trigger_pct"
        )
    )

    if (
        change_24h <= 8
        and from_base <= 15
        and above_trigger <= 5
    ):
        return "EARLY"

    if (
        change_24h <= 18
        and from_base <= 25
        and above_trigger <= 15
    ):
        return "FAIR"

    return "LATE"


# =========================================================
# BEHAVIOUR SCORE
# =========================================================

def calculate_behaviour_score(
    record: dict[str, Any],
    previous:
        dict[str, Any] | None,
    btc_change_24h: float,
    config: dict[str, Any],
) -> dict[str, Any]:

    settings = config.get(
        "behaviour_engine",
        {},
    )

    one_hour = (
        record.get(
            "timeframes",
            {},
        ).get(
            "1H",
            {},
        )
    )

    indicators = one_hour.get(
        "indicators",
        {},
    )

    volume_ratio = safe_float(
        indicators.get(
            "volume_anomaly",
            {},
        ).get(
            "ratio"
        )
    )

    compression = safe_float(
        one_hour.get(
            "compression",
            {},
        ).get(
            "score"
        )
    )

    symbol_change = safe_float(
        record.get(
            "change_24h_pct"
        )
    )

    relative_strength = (
        symbol_change
        - btc_change_24h
    )

    previous_rs: float | None = None

    if previous:
        previous_symbol_change = (
            safe_float(
                previous.get(
                    "change_24h_pct"
                )
            )
        )

        previous_btc_change = (
            safe_float(
                previous.get(
                    "btc_change_24h_pct"
                )
            )
        )

        previous_rs = (
            previous_symbol_change
            - previous_btc_change
        )

    rs_acceleration = (
        relative_strength
        - previous_rs
        if previous_rs
        is not None
        else 0.0
    )

    oi_change = safe_float(
        record.get(
            "open_interest_change_pct"
        )
    )

    funding_change = safe_float(
        record.get(
            "funding_history",
            {},
        ).get(
            "change_vs_average_pct"
        )
    )

    atr_pct = safe_float(
        indicators.get(
            "atr_pct"
        )
    )

    volume_component = clamp(
        volume_ratio / 2,
        0,
        1,
    )

    compression_component = clamp(
        compression / 10,
        0,
        1,
    )

    rs_component = clamp(
        (
            relative_strength
            + rs_acceleration
        )
        / 10,
        0,
        1,
    )

    oi_component = clamp(
        oi_change / 10,
        0,
        1,
    )

    funding_component = clamp(
        abs(
            funding_change
        )
        / 100,
        0,
        1,
    )

    volatility_component = clamp(
        atr_pct / 5,
        0,
        1,
    )

    trend_count = sum(
        record.get(
            "timeframes",
            {},
        ).get(
            timeframe,
            {},
        ).get(
            "trend"
        )
        in {
            "BULLISH",
            "BEARISH",
        }
        for timeframe
        in (
            "15m",
            "1H",
            "4H",
        )
    )

    trend_component = (
        trend_count
        / 3
    )

    spread: float | None = None

    bid = record.get(
        "bid_price"
    )

    ask = record.get(
        "ask_price"
    )

    price = record.get(
        "last_price"
    )

    if (
        bid
        and ask
        and price
    ):
        spread = (
            (ask - bid)
            / price
            * 100
        )

    liquidity_component = (
        1.0
        if (
            spread is not None
            and spread <= 0.1
        )
        else 0.5
    )

    components = {
        "volume_acceleration":
            volume_component,

        "compression":
            compression_component,

        "relative_strength":
            rs_component,

        "open_interest":
            oi_component,

        "funding_change":
            funding_component,

        "volatility_transition":
            volatility_component,

        "trend_acceleration":
            trend_component,

        "liquidity":
            liquidity_component,
    }

    weights = {
        "volume_acceleration":
            float(
                settings.get(
                    "volume_acceleration_weight",
                    1.5,
                )
            ),

        "compression":
            float(
                settings.get(
                    "compression_weight",
                    1.5,
                )
            ),

        "relative_strength":
            float(
                settings.get(
                    "relative_strength_weight",
                    1.5,
                )
            ),

        "open_interest":
            float(
                settings.get(
                    "open_interest_weight",
                    1.25,
                )
            ),

        "funding_change":
            float(
                settings.get(
                    "funding_change_weight",
                    0.75,
                )
            ),

        "volatility_transition":
            float(
                settings.get(
                    "volatility_transition_weight",
                    1.25,
                )
            ),

        "trend_acceleration":
            float(
                settings.get(
                    "trend_acceleration_weight",
                    1.0,
                )
            ),

        "liquidity":
            float(
                settings.get(
                    "liquidity_weight",
                    0.75,
                )
            ),
    }

    weighted_total = sum(
        components[key]
        * weights[key]
        for key in components
    )

    maximum_total = sum(
        weights.values()
    )

    score = (
        (
            weighted_total
            / maximum_total
        )
        * 10
        if maximum_total
        else 0
    )

    return {
        "score":
            round(
                score,
                2,
            ),

        "relative_strength_vs_btc_pct":
            round(
                relative_strength,
                3,
            ),

        "relative_strength_acceleration":
            round(
                rs_acceleration,
                3,
            ),

        "volume_ratio":
            volume_ratio,

        "oi_change_pct":
            oi_change,

        "funding_change_pct":
            funding_change,

        "atr_pct":
            atr_pct,

        "spread_pct":
            spread,

        "components":
            components,
    }


# =========================================================
# QUALITY FILTER
# =========================================================

def apply_candidate_quality(
    record: dict[str, Any],
    previous:
        dict[str, Any] | None,
    btc_change_24h: float,
    config: dict[str, Any],
) -> None:

    quality = config.get(
        "candidate_quality",
        {},
    )

    universe = config.get(
        "universe_scan",
        {},
    )

    phase = classify_market_phase(
        record,
        config,
    )

    timing = classify_opportunity_timing(
        record
    )

    behaviour = calculate_behaviour_score(
        record,
        previous,
        btc_change_24h,
        config,
    )

    record[
        "market_phase"
    ] = phase

    record[
        "opportunity_timing"
    ] = timing

    record[
        "behaviour_score"
    ] = behaviour[
        "score"
    ]

    record[
        "behaviour"
    ] = behaviour

    record[
        "btc_change_24h_pct"
    ] = btc_change_24h

    reasons: list[str] = []

    change_24h = safe_float(
        record.get(
            "change_24h_pct"
        )
    )

    change_3d = safe_float(
        record.get(
            "change_3d_pct"
        )
    )

    from_base = safe_float(
        record.get(
            "distance_from_compression_base_pct"
        )
    )

    above_trigger = safe_float(
        record.get(
            "distance_above_breakout_trigger_pct"
        )
    )

    above_average = safe_float(
        record.get(
            "distance_from_7d_average_pct"
        )
    )

    stoch_1h = safe_float(
        record.get(
            "timeframes",
            {},
        ).get(
            "1H",
            {},
        ).get(
            "indicators",
            {},
        ).get(
            "stoch_rsi"
        )
    )

    stoch_4h = safe_float(
        record.get(
            "timeframes",
            {},
        ).get(
            "4H",
            {},
        ).get(
            "indicators",
            {},
        ).get(
            "stoch_rsi"
        )
    )

    one_hour = (
        record.get(
            "timeframes",
            {},
        ).get(
            "1H",
            {},
        )
    )

    bb_upper = (
        one_hour.get(
            "indicators",
            {},
        ).get(
            "bollinger",
            {},
        ).get(
            "upper"
        )
    )

    volume_ratio = safe_float(
        one_hour.get(
            "indicators",
            {},
        ).get(
            "volume_anomaly",
            {},
        ).get(
            "ratio"
        )
    )

    price = record.get(
        "last_price"
    )

    if (
        abs(
            change_24h
        )
        > float(
            universe.get(
                "maximum_24h_extension_pct",
                25,
            )
        )
    ):
        reasons.append(
            "24H_EXTENSION"
        )

    if (
        abs(
            change_3d
        )
        > float(
            universe.get(
                "maximum_3d_extension_pct",
                40,
            )
        )
    ):
        reasons.append(
            "3D_EXTENSION"
        )

    if (
        from_base
        > float(
            universe.get(
                "maximum_from_compression_base_pct",
                30,
            )
        )
    ):
        reasons.append(
            "TOO_FAR_FROM_COMPRESSION_BASE"
        )

    if (
        above_trigger
        > float(
            universe.get(
                "maximum_above_breakout_trigger_pct",
                20,
            )
        )
    ):
        reasons.append(
            "TOO_FAR_ABOVE_BREAKOUT"
        )

    if (
        above_average
        > float(
            universe.get(
                "maximum_above_7d_average_pct",
                50,
            )
        )
    ):
        reasons.append(
            "TOO_FAR_ABOVE_7D_AVERAGE"
        )

    stoch_limits = quality.get(
        "stoch_rsi_limits",
        {},
    )

    if (
        stoch_1h
        > float(
            stoch_limits.get(
                "1H",
                90,
            )
        )
        and stoch_4h
        > float(
            stoch_limits.get(
                "4H",
                85,
            )
        )
    ):
        reasons.append(
            "STOCH_RSI_OVEREXTENDED"
        )

    bb_tolerance = float(
        quality.get(
            "bollinger_upper_band_tolerance_pct",
            2,
        )
    )

    if (
        price
        and bb_upper
        and price
        > (
            bb_upper
            * (
                1
                + (
                    bb_tolerance
                    / 100
                )
            )
        )
    ):
        reasons.append(
            "ABOVE_UPPER_BOLLINGER"
        )

    max_volume_ratio = float(
        quality.get(
            "maximum_post_expansion_volume_ratio",
            4,
        )
    )

    if (
        volume_ratio
        > max_volume_ratio
        and abs(
            change_24h
        )
        >= 10
    ):
        reasons.append(
            "POST_EXPANSION_VOLUME"
        )

    allowed_phases = set(
        quality.get(
            "allowed_phases",
            [],
        )
    )

    if phase not in allowed_phases:
        reasons.append(
            f"PHASE_{phase}"
        )

    minimum_integrity = float(
        quality.get(
            "minimum_data_integrity",
            88,
        )
    )

    integrity = safe_float(
        record.get(
            "data_integrity_score"
        )
    )

    if (
        integrity
        < minimum_integrity
    ):
        reasons.append(
            "DATA_INTEGRITY"
        )

    discovery_score = safe_float(
        record.get(
            "behaviour_score"
        )
    )

    minimum_discovery = float(
        quality.get(
            "minimum_discovery_score",
            5,
        )
    )

    discovery_permission = (
        len(reasons) == 0
        and discovery_score
        >= minimum_discovery
    )

    record[
        "candidate_quality_status"
    ] = (
        "PASS"
        if discovery_permission
        else "REJECT"
    )

    record[
        "rejection_reasons"
    ] = reasons

    record[
        "discovery_permission"
    ] = discovery_permission

    notify_timing = set(
        quality.get(
            "notify_timing",
            [
                "EARLY"
            ],
        )
    )

    record[
        "notification_permission"
    ] = bool(
        discovery_permission
        and timing
        in notify_timing
    )

    minimum_execution_score = float(
        quality.get(
            "minimum_execution_score",
            7.5,
        )
    )

    execution_rr = (
        record.get(
            "execution_setup",
            {},
        ).get(
            "rr"
        )
    )

    minimum_execution_rr = float(
        quality.get(
            "minimum_execution_reward_risk",
            5,
        )
    )

    record[
        "v7_trade_ready"
    ] = bool(
        record.get(
            "trade_permission"
        )
        and discovery_score
        >= minimum_execution_score
        and execution_rr
        is not None
        and execution_rr
        >= minimum_execution_rr
        and phase
        in {
            "RECOVERY",
            "IGNITION",
        }
        and timing
        == "EARLY"
    )


    record["decision_trace"] = build_decision_trace(
        record,
        previous,
        config,
    )



# =========================================================
# STATE HISTORY
# =========================================================

def append_state_history(
    snapshot: dict[str, Any],
    config_path: Path,
    config: dict[str, Any],
) -> Path:

    history_path = (
        config_path.parent
        / config.get(
            "state_history_file",
            "data/state-history.jsonl",
        )
    )

    history_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with history_path.open(
        "a",
        encoding="utf-8",
    ) as handle:

        for item in snapshot.get(
            "symbols",
            [],
        ):

            if "error" in item:
                continue

            event = {
                "collected_at_utc":
                    snapshot[
                        "collected_at_utc"
                    ],

                "symbol":
                    item.get(
                        "symbol"
                    ),

                "previous_state":
                    item.get(
                        "previous_state"
                    ),

                "state":
                    item.get(
                        "state"
                    ),

                "state_changed":
                    item.get(
                        "state_changed",
                        False,
                    ),

                "market_phase":
                    item.get(
                        "market_phase"
                    ),

                "opportunity_timing":
                    item.get(
                        "opportunity_timing"
                    ),

                "behaviour_score":
                    item.get(
                        "behaviour_score"
                    ),

                "candidate_quality_status":
                    item.get(
                        "candidate_quality_status"
                    ),

                "rejection_reasons":
                    item.get(
                        "rejection_reasons",
                        [],
                    ),

                "discovery_permission":
                    item.get(
                        "discovery_permission",
                        False,
                    ),

                "notification_permission":
                    item.get(
                        "notification_permission",
                        False,
                    ),

                "trade_permission":
                    item.get(
                        "trade_permission",
                        False,
                    ),

                "v7_trade_ready":
                    item.get(
                        "v7_trade_ready",
                        False,
                    ),

                "rr":
                    item.get(
                        "execution_setup",
                        {},
                    ).get(
                        "rr"
                    ),

                "price":
                    item.get(
                        "last_price"
                    ),

                "data_integrity_score":
                    item.get(
                        "data_integrity_score"
                    ),
            }

            handle.write(
                json.dumps(
                    event
                )
                + "\n"
            )

    return history_path


# =========================================================
# SNAPSHOT STORAGE
# =========================================================

def save_snapshot(
    snapshot: dict[str, Any],
    config_path: Path,
    config: dict[str, Any],
) -> Path:

    root = config_path.parent

    output_dir = (
        root
        / config[
            "snapshot_directory"
        ]
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    path = (
        output_dir
        / f"snapshot-{stamp}.json"
    )

    payload = json.dumps(
        snapshot,
        indent=2,
    )

    path.write_text(
        payload,
        encoding="utf-8",
    )

    (
        output_dir
        / "latest.json"
    ).write_text(
        payload,
        encoding="utf-8",
    )

    return path


# =========================================================
# TERMINAL REPORT
# =========================================================

def print_report(
    snapshot: dict[str, Any],
) -> None:

    print(
        "\n"
        "ALPHA HUNTER V7.1"
        " — "
        f"{snapshot['collected_at_utc']}"
        "\n"
    )

    universe = snapshot.get(
        "universe",
        {},
    )

    print(
        "Universe: "
        f"{universe.get('selected_count', 0)} "
        "deep-scanned of "
        f"{universe.get('total_contracts', 0)} "
        "contracts"
    )

    print(
        "Eligible after prefilter: "
        f"{universe.get('eligible_count', 0)}"
    )

    print(
        "Non-crypto rejected: "
        f"{universe.get('rejected_non_crypto', 0)}"
    )

    print()

    header = (
        f"{'SYMBOL':<14} "
        f"{'PHASE':>14} "
        f"{'TIME':>7} "
        f"{'BEHAV':>7} "
        f"{'STATE':>25} "
        f"{'RR':>7} "
        f"{'DISC':>6} "
        f"{'TRADE':>6}"
    )

    print(header)

    print(
        "-" * len(header)
    )

    for item in snapshot[
        "symbols"
    ]:

        if "error" in item:

            print(
                f"{item['symbol']:<14} "
                f"ERROR: {item['error']}"
            )

            continue

        rr = (
            item.get(
                "execution_setup",
                {},
            ).get(
                "rr"
            )
        )

        rr_text = (
            f"{rr:.2f}"
            if rr is not None
            else "—"
        )

        print(
            f"{item['symbol']:<14} "
            f"{item.get('market_phase', '—'):>14} "
            f"{item.get('opportunity_timing', '—'):>7} "
            f"{safe_float(item.get('behaviour_score')):>7.2f} "
            f"{item.get('state', '—'):>25} "
            f"{rr_text:>7} "
            f"{('YES' if item.get('discovery_permission') else 'NO'):>6} "
            f"{('YES' if item.get('v7_trade_ready') else 'NO'):>6}"
        )

    print()


# =========================================================
# MAIN
# =========================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Alpha Hunter V7.1 "
            "full-market behaviour scan"
        )
    )

    parser.add_argument(
        "--config",
        default="config.json",
    )

    args = parser.parse_args()

    config_path = Path(
        args.config
    ).resolve()

    load_env_file(
        config_path.parent
        / ".env"
    )

    config = load_config(
        config_path
    )

    client = (
        BitgetClient
        .from_environment(
            timeout=config.get(
                "request_timeout_seconds",
                12,
            ),
            max_retries=config.get(
                "max_retries",
                3,
            ),
        )
    )

    previous_snapshot = (
        load_previous_snapshot(
            config_path,
            config,
        )
    )

    contracts = (
        client.contracts(
            config[
                "product_type"
            ]
        )
        or []
    )

    tickers = (
        client.tickers(
            config[
                "product_type"
            ]
        )
        or []
    )

    try:

        instruments = (
            client.instruments(
                config[
                    "product_type"
                ]
            )
            or []
        )

    except BitgetAPIError:

        instruments = []

    ticker_by_symbol = {
        str(
            row.get(
                "symbol",
                "",
            )
        ).upper():
            row
        for row in tickers
    }

    btc_ticker = (
        ticker_by_symbol.get(
            "BTCUSDT",
            {},
        )
    )

    btc_change_24h = (
        (
            to_float(
                btc_ticker.get(
                    "change24h"
                )
            )
            or 0.0
        )
        * 100
    )

    (
        selected_symbols,
        universe,
    ) = select_market_universe(
        contracts,
        instruments,
        tickers,
        previous_snapshot,
        config,
    )

    available = {
        str(
            row.get(
                "symbol"
            )
        ).upper():
            row
        for row in contracts
        if row.get(
            "symbol"
        )
    }

    previous_by_symbol: dict[
        str,
        dict[str, Any],
    ] = {}

    if previous_snapshot:

        previous_by_symbol = {
            str(
                item.get(
                    "symbol",
                    ""
                )
            ):
                item
            for item
            in previous_snapshot.get(
                "symbols",
                [],
            )
        }

    results: list[
        dict[str, Any]
    ] = []

    for symbol in selected_symbols:

        if symbol not in available:

            results.append({
                "symbol":
                    symbol,

                "error":
                    (
                        "Symbol is not listed "
                        "in Bitget USDT futures"
                    ),
            })

            continue

        try:

            results.append(
                collect_symbol(
                    client,
                    symbol,
                    config,
                )
            )

        except BitgetAPIError as exc:

            results.append({
                "symbol":
                    symbol,

                "error":
                    str(exc),
            })

    apply_snapshot_comparisons(
        results,
        previous_snapshot,
        config.get(
            "minimum_reward_risk",
            5.0,
        ),
    )

    for item in results:

        if "error" in item:
            continue

        previous = (
            previous_by_symbol.get(
                item[
                    "symbol"
                ]
            )
        )

        apply_candidate_quality(
            item,
            previous,
            btc_change_24h,
            config,
        )

    pre_move_summary = apply_pre_move_engine(
        results,
        config,
    )

    results.sort(
        key=lambda item:
            (
                safe_float(
                    item.get(
                        "behaviour_score"
                    )
                ),
                safe_intelligence_score(
                    item
                ),
            ),
        reverse=True,
    )

    private_account = (
        collect_private_account_snapshot(
            client,
            config[
                "product_type"
            ],
            config.get(
                "margin_coin",
                "USDT",
            ),
        )
    )

    discovery_candidates = [
        item
        for item in results
        if item.get(
            "discovery_permission"
        )
    ]

    early_candidates = [
        item
        for item
        in discovery_candidates
        if item.get(
            "opportunity_timing"
        )
        == "EARLY"
    ]

    trade_ready = [
        item
        for item in results
        if item.get(
            "v7_trade_ready"
        )
    ]

    snapshot = {
        "version":
            "0.7.1",

        "collected_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "product_type":
            config[
                "product_type"
            ],

        "btc_change_24h_pct":
            btc_change_24h,

        "universe":
            universe,

        "pre_move_summary":
            pre_move_summary,

        "discovery_summary": {
            "qualified_count":
                len(
                    discovery_candidates
                ),

            "early_count":
                len(
                    early_candidates
                ),

            "trade_ready_count":
                len(
                    trade_ready
                ),
        },

        "symbols":
            results,

        "private_account":
            private_account,
    }

    snapshot[
        "run_id"
    ] = build_run_id(
        snapshot
    )

    path = save_snapshot(
        snapshot,
        config_path,
        config,
    )

    history_path = (
        append_state_history(
            snapshot,
            config_path,
            config,
        )
    )

    cloud_status = "DISABLED"

    supabase_settings = (
        SupabaseConfig
        .from_environment(
            config
        )
    )

    if (
        config.get(
            "supabase",
            {},
        ).get(
            "enabled",
            False,
        )
    ):

        if supabase_settings is None:

            cloud_status = (
                "NOT_CONFIGURED"
            )

        else:

            try:

                SupabaseStorage(
                    supabase_settings
                ).save_snapshot(
                    snapshot
                )

                cloud_status = "SAVED"

            except (
                SupabaseStorageError
            ) as exc:

                cloud_status = (
                    f"FAILED: {exc}"
                )

    print_report(
        snapshot
    )

    print(
        "Run ID: "
        f"{snapshot['run_id']}"
    )

    print(
        "Snapshot saved: "
        f"{path}"
    )

    print(
        "State history: "
        f"{history_path}"
    )

    print(
        "Supabase: "
        f"{cloud_status}"
    )

    print(
        "Qualified discovery candidates: "
        f"{len(discovery_candidates)}"
    )

    print(
        "EARLY candidates: "
        f"{len(early_candidates)}"
    )

    print(
        "V7 Trade Ready: "
        f"{len(trade_ready)}"
    )

    private_status = (
        snapshot.get(
            "private_account",
            {},
        ).get(
            "status",
            "UNKNOWN",
        )
    )

    print(
        "Bitget private API: "
        f"{private_status}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
