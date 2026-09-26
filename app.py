from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template_string, request

from alpha_hunter.services.statistics import StatisticsService
from performance_page import PERFORMANCE_PAGE


app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SNAPSHOT_TABLE = os.getenv("ALPHA_HUNTER_SNAPSHOT_TABLE", "alpha_hunter_snapshots")
APP_VERSION = os.getenv("ALPHA_HUNTER_VERSION", "7.2")
CANONICAL_RUN_SOURCE = os.getenv(
    "ALPHA_HUNTER_CANONICAL_RUN_SOURCE",
    "RENDER_CRON",
).strip().upper()
SERVICE_STARTED_AT_UTC = datetime.now(timezone.utc).isoformat()

SUPABASE_READ_ATTEMPTS = 3
SUPABASE_READ_TIMEOUT_SECONDS = 12
SUPABASE_RETRY_BACKOFF_SECONDS = 0.75
SUPABASE_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

REFERENCE_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}

scan_lock = threading.Lock()
scan_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": "idle",
    "error": None,
    "return_code": None,
}


def load_runtime_config() -> dict[str, Any]:
    path = Path(__file__).resolve().with_name("config.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


RUNTIME_CONFIG = load_runtime_config()
MINIMUM_EXECUTION_RR = float(
    RUNTIME_CONFIG.get("candidate_quality", {}).get(
        "minimum_execution_reward_risk",
        RUNTIME_CONFIG.get("minimum_reward_risk", 5.0),
    )
)


def build_identity() -> dict[str, Any]:
    """Return non-secret runtime identity for production traceability.

    Render provides the Git commit and branch at runtime. Render does not expose
    a documented deploy timestamp, so the service start time is used as an
    explicit fallback unless ALPHA_HUNTER_DEPLOYED_AT_UTC is injected by a
    deployment workflow.
    """
    commit = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or "unknown"
    deployed_at = os.getenv("ALPHA_HUNTER_DEPLOYED_AT_UTC") or SERVICE_STARTED_AT_UTC
    deployed_at_source = (
        "deployment_environment"
        if os.getenv("ALPHA_HUNTER_DEPLOYED_AT_UTC")
        else "process_start_fallback"
    )
    return {
        "version": APP_VERSION,
        "git_commit": commit,
        "git_commit_short": commit[:7] if commit != "unknown" else "unknown",
        "git_branch": os.getenv("RENDER_GIT_BRANCH") or os.getenv("GIT_BRANCH") or "unknown",
        "git_repo": os.getenv("RENDER_GIT_REPO_SLUG") or "unknown",
        "render_service": os.getenv("RENDER_SERVICE_NAME") or "unknown",
        "render_instance_id": os.getenv("RENDER_INSTANCE_ID") or "unknown",
        "deployed_at_utc": deployed_at,
        "deployed_at_source": deployed_at_source,
        "service_started_at_utc": SERVICE_STARTED_AT_UTC,
    }


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def supabase_get_rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Read Supabase with bounded retries for transient infrastructure failures.

    Dashboard reads are idempotent. We retry only connection failures and
    transient HTTP statuses, then fail closed rather than displaying stale
    trading evidence as if it were current.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase environment variables are not configured")

    for attempt in range(1, SUPABASE_READ_ATTEMPTS + 1):
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}",
                params=params,
                headers=supabase_headers(),
                timeout=SUPABASE_READ_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            if attempt >= SUPABASE_READ_ATTEMPTS:
                raise
            time.sleep(SUPABASE_RETRY_BACKOFF_SECONDS * attempt)
            continue

        if (
            response.status_code in SUPABASE_TRANSIENT_STATUSES
            and attempt < SUPABASE_READ_ATTEMPTS
        ):
            time.sleep(SUPABASE_RETRY_BACKOFF_SECONDS * attempt)
            continue

        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected Supabase response shape")
        return rows

    raise RuntimeError("Supabase read retry budget exhausted")


def _hydrate_dashboard_snapshot(
    row: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    snapshot = dict(payload)
    snapshot.setdefault("run_id", row.get("run_id"))
    snapshot.setdefault("collected_at_utc", row.get("collected_at_utc"))

    if snapshot.get("_storage_contract") != "snapshot-parent-v0.2":
        return snapshot

    run_id = str(snapshot.get("run_id") or "")
    if not run_id:
        raise RuntimeError("Compact canonical snapshot is missing run_id")

    children = supabase_get_rows(
        "alpha_hunter_symbol_snapshots",
        {
            "select": "symbol,payload",
            "run_id": f"eq.{run_id}",
            "order": "symbol.asc",
            "limit": "2000",
        },
    )
    snapshot["symbols"] = [
        child.get("payload")
        for child in children
        if isinstance(child, dict)
        and isinstance(child.get("payload"), dict)
    ]
    return snapshot


def latest_snapshot() -> dict[str, Any]:
    params = {
        "select": "run_id,collected_at_utc,version,symbol_count,error_count,payload",
        "order": "collected_at_utc.desc",
        "limit": "1",
    }
    if CANONICAL_RUN_SOURCE:
        params["payload->validation_identity->>run_source"] = (
            f"eq.{CANONICAL_RUN_SOURCE}"
        )

    rows = supabase_get_rows(SNAPSHOT_TABLE, params)
    if not rows:
        raise RuntimeError(
            "No Alpha Hunter snapshots found for canonical run source "
            f"{CANONICAL_RUN_SOURCE or '<ANY>'}"
        )

    row = rows[0]
    payload = row.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("Canonical snapshot payload is missing")

    if CANONICAL_RUN_SOURCE:
        identity = payload.get("validation_identity")
        if not isinstance(identity, dict):
            raise RuntimeError("Canonical snapshot is missing validation identity")
        actual_source = str(identity.get("run_source") or "").upper()
        if actual_source != CANONICAL_RUN_SOURCE:
            raise RuntimeError(
                "Canonical snapshot source mismatch: "
                f"expected {CANONICAL_RUN_SOURCE}, got {actual_source or '<NONE>'}"
            )

    return _hydrate_dashboard_snapshot(row, payload)


def latest_test_engine_status() -> dict[str, Any]:
    try:
        rows = supabase_get_rows(
            "alpha_hunter_test_engine_latest_v01",
            {"select": "*", "limit": "1"},
        )
        if rows and isinstance(rows[0], dict):
            return rows[0]
    except (requests.RequestException, RuntimeError, ValueError):
        return {}
    return {}

def latest_control_tower_status() -> dict[str, Any]:
    rows = supabase_get_rows(
        "alpha_hunter_v14_watchdog_status_v01",
        {"select": "*", "limit": "1"},
    )
    if not rows or not isinstance(rows[0], dict):
        raise RuntimeError("V14 control-tower status is unavailable")
    return rows[0]


def latest_control_tower_events(limit: int = 12) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 50))
    rows = supabase_get_rows(
        "alpha_hunter_v14_watchdog_events_v01",
        {
            "select": (
                "checked_at_utc,spec_id,status,critical_alerts,"
                "warning_alerts,expected_gates,payload,"
                "trade_permission,order_path"
            ),
            "order": "checked_at_utc.desc",
            "limit": str(bounded_limit),
        },
    )
    return [row for row in rows if isinstance(row, dict)]


