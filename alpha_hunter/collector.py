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
from .storage import SupabaseStorage, SupabaseStorageError, SupabaseConfig, build_run_id


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_symbol(client: BitgetClient, symbol: str, config: dict[str, Any]) -> dict[str, Any]:
    product_type = config["product_type"]
    ticker = client.ticker(symbol, product_type)
    prices = client.symbol_price(symbol, product_type)
    oi_payload = client.open_interest(symbol, product_type)
    funding = client.current_funding(symbol, product_type)
    funding_rows = client.funding_history(symbol, product_type, config.get("funding_history_limit", 30))

    timeframes: dict[str, Any] = {}
    combined_levels: dict[str, float | None] = {"support": None, "resistance": None}
    for timeframe in config["timeframes"]:
        candles = parse_candles(
            client.candles(symbol, product_type, timeframe, config["candle_limit"])
        )
        levels = support_resistance(candles)
        timeframes[timeframe] = {
            "trend": trend_state(candles),
            "candle_count": len(candles),
            "latest_candle": candles[-1] if candles else None,
            "indicators": calculate_indicators(candles),
            "compression": compression_score(candles),
            **levels,
        }
        if timeframe == "1H":
            combined_levels = levels

    oi_list = oi_payload.get("openInterestList", []) if isinstance(oi_payload, dict) else []
    oi = to_float(oi_list[0].get("size")) if oi_list else None
    last_price = to_float(prices.get("price") or ticker.get("lastPr"))
    trends = {tf: values["trend"] for tf, values in timeframes.items()}
    state, permission, permission_reason = classify_state(trends, last_price, combined_levels)
    current_funding = to_float(funding.get("fundingRate"))

    record = {
        "symbol": symbol,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "exchange_timestamp_ms": int(prices.get("ts") or ticker.get("ts") or 0),
        "last_price": last_price,
        "mark_price": to_float(prices.get("markPrice") or ticker.get("markPrice")),
        "index_price": to_float(prices.get("indexPrice") or ticker.get("indexPrice")),
        "bid_price": to_float(ticker.get("bidPr")),
        "ask_price": to_float(ticker.get("askPr")),
        "change_24h_pct": (to_float(ticker.get("change24h")) or 0.0) * 100,
        "quote_volume_24h": to_float(ticker.get("quoteVolume") or ticker.get("usdtVolume")),
        "open_interest": oi,
        "open_interest_change_pct": None,
        "funding_rate": current_funding,
        "funding_history": funding_summary(funding_rows, current_funding),
        "funding_interval_hours": int(funding.get("fundingRateInterval") or 0),
        "next_funding_time_ms": int(funding.get("nextUpdate") or 0),
        "timeframes": timeframes,
        "support": combined_levels.get("support"),
        "resistance": combined_levels.get("resistance"),
        "state": state,
        "trade_permission": permission,
        "trade_permission_reason": permission_reason,
    }
    record["data_integrity_score"] = integrity_score(record)
    setup = validate_trade_setup(record, config.get("minimum_reward_risk", 5.0))
    record["execution_setup"] = setup
    record["trade_permission"] = setup["permission"]
    record["trade_permission_reason"] = setup["reason"]
    record["intelligence"] = build_intelligence_score(record, config.get("minimum_reward_risk", 5.0))
    return record


