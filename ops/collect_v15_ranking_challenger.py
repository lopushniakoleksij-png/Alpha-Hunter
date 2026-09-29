#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alpha_hunter.analysis import to_float
from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import (
    apply_candidate_quality,
    collect_symbol,
    load_config,
)
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.strategy_engine import apply_multi_strategy_engine


TARGET_VIEW = "alpha_hunter_v15_ranking_challenger_targets_v02"
OBSERVATION_TABLE = "alpha_hunter_v15_ranking_challenger_observations_v01"
RUN_TABLE = "alpha_hunter_v15_ranking_challenger_runs_v01"
MODEL_VERSION = "v15-ranking-challenger-v0.2"
MAX_TARGETS = 5


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


def _load_targets(settings: SupabaseConfig) -> list[dict[str, Any]]:
    response = requests.get(
        f"{settings.url}/rest/v1/{TARGET_VIEW}",
        params={
            "select": (
                "target_observation_id,selection_run_id,target_observed_at_utc,"
                "symbol,change_24h_pct,quote_volume_24h,previous_gap_seconds,"
                "hourly_normalized_volume_log_growth,challenger_rank"
            ),
            "order": "challenger_rank.asc",
            "limit": str(MAX_TARGETS),
        },
        headers=_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"V15 ranking target load failed: HTTP {response.status_code}"
        )
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("V15 ranking target load returned unexpected shape")
    return [row for row in payload if isinstance(row, dict)][:MAX_TARGETS]


def _best_shadow_strategy(record: dict[str, Any]) -> dict[str, Any]:
    engine = record.get("multi_strategy_engine")
    if not isinstance(engine, dict):
        return {}
    best = engine.get("best_shadow_candidate")
    return best if isinstance(best, dict) else {}


def _build_observation(
    *,
    target: dict[str, Any],
    run_id: str,
    checked_at: datetime,
    record: dict[str, Any] | None,
    error: Exception | None,
) -> dict[str, Any]:
    symbol = str(target.get("symbol") or "").upper()
    selection_run_id = str(target.get("selection_run_id") or "")
    target_id = str(target.get("target_observation_id") or "")
    obs_id = hashlib.sha256(
        (
            f"{MODEL_VERSION}|{selection_run_id}|{target_id}|{symbol}"
        ).encode("utf-8")
    ).hexdigest()[:32]

    if record is None:
        return {
            "observation_id": obs_id,
            "challenger_run_id": run_id,
            "selection_run_id": selection_run_id,
            "target_observation_id": target_id,
            "target_observed_at_utc": target["target_observed_at_utc"],
            "deep_scanned_at_utc": _iso(checked_at),
            "symbol": symbol,
            "challenger_rank": int(target["challenger_rank"]),
            "source_change_24h_pct": target.get("change_24h_pct"),
            "source_quote_volume_24h": target.get("quote_volume_24h"),
            "previous_gap_seconds": target.get("previous_gap_seconds"),
            "hourly_normalized_volume_log_growth": target.get(
                "hourly_normalized_volume_log_growth"
            ),
            "collection_status": "FAILED",
            "error_class": error.__class__.__name__ if error else "UNKNOWN",
            "diagnostic": {"error_message_persisted": False},
            "public_get_only": True,
            "counted_in_v14": False,
            "production_selector_changed": False,
            "threshold_change_permitted": False,
            "production_promotion_permitted": False,
            "shadow_only": True,
            "trade_permission": False,
            "order_path": "NONE",
        }

    best = _best_shadow_strategy(record)
    engine = record.get("multi_strategy_engine")
    shadow_count = (
        int(engine.get("shadow_candidate_count") or 0)
        if isinstance(engine, dict)
        else 0
    )

    return {
        "observation_id": obs_id,
        "challenger_run_id": run_id,
        "selection_run_id": selection_run_id,
        "target_observation_id": target_id,
        "target_observed_at_utc": target["target_observed_at_utc"],
        "deep_scanned_at_utc": _iso(checked_at),
        "symbol": symbol,
        "challenger_rank": int(target["challenger_rank"]),
        "source_change_24h_pct": target.get("change_24h_pct"),
        "source_quote_volume_24h": target.get("quote_volume_24h"),
        "previous_gap_seconds": target.get("previous_gap_seconds"),
        "hourly_normalized_volume_log_growth": target.get(
            "hourly_normalized_volume_log_growth"
        ),
        "collection_status": "PASS",
        "error_class": None,
        "legacy_state": record.get("state"),
        "legacy_trade_permission_would_be": bool(
            record.get("trade_permission", False)
        ),
        "legacy_v7_trade_ready_would_be": bool(
            record.get("v7_trade_ready", False)
        ),
        "market_phase": record.get("market_phase"),
        "opportunity_timing": record.get("opportunity_timing"),
        "behaviour_score": record.get("behaviour_score"),
        "best_shadow_strategy_id": best.get("strategy_id"),
        "best_shadow_strategy_direction": best.get("direction"),
        "best_shadow_strategy_action": best.get("action"),
        "best_shadow_strategy_rr": best.get("rr"),
        "best_shadow_strategy_score": best.get("signal_score"),
        "shadow_candidate_count": shadow_count,
        "diagnostic": {
            "last_price": record.get("last_price"),
            "change_24h_pct": record.get("change_24h_pct"),
            "quote_volume_24h": record.get("quote_volume_24h"),
            "data_integrity_score": record.get("data_integrity_score"),
            "trade_permission_is_diagnostic_only": True,
            "order_write_path_present": False,
        },
        "public_get_only": True,
        "counted_in_v14": False,
        "production_selector_changed": False,
        "threshold_change_permitted": False,
        "production_promotion_permitted": False,
        "shadow_only": True,
        "trade_permission": False,
        "order_path": "NONE",
    }


