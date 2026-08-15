from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import (
    build_instrument_map,
    instrument_is_allowed,
    load_config,
    load_previous_snapshot,
)
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


ROOT = Path(__file__).resolve().parent

TABLE = "alpha_hunter_universe_hourly"
MODEL_VERSION = "7.9-universe-ledger-v1"

RETENTION_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def f(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def b(value: Any) -> bool:
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


def headers(
    settings: SupabaseConfig,
    *,
    ignore_duplicates: bool = False,
) -> dict[str, str]:

    result = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }

    if ignore_duplicates:
        result["Prefer"] = (
            "resolution=ignore-duplicates,"
            "return=minimal"
        )

    return result


def hour_bucket(
    value: datetime,
) -> datetime:

    return value.astimezone(
        timezone.utc
    ).replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def observation_id(
    symbol: str,
    bucket: datetime,
) -> str:

    raw = (
        f"{symbol.upper()}|"
        f"{MODEL_VERSION}|"
        f"{bucket.isoformat()}"
    ).encode("utf-8")

    return hashlib.sha256(
        raw
    ).hexdigest()[:24]


def selected_symbols_from_snapshot(
    snapshot: dict[str, Any] | None,
) -> set[str]:

    if not snapshot:
        return set()

    selected: set[str] = set()

    universe = snapshot.get(
        "universe",
        {},
    )

    if isinstance(universe, dict):
        for symbol in (
            universe.get(
                "selected_symbols",
                [],
            )
            or []
        ):
            selected.add(
                str(symbol).upper()
            )

    if not selected:
        for row in (
            snapshot.get(
                "symbols",
                [],
            )
            or []
        ):
            if (
                isinstance(row, dict)
                and "error" not in row
                and row.get("symbol")
            ):
                selected.add(
                    str(
                        row["symbol"]
                    ).upper()
                )

    return selected


def classify_reason(
    *,
    deep_scan_selected: bool,
    crypto_allowed: bool,
    liquidity_pass: bool,
    extension_pass: bool,
) -> str:

    # This field describes CURRENT prefilter status.
    # Selection status is preserved separately in
    # deep_scan_selected + selection_run_id.
    if not crypto_allowed:
        return "NON_CRYPTO"

    if not liquidity_pass:
        return "LOW_LIQUIDITY"

    if not extension_pass:
        return "OVER_EXTENDED"

    if deep_scan_selected:
        return "DEEP_SCAN_SELECTED"

    return "ELIGIBLE_NOT_SELECTED"