def load_previous_snapshot(config_path: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    path = config_path.parent / config["snapshot_directory"] / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def apply_snapshot_comparisons(results: list[dict[str, Any]], previous: dict[str, Any] | None, minimum_rr: float = 5.0) -> None:
    if not previous:
        return
    previous_by_symbol = {item.get("symbol"): item for item in previous.get("symbols", [])}
    for item in results:
        if "error" in item:
            continue
        old = previous_by_symbol.get(item["symbol"], {})
        item["open_interest_change_pct"] = percentage_change(
            item.get("open_interest"), old.get("open_interest")
        )
        item["price_change_since_snapshot_pct"] = percentage_change(
            item.get("last_price"), old.get("last_price")
        )
        previous_state = old.get("state")
        item["previous_state"] = previous_state
        item["state_changed"] = bool(previous_state and previous_state != item.get("state"))
        setup = validate_trade_setup(item, minimum_rr)
        item["execution_setup"] = setup
        item["trade_permission"] = setup["permission"]
        item["trade_permission_reason"] = setup["reason"]
        item["intelligence"] = build_intelligence_score(item, minimum_rr)


def append_state_history(snapshot: dict[str, Any], config_path: Path, config: dict[str, Any]) -> Path:
    history_path = config_path.parent / config.get("state_history_file", "data/state-history.jsonl")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        for item in snapshot.get("symbols", []):
            if "error" in item:
                continue
            event = {
                "collected_at_utc": snapshot["collected_at_utc"],
                "symbol": item["symbol"],
                "previous_state": item.get("previous_state"),
                "state": item.get("state"),
                "state_changed": item.get("state_changed", False),
                "trade_permission": item.get("trade_permission", False),
                "rr": item.get("execution_setup", {}).get("rr"),
                "data_integrity_score": item.get("data_integrity_score"),
            }
            handle.write(json.dumps(event) + "\n")
    return history_path


def save_snapshot(snapshot: dict[str, Any], config_path: Path, config: dict[str, Any]) -> Path:
    root = config_path.parent
    output_dir = root / config["snapshot_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"snapshot-{stamp}.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    (output_dir / "latest.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path


def print_report(snapshot: dict[str, Any]) -> None:
    print(f"\nALPHA HUNTER V1.4 — {snapshot['collected_at_utc']}\n")
    header = f"{'SYMBOL':<14} {'LAST':>11} {'15m':>8} {'1H':>8} {'4H':>8} {'STATE':>25} {'RR':>7} {'SCORE':>7} {'CONF':>7} {'TRADE':>7}"
    print(header)
    print("-" * len(header))
    for item in snapshot["symbols"]:
        if "error" in item:
            print(f"{item['symbol']:<14} ERROR: {item['error']}")
            continue
        tfs = item["timeframes"]
        rr = item.get("execution_setup", {}).get("rr")
        intel = item.get("intelligence", {})
        rr_text = f"{rr:.2f}" if rr is not None else "—"
        print(
            f"{item['symbol']:<14} {item['last_price']:>11.8g} "
            f"{tfs['15m']['trend']:>8} {tfs['1H']['trend']:>8} {tfs['4H']['trend']:>8} "
            f"{item['state']:>25} {rr_text:>7} {intel.get('huge_rr_score', 0):>6.1f} "
            f"{intel.get('confidence_estimate_pct', 0):>6.1f}% {('YES' if item['trade_permission'] else 'NO'):>7}"
        )
    print("\nNote: CONF is a transparent heuristic estimate, not a statistically calibrated probability.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect an Alpha Hunter V1 Bitget snapshot")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    load_env_file(config_path.parent / ".env")
    config = load_config(config_path)

    client = BitgetClient.from_environment(
        timeout=config.get("request_timeout_seconds", 12),
        max_retries=config.get("max_retries", 3),
    )

    previous_snapshot = load_previous_snapshot(config_path, config)
    available = {row["symbol"]: row for row in client.contracts(config["product_type"])}
    results = []
    for symbol in config["symbols"]:
        if symbol not in available:
            results.append({"symbol": symbol, "error": "Symbol is not listed in Bitget USDT futures"})
            continue
        try:
            results.append(collect_symbol(client, symbol, config))
        except BitgetAPIError as exc:
            results.append({"symbol": symbol, "error": str(exc)})

    apply_snapshot_comparisons(results, previous_snapshot, config.get("minimum_reward_risk", 5.0))

    private_account = collect_private_account_snapshot(
        client,
        config["product_type"],
        config.get("margin_coin", "USDT"),
    )

    snapshot = {
        "version": "0.5.0",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_type": config["product_type"],
        "symbols": results,
        "private_account": private_account,
    }
    snapshot["run_id"] = build_run_id(snapshot)
    path = save_snapshot(snapshot, config_path, config)
    history_path = append_state_history(snapshot, config_path, config)

    cloud_status = "DISABLED"
    supabase_settings = SupabaseConfig.from_environment(config)
    if config.get("supabase", {}).get("enabled", False):
        if supabase_settings is None:
            cloud_status = "NOT_CONFIGURED"
        else:
            try:
                SupabaseStorage(supabase_settings).save_snapshot(snapshot)
                cloud_status = "SAVED"
            except SupabaseStorageError as exc:
                cloud_status = f"FAILED: {exc}"

    print_report(snapshot)
    print(f"Run ID: {snapshot['run_id']}")
    print(f"Snapshot saved: {path}")
    print(f"State history: {history_path}")
    print(f"Supabase: {cloud_status}")
    private_status = snapshot.get("private_account", {}).get("status", "UNKNOWN")
    position_count = snapshot.get("private_account", {}).get("open_position_count", 0)
    print(f"Bitget private API: {private_status}")
    print(f"Open positions detected: {position_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
