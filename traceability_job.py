from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.bitget import BitgetAPIError, BitgetClient
from alpha_hunter.collector import load_config, load_previous_snapshot
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage
from alpha_hunter.traceability import (
    TRACEABILITY_VERSION,
    ReadyEpisode,
    attach_fill_matches,
    readiness_diagnostic,
    rolling_summary,
    update_ready_ledger,
)


ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "signal-execution-ledger-7d.json"
HISTORY_PATH = ROOT / "data" / "signal-execution-ledger-history.jsonl"
WINDOW_HOURS = 168
MAX_FILL_PAGES = 20


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def supabase_headers(settings: SupabaseConfig) -> dict[str, str]:
    return {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
    }


def load_snapshot_window(
    settings: SupabaseConfig,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{settings.url}/rest/v1/{settings.snapshot_table}",
        params={
            "select": "run_id,collected_at_utc,payload",
            "collected_at_utc": f"gte.{iso(start)}",
            "order": "collected_at_utc.asc",
            "limit": "10000",
        },
        headers=supabase_headers(settings),
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "traceability snapshot load failed: "
            f"HTTP {response.status_code}: {response.text[:800]}"
        )
    payload = response.json()
    if not isinstance(payload, list):
        return []
    rows = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        collected = row.get("collected_at_utc")
        snapshot = row.get("payload")
        if not collected or not isinstance(snapshot, dict):
            continue
        try:
            collected_dt = datetime.fromisoformat(str(collected).replace("Z", "+00:00"))
            if collected_dt.tzinfo is None:
                collected_dt = collected_dt.replace(tzinfo=timezone.utc)
            collected_dt = collected_dt.astimezone(timezone.utc)
        except ValueError:
            continue
        if collected_dt > end:
            continue
        rows.append(snapshot)
    return rows


def snapshot_time(snapshot: dict[str, Any]) -> str:
    for key in (
        "collected_at_utc",
        "generated_at_utc",
        "detected_at_utc",
        "timestamp_utc",
        "created_at_utc",
    ):
        if snapshot.get(key):
            return str(snapshot[key])
    return iso(now_utc())


def rebuild_ready_episodes(
    snapshots: list[dict[str, Any]],
) -> list[ReadyEpisode]:
    episodes: list[ReadyEpisode] = []
    for snapshot in snapshots:
        symbols = snapshot.get("symbols") or []
        if not isinstance(symbols, list):
            continue
        update_ready_ledger(
            episodes,
            [row for row in symbols if isinstance(row, dict)],
            snapshot_time(snapshot),
        )
    return episodes


def load_fill_history(
    client: BitgetClient,
    product_type: str,
    start: datetime,
    end: datetime,
) -> tuple[str, list[dict[str, Any]]]:
    if not client.private_api_configured:
        return "NOT_CONFIGURED", []

    params: dict[str, Any] = {
        "productType": product_type,
        "startTime": str(int(start.timestamp() * 1000)),
        "endTime": str(int(end.timestamp() * 1000)),
        "limit": "100",
    }
    fills: list[dict[str, Any]] = []
    seen_trade_ids: set[str] = set()
    cursor: str | None = None

    for _ in range(MAX_FILL_PAGES):
        if cursor:
            params["idLessThan"] = cursor
        try:
            data = client._get(
                "/api/v2/mix/order/fill-history",
                params,
                private=True,
            )
        except BitgetAPIError as exc:
            return f"FAILED: {exc}", fills

        if not isinstance(data, dict):
            break
        page = data.get("fillList") or []
        if not isinstance(page, list) or not page:
            break
        added = 0
        for fill in page:
            if not isinstance(fill, dict):
                continue
            trade_id = str(fill.get("tradeId") or "")
            if trade_id and trade_id in seen_trade_ids:
                continue
            if trade_id:
                seen_trade_ids.add(trade_id)
            fills.append(fill)
            added += 1
        next_cursor = str(data.get("endId") or "").strip()
        if not next_cursor or next_cursor == cursor or added == 0:
            break
        cursor = next_cursor

    return "CONNECTED", fills


def save_cache(
    episodes: list[ReadyEpisode],
    summary: dict[str, Any],
    diagnostic: dict[str, Any],
    fill_status: str,
) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "traceability_version": TRACEABILITY_VERSION,
        "generated_at_utc": iso(now_utc()),
        "fill_history_status": fill_status,
        "summary": summary,
        "readiness_diagnostic": diagnostic,
        "episodes": [episode.to_dict() for episode in episodes],
    }
    temp = CACHE_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(CACHE_PATH)

    with HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def enrich_latest_snapshot(
    latest: dict[str, Any],
    episodes: list[ReadyEpisode],
    summary: dict[str, Any],
    diagnostic: dict[str, Any],
    fill_status: str,
    settings: SupabaseConfig,
) -> None:
    latest["signal_execution_traceability"] = {
        "version": TRACEABILITY_VERSION,
        "generated_at_utc": iso(now_utc()),
        "fill_history_status": fill_status,
        "summary": summary,
        "readiness_diagnostic": diagnostic,
        "ready_episodes": [episode.to_dict() for episode in episodes],
    }
    SupabaseStorage(settings).save_snapshot(latest)


