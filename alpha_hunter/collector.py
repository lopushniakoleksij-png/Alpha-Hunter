from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
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
from .private_account import collect_private_account_snapshot
from .storage import (
    SupabaseConfig,
    SupabaseStorage,
    SupabaseStorageError,
    build_run_id,
)


def load_config(
    path: Path,
) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        return json.load(handle)


def collect_symbol(
    client: BitgetClient,
    symbol: str,
    config: dict[str, Any],
) -> dict[str, Any]:

    product_type = config["product_type"]

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

    for timeframe in config["timeframes"]:

        candles = parse_candles(
            client.candles(
                symbol,
                product_type,
                timeframe,
                config["candle_limit"],
            )
        )

        levels = support_resistance(
            candles
        )

        timeframes[timeframe] = {
            "trend":
                trend_state(candles),
            "candle_count":
                len(candles),
            "latest_candle":
                candles[-1]
                if candles
                else None,
            "indicators":
                calculate_indicators(
                    candles
                ),
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
            oi_list[0].get("size")
        )
        if oi_list
        else None
    )

    last_price = to_float(
        prices.get("price")
        or ticker.get("lastPr")
    )

    trends = {
        tf: values["trend"]
        for tf, values
        in timeframes.items()
    }

    state, permission, permission_reason = (
        classify_state(
            trends,
            last_price,
            combined_levels,
        )
    )

    current_funding = to_float(
        funding.get("fundingRate")
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
                prices.get("ts")
                or ticker.get("ts")
                or 0
            ),

        "last_price":
            last_price,

        "mark_price":
            to_float(
                prices.get("markPrice")
                or ticker.get(
                    "markPrice"
                )
            ),

        "index_price":
            to_float(
                prices.get("indexPrice")
                or ticker.get(
                    "indexPrice"
                )
            ),

        "bid_price":
            to_float(
                ticker.get("bidPr")
            ),

        "ask_price":
            to_float(
                ticker.get("askPr")
            ),

        "change_24h_pct":
            (
                to_float(
                    ticker.get(
                        "change24h"
                    )
                )
                or 0.0
            )
            * 100,

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

        "state":
            state,

        "trade_permission":
            permission,

        "trade_permission_reason":
            permission_reason,
    }

    record["data_integrity_score"] = (
        integrity_score(
            record
        )
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
    ] = setup["permission"]

    record[
        "trade_permission_reason"
    ] = setup["reason"]

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

    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def select_market_universe(
    contracts: list[
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

    contract_symbols = {
        str(
            row.get(
                "symbol",
                "",
            )
        ).upper()
        for row in contracts
        if row.get("symbol")
    }

    if not settings.get(
        "enabled",
        False,
    ):

        symbols = [
            symbol
            for symbol
            in config.get(
                "symbols",
                [],
            )
            if symbol
            in contract_symbols
        ]

        return symbols, {
            "total_contracts":
                len(
                    contract_symbols
                ),

            "ticker_count":
                len(tickers),

            "eligible_count":
                len(symbols),

            "selected_count":
                len(symbols),

            "selection_method":
                "frozen-list",

            "selected_symbols":
                symbols,
        }

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

    candidates = []

    for ticker in tickers:

        symbol = str(
            ticker.get(
                "symbol",
                "",
            )
        ).upper()

        if not symbol:
            continue

        if (
            symbol
            not in contract_symbols
        ):
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
            to_float(
                ticker.get(
                    "change24h"
                )
            )
            or 0.0
        ) * 100

        if (
            not last_price
            or last_price <= 0
        ):
            continue

        if (
            quote_volume
            < minimum_quote_volume
        ):
            continue

        if (
            abs(
                change_24h_pct
            )
            > maximum_extension
        ):
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

        for row in previous_rows[:10]:
            add_symbol(
                str(
                    row.get(
                        "symbol",
                        "",
                    )
                ).upper()
            )

    liquidity_size = int(
        settings.get(
            "liquidity_bucket_size",
            10,
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
        :liquidity_size
    ]:
        add_symbol(
            row["symbol"]
        )

    movement_size = int(
        settings.get(
            "movement_bucket_size",
            10,
        )
    )

    movement = [
        row
        for row
        in candidates
        if (
            1.0
            <= abs(
                row[
                    "change_24h_pct"
                ]
            )
            <= 15.0
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
        :movement_size
    ]:
        add_symbol(
            row["symbol"]
        )

    quiet_size = int(
        settings.get(
            "quiet_bucket_size",
            10,
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
        ) <= 3.0
    ]

    quiet.sort(
        key=lambda row:
            row[
                "quote_volume"
            ],
        reverse=True,
    )

    for row in quiet[
        :quiet_size
    ]:
        add_symbol(
            row["symbol"]
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
                "balanced-full-"
                "market-prefilter"
            ),

        "selected_symbols":
            selected,

        "minimum_quote_volume":
            minimum_quote_volume,

        "maximum_24h_extension_pct":
            maximum_extension,
    }

    return (
        selected,
        universe,
    )


def apply_snapshot_comparisons(
    results:
        list[dict[str, Any]],
    previous:
        dict[str, Any] | None,
    minimum_rr:
        float = 5.0,
) -> None:

    if not previous:
        return

    previous_by_symbol = {
        item.get("symbol"):
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


def append_state_history(
    snapshot:
        dict[str, Any],
    config_path:
        Path,
    config:
        dict[str, Any],
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
                    item[
                        "symbol"
                    ],

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

                "trade_permission":
                    item.get(
                        "trade_permission",
                        False,
                    ),

                "rr":
                    item.get(
                        "execution_setup",
                        {},
                    ).get(
                        "rr"
                    ),

                "data_integrity_score":
                    item.get(
                        "data_integrity_score"
                    ),

                "huge_rr_score":
                    item.get(
                        "intelligence",
                        {},
                    ).get(
                        "huge_rr_score"
                    ),

                "price":
                    item.get(
                        "last_price"
                    ),
            }

            handle.write(
                json.dumps(
                    event
                )
                + "\n"
            )

    return history_path


def save_snapshot(
    snapshot:
        dict[str, Any],
    config_path:
        Path,
    config:
        dict[str, Any],
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

    path.write_text(
        json.dumps(
            snapshot,
            indent=2,
        ),
        encoding="utf-8",
    )

    (
        output_dir
        / "latest.json"
    ).write_text(
        json.dumps(
            snapshot,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path


def print_report(
    snapshot:
        dict[str, Any],
) -> None:

    print(
        "\n"
        "ALPHA HUNTER V7"
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
        "Bitget futures contracts"
    )

    print(
        "Eligible after prefilter: "
        f"{universe.get('eligible_count', 0)}"
    )

    print()

    header = (
        f"{'SYMBOL':<14} "
        f"{'LAST':>11} "
        f"{'15m':>8} "
        f"{'1H':>8} "
        f"{'4H':>8} "
        f"{'STATE':>25} "
        f"{'RR':>7} "
        f"{'SCORE':>7} "
        f"{'CONF':>7} "
        f"{'TRADE':>7}"
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
                f"ERROR: "
                f"{item['error']}"
            )

            continue

        tfs = item[
            "timeframes"
        ]

        rr = item.get(
            "execution_setup",
            {},
        ).get(
            "rr"
        )

        intel = item.get(
            "intelligence",
            {},
        )

        rr_text = (
            f"{rr:.2f}"
            if rr is not None
            else "—"
        )

        print(
            f"{item['symbol']:<14} "
            f"{item['last_price']:>11.8g} "
            f"{tfs['15m']['trend']:>8} "
            f"{tfs['1H']['trend']:>8} "
            f"{tfs['4H']['trend']:>8} "
            f"{item['state']:>25} "
            f"{rr_text:>7} "
            f"{intel.get('huge_rr_score', 0):>6.1f} "
            f"{intel.get('confidence_estimate_pct', 0):>6.1f}% "
            f"{('YES' if item['trade_permission'] else 'NO'):>7}"
        )

    print(
        "\n"
        "Note: CONF is a transparent "
        "heuristic estimate, not a "
        "statistically calibrated probability."
        "\n"
    )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Collect an Alpha Hunter V7 "
            "Bitget full-market snapshot"
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

    contracts = client.contracts(
        config[
            "product_type"
        ]
    ) or []

    tickers = client.tickers(
        config[
            "product_type"
        ]
    ) or []

    available = {
        row["symbol"]:
            row
        for row
        in contracts
        if row.get(
            "symbol"
        )
    }

    (
        selected_symbols,
        universe,
    ) = select_market_universe(
        contracts,
        tickers,
        previous_snapshot,
        config,
    )

    results = []

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

    snapshot = {
        "version":
            "0.7.0",

        "collected_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "product_type":
            config[
                "product_type"
            ],

        "universe":
            universe,

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

    if config.get(
        "supabase",
        {},
    ).get(
        "enabled",
        False,
    ):

        if (
            supabase_settings
            is None
        ):

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

                cloud_status = (
                    "SAVED"
                )

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

    private_status = (
        snapshot.get(
            "private_account",
            {},
        ).get(
            "status",
            "UNKNOWN",
        )
    )

    position_count = (
        snapshot.get(
            "private_account",
            {},
        ).get(
            "open_position_count",
            0,
        )
    )

    print(
        "Bitget private API: "
        f"{private_status}"
    )

    print(
        "Open positions detected: "
        f"{position_count}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