def control_tower_payload() -> dict[str, Any]:
    status = latest_control_tower_status()
    return {
        "status": status,
        "events": latest_control_tower_events(),
        "build": build_identity(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def execution_checks(row: dict[str, Any]) -> dict[str, bool]:
    setup = row.get("execution_setup", {})
    raw = setup.get("checks", {})
    return {
        "direction": raw.get("direction_aligned") is True,
        "structure": raw.get("structure_valid") is True,
        "momentum": raw.get("momentum_confirmed") is True,
        "participation": raw.get("participation_confirmed") is True,
        "funding": raw.get("funding_not_extreme") is True,
        "integrity": raw.get("data_integrity_min_88") is True,
        "rr": raw.get("rr_minimum_met") is True,
    }


def required_entry_for_rr(
    stop: float,
    target: float,
    minimum_rr: float,
) -> float | None:
    if minimum_rr <= 0 or stop == target:
        return None
    return (target + minimum_rr * stop) / (minimum_rr + 1.0)


def build_money_action(row: dict[str, Any]) -> dict[str, Any]:
    """Turn scanner evidence into an explicit execution state.

    Discovery is never presented as an execution recommendation. A READY_NOW
    action requires the existing V7 execution permission. A RETEST_PLAN is only
    calculated when every core execution check except remaining R already passes,
    the current market phase is still an allowed pre/early phase, and a better
    price can restore the configured minimum R:R without crossing invalidation.
    """
    setup = row.get("execution_setup", {})
    checks = execution_checks(row)
    direction = str(setup.get("direction") or "").upper()
    current = safe_optional_float(row.get("last_price"))
    stop = safe_optional_float(setup.get("stop"))
    target = safe_optional_float(setup.get("target"))
    rr = safe_optional_float(setup.get("rr"))
    phase = str(row.get("market_phase") or "")
    timing = str(row.get("opportunity_timing") or "")
    rejections = list(row.get("rejection_reasons") or [])

    if bool(row.get("v7_trade_ready")):
        return {
            "status": "READY_NOW",
            "label": "EXECUTE NOW",
            "priority": 3,
            "direction": direction,
            "entry": current,
            "stop": stop,
            "target": target,
            "rr": rr,
            "minimum_rr": MINIMUM_EXECUTION_RR,
            "distance_pct": 0.0,
            "reason": "All existing V7 execution gates passed.",
            "cancel": "Cancel if structure invalidates or execution evidence changes before entry.",
        }

    core_without_rr = all(
        checks[name]
        for name in (
            "direction",
            "structure",
            "momentum",
            "participation",
            "funding",
            "integrity",
        )
    )

    allowed_retest_phase = phase in {
        "ACCUMULATION",
        "COMPRESSION",
        "RECOVERY",
        "IGNITION",
    }

    if (
        core_without_rr
        and not checks["rr"]
        and allowed_retest_phase
        and direction in {"LONG", "SHORT"}
        and current is not None
        and stop is not None
        and target is not None
    ):
        required = required_entry_for_rr(stop, target, MINIMUM_EXECUTION_RR)
        geometry_ok = False
        if required is not None:
            if direction == "LONG":
                geometry_ok = stop < required < current < target
            else:
                geometry_ok = target < current < required < stop

        if geometry_ok and required is not None:
            distance_pct = abs(required - current) / current * 100 if current else None
            return {
                "status": "RETEST_PLAN",
                "label": "BEST RETEST / LIMIT ZONE",
                "priority": 2,
                "direction": direction,
                "entry": required,
                "stop": stop,
                "target": target,
                "rr": MINIMUM_EXECUTION_RR,
                "minimum_rr": MINIMUM_EXECUTION_RR,
                "distance_pct": distance_pct,
                "reason": (
                    "Signal quality passes, but the current price is too late. "
                    "This is the nearest price that restores the configured minimum R:R."
                ),
                "cancel": (
                    "Do not use the zone if direction, momentum or participation has failed by retest, "
                    "or if structural invalidation is reached first."
                ),
            }

    failed = [name for name, passed in checks.items() if not passed]
    reason = "Blocked: " + ", ".join(failed) if failed else "No executable geometry"
    if rejections:
        reason += ". Quality: " + ", ".join(rejections)

    return {
        "status": "RESEARCH_ONLY",
        "label": "RESEARCH / WATCH",
        "priority": 0,
        "direction": direction or None,
        "entry": None,
        "stop": stop,
        "target": target,
        "rr": rr,
        "minimum_rr": MINIMUM_EXECUTION_RR,
        "distance_pct": None,
        "reason": reason,
        "cancel": None,
        "phase": phase,
        "timing": timing,
    }


def build_strategy_money_action(strategy: dict[str, Any]) -> dict[str, Any] | None:
    """Promote an S1-S10 SHADOW_CANDIDATE into the decision-support action queue.

    This does not grant exchange/order authority. It only makes the strategy
    engine's already-gated 5R candidate visible to the Money Action layer.
    """
    if str(strategy.get("status") or "") != "SHADOW_CANDIDATE":
        return None

    proposed = str(
        strategy.get("action")
        or strategy.get("proposed_action")
        or ""
    ).upper()
    direction = str(strategy.get("direction") or "").upper()
    entry = safe_optional_float(strategy.get("entry"))
    stop = safe_optional_float(strategy.get("stop"))
    target = safe_optional_float(strategy.get("target"))
    rr = safe_optional_float(strategy.get("rr"))

    if (
        proposed not in {"EXECUTE_NOW", "PLACE_LIMIT"}
        or direction not in {"LONG", "SHORT"}
        or entry is None
        or stop is None
        or target is None
        or rr is None
        or rr < MINIMUM_EXECUTION_RR
    ):
        return None

    if direction == "LONG":
        geometry_ok = stop < entry < target
    else:
        geometry_ok = target < entry < stop
    if not geometry_ok:
        return None

    execute_now = proposed == "EXECUTE_NOW"
    return {
        "status": (
            "STRATEGY_READY_NOW"
            if execute_now
            else "STRATEGY_LIMIT_READY"
        ),
        "label": (
            "READY SETUP — EXECUTE NOW"
            if execute_now
            else "READY SETUP — PLACE LIMIT"
        ),
        "priority": 4 if execute_now else 3,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "minimum_rr": MINIMUM_EXECUTION_RR,
        "distance_pct": safe_optional_float(
            strategy.get("distance_to_entry_pct")
        ) or 0.0,
        "reason": (
            f"{strategy.get('strategy_id','S?')} "
            f"{strategy.get('strategy_name','strategy')} passed its signal, "
            "shared safety/data gates, valid geometry and the configured 5R minimum. "
            "Decision support only; order authority remains disabled."
        ),
        "cancel": (
            "Cancel if direction, participation, liquidity/funding safety, "
            "or structural invalidation changes before entry."
        ),
        "strategy_id": strategy.get("strategy_id"),
        "strategy_name": strategy.get("strategy_name"),
        "execution_authority": False,
    }


def dashboard_payload(
    snapshot: dict[str, Any],
    test_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbols = [
        dict(row)
        for row in snapshot.get("symbols", [])
        if "error" not in row
    ]

    for row in symbols:
        intel = row.get("intelligence", {})
        setup = row.get("execution_setup", {})
        row["_score"] = safe_float(intel.get("huge_rr_score"))
        row["_confidence"] = safe_float(intel.get("confidence_estimate_pct"))
        row["_behaviour"] = safe_float(row.get("behaviour_score"))
        row["_rr"] = setup.get("rr")
        row["_direction"] = setup.get("direction")
        row["_trade"] = bool(row.get("v7_trade_ready"))
        row["_discovery"] = bool(row.get("discovery_permission"))
        row["_phase"] = row.get("market_phase", "—")
        row["_timing"] = row.get("opportunity_timing", "—")
        row["_reference"] = row.get("symbol") in REFERENCE_SYMBOLS
        row["_rejection"] = ", ".join(row.get("rejection_reasons") or [])
        row["_action"] = build_money_action(row)
        engine = row.get("multi_strategy_engine", {})
        row["_strategies"] = list(engine.get("strategies", [])) if isinstance(engine, dict) else []

    discovery_symbols = [row for row in symbols if not row["_reference"]]

    strategy_shadow = []
    for row in discovery_symbols:
        for strategy in row["_strategies"]:
            if not isinstance(strategy, dict):
                continue
            item = dict(strategy)
            item["symbol"] = row.get("symbol")
            item["price"] = row.get("last_price")
            persistence = item.get("persistence")
            if not isinstance(persistence, dict):
                persistence = {}
            item["_persistence_state"] = str(persistence.get("state") or "—")
            item["_consecutive_scans"] = int(persistence.get("consecutive_scans") or 0)
            strategy_shadow.append(item)

    strategy_status_priority = {
        "SHADOW_CANDIDATE": 4,
        "WATCH": 3,
        "DATA_INSUFFICIENT": 2,
        "NO_SETUP": 1,
        "DISABLED": 0,
    }
    strategy_shadow.sort(
        key=lambda item: (
            strategy_status_priority.get(str(item.get("status")), 0),
            safe_float(item.get("signal_score")),
            safe_float(item.get("rr")),
        ),
        reverse=True,
    )

    strategy_ready = []
    for item in strategy_shadow:
        action = build_strategy_money_action(item)
        if action is None:
            continue
        strategy_ready.append({
            "symbol": item.get("symbol"),
            "last_price": item.get("price"),
            "state": item.get("status"),
            "_strategy": True,
            "_score": safe_float(item.get("signal_score")),
            "_behaviour": 0.0,
            "_action": action,
            "_strategy_payload": item,
        })

    actionable = sorted(
        [row for row in discovery_symbols if row["_action"]["priority"] > 0],
        key=lambda row: (
            row["_action"]["priority"],
            -safe_float(row["_action"].get("distance_pct")),
            row["_behaviour"],
            row["_score"],
        ),
        reverse=True,
    )

    ranked_research = sorted(
        discovery_symbols,
        key=lambda row: (
            row["_discovery"],
            row["_behaviour"],
            row["_score"],
        ),
        reverse=True,
    )

    trade_ready = [row for row in actionable if row["_action"]["status"] == "READY_NOW"]
    retest_plans = [row for row in actionable if row["_action"]["status"] == "RETEST_PLAN"]

    combined_actionable = sorted(
        actionable + strategy_ready,
        key=lambda row: (
            row["_action"]["priority"],
            -safe_float(row["_action"].get("distance_pct")),
            safe_float(row.get("_behaviour")),
            safe_float(row.get("_score")),
        ),
        reverse=True,
    )
    best_action = combined_actionable[0] if combined_actionable else None

    account = snapshot.get("private_account", {})
    universe = snapshot.get("universe", {})
    strategy_summary = snapshot.get("multi_strategy_summary", {})
    if not isinstance(strategy_summary, dict):
        strategy_summary = {}
    microstructure_summary = snapshot.get("microstructure_summary", {})
    if not isinstance(microstructure_summary, dict):
        microstructure_summary = {}
    catalyst_summary = snapshot.get("catalyst_summary", {})
    if not isinstance(catalyst_summary, dict):
        catalyst_summary = {}
    previous_snapshot_context = snapshot.get("previous_snapshot_context", {})
    if not isinstance(previous_snapshot_context, dict):
        previous_snapshot_context = {}
    evaluations = strategy_summary.get("evaluations_by_strategy", {})
    candidates = strategy_summary.get("candidates_by_strategy", {})
    strategy_coverage = [
        {
            "strategy_id": f"S{index}",
            "evaluations": int((evaluations or {}).get(f"S{index}", 0) or 0),
            "candidates": int((candidates or {}).get(f"S{index}", 0) or 0),
        }
        for index in range(1, 11)
    ]

    return {
        "snapshot": snapshot,
        "best_action": best_action,
        "actionable": combined_actionable[:10],
        "trade_ready": trade_ready,
        "strategy_ready": strategy_ready[:10],
        "retest_plans": retest_plans,
        "research": ranked_research[:25],
        "strategy_shadow": strategy_shadow[:60],
        "strategy_summary": strategy_summary,
        "microstructure_summary": microstructure_summary,
        "catalyst_summary": catalyst_summary,
        "previous_snapshot_context": previous_snapshot_context,
        "strategy_coverage": strategy_coverage,
        "references": sorted(
            [row for row in symbols if row["_reference"]],
            key=lambda row: row.get("symbol", ""),
        ),
        "positions": account.get("open_positions", []),
        "account_status": account.get("status", "UNKNOWN"),
        "universe": universe,
        "updated": snapshot.get("collected_at_utc"),
        "btc_change_24h": safe_float(snapshot.get("btc_change_24h_pct")),
        "minimum_execution_rr": MINIMUM_EXECUTION_RR,
        "discovery_summary": snapshot.get("discovery_summary", {}),
        "build": build_identity(),
        "test_engine": test_engine or {},
    }


def run_scan_worker() -> None:
    project_root = os.path.dirname(os.path.abspath(__file__))
    with scan_lock:
        scan_state.update(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            status="running",
            error=None,
            return_code=None,
        )

    try:
        scan_env = os.environ.copy()
        scan_env["ALPHA_HUNTER_RUN_SOURCE"] = "RENDER_WEB"
        scan_env["ALPHA_HUNTER_RUNTIME_ROLE"] = "RENDER_WEB"

        completed = subprocess.run(
            [sys.executable, "run.py"],
            cwd=project_root,
            env=scan_env,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        with scan_lock:
            scan_state["return_code"] = completed.returncode
            if completed.returncode == 0:
                scan_state["status"] = "completed"
                scan_state["error"] = None
            else:
                scan_state["status"] = "failed"
                scan_state["error"] = (completed.stderr or completed.stdout or "Unknown scanner error").strip()[-5000:]
    except subprocess.TimeoutExpired:
        with scan_lock:
            scan_state["status"] = "failed"
            scan_state["error"] = "Scan timed out after 15 minutes"
    except Exception as exc:
        with scan_lock:
            scan_state["status"] = "failed"
            scan_state["error"] = f"Unable to run scanner: {exc}"
    finally:
        with scan_lock:
            scan_state["running"] = False
            scan_state["finished_at"] = datetime.now(timezone.utc).isoformat()


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Alpha Hunter V7.2 — Money Action</title>
<style>
:root{--bg:#071018;--panel:#0d1822;--line:#1c2c39;--text:#e8f0f6;--muted:#8ea1b2;--green:#24d18f;--red:#ff6474;--amber:#ffbf47;--blue:#4db6ff}
*{box-sizing:border-box} body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:20px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;margin-bottom:18px}
h1{margin:0;font-size:28px}.sub,.muted,.small{color:var(--muted)}.small{font-size:12px}.panel,.card{background:rgba(13,24,34,.96);border:1px solid var(--line);border-radius:16px}.panel{padding:18px;margin-bottom:16px}.cards{display:grid;grid-template-columns:repeat(9,1fr);gap:12px;margin-bottom:16px}.card{padding:14px}.label{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:24px;font-weight:800;margin-top:4px}
.action-ready{border-color:#1f6a50;box-shadow:0 0 0 1px rgba(36,209,143,.15)}.action-retest{border-color:#7a6224}.action-none{border-color:#314454}.action-title{font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.ready{color:var(--green)}.retest{color:var(--amber)}.reject,.short{color:var(--red)}.long{color:var(--green)}
.action-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:14px}.metric{background:#09131c;border:1px solid #162734;border-radius:12px;padding:11px}.metric b{display:block;margin-top:4px;font-size:16px}.reason{margin-top:12px;padding:11px;border-left:3px solid var(--blue);background:#09131c;color:#b9c7d2;font-size:13px;line-height:1.45}
.layout{display:grid;grid-template-columns:3fr 1fr;gap:16px}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:var(--muted);padding:9px 6px;border-bottom:1px solid var(--line)}td{padding:10px 6px;border-bottom:1px solid #142431;white-space:nowrap}.wrap-cell{white-space:normal;min-width:180px}.badge{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid var(--line);font-size:10px;font-weight:700}.badge-ready{color:var(--green);border-color:#1f6a50}.badge-retest{color:var(--amber);border-color:#7a6224}.badge-research{color:var(--muted)}
.run-button{border:1px solid #1f6a50;background:#123b2d;color:var(--green);padding:10px 14px;border-radius:10px;font-weight:800;cursor:pointer}.run-button:disabled{opacity:.5}.status{padding:9px 12px;border:1px solid var(--line);border-radius:999px;background:var(--panel);font-size:12px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.side-row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid #142431;font-size:12px}.empty{color:var(--muted);padding:16px 0}.warning{color:var(--amber)}
@media(max-width:1000px){.cards{grid-template-columns:repeat(2,1fr)}.layout{grid-template-columns:1fr}.action-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:650px){.wrap{padding:12px}.top{align-items:flex-start;flex-direction:column}.cards{grid-template-columns:1fr 1fr}.action-grid{grid-template-columns:1fr 1fr}table{display:block;overflow-x:auto}h1{font-size:24px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><h1>Alpha Hunter V{{ data.build.version }}</h1><div class="sub">Execution first. Discovery is research until it becomes a money action.</div><div class="small" style="margin-top:5px">Build {{ data.build.git_commit_short }} · {{ data.build.git_branch }} · deployed {{ data.build.deployed_at_utc }}{% if data.build.deployed_at_source == 'process_start_fallback' %} (instance-start fallback){% endif %}</div></div>
    <div><div class="toolbar"><a href="/control-tower" style="color:#4db6ff;text-decoration:none">V14 Control Tower</a><a href="/performance" style="color:#4db6ff;text-decoration:none">Performance</a><button id="runScanButton" class="run-button" onclick="runScan()">Run Fresh Scan</button><div class="status">Updated {{ data.updated or 'Unavailable' }}</div></div><div id="scanMessage" class="small" style="margin-top:7px;text-align:right">Scanner ready</div></div>
  </div>

  <div class="cards">
    <div class="card"><div class="label">Universe</div><div class="value">{{ data.universe.get('selected_count',0) }}</div><div class="small">deep-scanned</div></div>
    <div class="card"><div class="label">Ready now</div><div class="value ready">{{ data.trade_ready|length }}</div><div class="small">strict execution</div></div>
    <div class="card"><div class="label">Retest plans</div><div class="value warning">{{ data.retest_plans|length }}</div><div class="small">price must come to us</div></div>
    <div class="card"><div class="label">Minimum R:R</div><div class="value">{{ '%.1f'|format(data.minimum_execution_rr) }}R</div><div class="small">not relaxed</div></div>
    <div class="card"><div class="label">BTC 24H</div><div class="value {{ 'long' if data.btc_change_24h>0 else 'short' if data.btc_change_24h<0 else '' }}">{{ '%.2f'|format(data.btc_change_24h) }}%</div><div class="small">regime reference</div></div>
    <div class="card"><div class="label">Strategies</div><div class="value">{{ data.strategy_summary.get('configured_strategy_count',0) }}</div><div class="small">S1-S10 shadow · {{ data.strategy_summary.get('shadow_candidate_count',0) }} candidates</div></div>
    <div class="card"><div class="label">Microstructure</div><div class="value">{{ data.microstructure_summary.get('complete_count',0) }}/{{ data.microstructure_summary.get('eligible_symbol_count',0) }}</div><div class="small">Bitget depth + public trades</div></div>
    <div class="card"><div class="label">Persistent</div><div class="value">{{ data.strategy_summary.get('persistent_continuing_count',0) }}</div><div class="small">strategy signals continuing</div></div>
    <div class="card"><div class="label">Catalysts</div><div class="value">{{ data.catalyst_summary.get('fresh_bound_symbol_count',0) }}</div><div class="small">fresh official Bitget matches</div></div>
  </div>

  <div class="panel">
    <h2 style="margin-top:0">Real-Time Profitability Test Engine</h2>
    {% if data.test_engine %}
      <div class="action-grid">
        <div class="metric"><span class="label">Operational</span><b>{{ data.test_engine.get('operational_status','UNKNOWN') }}</b></div>
        <div class="metric"><span class="label">Verdict</span><b>{{ data.test_engine.get('verdict','NOT_PROVEN') }}</b></div>
        <div class="metric"><span class="label">Real scans</span><b>{{ data.test_engine.get('real_scans_since_registration',0) }}</b></div>
        <div class="metric"><span class="label">Paper trades</span><b>{{ data.test_engine.get('completed_paper_trades',0) }}/{{ data.test_engine.get('minimum_completed_paper_trades',100) }}</b></div>
        <div class="metric"><span class="label">Test days</span><b>{{ '%.2f'|format(data.test_engine.get('test_days_elapsed',0) or 0) }}/{{ data.test_engine.get('minimum_test_days',30) }}</b></div>
        <div class="metric"><span class="label">24H outcomes</span><b>{{ data.test_engine.get('real_24h_forward_outcomes_since_registration',0) }}</b></div>
      </div>
      <div class="reason">
        <b>Real-time:</b> {{ data.test_engine.get('evaluated_at_utc') }}<br>
        <b>Latest market scan:</b> {{ data.test_engine.get('latest_live_scan_at_utc') }}<br>
        <b>Profitability status:</b> {{ data.test_engine.get('profitability_status') }}<br>
        <b>Blockers:</b> {{ (data.test_engine.get('blockers') or [])|join(', ') if data.test_engine.get('blockers') else 'NONE' }}<br>
        <span class="small">Forward-only real market evidence. Historical replay/backtest is not counted. Paper-only; no order authority.</span>
      </div>
    {% else %}
      <div class="empty">No test-engine evaluation has been persisted yet. The hourly real-time test runner will populate this panel.</div>
    {% endif %}
  </div>

  {% if data.best_action %}
    {% set row=data.best_action %}{% set a=row._action %}
    <div class="panel {{ 'action-ready' if a.status in ['READY_NOW','STRATEGY_READY_NOW','STRATEGY_LIMIT_READY'] else 'action-retest' }}">
      <div class="action-title {{ 'ready' if a.status in ['READY_NOW','STRATEGY_READY_NOW','STRATEGY_LIMIT_READY'] else 'retest' }}">🟢 MONEY ACTION NOW — {{ a.label }}</div>
      <h2 style="margin:8px 0 0">{{ row.symbol }} {{ a.direction }}</h2>
      <div class="action-grid">
        <div class="metric"><span class="label">Status</span><b>{{ a.status }}</b></div>
        <div class="metric"><span class="label">Entry / zone</span><b>{{ a.entry }}</b></div>
        <div class="metric"><span class="label">Stop / invalidation</span><b>{{ a.stop }}</b></div>
        <div class="metric"><span class="label">Target</span><b>{{ a.target }}</b></div>
        <div class="metric"><span class="label">R:R</span><b>{{ '%.2f'|format(a.rr or 0) }}</b></div>
        <div class="metric"><span class="label">Distance to action</span><b>{{ '%.2f'|format(a.distance_pct or 0) }}%</b></div>
      </div>
      <div class="reason"><b>Why:</b> {{ a.reason }}<br><b>Cancel:</b> {{ a.cancel }}</div>
    </div>
  {% else %}
    <div class="panel action-none">
      <div class="action-title">MONEY ACTION NOW</div>
      <h2 style="margin:8px 0">NO VALID EXECUTION YET</h2>
      <div class="reason">The app will not turn a discovery coin into a trade recommendation. Run a fresh scan or wait for the next scan; the first candidate that passes the execution contract will replace this block automatically.</div>
    </div>
  {% endif %}

  <div class="panel">
    <h2 style="margin-top:0">S1-S10 Strategy Matrix — Shadow</h2>
    <div class="small" style="margin-bottom:10px">S1-S10 candidates can now feed the Money Action decision-support queue when they pass their strategy gates, valid geometry and the configured 5R minimum. They still cannot grant exchange/order authority. Coverage: {{ data.strategy_summary.get('total_evaluations',0) }} evaluations across {{ data.strategy_summary.get('covered_symbol_count',0) }} symbols. Previous canonical context: {{ data.previous_snapshot_context.get('source','NONE') }}{% if data.previous_snapshot_context.get('collected_at_utc') %} · {{ data.previous_snapshot_context.get('collected_at_utc') }}{% endif %}.</div>
    <div class="toolbar" style="margin-bottom:12px">
      {% for row in data.strategy_coverage %}
      <span class="badge badge-research">{{ row.strategy_id }}: {{ row.evaluations }} eval / {{ row.candidates }} cand</span>
      {% endfor %}
    </div>
    {% if data.strategy_shadow %}
    <table><thead><tr><th>Symbol</th><th>Strategy</th><th>Status</th><th>Persistence</th><th>Scans</th><th>Side</th><th>Gate action</th><th>Setup intent</th><th>Score</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th><th>Why / blocker</th></tr></thead><tbody>
    {% for s in data.strategy_shadow %}
      <tr>
        <td><b>{{ s.symbol }}</b></td>
        <td><b>{{ s.strategy_id }}</b> {{ s.strategy_name }}</td>
        <td><span class="badge {{ 'badge-ready' if s.status=='SHADOW_CANDIDATE' else 'badge-retest' if s.status=='WATCH' else 'badge-research' }}">{{ s.status }}</span></td>
        <td>{{ s._persistence_state }}</td>
        <td>{{ s._consecutive_scans }}</td>
        <td class="{{ 'long' if s.direction=='LONG' else 'short' if s.direction=='SHORT' else '' }}">{{ s.direction or '—' }}</td>
        <td>{{ s.action }}</td>
        <td>{{ s.proposed_action or s.action }}</td>
        <td>{{ '%.2f'|format(s.signal_score or 0) }}</td>
        <td>{{ s.entry if s.entry is not none else '—' }}</td>
        <td>{{ s.stop if s.stop is not none else '—' }}</td>
        <td>{{ s.target if s.target is not none else '—' }}</td>
        <td>{{ '%.2f'|format(s.rr) if s.rr is not none else '—' }}</td>
        <td class="wrap-cell muted">{{ (s.reasons or [])|join('; ') }}</td>
      </tr>
    {% endfor %}
    </tbody></table>
    {% else %}
      <div class="empty">No S1-S10 matrix in this snapshot yet. Run a fresh scan after this build is deployed.</div>
    {% endif %}
  </div>

  <div class="layout">
    <main>
      <div class="panel">
        <h2 style="margin-top:0">Action Queue</h2>
        {% if data.actionable %}
        <table><thead><tr><th>Symbol</th><th>Action</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th><th>Distance</th></tr></thead><tbody>
        {% for row in data.actionable %}{% set a=row._action %}
        <tr><td><b>{{ row.symbol }}</b></td><td><span class="badge {{ 'badge-ready' if a.status in ['READY_NOW','STRATEGY_READY_NOW','STRATEGY_LIMIT_READY'] else 'badge-retest' }}">{{ a.status }}</span></td><td class="{{ 'long' if a.direction=='LONG' else 'short' }}">{{ a.direction }}</td><td>{{ a.entry }}</td><td>{{ a.stop }}</td><td>{{ a.target }}</td><td>{{ '%.2f'|format(a.rr or 0) }}</td><td>{{ '%.2f'|format(a.distance_pct or 0) }}%</td></tr>
        {% endfor %}</tbody></table>
        {% else %}<div class="empty">No executable or valid retest plan in the current snapshot.</div>{% endif %}
      </div>

      <div class="panel">
        <h2 style="margin-top:0">Research / Discovery Radar</h2>
        <div class="small" style="margin-bottom:10px">These rows are information, not trade recommendations. They become actionable only through the Money Action block above.</div>
        <table><thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>Phase</th><th>Timing</th><th>Behaviour</th><th>State</th><th>R:R</th><th>Execution</th><th>Reason</th></tr></thead><tbody>
        {% for row in data.research %}
        <tr><td>{{ loop.index }}</td><td><b>{{ row.symbol }}</b></td><td>{{ row.last_price }}</td><td>{{ row._phase }}</td><td>{{ row._timing }}</td><td>{{ '%.2f'|format(row._behaviour) }}</td><td class="{{ 'long' if 'LONG' in row.state else 'short' if 'SHORT' in row.state else '' }}">{{ row.state }}</td><td>{{ '%.2f'|format(row._rr) if row._rr is not none else '—' }}</td><td><span class="badge {{ 'badge-ready' if row._action.status=='READY_NOW' else 'badge-retest' if row._action.status=='RETEST_PLAN' else 'badge-research' }}">{{ row._action.label }}</span></td><td class="wrap-cell muted">{{ row._action.reason }}</td></tr>
        {% endfor %}</tbody></table>
      </div>

      <div class="panel"><h2 style="margin-top:0">Bitget Open Positions</h2>
      {% if data.positions %}<table><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>Leverage</th><th>Unrealized P/L</th></tr></thead><tbody>
      {% for p in data.positions %}<tr><td><b>{{ p.symbol }}</b></td><td>{{ p.hold_side }}</td><td>{{ p.total }}</td><td>{{ p.open_price_avg }}</td><td>{{ p.mark_price }}</td><td>{{ p.leverage }}×</td><td>{{ p.unrealized_pl }}</td></tr>{% endfor %}
      </tbody></table>{% else %}<div class="empty">No open Bitget positions detected.</div>{% endif %}</div>
    </main>

    <aside>
      <div class="panel"><h2 style="margin-top:0">Reference / Regime</h2>{% for row in data.references %}<div class="side-row"><span><b>{{ row.symbol }}</b></span><span>{{ row.last_price }}</span></div>{% else %}<div class="empty">No reference assets.</div>{% endfor %}</div>
      <div class="panel"><h2 style="margin-top:0">Product Contract</h2><div class="small">Discovery ≠ recommendation.<br><br>READY NOW keeps the existing V7 execution permission. S1-S10 READY SETUP means the strategy candidate passed its own safety/data gates, valid geometry and the configured 5R minimum; it is decision support, not order authority.<br><br>RETEST PLAN requires direction + structure + momentum + participation + funding + integrity, with only price/R:R still needing improvement.<br><br>No threshold is relaxed.</div></div>
    </aside>
  </div>
</div>
<script>
let scanPollTimer=null;
async function runScan(){const b=document.getElementById('runScanButton'),m=document.getElementById('scanMessage');b.disabled=true;m.textContent='Starting fresh scan...';try{const r=await fetch('/api/run-scan',{method:'POST'}),x=await r.json();if(!r.ok)throw new Error(x.error||'Unable to start scan');m.textContent='Scan running...';if(scanPollTimer)clearInterval(scanPollTimer);scanPollTimer=setInterval(checkScanStatus,3000)}catch(e){m.textContent='Scan failed: '+e.message;b.disabled=false}}
async function checkScanStatus(){const b=document.getElementById('runScanButton'),m=document.getElementById('scanMessage');try{const r=await fetch('/api/scan-status'),x=await r.json();if(x.running){m.textContent='Scan running...';b.disabled=true;return}if(x.status==='completed'){clearInterval(scanPollTimer);m.textContent='Scan complete. Refreshing...';setTimeout(()=>location.reload(),700);return}if(x.status==='failed'){clearInterval(scanPollTimer);m.textContent='Scan failed: '+(x.error||'unknown error');b.disabled=false;return}b.disabled=false}catch(e){m.textContent='Unable to read scan status';b.disabled=false}}
</script>
</body>
</html>
"""


CONTROL_TOWER_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Alpha Hunter — V14 Control Tower</title>
  <style>
    :root{--bg:#071018;--panel:#0d1822;--line:#1d2e3a;--text:#e8f0f6;--muted:#91a3b1;--ok:#2bd39a;--warn:#ffbf47;--bad:#ff6474;--blue:#4db6ff}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
    .wrap{max-width:1120px;margin:auto;padding:16px}.top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px}
    h1{font-size:26px;margin:0 0 4px}.muted,.small{color:var(--muted)}.small{font-size:12px}.links a{color:var(--blue);text-decoration:none;margin-left:12px}
    .hero,.card,.panel{background:rgba(13,24,34,.96);border:1px solid var(--line);border-radius:16px}.hero,.panel{padding:16px;margin-bottom:14px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.card{padding:13px}
    .label{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}.value{font-size:22px;font-weight:800;margin-top:4px}.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
    .pill{display:inline-block;padding:5px 9px;border:1px solid var(--line);border-radius:999px;font-size:11px;margin:3px 4px 3px 0}.pill-ok{border-color:#21634e;color:var(--ok)}.pill-warn{border-color:#76602a;color:var(--warn)}.pill-bad{border-color:#78313c;color:var(--bad)}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}.row{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid #152633;font-size:13px}.row:last-child{border-bottom:0}.right{text-align:right;overflow-wrap:anywhere}
    table{width:100%;border-collapse:collapse;font-size:12px}th,td{text-align:left;padding:9px 6px;border-bottom:1px solid #152633;vertical-align:top}th{color:var(--muted)}
    @media(max-width:760px){.wrap{padding:10px}.top{display:block}.links{margin-top:8px}.links a{margin:0 12px 0 0}.cards{grid-template-columns:1fr 1fr}.grid2{grid-template-columns:1fr}.value{font-size:20px}}
  </style>
</head>
<body>
<div class="wrap">
  {% set s=data.status %}
  <div class="top">
    <div><h1>V14 Control Tower</h1><div class="small">Forward scientific test · operations only · no order authority</div></div>
    <div class="links"><a href="/">Money Action</a><a href="/performance">Performance</a></div>
  </div>

  <div class="hero">
    <div class="label">Watchdog</div>
    <div class="value {{ 'bad' if s.watchdog_status=='CRITICAL' else 'warn' if s.watchdog_status=='WARNING' else 'ok' }}">{{ s.watchdog_status }}</div>
    <div class="small" style="margin-top:7px">Spec {{ s.spec_id }} · generated {{ data.generated_at_utc }}</div>
    <div style="margin-top:10px">
      {% for a in s.critical_alerts or [] %}<span class="pill pill-bad">{{ a }}</span>{% endfor %}
      {% for a in s.warning_alerts or [] %}<span class="pill pill-warn">{{ a }}</span>{% endfor %}
      {% if not s.critical_alerts and not s.warning_alerts %}<span class="pill pill-ok">NO ACTIVE OPERATIONAL ALERTS</span>{% endif %}
    </div>
  </div>

  <div class="cards">
    <div class="card"><div class="label">Operational</div><div class="value {{ 'ok' if s.operational_status=='PASS' else 'bad' }}">{{ s.operational_status }}</div></div>
    <div class="card"><div class="label">Test days</div><div class="value">{{ '%.2f'|format(s.test_days_elapsed or 0) }}/{{ s.minimum_test_days or 30 }}</div><div class="small">{{ '%.2f'|format(s.test_days_remaining or 0) }} remaining</div></div>
    <div class="card"><div class="label">Paper trades</div><div class="value">{{ s.completed_paper_trades or 0 }}/{{ s.minimum_completed_paper_trades or 100 }}</div><div class="small">{{ s.paper_trades_remaining or 0 }} remaining</div></div>
    <div class="card"><div class="label">Cadence</div><div class="value {{ 'ok' if s.cadence_integrity_status=='PASS' else 'bad' }}">{{ s.cadence_integrity_status }}</div><div class="small">{{ s.expected_schedule }}</div></div>
    <div class="card"><div class="label">Identity drift</div><div class="value {{ 'ok' if (s.identity_drift_scans or 0)==0 else 'bad' }}">{{ s.identity_drift_scans or 0 }}</div><div class="small">scientific fingerprint</div></div>
    <div class="card"><div class="label">Latest scan age</div><div class="value">{{ '%.1f'|format((s.latest_live_scan_age_seconds or 0)/60) }}m</div><div class="small">{{ s.latest_live_scan_at_utc }}</div></div>
    <div class="card"><div class="label">Bitget continuity</div><div class="value {{ 'warn' if s.historical_fill_continuity_conflict else 'ok' }}">{{ 'CONFLICT' if s.historical_fill_continuity_conflict else 'PASS' }}</div><div class="small">{{ s.account_identity_probe_status }}</div></div>
    <div class="card"><div class="label">Database</div><div class="value">{{ s.database_size_pretty or '—' }}</div><div class="small">{{ s.live_toast_review_tables or 0 }} live-TOAST review tables</div></div>
  </div>

  <div class="grid2">
    <div class="panel">
      <h2 style="margin-top:0">Validation gates</h2>
      {% for g in s.expected_gates or [] %}<span class="pill pill-warn">{{ g }}</span>{% endfor %}
      <div class="row"><span>Profitability status</span><b class="right">{{ s.profitability_status }}</b></div>
      <div class="row"><span>Verdict</span><b class="right">{{ s.verdict }}</b></div>
      <div class="row"><span>Earliest duration gate</span><b class="right">{{ s.earliest_duration_gate_at_utc or '—' }}</b></div>
      <div class="row"><span>Cost model</span><b class="right">{{ s.cost_scientific_status or 'NOT VALIDATED' }}</b></div>
      <div class="row"><span>Next cost gate</span><b class="right">{{ s.cost_next_gate or '—' }}</b></div>
    </div>
    <div class="panel">
      <h2 style="margin-top:0">Production integrity</h2>
      <div class="row"><span>Post-baseline scans</span><b>{{ s.post_start_scans or 0 }}</b></div>
      <div class="row"><span>Cadence mismatches</span><b>{{ s.identity_mismatch_scan_count or 0 }}</b></div>
      <div class="row"><span>Too-frequent intervals</span><b>{{ s.too_frequent_scan_intervals or 0 }}</b></div>
      <div class="row"><span>Excessive gaps</span><b>{{ s.excessive_gap_intervals or 0 }}</b></div>
      <div class="row"><span>Historical fills same window</span><b>{{ s.historical_fill_rows_same_window or 0 }}</b></div>
      <div class="row"><span>Legacy control plane</span><b class="{{ 'ok' if s.legacy_control_plane_status=='PASS' else 'warn' }}">{{ s.legacy_control_plane_status or '—' }}</b></div>
    </div>
  </div>

  <div class="panel">
    <h2 style="margin-top:0">Recent watchdog events</h2>
    {% if data.events %}
    <table><thead><tr><th>UTC</th><th>Status</th><th>Critical</th><th>Warnings</th></tr></thead><tbody>
    {% for e in data.events %}<tr><td>{{ e.checked_at_utc }}</td><td><b class="{{ 'bad' if e.status=='CRITICAL' else 'warn' if e.status=='WARNING' else 'ok' }}">{{ e.status }}</b></td><td>{{ (e.critical_alerts or [])|join(', ') or '—' }}</td><td>{{ (e.warning_alerts or [])|join(', ') or '—' }}</td></tr>{% endfor %}
    </tbody></table>
    {% else %}<div class="small">No watchdog events persisted yet. The scheduled watchdog will populate this automatically.</div>{% endif %}
  </div>

  <div class="panel small">
    Safety contract: paper/shadow only. trade_permission=false · production_promotion_permitted=false · order_path=NONE.
    This page is observability only and cannot place, cancel, or modify an exchange order.
  </div>
</div>
</body>
</html>
"""


DASHBOARD_RECOVERY_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <title>Alpha Hunter — recovering</title>
  <style>
    body{margin:0;background:#071018;color:#e7edf2;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .wrap{max-width:720px;margin:0 auto;padding:28px 18px}
    .card{margin-top:18px;background:#0d1923;border:1px solid #1b3040;border-radius:16px;padding:20px}
    h1{margin:0 0 8px;font-size:28px}.muted{color:#91a3b1;line-height:1.55}
    .warn{color:#ffbf69;font-weight:700}.ok{color:#75e6b5}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Alpha Hunter Dashboard</h1>
    <div class="card">
      <div class="warn">LIVE DATA TEMPORARILY UNAVAILABLE</div>
      <p class="muted">The web service is running, but current canonical Supabase evidence could not be read after bounded retries.</p>
      <p class="muted">Trading actions are intentionally hidden until live data is available again. No stale snapshot is promoted as current evidence.</p>
      <p class="muted">This page retries automatically every 10 seconds.</p>
      <p class="muted">Build {{ build.git_commit_short }} · {{ build.git_branch }}</p>
    </div>
  </div>
</body>
</html>
"""


@app.get("/")
def dashboard():
    try:
        return render_template_string(
            PAGE,
            data=dashboard_payload(
                latest_snapshot(),
                latest_test_engine_status(),
            ),
        )
    except Exception:
        app.logger.exception("Dashboard live-data read failed")
        return render_template_string(
            DASHBOARD_RECOVERY_PAGE,
            build=build_identity(),
        ), 503


@app.get("/api/latest")
def api_latest():
    try:
        return jsonify(
            dashboard_payload(
                latest_snapshot(),
                latest_test_engine_status(),
            )
        )
    except Exception:
        app.logger.exception("API latest live-data read failed")
        return jsonify({
            "error": "live_data_unavailable",
            "retry_after_seconds": 10,
            "build": build_identity(),
        }), 503


@app.get("/api/build")
def api_build():
    return jsonify(build_identity())


@app.post("/api/run-scan")
def api_run_scan():
    with scan_lock:
        if scan_state["running"]:
            return jsonify({"status": "running", "message": "A scan is already running"}), 202
        scan_state["running"] = True
        scan_state["status"] = "starting"
        scan_state["error"] = None

    threading.Thread(target=run_scan_worker, daemon=True).start()
    return jsonify({"status": "started", "message": "Alpha Hunter V7.2 scan started"}), 202


@app.get("/api/scan-status")
def api_scan_status():
    with scan_lock:
        return jsonify(dict(scan_state))


@app.get("/control-tower")
def control_tower():
    try:
        return render_template_string(
            CONTROL_TOWER_PAGE,
            data=control_tower_payload(),
        )
    except Exception:
        app.logger.exception("V14 control-tower live-data read failed")
        return render_template_string(
            DASHBOARD_RECOVERY_PAGE,
            build=build_identity(),
        ), 503


@app.get("/api/control-tower")
def api_control_tower():
    try:
        return jsonify(control_tower_payload())
    except Exception:
        app.logger.exception("V14 control-tower API read failed")
        return jsonify({
            "error": "control_tower_unavailable",
            "retry_after_seconds": 10,
            "build": build_identity(),
        }), 503


@app.get("/performance")
def performance_dashboard():
    try:
        horizon = int(request.args.get("horizon", "1"))
        if horizon not in {1, 4, 12, 24}:
            horizon = 1
        report = StatisticsService(SUPABASE_URL, SUPABASE_KEY).report(horizon)
        return render_template_string(PERFORMANCE_PAGE, data=report)
    except Exception as exc:
        return render_template_string("<h1>Performance Analytics</h1><p>{{ error }}</p><p><a href='/'>Back</a></p>", error=str(exc)), 503


@app.get("/api/performance")
def api_performance():
    try:
        horizon = int(request.args.get("horizon", "1"))
        if horizon not in {1, 4, 12, 24}:
            horizon = 1
        return jsonify(StatisticsService(SUPABASE_URL, SUPABASE_KEY).report(horizon))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "alpha-hunter-dashboard",
        "version": APP_VERSION,
        "build": build_identity(),
        "scan_status": scan_state["status"],
        "scan_running": scan_state["running"],
        "minimum_execution_rr": MINIMUM_EXECUTION_RR,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