def build_rows(
    *,
    contracts: list[dict[str, Any]],
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    selected_symbols: set[str],
    selection_snapshot_at_utc: str | None,
    selection_run_id: str | None,
    product_type: str,
    config: dict[str, Any],
    observed_at: datetime,
) -> tuple[
    list[dict[str, Any]],
    dict[str, int],
]:

    metadata_map = build_instrument_map(
        contracts,
        instruments,
    )

    contract_symbols = set(
        metadata_map.keys()
    )

    settings = config.get(
        "universe_scan",
        {},
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

    bucket = hour_bucket(
        observed_at
    )

    rows: list[
        dict[str, Any]
    ] = []

    stats = {
        "tickers": 0,
        "contract_tickers": 0,
        "stored": 0,
        "invalid_price": 0,
        "non_crypto": 0,
        "low_liquidity": 0,
        "over_extended": 0,
        "eligible": 0,
        "selected": 0,
        "eligible_not_selected": 0,
    }

    for ticker in tickers:

        if not isinstance(
            ticker,
            dict,
        ):
            continue

        stats["tickers"] += 1

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
        ).upper()

        if (
            not symbol
            or symbol
            not in contract_symbols
        ):
            continue

        stats[
            "contract_tickers"
        ] += 1

        metadata = metadata_map.get(
            symbol,
            {},
        )

        last_price = f(
            ticker.get(
                "lastPr"
            )
        )

        if (
            last_price is None
            or last_price <= 0
        ):
            stats[
                "invalid_price"
            ] += 1
            continue

        quote_volume = (
            f(
                ticker.get(
                    "quoteVolume"
                )
            )
            or f(
                ticker.get(
                    "usdtVolume"
                )
            )
            or 0.0
        )

        change_raw = f(
            ticker.get(
                "change24h"
            )
        )

        change_24h_pct = (
            change_raw * 100.0
            if change_raw
            is not None
            else None
        )

        crypto_allowed = (
            instrument_is_allowed(
                metadata,
                config,
            )
        )

        liquidity_pass = (
            quote_volume
            >= minimum_quote_volume
        )

        extension_pass = (
            change_24h_pct is not None
            and abs(
                change_24h_pct
            )
            <= maximum_extension
        )

        prefilter_eligible = bool(
            crypto_allowed
            and liquidity_pass
            and extension_pass
        )

        deep_scan_selected = (
            symbol
            in selected_symbols
        )

        reason = classify_reason(
            deep_scan_selected=
                deep_scan_selected,
            crypto_allowed=
                crypto_allowed,
            liquidity_pass=
                liquidity_pass,
            extension_pass=
                extension_pass,
        )

        if not crypto_allowed:
            stats["non_crypto"] += 1

        elif not liquidity_pass:
            stats[
                "low_liquidity"
            ] += 1

        elif not extension_pass:
            stats[
                "over_extended"
            ] += 1

        else:
            stats["eligible"] += 1

            if (
                not
                deep_scan_selected
            ):
                stats[
                    "eligible_not_selected"
                ] += 1

        if deep_scan_selected:
            stats["selected"] += 1

        row = {
            "observation_id":
                observation_id(
                    symbol,
                    bucket,
                ),

            "observed_at_utc":
                observed_at.isoformat(),

            "hour_bucket_utc":
                bucket.isoformat(),

            "symbol":
                symbol,

            "product_type":
                product_type,

            "last_price":
                last_price,

            "change_24h_pct":
                change_24h_pct,

            "quote_volume_24h":
                quote_volume,

            "symbol_type":
                (
                    str(
                        metadata.get(
                            "symbolType"
                        )
                    )
                    if metadata.get(
                        "symbolType"
                    )
                    is not None
                    else None
                ),

            "is_rwa":
                b(
                    metadata.get(
                        "isRwa",
                        False,
                    )
                ),

            "is_reality":
                b(
                    metadata.get(
                        "isReality",
                        False,
                    )
                ),

            "crypto_allowed":
                crypto_allowed,

            "liquidity_pass":
                liquidity_pass,

            "extension_pass":
                extension_pass,

            "prefilter_eligible":
                prefilter_eligible,

            "deep_scan_selected":
                deep_scan_selected,

            "selection_snapshot_at_utc":
                selection_snapshot_at_utc,

            "selection_run_id":
                selection_run_id,

            "rejection_reason":
                reason,

            "source":
                "BITGET_ALL_TICKERS",

            "measurement_quality":
                "HOURLY_TICKER_SNAPSHOT",

            "trade_permission":
                False,

            "updated_at":
                observed_at.isoformat(),
        }

        rows.append(
            row
        )

    stats["stored"] = len(
        rows
    )

    return rows, stats


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
                "observation_id",
        },
        headers=headers(
            settings,
            ignore_duplicates=True,
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
            "V7.9 universe ledger save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(rows)


def purge_old_rows(
    settings: SupabaseConfig,
    now: datetime,
) -> int:

    cutoff = (
        now
        - timedelta(
            days=RETENTION_DAYS
        )
    )

    response = requests.delete(
        (
            f"{settings.url}"
            f"/rest/v1/{TABLE}"
        ),
        params={
            "hour_bucket_utc":
                f"lt.{cutoff.isoformat()}",
        },
        headers={
            **headers(settings),
            "Prefer":
                "return=representation",
        },
        timeout=settings.timeout_seconds,
    )

    if response.status_code not in {
        200,
        204,
    }:
        raise RuntimeError(
            "V7.9 retention cleanup failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    try:
        payload = response.json()

        return (
            len(payload)
            if isinstance(
                payload,
                list,
            )
            else 0
        )

    except ValueError:
        return 0


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

    observed_at = utc_now()

    current_snapshot = (
        load_previous_snapshot(
            ROOT / "config.json",
            config,
        )
    )

    selected_symbols = (
        selected_symbols_from_snapshot(
            current_snapshot
        )
    )

    selection_snapshot_at_utc = (
        str(
            current_snapshot.get(
                "collected_at_utc"
            )
        )
        if (
            current_snapshot
            and current_snapshot.get(
                "collected_at_utc"
            )
        )
        else None
    )

    selection_run_id = (
        str(
            current_snapshot.get(
                "run_id"
            )
        )
        if (
            current_snapshot
            and current_snapshot.get(
                "run_id"
            )
        )
        else None
    )

    contracts = (
        client.contracts(
            product_type
        )
        or []
    )

    instruments = (
        client.instruments(
            product_type
        )
        or []
    )

    tickers = (
        client.tickers(
            product_type
        )
        or []
    )

    rows, stats = build_rows(
        contracts=contracts,
        instruments=instruments,
        tickers=tickers,
        selected_symbols=
            selected_symbols,
        selection_snapshot_at_utc=
            selection_snapshot_at_utc,
        selection_run_id=
            selection_run_id,
        product_type=product_type,
        config=config,
        observed_at=observed_at,
    )

    attempted = save_rows(
        settings,
        rows,
    )

    purged = purge_old_rows(
        settings,
        observed_at,
    )

    top_absolute = sorted(
        rows,
        key=lambda row:
            abs(
                float(
                    row.get(
                        "change_24h_pct"
                    )
                    or 0.0
                )
            ),
        reverse=True,
    )[:15]

    print()
    print("=" * 118)
    print(
        "ALPHA HUNTER V7.9 "
        "FULL-UNIVERSE HOURLY LEDGER — SHADOW"
    )
    print("=" * 118)

    print(
        "Observed:",
        observed_at.isoformat(),
    )

    print(
        "Hour bucket:",
        hour_bucket(
            observed_at
        ).isoformat(),
    )

    print(
        "Contract tickers:",
        stats["contract_tickers"],
    )

    print(
        "Rows attempted:",
        attempted,
    )

    print(
        "Deep-scan selected:",
        stats["selected"],
    )

    print(
        "Selection snapshot:",
        selection_snapshot_at_utc
        or "UNAVAILABLE",
    )

    print(
        "Selection run ID:",
        selection_run_id
        or "UNAVAILABLE",
    )

    print(
        "Prefilter eligible:",
        stats["eligible"],
    )

    print(
        "Eligible not selected:",
        stats[
            "eligible_not_selected"
        ],
    )

    print(
        "Non-crypto:",
        stats["non_crypto"],
    )

    print(
        "Low liquidity:",
        stats["low_liquidity"],
    )

    print(
        "Over-extended:",
        stats["over_extended"],
    )

    print(
        "Invalid price skipped:",
        stats["invalid_price"],
    )

    print(
        "Rows purged >7d:",
        purged,
    )

    print()
    print(
        "TOP ABSOLUTE 24H MOVERS"
    )

    print(
        f"{'SYMBOL':<18}"
        f"{'24H':>9}"
        f"{'ELIG':>8}"
        f"{'SCAN':>8}  "
        f"STATUS"
    )

    print("-" * 72)

    for row in top_absolute:

        change = row.get(
            "change_24h_pct"
        )

        change_text = (
            f"{change:+.2f}%"
            if change is not None
            else "—"
        )

        print(
            f"{row['symbol']:<18}"
            f"{change_text:>9}"
            f"{('Y' if row['prefilter_eligible'] else 'N'):>8}"
            f"{('Y' if row['deep_scan_selected'] else 'N'):>8}  "
            f"{row['rejection_reason']}"
        )

    print()
    print(
        "IMPORTANT: V7.9 IS "
        "MEASUREMENT/AUDIT ONLY."
    )

    print(
        "Same-hour reruns do not overwrite "
        "the first stored universe snapshot."
    )

    print(
        "Raw universe evidence is retained "
        f"for {RETENTION_DAYS} days."
    )

    print(
        "No trade permission was generated."
    )

    print()
    print(
        "V7.9 FULL-UNIVERSE LEDGER: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
