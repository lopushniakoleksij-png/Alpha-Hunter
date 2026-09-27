#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_hunter.analysis import parse_candles
from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


DISCOVERY_VIEW = "alpha_hunter_candidate_retention_targets_v01"
TARGET_TABLE = "alpha_hunter_candidate_retention_shadow_targets_v02"
COLLECTION_VIEW = "alpha_hunter_candidate_retention_collection_targets_v02"
CANDLE_TABLE = "alpha_hunter_candidate_retention_shadow_candles_v01"
RUN_TABLE = "alpha_hunter_candidate_retention_shadow_runs_v01"
PRODUCT_TYPE = "USDT-FUTURES"
GRANULARITY = "1H"
CANDLE_LIMIT = 30


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _headers(settings: SupabaseConfig, *, prefer: str | None = None) -> dict[str, str]:
    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _load_targets(
    settings: SupabaseConfig,
    view_name: str,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{settings.url}/rest/v1/{view_name}",
        params={
            "select": (
                "episode_id,first_candidate_observation_id,symbol,strategy_id,"
                "direction,first_observed_at_utc,first_candidate_at_utc,"
                "first_candidate_action,retention_start_utc,"
                "retention_horizon_end_utc,expected_closed_1h_candles"
            ),
            "order": "symbol.asc,first_candidate_at_utc.asc",
            "limit": "2000",
        },
        headers=_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Retention target load failed: HTTP {response.status_code}"
        )
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Retention target load returned unexpected shape")
    return [row for row in payload if isinstance(row, dict)]


def _persist_targets(
    settings: SupabaseConfig,
    targets: list[dict[str, Any]],
    checked_at: datetime,
) -> None:
    if not targets:
        return

    rows: list[dict[str, Any]] = []
    for target in targets:
        rows.append(
            {
                "episode_id": str(target["episode_id"]),
                "first_candidate_observation_id": str(
                    target["first_candidate_observation_id"]
                ),
                "symbol": str(target["symbol"]).upper(),
                "strategy_id": str(target["strategy_id"]),
                "direction": str(target["direction"]).upper(),
                "first_observed_at_utc": str(target["first_observed_at_utc"]),
                "first_candidate_at_utc": str(target["first_candidate_at_utc"]),
                "first_candidate_action": str(
                    target["first_candidate_action"]
                ),
                "retention_start_utc": str(target["retention_start_utc"]),
                "retention_horizon_end_utc": str(
                    target["retention_horizon_end_utc"]
                ),
                "expected_closed_1h_candles": int(
                    target["expected_closed_1h_candles"]
                ),
                "target_registered_at_utc": _iso(checked_at),
                "target_source": "SEALED_CANDIDATE_EPISODES_ONLY",
                "scientific_role": "V15_PARALLEL_SHADOW",
                "audit_only": True,
                "counted_in_v14": False,
                "mutation_permitted": False,
                "shadow_only": True,
                "trade_permission": False,
                "production_promotion_permitted": False,
                "order_path": "NONE",
            }
        )

    for offset in range(0, len(rows), 500):
        chunk = rows[offset : offset + 500]
        response = requests.post(
            f"{settings.url}/rest/v1/{TARGET_TABLE}",
            headers=_headers(
                settings,
                prefer="resolution=ignore-duplicates,return=minimal",
            ),
            data=json.dumps(chunk, separators=(",", ":")),
            timeout=settings.timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                "Retention target persistence failed: "
                f"HTTP {response.status_code}"
            )


def _load_existing_keys(
    settings: SupabaseConfig,
    checked_at: datetime,
) -> set[tuple[str, str]]:
    cutoff = checked_at - timedelta(hours=30)
    response = requests.get(
        f"{settings.url}/rest/v1/{CANDLE_TABLE}",
        params={
            "select": "episode_id,candle_open_utc",
            "candle_open_utc": f"gte.{_iso(cutoff)}",
            "limit": "10000",
        },
        headers=_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Retention existing-key load failed: "
            f"HTTP {response.status_code}"
        )
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(
            "Retention existing-key load returned unexpected shape"
        )

    keys: set[tuple[str, str]] = set()
    for row in payload:
        if not isinstance(row, dict):
            continue
        episode_id = str(row.get("episode_id") or "")
        candle_open_utc = str(row.get("candle_open_utc") or "")
        if episode_id and candle_open_utc:
            keys.add((episode_id, candle_open_utc))
    return keys


