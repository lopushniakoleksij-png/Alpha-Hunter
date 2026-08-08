from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests


# =========================================================
# BASIC HELPERS
# =========================================================

def _float(
    value: Any,
) -> float | None:
    try:
        if value in (
            None,
            "",
            "N/A",
            "—",
        ):
            return None

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _bool(
    value: Any,
) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = (
            value
            .strip()
            .lower()
        )

        if normalized in {
            "true",
            "yes",
            "1",
            "expanded",
            "expanding",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "contracting",
            "not_expanding",
        }:
            return False

    return None


def _signal_id(
    run_id: str,
    symbol: str,
) -> str:
    raw = (
        f"{run_id}|{symbol}"
        .encode("utf-8")
    )

    return (
        hashlib
        .sha256(raw)
        .hexdigest()[:32]
    )


def _session(
    hour: int,
) -> str:
    if hour < 7:
        return "ASIA"

    if hour < 13:
        return "LONDON"

    if hour < 21:
        return "NEW_YORK"

    return "LATE_US"


# =========================================================
# BACKWARD-COMPATIBLE FLATTENING
# =========================================================

def _walk(
    obj: Any,
    prefix: str = "",
) -> dict[str, Any]:

    flat: dict[str, Any] = {}

    if isinstance(obj, dict):

        for key, value in obj.items():

            path = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )

            flat[
                path.lower()
            ] = value

            flat.update(
                _walk(
                    value,
                    path,
                )
            )

    elif isinstance(obj, list):

        for index, value in enumerate(
            obj[:20]
        ):

            path = (
                f"{prefix}.{index}"
                if prefix
                else str(index)
            )

            flat.update(
                _walk(
                    value,
                    path,
                )
            )

    return flat


def _pick(
    flat: dict[str, Any],
    *names: str,
) -> Any:

    normalized_names = tuple(
        name.lower()
        for name in names
    )

    for name in normalized_names:

        if name in flat:
            return flat[name]

    for path, value in flat.items():

        final_name = (
            path
            .rsplit(".", 1)[-1]
        )

        if final_name in normalized_names:
            return value

    for name in normalized_names:

        for path, value in flat.items():

            if (
                path.endswith(name)
                or name in path
            ):
                return value

    return None


def _text(
    value: Any,
) -> str | None:

    if value in (
        None,
        "",
    ):
        return None

    return str(
        value
    ).upper()


# =========================================================
# DIRECT V7 PAYLOAD HELPERS
# =========================================================

