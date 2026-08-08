from __future__ import annotations

from typing import Any


PRE_MOVE_VERSION = "7.4"


def _f(
    value: Any,
    default: float | None = None,
) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _tf(
    record: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    value = (
        record
        .get("timeframes", {})
        .get(timeframe, {})
    )

    return value if isinstance(value, dict) else {}


def _ind(
    record: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:
    value = _tf(
        record,
        timeframe,
    ).get(
        "indicators",
        {},
    )

    return value if isinstance(value, dict) else {}


def _behaviour(
    record: dict[str, Any],
) -> dict[str, Any]:
    value = record.get(
        "behaviour",
        {},
    )

    return value if isinstance(value, dict) else {}


def _ema_alignment(
    indicators: dict[str, Any],
) -> str | None:
    ema9 = _f(
        indicators.get("ema_9")
    )

    ema21 = _f(
        indicators.get("ema_21")
    )

    ema50 = _f(
        indicators.get("ema_50")
    )

    if (
        ema9 is None
        or ema21 is None
        or ema50 is None
    ):
        return None

    if ema9 > ema21 > ema50:
        return "BULLISH"

    if ema9 < ema21 < ema50:
        return "BEARISH"

    return "MIXED"


def _distance_to_resistance_pct(
    record: dict[str, Any],
) -> float | None:
    price = _f(
        record.get("last_price")
    )

    resistance = _f(
        record.get("resistance")
    )

    if (
        price in (None, 0)
        or resistance is None
    ):
        return None

    return (
        (resistance - price)
        / price
        * 100
    )


def _distance_to_support_pct(
    record: dict[str, Any],
) -> float | None:
    price = _f(
        record.get("last_price")
    )

    support = _f(
        record.get("support")
    )

    if (
        price is None
        or support in (None, 0)
    ):
        return None

    return (
        (price - support)
        / support
        * 100
    )


def _liquidity_state(
    record: dict[str, Any],
) -> str | None:
    behaviour = _behaviour(record)

    spread = _f(
        behaviour.get("spread_pct")
    )

    if spread is None:
        bid = _f(
            record.get("bid_price")
        )

        ask = _f(
            record.get("ask_price")
        )

        price = _f(
            record.get("last_price")
        )

        if (
            bid is not None
            and ask is not None
            and price not in (None, 0)
        ):
            spread = (
                (ask - bid)
                / price
                * 100
            )

    if spread is None:
        return None

    if spread <= 0.05:
        return "HIGH"

    if spread <= 0.10:
        return "GOOD"

    if spread <= 0.25:
        return "FAIR"

    return "POOR"


def _feature_context(
    record: dict[str, Any],
) -> dict[str, Any]:
    tf15 = _tf(
        record,
        "15m",
    )

    tf1 = _tf(
        record,
        "1H",
    )

    tf4 = _tf(
        record,
        "4H",
    )

    ind15 = _ind(
        record,
        "15m",
    )

    ind1 = _ind(
        record,
        "1H",
    )

    ind4 = _ind(
        record,
        "4H",
    )

    behaviour = _behaviour(
        record
    )

    compression = (
        tf1.get(
            "compression",
            {},
        )
    )

    if not isinstance(
        compression,
        dict,
    ):
        compression = {}

    relative_strength = _f(
        behaviour.get(
            "relative_strength_vs_btc_pct"
        )
    )

    volatility = _f(
        behaviour.get(
            "atr_pct"
        )
    )

    if volatility is None:
        volatility = _f(
            ind1.get(
                "atr_pct"
            )
        )

    return {
        "trend_15m":
            tf15.get("trend"),

        "trend_1h":
            tf1.get("trend"),

        "trend_4h":
            tf4.get("trend"),

        "ema_15m":
            _ema_alignment(ind15),

        "ema_1h":
            _ema_alignment(ind1),

        "ema_4h":
            _ema_alignment(ind4),

        "rsi_15m":
            _f(
                ind15.get("rsi_14")
            ),

        "rsi_1h":
            _f(
                ind1.get("rsi_14")
            ),

        "rsi_4h":
            _f(
                ind4.get("rsi_14")
            ),

        "compression_score":
            _f(
                compression.get("score")
            ),

        "relative_strength_btc":
            relative_strength,

        "volatility_pct":
            volatility,

        "distance_to_resistance_pct":
            _distance_to_resistance_pct(
                record
            ),

        "distance_to_support_pct":
            _distance_to_support_pct(
                record
            ),

        "liquidity_state":
            _liquidity_state(
                record
            ),
    }


def _continuation(
    features: dict[str, Any],
) -> dict[str, Any]:
    compression = _f(
        features.get(
            "compression_score"
        )
    )

    rs = _f(
        features.get(
            "relative_strength_btc"
        )
    )

    rsi1 = _f(
        features.get(
            "rsi_1h"
        )
    )

    rsi4 = _f(
        features.get(
            "rsi_4h"
        )
    )

    dist_r = _f(
        features.get(
            "distance_to_resistance_pct"
        )
    )

    volatility = _f(
        features.get(
            "volatility_pct"
        )
    )

    ema1 = features.get(
        "ema_1h"
    )

    ema4 = features.get(
        "ema_4h"
    )

    liquidity = features.get(
        "liquidity_state"
    )

    hard_gate = bool(
        compression is not None
        and compression >= 7
        and ema1 == "BULLISH"
        and ema4 == "BULLISH"
        and rsi4 is not None
        and 55 <= rsi4 <= 78
        and liquidity
        in {
            "HIGH",
            "GOOD",
            "FAIR",
        }
    )

    if not hard_gate:
        return {
            "eligible": False,
            "score": 0.0,
            "confirmations": 0,
            "reasons": [],
        }

    confirmations = 0

    reasons = [
        "COMP>=7",
        "EMA1_BULL",
        "EMA4_BULL",
        "RSI4_OK",
    ]

    if (
        rs is not None
        and rs >= 0.5
    ):
        confirmations += 1
        reasons.append(
            "RS_STRONG"
        )

    if (
        volatility is not None
        and volatility >= 0.5
    ):
        confirmations += 1
        reasons.append(
            "VOL_CAPACITY"
        )

    if (
        dist_r is not None
        and dist_r <= 20
    ):
        confirmations += 1
        reasons.append(
            "NEAR_RESISTANCE"
        )

    if (
        rsi1 is not None
        and 45 <= rsi1 <= 68
    ):
        confirmations += 1
        reasons.append(
            "RSI1_OK"
        )

    eligible = (
        confirmations >= 2
    )

    score = (
        6.0
        + confirmations
        + min(
            (compression or 0)
            / 10,
            1,
        )
        + min(
            max(
                rs or 0,
                0,
            )
            / 10,
            1,
        )
    )

    return {
        "eligible":
            eligible,

        "score":
            round(
                score,
                2,
            )
            if eligible
            else 0.0,

        "confirmations":
            confirmations,

        "reasons":
            reasons,
    }


def _reversal(
    features: dict[str, Any],
) -> dict[str, Any]:
    compression = _f(
        features.get(
            "compression_score"
        )
    )

    rs = _f(
        features.get(
            "relative_strength_btc"
        )
    )

    rsi15 = _f(
        features.get(
            "rsi_15m"
        )
    )

    rsi1 = _f(
        features.get(
            "rsi_1h"
        )
    )

    rsi4 = _f(
        features.get(
            "rsi_4h"
        )
    )

    dist_r = _f(
        features.get(
            "distance_to_resistance_pct"
        )
    )

    volatility = _f(
        features.get(
            "volatility_pct"
        )
    )

    trend15 = features.get(
        "trend_15m"
    )

    trend1 = features.get(
        "trend_1h"
    )

    ema1 = features.get(
        "ema_1h"
    )

    ema4 = features.get(
        "ema_4h"
    )

    liquidity = features.get(
        "liquidity_state"
    )

    hard_gate = bool(
        ema4 == "BULLISH"
        and trend1
        in {
            "BEARISH",
            "NEUTRAL",
        }
        and rsi1 is not None
        and 35 <= rsi1 <= 55
        and rsi4 is not None
        and 45 <= rsi4 <= 75
        and liquidity
        in {
            "HIGH",
            "GOOD",
            "FAIR",
        }
    )

    if not hard_gate:
        return {
            "eligible": False,
            "score": 0.0,
            "confirmations": 0,
            "reasons": [],
        }

    confirmations = 0

    reasons = [
        "EMA4_BULL",
        "1H_WEAK",
        "RSI1_RESET",
        "RSI4_OK",
    ]

    if (
        rs is not None
        and rs <= -5
    ):
        confirmations += 1
        reasons.append(
            "NEG_RS_EXTREME"
        )

    if (
        dist_r is not None
        and dist_r >= 25
    ):
        confirmations += 1
        reasons.append(
            "ROOM"
        )

    if (
        compression is not None
        and compression >= 3
    ):
        confirmations += 1
        reasons.append(
            "COMPRESSION"
        )

    if (
        trend15
        in {
            "BULLISH",
            "NEUTRAL",
        }
        or (
            rsi15 is not None
            and 45 <= rsi15 <= 60
        )
    ):
        confirmations += 1
        reasons.append(
            "STABILIZING_15M"
        )

    if (
        volatility is not None
        and volatility >= 0.5
    ):
        confirmations += 1
        reasons.append(
            "VOL_CAPACITY"
        )

    if (
        ema1
        in {
            "MIXED",
            "BEARISH",
        }
    ):
        confirmations += 1
        reasons.append(
            "EMA1_RESET"
        )

    eligible = (
        confirmations >= 3
    )

    score = (
        6.0
        + confirmations
        + min(
            abs(
                rs or 0
            )
            / 15,
            1,
        )
        + min(
            (compression or 0)
            / 10,
            1,
        )
    )

    return {
        "eligible":
            eligible,

        "score":
            round(
                score,
                2,
            )
            if eligible
            else 0.0,

        "confirmations":
            confirmations,

        "reasons":
            reasons,
    }


def evaluate_pre_move(
    record: dict[str, Any],
) -> dict[str, Any]:
    features = _feature_context(
        record
    )

    continuation = _continuation(
        features
    )

    reversal = _reversal(
        features
    )

    if (
        continuation[
            "eligible"
        ]
        and reversal[
            "eligible"
        ]
    ):
        if (
            continuation[
                "score"
            ]
            >= reversal[
                "score"
            ]
        ):
            path = "CONTINUATION"
            chosen = continuation
        else:
            path = "REVERSAL"
            chosen = reversal

    elif continuation[
        "eligible"
    ]:
        path = "CONTINUATION"
        chosen = continuation

    elif reversal[
        "eligible"
    ]:
        path = "REVERSAL"
        chosen = reversal

    else:
        path = None
        chosen = {
            "score": 0.0,
            "confirmations": 0,
            "reasons": [],
        }

    state = (
        f"PRE_IGNITION_{path}"
        if path
        else None
    )

    return {
        "version":
            PRE_MOVE_VERSION,

        "eligible":
            bool(path),

        "path":
            path,

        "state":
            state,

        "score":
            chosen[
                "score"
            ],

        "confirmations":
            chosen[
                "confirmations"
            ],

        "reasons":
            chosen[
                "reasons"
            ],

        "features":
            features,

        "continuation":
            continuation,

        "reversal":
            reversal,

        # Explicit safety contract.
        "trade_permission":
            False,
    }


def apply_pre_move_engine(
    records: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    settings = config.get(
        "pre_move_engine",
        {},
    )

    enabled = bool(
        settings.get(
            "enabled",
            True,
        )
    )

    primary_limit = int(
        settings.get(
            "primary_limit",
            5,
        )
    )

    reserve_limit = int(
        settings.get(
            "reserve_limit",
            5,
        )
    )

    eligible: list[
        dict[str, Any]
    ] = []

    for record in records:
        if (
            not isinstance(
                record,
                dict,
            )
            or "error"
            in record
        ):
            continue

        if enabled:
            result = (
                evaluate_pre_move(
                    record
                )
            )
        else:
            result = {
                "version":
                    PRE_MOVE_VERSION,
                "eligible":
                    False,
                "path":
                    None,
                "state":
                    None,
                "score":
                    0.0,
                "confirmations":
                    0,
                "reasons":
                    [],
                "features":
                    {},
                "continuation":
                    {},
                "reversal":
                    {},
                "trade_permission":
                    False,
            }

        record[
            "pre_move"
        ] = result

        record[
            "pre_move_state"
        ] = result[
            "state"
        ]

        record[
            "pre_move_path"
        ] = result[
            "path"
        ]

        record[
            "pre_move_score"
        ] = result[
            "score"
        ]

        record[
            "pre_move_permission"
        ] = False

        record[
            "pre_move_rank"
        ] = None

        record[
            "pre_move_tier"
        ] = None

        if result[
            "eligible"
        ]:
            eligible.append(
                record
            )

    eligible.sort(
        key=lambda row: (
            float(
                row.get(
                    "pre_move_score"
                )
                or 0
            ),
            float(
                row.get(
                    "behaviour_score"
                )
                or 0
            ),
        ),
        reverse=True,
    )

    primary = eligible[
        :primary_limit
    ]

    reserve = eligible[
        primary_limit:
        primary_limit
        + reserve_limit
    ]

    for index, row in enumerate(
        eligible,
        1,
    ):
        row[
            "pre_move_rank"
        ] = index

    for row in primary:
        row[
            "pre_move_tier"
        ] = "PRIMARY"

    for row in reserve:
        row[
            "pre_move_tier"
        ] = "RESERVE"

    return {
        "version":
            PRE_MOVE_VERSION,

        "enabled":
            enabled,

        "eligible_count":
            len(
                eligible
            ),

        "primary_count":
            len(
                primary
            ),

        "reserve_count":
            len(
                reserve
            ),

        "primary_symbols":
            [
                row.get(
                    "symbol"
                )
                for row in primary
            ],

        "reserve_symbols":
            [
                row.get(
                    "symbol"
                )
                for row in reserve
            ],
    }