def _build_rows_for_symbol(
    symbol: str,
    targets: list[dict[str, Any]],
    raw_candles: list[list[str]],
    checked_at: datetime,
    existing_keys: set[tuple[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    parsed = parse_candles(raw_candles)
    closed: list[dict[str, float | int]] = []
    for candle in parsed:
        candle_open = datetime.fromtimestamp(
            int(candle["timestamp"]) / 1000.0,
            tz=timezone.utc,
        )
        candle_known = candle_open + timedelta(hours=1)
        if candle_known <= checked_at:
            closed.append(candle)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    existing = existing_keys if existing_keys is not None else set()

    for target in targets:
        episode_id = str(target["episode_id"])
        retention_start = _parse_utc(str(target["retention_start_utc"]))
        horizon_end = _parse_utc(str(target["retention_horizon_end_utc"]))

        for candle in closed:
            candle_open = datetime.fromtimestamp(
                int(candle["timestamp"]) / 1000.0,
                tz=timezone.utc,
            )
            candle_known = candle_open + timedelta(hours=1)

            if candle_open < retention_start:
                continue
            if candle_known > horizon_end:
                continue

            key = (episode_id, _iso(candle_open))
            if key in seen or key in existing:
                continue
            seen.add(key)
            existing.add(key)

            retention_row_id = hashlib.sha256(
                (
                    "candidate-retention-shadow-v0.1|"
                    f"{episode_id}|{_iso(candle_open)}"
                ).encode("utf-8")
            ).hexdigest()[:32]

            rows.append(
                {
                    "retention_row_id": retention_row_id,
                    "episode_id": episode_id,
                    "first_candidate_observation_id": str(
                        target["first_candidate_observation_id"]
                    ),
                    "symbol": symbol,
                    "strategy_id": str(target["strategy_id"]),
                    "direction": str(target["direction"]).upper(),
                    "first_observed_at_utc": str(
                        target["first_observed_at_utc"]
                    ),
                    "first_candidate_at_utc": str(
                        target["first_candidate_at_utc"]
                    ),
                    "first_candidate_action": str(
                        target["first_candidate_action"]
                    ),
                    "retention_start_utc": str(target["retention_start_utc"]),
                    "retention_horizon_end_utc": str(
                        target["retention_horizon_end_utc"]
                    ),
                    "candle_open_utc": _iso(candle_open),
                    "candle_known_at_utc": _iso(candle_known),
                    "captured_at_utc": _iso(checked_at),
                    "open_price": float(candle["open"]),
                    "high_price": float(candle["high"]),
                    "low_price": float(candle["low"]),
                    "close_price": float(candle["close"]),
                    "base_volume": float(candle["base_volume"]),
                    "quote_volume": float(candle["quote_volume"]),
                    "source_exchange": "BITGET",
                    "source_endpoint": "/api/v2/mix/market/candles",
                    "product_type": PRODUCT_TYPE,
                    "granularity": GRANULARITY,
                    "fully_closed": True,
                    "scientific_role": "V15_PARALLEL_SHADOW",
                    "target_source": "SEALED_CANDIDATE_EPISODES_ONLY",
                    "audit_only": True,
                    "counted_in_v14": False,
                    "mutation_permitted": False,
                    "shadow_only": True,
                    "trade_permission": False,
                    "production_promotion_permitted": False,
                    "order_path": "NONE",
                }
            )

    return rows, len(closed)


def _persist_rows(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> None:
    for offset in range(0, len(rows), 500):
        chunk = rows[offset : offset + 500]
        response = requests.post(
            f"{settings.url}/rest/v1/{CANDLE_TABLE}",
            headers=_headers(
                settings,
                prefer="resolution=ignore-duplicates,return=minimal",
            ),
            data=json.dumps(chunk, separators=(",", ":")),
            timeout=settings.timeout_seconds,
        )
        if response.status_code not in {200, 201, 204}:
            raise RuntimeError(
                "Retention candle persistence failed: "
                f"HTTP {response.status_code}"
            )


def _persist_run(
    settings: SupabaseConfig,
    *,
    checked_at: datetime,
    target_episode_count: int,
    target_symbol_count: int,
    symbols_requested: int,
    symbols_succeeded: int,
    symbols_failed: int,
    candles_considered: int,
    rows_attempted: int,
    result_class: str,
    error_classes: Counter[str],
) -> None:
    collector_run_id = hashlib.sha256(
        (
            "candidate-retention-shadow-run-v0.1|"
            f"{_iso(checked_at)}|{target_episode_count}|{target_symbol_count}"
        ).encode("utf-8")
    ).hexdigest()[:32]

    row = {
        "collector_run_id": collector_run_id,
        "checked_at_utc": _iso(checked_at),
        "target_episode_count": target_episode_count,
        "target_symbol_count": target_symbol_count,
        "symbols_requested": symbols_requested,
        "symbols_succeeded": symbols_succeeded,
        "symbols_failed": symbols_failed,
        "candles_considered": candles_considered,
        "rows_attempted": rows_attempted,
        "result_class": result_class,
        "error_classes": dict(error_classes),
        "public_get_only": True,
        "private_credentials_required": False,
        "universe_discovery_permitted": False,
        "audit_only": True,
        "counted_in_v14": False,
        "mutation_permitted": False,
        "shadow_only": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }

    response = requests.post(
        f"{settings.url}/rest/v1/{RUN_TABLE}",
        headers=_headers(settings, prefer="return=minimal"),
        data=json.dumps(row, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            f"Retention run persistence failed: HTTP {response.status_code}"
        )


def main() -> int:
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    checked_at = datetime.now(timezone.utc)

    discovered_targets = _load_targets(settings, DISCOVERY_VIEW)
    _persist_targets(settings, discovered_targets, checked_at)

    targets = _load_targets(settings, COLLECTION_VIEW)
    existing_keys = _load_existing_keys(settings, checked_at)

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in targets:
        symbol = str(target.get("symbol") or "").upper().strip()
        if symbol:
            by_symbol[symbol].append(target)

    if not targets or not by_symbol:
        _persist_run(
            settings,
            checked_at=checked_at,
            target_episode_count=len(targets),
            target_symbol_count=len(by_symbol),
            symbols_requested=0,
            symbols_succeeded=0,
            symbols_failed=0,
            candles_considered=0,
            rows_attempted=0,
            result_class="NO_TARGETS",
            error_classes=Counter(),
        )
        print(
            json.dumps(
                {
                    "result_class": "NO_TARGETS",
                    "target_episode_count": len(targets),
                    "target_symbol_count": len(by_symbol),
                    "counted_in_v14": False,
                    "trade_permission": False,
                    "order_path": "NONE",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    client = BitgetClient(timeout=5, max_retries=2)
    all_rows: list[dict[str, Any]] = []
    error_classes: Counter[str] = Counter()
    symbols_succeeded = 0
    symbols_failed = 0
    candles_considered = 0

    for symbol, symbol_targets in sorted(by_symbol.items()):
        try:
            raw = client.candles(
                symbol,
                PRODUCT_TYPE,
                GRANULARITY,
                CANDLE_LIMIT,
            )
            rows, considered = _build_rows_for_symbol(
                symbol,
                symbol_targets,
                raw,
                checked_at,
                existing_keys,
            )
            all_rows.extend(rows)
            candles_considered += considered
            symbols_succeeded += 1
        except (BitgetAPIError, RuntimeError, ValueError, TypeError) as exc:
            symbols_failed += 1
            error_classes[exc.__class__.__name__] += 1

    if all_rows:
        _persist_rows(settings, all_rows)

    result_class = "PASS" if symbols_failed == 0 else "DEGRADED"
    _persist_run(
        settings,
        checked_at=checked_at,
        target_episode_count=len(targets),
        target_symbol_count=len(by_symbol),
        symbols_requested=len(by_symbol),
        symbols_succeeded=symbols_succeeded,
        symbols_failed=symbols_failed,
        candles_considered=candles_considered,
        rows_attempted=len(all_rows),
        result_class=result_class,
        error_classes=error_classes,
    )

    print(
        json.dumps(
            {
                "result_class": result_class,
                "target_episode_count": len(targets),
                "target_symbol_count": len(by_symbol),
                "symbols_requested": len(by_symbol),
                "symbols_succeeded": symbols_succeeded,
                "symbols_failed": symbols_failed,
                "candles_considered": candles_considered,
                "rows_attempted": len(all_rows),
                "error_classes": dict(error_classes),
                "public_get_only": True,
                "private_credentials_required": False,
                "universe_discovery_permitted": False,
                "counted_in_v14": False,
                "trade_permission": False,
                "order_path": "NONE",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result_class == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