def _timeframe(
    item: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:

    timeframes = item.get(
        "timeframes",
        {},
    )

    if not isinstance(
        timeframes,
        dict,
    ):
        return {}

    value = timeframes.get(
        timeframe,
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def _indicators(
    item: dict[str, Any],
    timeframe: str,
) -> dict[str, Any]:

    tf = _timeframe(
        item,
        timeframe,
    )

    indicators = tf.get(
        "indicators",
        {},
    )

    return (
        indicators
        if isinstance(
            indicators,
            dict,
        )
        else {}
    )


def _behaviour(
    item: dict[str, Any],
) -> dict[str, Any]:

    value = item.get(
        "behaviour",
        {},
    )

    return (
        value
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def _ema_alignment(
    indicators: dict[str, Any],
) -> str | None:

    ema_9 = _float(
        indicators.get(
            "ema_9"
        )
    )

    ema_21 = _float(
        indicators.get(
            "ema_21"
        )
    )

    ema_50 = _float(
        indicators.get(
            "ema_50"
        )
    )

    if (
        ema_9 is None
        or ema_21 is None
        or ema_50 is None
    ):
        return None

    if (
        ema_9
        > ema_21
        > ema_50
    ):
        return "BULLISH"

    if (
        ema_9
        < ema_21
        < ema_50
    ):
        return "BEARISH"

    return "MIXED"


def _distance_pct(
    price: Any,
    level: Any,
) -> float | None:

    current = _float(
        price
    )

    reference = _float(
        level
    )

    if (
        current is None
        or reference in (
            None,
            0,
        )
    ):
        return None

    return (
        (
            current
            - reference
        )
        / reference
        * 100
    )


def _liquidity_state(
    item: dict[str, Any],
) -> str | None:

    behaviour = _behaviour(
        item
    )

    spread = _float(
        behaviour.get(
            "spread_pct"
        )
    )

    if spread is None:

        bid = _float(
            item.get(
                "bid_price"
            )
        )

        ask = _float(
            item.get(
                "ask_price"
            )
        )

        price = _float(
            item.get(
                "last_price"
            )
        )

        if (
            bid is not None
            and ask is not None
            and price not in (
                None,
                0,
            )
        ):
            spread = (
                (
                    ask
                    - bid
                )
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


def _volume_ratio(
    item: dict[str, Any],
) -> float | None:

    behaviour = _behaviour(
        item
    )

    direct = _float(
        behaviour.get(
            "volume_ratio"
        )
    )

    if direct is not None:
        return direct

    one_hour = _indicators(
        item,
        "1H",
    )

    anomaly = one_hour.get(
        "volume_anomaly",
        {},
    )

    if isinstance(
        anomaly,
        dict,
    ):
        return _float(
            anomaly.get(
                "ratio"
            )
        )

    return None


def _compression_score(
    item: dict[str, Any],
) -> float | None:

    one_hour = _timeframe(
        item,
        "1H",
    )

    compression = one_hour.get(
        "compression",
        {},
    )

    if isinstance(
        compression,
        dict,
    ):
        return _float(
            compression.get(
                "score"
            )
        )

    return None


def _volatility_pct(
    item: dict[str, Any],
) -> float | None:

    behaviour = _behaviour(
        item
    )

    value = _float(
        behaviour.get(
            "atr_pct"
        )
    )

    if value is not None:
        return value

    return _float(
        _indicators(
            item,
            "1H",
        ).get(
            "atr_pct"
        )
    )


def _relative_strength_btc(
    item: dict[str, Any],
) -> float | None:

    behaviour = _behaviour(
        item
    )

    value = _float(
        behaviour.get(
            "relative_strength_vs_btc_pct"
        )
    )

    if value is not None:
        return value

    symbol_change = _float(
        item.get(
            "change_24h_pct"
        )
    )

    btc_change = _float(
        item.get(
            "btc_change_24h_pct"
        )
    )

    if (
        symbol_change is None
        or btc_change is None
    ):
        return None

    return (
        symbol_change
        - btc_change
    )


def _oi_change_pct(
    item: dict[str, Any],
) -> float | None:

    direct = _float(
        item.get(
            "open_interest_change_pct"
        )
    )

    if direct is not None:
        return direct

    behaviour = _behaviour(
        item
    )

    return _float(
        behaviour.get(
            "oi_change_pct"
        )
    )


def _btc_regime(
    snapshot: dict[str, Any],
    item: dict[str, Any],
) -> str | None:

    direct = (
        item.get(
            "btc_regime"
        )
        or item.get(
            "market_regime"
        )
        or snapshot.get(
            "btc_regime"
        )
        or snapshot.get(
            "market_regime"
        )
    )

    if direct not in (
        None,
        "",
    ):
        return _text(
            direct
        )

    btc_change = _float(
        snapshot.get(
            "btc_change_24h_pct"
        )
    )

    if btc_change is None:
        return None

    # This is intentionally a descriptive
    # fallback, not a replacement for a
    # dedicated BTC Regime Engine.
    if btc_change >= 3:
        return "BTC_STRONG_UP"

    if btc_change >= 0.75:
        return "BTC_UP"

    if btc_change <= -3:
        return "BTC_STRONG_DOWN"

    if btc_change <= -0.75:
        return "BTC_DOWN"

    return "BTC_NEUTRAL"


# =========================================================
# FEATURE EXTRACTION
# =========================================================

def extract_feature_rows(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:

    run_id = str(
        snapshot.get(
            "run_id"
        )
        or ""
    )

    captured_at = (
        snapshot.get(
            "collected_at_utc"
        )
        or datetime.now(
            timezone.utc
        ).isoformat()
    )

    dt = datetime.fromisoformat(
        str(
            captured_at
        ).replace(
            "Z",
            "+00:00",
        )
    )

    rows: list[
        dict[str, Any]
    ] = []

    for item in snapshot.get(
        "symbols",
        [],
    ):

        if not isinstance(
            item,
            dict,
        ):
            continue

        if item.get(
            "error"
        ):
            continue

        symbol = str(
            item.get(
                "symbol"
            )
            or ""
        )

        if not symbol:
            continue

        # Keep flattened fallback support
        # for historical signal payloads.
        flat = _walk(
            item
        )

        setup = item.get(
            "execution_setup",
            {},
        )

        if not isinstance(
            setup,
            dict,
        ):
            setup = {}

        intel = item.get(
            "intelligence",
            {},
        )

        if not isinstance(
            intel,
            dict,
        ):
            intel = {}

        tf_15m = _timeframe(
            item,
            "15m",
        )

        tf_1h = _timeframe(
            item,
            "1H",
        )

        tf_4h = _timeframe(
            item,
            "4H",
        )

        ind_15m = _indicators(
            item,
            "15m",
        )

        ind_1h = _indicators(
            item,
            "1H",
        )

        ind_4h = _indicators(
            item,
            "4H",
        )

        behaviour = _behaviour(
            item
        )

        volume_ratio = _volume_ratio(
            item
        )

        volume_expansion = _bool(
            item.get(
                "volume_expansion"
            )
        )

        if volume_expansion is None:

            anomaly = ind_1h.get(
                "volume_anomaly",
                {},
            )

            if isinstance(
                anomaly,
                dict,
            ):
                anomaly_state = str(
                    anomaly.get(
                        "state",
                        "",
                    )
                ).upper()

                if anomaly_state in {
                    "HIGH",
                    "ELEVATED",
                }:
                    volume_expansion = True

        if (
            volume_expansion is None
            and volume_ratio is not None
        ):
            volume_expansion = (
                volume_ratio
                >= 1.25
            )

        last_price = _float(
            item.get(
                "last_price"
            )
        )

        support = _float(
            item.get(
                "support"
            )
        )

        resistance = _float(
            item.get(
                "resistance"
            )
        )

        features = {
            "trend_15m":
                _text(
                    tf_15m.get(
                        "trend"
                    )
                )
                or _text(
                    _pick(
                        flat,
                        "trend_15m",
                        "15m_trend",
                    )
                ),

            "trend_1h":
                _text(
                    tf_1h.get(
                        "trend"
                    )
                )
                or _text(
                    _pick(
                        flat,
                        "trend_1h",
                        "1h_trend",
                    )
                ),

            "trend_4h":
                _text(
                    tf_4h.get(
                        "trend"
                    )
                )
                or _text(
                    _pick(
                        flat,
                        "trend_4h",
                        "4h_trend",
                    )
                ),

            "btc_regime":
                _btc_regime(
                    snapshot,
                    item,
                ),

            "sector":
                _text(
                    item.get(
                        "sector"
                    )
                    or item.get(
                        "category"
                    )
                    or item.get(
                        "narrative"
                    )
                    or _pick(
                        flat,
                        "sector",
                        "category",
                        "narrative",
                    )
                ),

            "session":
                _session(
                    dt.hour
                ),

            "weekday":
                dt.weekday(),

            "hour_utc":
                dt.hour,

            "volume_ratio":
                volume_ratio,

            "volume_expansion":
                volume_expansion,

            "volatility_pct":
                _volatility_pct(
                    item
                ),

            "compression_score":
                _compression_score(
                    item
                ),

            "funding_rate":
                _float(
                    item.get(
                        "funding_rate"
                    )
                ),

            "open_interest":
                _float(
                    item.get(
                        "open_interest"
                    )
                ),

            "open_interest_change_pct":
                _oi_change_pct(
                    item
                ),

            "relative_strength_btc":
                _relative_strength_btc(
                    item
                ),

            "rsi_15m":
                _float(
                    ind_15m.get(
                        "rsi_14"
                    )
                ),

            "rsi_1h":
                _float(
                    ind_1h.get(
                        "rsi_14"
                    )
                ),

            "rsi_4h":
                _float(
                    ind_4h.get(
                        "rsi_14"
                    )
                ),

            "distance_to_support_pct":
                _distance_pct(
                    last_price,
                    support,
                ),

            "distance_to_resistance_pct":
                (
                    (
                        resistance
                        - last_price
                    )
                    / last_price
                    * 100
                    if (
                        resistance
                        is not None
                        and last_price
                        not in (
                            None,
                            0,
                        )
                    )
                    else None
                ),

            "ema_alignment_15m":
                _ema_alignment(
                    ind_15m
                ),

            "ema_alignment_1h":
                _ema_alignment(
                    ind_1h
                ),

            "ema_alignment_4h":
                _ema_alignment(
                    ind_4h
                ),

            "liquidity_state":
                _liquidity_state(
                    item
                ),
        }

        # Preserve V7 intelligence fields inside
        # JSON diagnostic payload even when they
        # do not have dedicated SQL columns.
        diagnostic_context = {
            "market_phase":
                item.get(
                    "market_phase"
                ),

            "opportunity_timing":
                item.get(
                    "opportunity_timing"
                ),

            "behaviour_score":
                _float(
                    item.get(
                        "behaviour_score"
                    )
                ),

            "behaviour_components":
                behaviour.get(
                    "components"
                ),

            "relative_strength_acceleration":
                _float(
                    behaviour.get(
                        "relative_strength_acceleration"
                    )
                ),

            "funding_change_pct":
                _float(
                    behaviour.get(
                        "funding_change_pct"
                    )
                ),

            "spread_pct":
                _float(
                    behaviour.get(
                        "spread_pct"
                    )
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
                bool(
                    item.get(
                        "discovery_permission"
                    )
                ),

            "notification_permission":
                bool(
                    item.get(
                        "notification_permission"
                    )
                ),

            "v7_trade_ready":
                bool(
                    item.get(
                        "v7_trade_ready"
                    )
                ),

            "decision_trace":
                item.get(
                    "decision_trace"
                ),
        }

        feature_payload = {
            **features,
            "diagnostic_context":
                diagnostic_context,
        }

        rows.append({
            "signal_id":
                _signal_id(
                    run_id,
                    symbol,
                ),

            "run_id":
                run_id,

            "symbol":
                symbol,

            "captured_at_utc":
                captured_at,

            "state":
                item.get(
                    "state"
                ),

            "direction":
                (
                    setup.get(
                        "direction"
                    )
                    or item.get(
                        "direction"
                    )
                ),

            "trade_permission":
                bool(
                    item.get(
                        "trade_permission"
                    )
                ),

            "huge_rr_score":
                _float(
                    intel.get(
                        "huge_rr_score"
                    )
                ),

            "confidence_estimate_pct":
                _float(
                    intel.get(
                        "confidence_estimate_pct"
                    )
                ),

            "reward_risk":
                _float(
                    setup.get(
                        "rr"
                    )
                ),

            **features,

            "features":
                feature_payload,

            "source_payload":
                item,
        })

    return rows


# =========================================================
# SUPABASE STORAGE
# =========================================================

class FeatureStorage:

    def __init__(
        self,
        url: str,
        key: str,
        timeout: int = 30,
    ) -> None:

        self.url = (
            url.rstrip("/")
        )

        self.key = key
        self.timeout = timeout

    @property
    def headers(
        self,
    ) -> dict[str, str]:

        return {
            "apikey":
                self.key,

            "Authorization":
                f"Bearer {self.key}",

            "Content-Type":
                "application/json",

            "Prefer":
                (
                    "resolution=merge-duplicates,"
                    "return=minimal"
                ),
        }

    def save(
        self,
        snapshot: dict[str, Any],
    ) -> int:

        rows = extract_feature_rows(
            snapshot
        )

        if not rows:
            return 0

        run_id = str(
            snapshot.get(
                "run_id"
            )
            or ""
        )

        lookup_headers = {
            "apikey":
                self.key,

            "Authorization":
                f"Bearer {self.key}",

            "Content-Type":
                "application/json",
        }

        lookup = requests.get(
            (
                f"{self.url}"
                "/rest/v1/"
                "alpha_hunter_signals"
            ),
            params={
                "select":
                    "signal_id,symbol",

                "run_id":
                    f"eq.{run_id}",

                "limit":
                    "1000",
            },
            headers=
                lookup_headers,
            timeout=
                self.timeout,
        )

        lookup.raise_for_status()

        signal_ids = {
            str(
                item[
                    "symbol"
                ]
            ):
                str(
                    item[
                        "signal_id"
                    ]
                )
            for item
            in lookup.json()
        }

        matched_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:

            real_signal_id = (
                signal_ids.get(
                    str(
                        row[
                            "symbol"
                        ]
                    )
                )
            )

            if not real_signal_id:

                print(
                    "Skipping feature row "
                    "without matching signal: "
                    f"{row['symbol']}"
                )

                continue

            row[
                "signal_id"
            ] = real_signal_id

            matched_rows.append(
                row
            )

        if not matched_rows:

            raise RuntimeError(
                "No matching Alpha Hunter "
                "signals found for "
                f"run_id={run_id}"
            )

        response = requests.post(
            (
                f"{self.url}"
                "/rest/v1/"
                "alpha_hunter_signal_features"
            ),
            params={
                "on_conflict":
                    "signal_id"
            },
            headers=
                self.headers,
            data=json.dumps(
                matched_rows,
                separators=(
                    ",",
                    ":",
                ),
            ),
            timeout=
                self.timeout,
        )

        if response.status_code not in {
            200,
            201,
            204,
        }:

            raise RuntimeError(
                "Feature save failed: "
                f"HTTP {response.status_code}: "
                f"{response.text[:600]}"
            )

        return len(
            matched_rows
        )