def _persist_observations(
    settings: SupabaseConfig,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    response = requests.post(
        f"{settings.url}/rest/v1/{OBSERVATION_TABLE}",
        params={"on_conflict": "observation_id"},
        headers=_headers(
            settings,
            prefer="resolution=ignore-duplicates,return=minimal",
        ),
        data=json.dumps(rows, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            "V15 ranking observation persistence failed: "
            f"HTTP {response.status_code}"
        )


def _persist_run(
    settings: SupabaseConfig,
    *,
    run_id: str,
    checked_at: datetime,
    selection_run_id: str | None,
    target_count: int,
    succeeded_count: int,
    failed_count: int,
    legacy_ready_count: int,
    shadow_candidate_count: int,
    result_class: str,
    error_classes: Counter[str],
) -> None:
    row = {
        "challenger_run_id": run_id,
        "checked_at_utc": _iso(checked_at),
        "selection_run_id": selection_run_id,
        "target_count": target_count,
        "succeeded_count": succeeded_count,
        "failed_count": failed_count,
        "legacy_ready_would_be_count": legacy_ready_count,
        "shadow_candidate_count": shadow_candidate_count,
        "result_class": result_class,
        "error_classes": dict(error_classes),
        "public_get_only": True,
        "counted_in_v14": False,
        "production_selector_changed": False,
        "threshold_change_permitted": False,
        "production_promotion_permitted": False,
        "shadow_only": True,
        "trade_permission": False,
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
            f"V15 ranking run persistence failed: HTTP {response.status_code}"
        )


def main() -> int:
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    checked_at = datetime.now(timezone.utc)
    targets = _load_targets(settings)
    selection_run_id = (
        str(targets[0].get("selection_run_id") or "") if targets else None
    )
    run_id = hashlib.sha256(
        (
            f"{MODEL_VERSION}|{_iso(checked_at)}|{selection_run_id or 'NONE'}"
        ).encode("utf-8")
    ).hexdigest()[:32]

    if not targets:
        _persist_run(
            settings,
            run_id=run_id,
            checked_at=checked_at,
            selection_run_id=None,
            target_count=0,
            succeeded_count=0,
            failed_count=0,
            legacy_ready_count=0,
            shadow_candidate_count=0,
            result_class="NO_TARGETS",
            error_classes=Counter(),
        )
        print(json.dumps({
            "result_class": "NO_TARGETS",
            "target_count": 0,
            "counted_in_v14": False,
            "trade_permission": False,
            "order_path": "NONE",
        }, indent=2, sort_keys=True))
        return 0

    client = BitgetClient(timeout=8, max_retries=2)
    product_type = str(config.get("product_type", "usdt-futures"))

    btc_change_24h = 0.0
    try:
        btc_ticker = client.ticker("BTCUSDT", product_type)
        btc_change_24h = (
            to_float(btc_ticker.get("change24h")) or 0.0
        ) * 100.0
    except BitgetAPIError:
        btc_change_24h = 0.0

    rows: list[dict[str, Any]] = []
    errors: Counter[str] = Counter()
    succeeded = 0
    legacy_ready_count = 0
    shadow_candidate_total = 0

    for target in targets:
        record: dict[str, Any] | None = None
        error: Exception | None = None
        try:
            symbol = str(target.get("symbol") or "").upper()
            record = collect_symbol(client, symbol, config)
            apply_candidate_quality(record, None, btc_change_24h, config)
            engine = apply_multi_strategy_engine(record, None, config)
            legacy_ready_count += int(bool(record.get("v7_trade_ready", False)))
            if isinstance(engine, dict):
                shadow_candidate_total += int(
                    engine.get("shadow_candidate_count") or 0
                )
            succeeded += 1
        except (BitgetAPIError, RuntimeError, ValueError, TypeError) as exc:
            error = exc
            errors[exc.__class__.__name__] += 1

        rows.append(_build_observation(
            target=target,
            run_id=run_id,
            checked_at=checked_at,
            record=record,
            error=error,
        ))

    _persist_observations(settings, rows)

    failed = len(targets) - succeeded
    result_class = "PASS" if failed == 0 else "DEGRADED"
    _persist_run(
        settings,
        run_id=run_id,
        checked_at=checked_at,
        selection_run_id=selection_run_id,
        target_count=len(targets),
        succeeded_count=succeeded,
        failed_count=failed,
        legacy_ready_count=legacy_ready_count,
        shadow_candidate_count=shadow_candidate_total,
        result_class=result_class,
        error_classes=errors,
    )

    print(json.dumps({
        "result_class": result_class,
        "selection_run_id": selection_run_id,
        "target_count": len(targets),
        "succeeded_count": succeeded,
        "failed_count": failed,
        "legacy_ready_would_be_count": legacy_ready_count,
        "shadow_candidate_count": shadow_candidate_total,
        "error_classes": dict(errors),
        "public_get_only": True,
        "counted_in_v14": False,
        "production_selector_changed": False,
        "trade_permission": False,
        "order_path": "NONE",
    }, indent=2, sort_keys=True))

    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
