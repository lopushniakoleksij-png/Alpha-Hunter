from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
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
    fill_timestamp,
    readiness_diagnostic,
    rolling_summary,
    update_ready_ledger,
)


ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "signal-execution-ledger-7d.json"
HISTORY_PATH = ROOT / "data" / "signal-execution-ledger-history.jsonl"
WINDOW_HOURS = 168
MAX_FILL_PAGES = 20
FILL_HISTORY_ENDPOINT = "/api/v2/mix/order/fills"
FILL_PAGE_LIMIT = 100
REQUIRED_FILL_FIELDS = (
    "tradeId",
    "orderId",
    "symbol",
    "cTime",
)


@dataclass
class FillHistoryResult:
    status: str
    fills: list[dict[str, Any]]
    coverage: dict[str, Any]


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


def fill_coverage_template(
    product_type: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    return {
        "endpoint": FILL_HISTORY_ENDPOINT,
        "product_type": product_type,
        "window_start_utc": iso(start),
        "window_end_utc": iso(end),
        "requested_page_limit": FILL_PAGE_LIMIT,
        "maximum_pages": MAX_FILL_PAGES,
        "pages_fetched": 0,
        "last_page_size": None,
        "fill_count": 0,
        "unique_trade_id_count": 0,
        "oldest_fill_at_utc": None,
        "newest_fill_at_utc": None,
        "schema_validated": False,
        "complete": False,
        "status": "NOT_STARTED",
        "detail": None,
    }


def finish_fill_history_result(
    status: str,
    fills: list[dict[str, Any]],
    coverage: dict[str, Any],
    *,
    complete: bool,
    schema_validated: bool,
    detail: str | None = None,
) -> FillHistoryResult:
    timestamps = [
        timestamp
        for fill in fills
        if (timestamp := fill_timestamp(fill)) is not None
    ]
    coverage.update(
        {
            "fill_count": len(fills),
            "unique_trade_id_count": len(
                {
                    str(fill.get("tradeId") or "").strip()
                    for fill in fills
                    if str(fill.get("tradeId") or "").strip()
                }
            ),
            "oldest_fill_at_utc": (
                min(timestamps).isoformat()
                if timestamps
                else None
            ),
            "newest_fill_at_utc": (
                max(timestamps).isoformat()
                if timestamps
                else None
            ),
            "schema_validated": schema_validated,
            "complete": complete,
            "status": status,
            "detail": detail,
        }
    )
    return FillHistoryResult(
        status=status,
        fills=fills,
        coverage=coverage,
    )


def invalid_fill_fields(fill: dict[str, Any]) -> list[str]:
    invalid = [
        field
        for field in REQUIRED_FILL_FIELDS
        if not str(fill.get(field) or "").strip()
    ]
    if "cTime" not in invalid and fill_timestamp(fill) is None:
        invalid.append("cTime")
    return invalid


def load_fill_history(
    client: BitgetClient,
    product_type: str,
    start: datetime,
    end: datetime,
) -> FillHistoryResult:
    coverage = fill_coverage_template(product_type, start, end)
    if not client.private_api_configured:
        return finish_fill_history_result(
            "NOT_CONFIGURED",
            [],
            coverage,
            complete=False,
            schema_validated=False,
            detail="Bitget private API credentials are not configured",
        )

    params: dict[str, Any] = {
        "productType": product_type,
        "startTime": str(int(start.timestamp() * 1000)),
        "endTime": str(int(end.timestamp() * 1000)),
        "limit": str(FILL_PAGE_LIMIT),
    }
    fills: list[dict[str, Any]] = []
    seen_trade_ids: set[str] = set()
    cursor: str | None = None

    for page_number in range(1, MAX_FILL_PAGES + 1):
        if cursor:
            params["idLessThan"] = cursor
        try:
            data = client._get(
                FILL_HISTORY_ENDPOINT,
                dict(params),
                private=True,
            )
        except BitgetAPIError as exc:
            return finish_fill_history_result(
                "FAILED",
                fills,
                coverage,
                complete=False,
                schema_validated=False,
                detail=f"Bitget fill request failed on page {page_number}: {exc}",
            )

        coverage["pages_fetched"] = page_number
        if not isinstance(data, dict):
            return finish_fill_history_result(
                "INVALID_SCHEMA",
                fills,
                coverage,
                complete=False,
                schema_validated=False,
                detail=(
                    f"Page {page_number} data must be an object containing "
                    "fillList and endId"
                ),
            )
        if "fillList" not in data or not isinstance(data["fillList"], list):
            return finish_fill_history_result(
                "INVALID_SCHEMA",
                fills,
                coverage,
                complete=False,
                schema_validated=False,
                detail=f"Page {page_number} fillList is missing or is not a list",
            )

        page = data["fillList"]
        coverage["last_page_size"] = len(page)
        if not page:
            status = "CONNECTED" if fills else "ZERO_FILLS"
            detail = None if fills else "The validated window returned zero fills"
            return finish_fill_history_result(
                status,
                fills,
                coverage,
                complete=True,
                schema_validated=True,
                detail=detail,
            )

        next_cursor = str(data.get("endId") or "").strip()
        if not next_cursor:
            return finish_fill_history_result(
                "INVALID_SCHEMA",
                fills,
                coverage,
                complete=False,
                schema_validated=False,
                detail=f"Page {page_number} endId is missing or empty",
            )

        for row_number, fill in enumerate(page, start=1):
            if not isinstance(fill, dict):
                return finish_fill_history_result(
                    "INVALID_SCHEMA",
                    fills,
                    coverage,
                    complete=False,
                    schema_validated=False,
                    detail=(
                        f"Page {page_number} fill {row_number} is not an object"
                    ),
                )
            invalid = invalid_fill_fields(fill)
            if invalid:
                return finish_fill_history_result(
                    "INVALID_SCHEMA",
                    fills,
                    coverage,
                    complete=False,
                    schema_validated=False,
                    detail=(
                        f"Page {page_number} fill {row_number} has invalid fields: "
                        + ", ".join(invalid)
                    ),
                )
            trade_id = str(fill["tradeId"]).strip()
            if trade_id in seen_trade_ids:
                continue
            seen_trade_ids.add(trade_id)
            fills.append(fill)

        if len(page) < FILL_PAGE_LIMIT:
            return finish_fill_history_result(
                "CONNECTED",
                fills,
                coverage,
                complete=True,
                schema_validated=True,
            )
        if next_cursor == cursor:
            return finish_fill_history_result(
                "PAGINATION_STALLED",
                fills,
                coverage,
                complete=False,
                schema_validated=True,
                detail=f"Bitget repeated endId on page {page_number}",
            )
        cursor = next_cursor

    return finish_fill_history_result(
        "PAGINATION_LIMIT_REACHED",
        fills,
        coverage,
        complete=False,
        schema_validated=True,
        detail=f"Fill retrieval reached the safety limit of {MAX_FILL_PAGES} pages",
    )


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
    coverage = summary.get("fill_history_coverage") or {}
    print()
    print("=" * 96)
    print("ALPHA HUNTER — ROLLING 7-DAY SIGNAL → EXECUTION TRACEABILITY")
    print("=" * 96)
    print("Window:", summary["window_start_utc"], "→", summary["window_end_utc"])
    print("Bitget private fill history:", fill_status)
    print("Fill endpoint:", coverage.get("endpoint") or "N/A")
    print(
        "Fill coverage:",
        f"fills={coverage.get('fill_count', 0)}",
        f"pages={coverage.get('pages_fetched', 0)}",
        f"complete={coverage.get('complete', False)}",
        f"schema_validated={coverage.get('schema_validated', False)}",
    )
    print(
        "Fill time range:",
        coverage.get("oldest_fill_at_utc") or "N/A",
        "→",
        coverage.get("newest_fill_at_utc") or "N/A",
    )
    if coverage.get("detail"):
        print("Fill coverage detail:", coverage["detail"])
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
            "across",
            diagnostic.get("snapshots_evaluated", 0),
            "snapshots",
            "| Data-error observations:",
            diagnostic.get("data_error_observations", 0),
        )
        print()
        print("ROOT-CAUSE GATE BLOCKERS — CONDITIONAL DENOMINATORS")
        blockers = diagnostic.get("ranked_root_gate_blockers") or []
        if blockers:
            for row in blockers[:8]:
                print(
                    f"- {row['reason']}: "
                    f"{row['failed_observations']}/"
                    f"{row['eligible_observations']} eligible failed "
                    f"({row['failure_pct_when_eligible']:.2f}%); "
                    f"{row['observation_pct']:.2f}% of all observations"
                )
        else:
            print("- No independent gate failures were observed.")

        composite = diagnostic.get("composite_trade_permission_gate") or {}
        if composite:
            print()
            print("COMPOSITE GATE — OUTCOME, NOT INDEPENDENT ROOT CAUSE")
            print(
                f"- {composite.get('gate', 'TRADE_PERMISSION')}: "
                f"{composite.get('failed_observations', 0)} failed "
                f"({composite.get('observation_pct', 0.0):.2f}%); "
                "depends on execution setup checks"
            )

        score_distribution = (
            diagnostic.get("behaviour_score_distribution") or {}
        )
        rr_distribution = (
            diagnostic.get("reward_risk_distribution_directional") or {}
        )
        print()
        print("GATE REACHABILITY — OBSERVED DATA / THRESHOLDS UNCHANGED")
        print(
            "- EXECUTION_SCORE: "
            f"median={score_distribution.get('median')} "
            f"p90={score_distribution.get('p90')} "
            f"max={score_distribution.get('maximum_observed')} | "
            f"met={score_distribution.get('meeting_minimum_observations', 0)}/"
            f"{score_distribution.get('eligible_observations', 0)} "
            f"(required >= {score_distribution.get('required_minimum')})"
        )
        print(
            "- EXECUTION_RR (directional cohort): "
            f"median={rr_distribution.get('median')} "
            f"p90={rr_distribution.get('p90')} "
            f"max={rr_distribution.get('maximum_observed')} | "
            f"met={rr_distribution.get('meeting_minimum_observations', 0)}/"
            f"{rr_distribution.get('eligible_observations', 0)} "
            f"(required >= {rr_distribution.get('required_minimum')})"
        )

        execution_failures = (
            diagnostic.get(
                "ranked_execution_check_failures_when_evaluated"
            )
            or []
        )
        if execution_failures:
            print()
            print("EXECUTION CHECK FAILURES — WHEN CHECK WAS EVALUATED")
            for row in execution_failures[:8]:
                print(
                    f"- {row['reason']}: "
                    f"{row['failed_observations']}/"
                    f"{row['eligible_observations']} failed "
                    f"({row['failure_pct_when_eligible']:.2f}%)"
                )

        closest = diagnostic.get("current_closest_candidates") or []
        if closest:
            print()
            print("CURRENT CLOSEST CANDIDATES — NOT TRADE READY")
            for row in closest:
                direction = row.get("direction") or "NONE"
                failed = ", ".join(
                    row.get("failed_independent_conditions") or []
                ) or "NONE"
                details = (
                    (row.get("execution_check_failures") or [])
                    + (row.get("quality_rejections") or [])
                )
                detail_text = ", ".join(details) or "NONE"
                reward_risk = row.get("reward_risk")
                required_rr = row.get("minimum_reward_risk")
                rr_text = (
                    "N/A"
                    if reward_risk is None
                    else f"{reward_risk:.2f}/{required_rr:.2f} required"
                )
                geometry = row.get("execution_geometry") or {}
                risk_pct = geometry.get("risk_pct_of_entry")
                reward_pct = geometry.get("reward_pct_of_entry")
                geometry_text = (
                    "N/A"
                    if risk_pct is None or reward_pct is None
                    else f"risk={risk_pct:.2f}% reward={reward_pct:.2f}%"
                )
                print(
                    f"- {row['symbol']} {direction}: "
                    f"{row['independent_conditions_passed']}/"
                    f"{row['independent_conditions_total']} independent conditions; "
                    f"RR={rr_text}; {geometry_text}; "
                    f"failed_independent={failed}; "
                    f"trade_permission={row.get('trade_permission')}; "
                    f"detail={detail_text}"
                )
    print("=" * 96)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Alpha Hunter signal-to-execution traceability",
    )
    parser.add_argument(
        "--fill-history-smoke-test",
        action="store_true",
        help=(
            "read and validate Bitget fill-history coverage without writing "
            "snapshots, caches, orders, or account changes"
        ),
    )
    return parser.parse_args(argv)