def print_report(
    episodes: list[ReadyEpisode],
    summary: dict[str, Any],
    diagnostic: dict[str, Any],
    fill_status: str,
) -> None:
    print()
    print("=" * 96)
    print("ALPHA HUNTER — ROLLING 7-DAY SIGNAL → EXECUTION TRACEABILITY")
    print("=" * 96)
    print("Window:", summary["window_start_utc"], "→", summary["window_end_utc"])
    print("Bitget private fill history:", fill_status)
    print("Distinct TRADE READY coins:", summary["distinct_trade_ready_coins"])
    print("Distinct TRADE READY episodes:", summary["distinct_trade_ready_episodes"])
    print("TRADE READY LONG:", summary["trade_ready_long"])
    print("TRADE READY SHORT:", summary["trade_ready_short"])
    print("Heuristic execution matches:", summary["heuristically_matched_executions"])
    conversion = summary.get("ready_to_execution_pct")
    print(
        "READY → EXECUTION:",
        "N/A" if conversion is None else f"{conversion:.2f}%",
    )
    print("Unlinked open-like fills:", summary["unlinked_open_like_fill_count"])
    print("Traceability status:", summary["traceability_status"])
    print()
    if episodes:
        print("READY_ID | SYMBOL | DIR | FIRST READY | LAST READY | EXECUTION | MATCH")
        for episode in episodes:
            execution = episode.first_execution_at_utc or "—"
            quality = episode.execution_match_quality or "—"
            print(
                f"{episode.ready_id} | {episode.symbol} | {episode.direction} | "
                f"{episode.first_ready_at_utc} | {episode.last_ready_at_utc} | "
                f"{execution} | {quality}"
            )
    else:
        print("No strict production TRADE READY episodes in the rolling window.")
        print()
        print("READINESS BLOCKER DIAGNOSTIC — AUDIT ONLY / NO PERMISSION")
        print(
            "Evaluated candidate observations:",
            diagnostic.get("evaluated_candidate_observations", 0),
            "| Data-error observations:",
            diagnostic.get("data_error_observations", 0),
        )
        blockers = diagnostic.get("ranked_gate_blockers") or []
        if blockers:
            for row in blockers[:8]:
                print(
                    f"- {row['reason']}: {row['observations']} observations "
                    f"({row['observation_pct']:.2f}%)"
                )
        else:
            print("- No evaluated candidate observations were available.")

        closest = diagnostic.get("current_closest_candidates") or []
        if closest:
            print()
            print("CURRENT CLOSEST CANDIDATES — NOT TRADE READY")
            for row in closest:
                direction = row.get("direction") or "NONE"
                failed = ", ".join(row.get("failed_conditions") or []) or "NONE"
                details = (
                    (row.get("execution_check_failures") or [])
                    + (row.get("quality_rejections") or [])
                )
                detail_text = ", ".join(details) or "NONE"
                print(
                    f"- {row['symbol']} {direction}: "
                    f"{row['conditions_passed']}/{row['conditions_total']} conditions; "
                    f"failed={failed}; detail={detail_text}"
                )
    print("=" * 96)


def main() -> int:
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)
    end = now_utc()
    start = end - timedelta(hours=WINDOW_HOURS)

    latest = load_previous_snapshot(ROOT / "config.json", config)
    if not latest:
        raise SystemExit("No latest Alpha Hunter snapshot found")

    snapshots: list[dict[str, Any]]
    if settings is None:
        snapshots = [latest]
        print("TRACEABILITY DATA COVERAGE INCOMPLETE — Supabase not configured")
    else:
        snapshots = load_snapshot_window(settings, start, end)
        if not snapshots:
            snapshots = [latest]
            print("TRACEABILITY DATA COVERAGE INCOMPLETE — no stored seven-day snapshots")

    episodes = rebuild_ready_episodes(snapshots)

    client = BitgetClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=int(config.get("max_retries", 3)),
    )
    fill_status, fills = load_fill_history(
        client,
        str(config.get("product_type") or "usdt-futures"),
        start,
        end,
    )
    attach_fill_matches(episodes, fills)
    summary = rolling_summary(episodes, fills=fills, now_utc=end, hours=WINDOW_HOURS)

    quality = config.get("candidate_quality") or {}
    diagnostic = readiness_diagnostic(
        snapshots,
        minimum_execution_score=float(
            quality.get("minimum_execution_score", 7.5)
        ),
        minimum_execution_rr=float(
            quality.get("minimum_execution_reward_risk", 5.0)
        ),
    )

    save_cache(episodes, summary, diagnostic, fill_status)
    if settings is not None:
        enrich_latest_snapshot(
            latest,
            episodes,
            summary,
            diagnostic,
            fill_status,
            settings,
        )
    print_report(episodes, summary, diagnostic, fill_status)

    if summary["unlinked_open_like_fill_count"]:
        print("SIGNAL → EXECUTION TRACEABILITY FAILURE: unlinked open-like fills exist")
    if summary["distinct_trade_ready_episodes"] == 0:
        print("ZERO TRADE READY DIAGNOSTIC REQUIRED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