def run_fill_history_smoke_test(config: dict[str, Any]) -> int:
    end = now_utc()
    start = end - timedelta(hours=WINDOW_HOURS)
    client = BitgetClient.from_environment(
        timeout=int(config.get("request_timeout_seconds", 12)),
        max_retries=int(config.get("max_retries", 3)),
    )
    result = load_fill_history(
        client,
        str(config.get("product_type") or "usdt-futures"),
        start,
        end,
    )
    pass_eligible = bool(
        result.status == "CONNECTED"
        and result.coverage.get("complete") is True
        and result.coverage.get("schema_validated") is True
        and result.coverage.get("fill_count", 0) > 0
    )
    print("ALPHA HUNTER — READ-ONLY BITGET FILL-HISTORY SMOKE TEST")
    print("No orders, snapshots, caches, or account changes are performed.")
    print(json.dumps(result.coverage, indent=2, sort_keys=True))
    print("Smoke-test status:", "PASS" if pass_eligible else "INCOMPLETE")
    return 0 if pass_eligible else 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    if args.fill_history_smoke_test:
        return run_fill_history_smoke_test(config)

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
    fill_history = load_fill_history(
        client,
        str(config.get("product_type") or "usdt-futures"),
        start,
        end,
    )
    fill_status = fill_history.status
    fills = fill_history.fills
    attach_fill_matches(episodes, fills)
    summary = rolling_summary(
        episodes,
        fills=fills,
        now_utc=end,
        hours=WINDOW_HOURS,
        fill_history_coverage=fill_history.coverage,
    )

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
    if summary["traceability_status"] == "FAIL":
        return 1
    if summary["traceability_status"] != "PASS":
        print("SIGNAL → EXECUTION TRACEABILITY INCOMPLETE: fill coverage is untrusted")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
