from __future__ import annotations

import contextvars
import hmac
import json
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template_string, request

from alpha_hunter.services.statistics import StatisticsService
from alpha_hunter.web_history_summary import archived_storage_summary
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

OPERATOR_USER = os.getenv("ALPHA_HUNTER_OPERATOR_USER", "").strip()
OPERATOR_PASSWORD = os.getenv("ALPHA_HUNTER_OPERATOR_PASSWORD", "")
EXECUTION_FREEZE_RPC = "alpha_hunter_freeze_execution_decision_api_v01"
EXECUTION_FREEZE_CONFIRM_HEADER = "X-Alpha-Hunter-Freeze-Confirm"
EXECUTION_BIND_RPC = "alpha_hunter_bind_execution_fill_api_v01"
EXECUTION_BIND_CONFIRM_HEADER = "X-Alpha-Hunter-Bind-Confirm"

SUPABASE_READ_ATTEMPTS = 3
SUPABASE_READ_TIMEOUT_SECONDS = 12
SUPABASE_RETRY_BACKOFF_SECONDS = 0.75
SUPABASE_TRANSIENT_STATUSES = {429, 500, 502, 503, 504}

# Keep dashboard requests below Gunicorn's 30-second default worker timeout.
# This scope never alters cron ingestion or operator write paths.
DASHBOARD_READ_BUDGET_SECONDS = 18.0
# The optional successor profitability view may exceed the PostgREST statement
# timeout. Fall back quickly to the recorded test-engine status, with an
# explicit successor-unavailable blocker; never infer a successor PASS.
# Web dashboard reads only; the sealed paper cron does not use this deadline.
DASHBOARD_OPTIONAL_STATUS_READ_TIMEOUT_SECONDS = 2.5
# During a confirmed outage, return the safe recovery page promptly instead
# of allowing every mobile refresh to open another expensive database query.
DASHBOARD_READ_FAILURE_COOLDOWN_SECONDS = 75.0
_DASHBOARD_READ_FAILURE_LOCK = threading.Lock()
_DASHBOARD_READ_UNAVAILABLE_UNTIL = 0.0
_DASHBOARD_READ_DEADLINE = contextvars.ContextVar(
    "alpha_hunter_dashboard_read_deadline", default=None,
)

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
MAXIMUM_ACTION_RR = float(
    RUNTIME_CONFIG.get("candidate_quality", {}).get(
        "maximum_action_reward_risk",
        25.0,
    )
)
MAXIMUM_ACTION_SNAPSHOT_AGE_SECONDS = float(
    RUNTIME_CONFIG.get("candidate_quality", {}).get(
        "maximum_action_snapshot_age_seconds",
        5400.0,
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

    deadline = _DASHBOARD_READ_DEADLINE.get()
    # Optional scientific status must never use the entire browser request
    # budget. Keep all other reads and non-dashboard callers unchanged.
    optional_dashboard_status = (
        deadline is not None
        and table == "alpha_hunter_paper_profitability_status_v09"
    )
    attempts = 1 if optional_dashboard_status else SUPABASE_READ_ATTEMPTS
    timeout_seconds = (
        min(SUPABASE_READ_TIMEOUT_SECONDS, DASHBOARD_OPTIONAL_STATUS_READ_TIMEOUT_SECONDS)
        if optional_dashboard_status else SUPABASE_READ_TIMEOUT_SECONDS
    )

    def bounded_backoff(attempt: int) -> None:
        delay = SUPABASE_RETRY_BACKOFF_SECONDS * attempt
        if deadline is not None and time.monotonic() + delay >= deadline:
            raise RuntimeError("Dashboard Supabase read budget exhausted")
        time.sleep(delay)

    for attempt in range(1, attempts + 1):
        remaining = deadline - time.monotonic() if deadline is not None else None
        if remaining is not None and remaining <= 0:
            raise RuntimeError("Dashboard Supabase read budget exhausted")
        request_timeout = (
            min(timeout_seconds, remaining)
            if remaining is not None else timeout_seconds
        )
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/{table}",
                params=params,
                headers=supabase_headers(),
                timeout=request_timeout,
            )
        except requests.RequestException:
            if attempt >= attempts:
                raise
            bounded_backoff(attempt)
            continue

        if (
            response.status_code in SUPABASE_TRANSIENT_STATUSES
            and attempt < attempts
        ):
            bounded_backoff(attempt)
            continue

        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected Supabase response shape")
        return rows

    raise RuntimeError("Supabase read retry budget exhausted")


class StaleExecutionDecision(RuntimeError):
    pass


def operator_auth_configured() -> bool:
    return bool(OPERATOR_USER and OPERATOR_PASSWORD)


def operator_authorized() -> bool:
    if not operator_auth_configured():
        return False
    auth = request.authorization
    if auth is None:
        return False
    return (
        hmac.compare_digest(auth.username or "", OPERATOR_USER)
        and hmac.compare_digest(auth.password or "", OPERATOR_PASSWORD)
    )


def operator_auth_response():
    if not operator_auth_configured():
        return jsonify({
            "error": "operator_auth_not_configured",
            "message": (
                "Set ALPHA_HUNTER_OPERATOR_USER and "
                "ALPHA_HUNTER_OPERATOR_PASSWORD on the Render web service."
            ),
        }), 503

    response = jsonify({"error": "operator_auth_required"})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = (
        'Basic realm="Alpha Hunter Freeze", charset="UTF-8"'
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def execution_freeze_candidates() -> list[dict[str, Any]]:
    rows = supabase_get_rows(
        "alpha_hunter_execution_attribution_candidates_v01",
        {
            "select": (
                "spec_id,decision_observation_id,strategy_instance_id,"
                "decision_run_id,symbol,strategy_id,direction,action,"
                "decision_observed_at_utc,decision_captured_at_utc,"
                "reference_price,planned_entry_price,stop_price,target_price,"
                "reward_risk,best_bid,best_ask,midpoint,entry_cross_price,"
                "entry_cross_half_spread_bps,quote_complete,"
                "prospective_capture,run_source,git_commit,config_sha256,"
                "freeze_available,trade_permission,"
                "production_promotion_permitted,order_path"
            ),
            "freeze_available": "eq.true",
            "order": "decision_observed_at_utc.desc",
            "limit": "20",
        },
    )
    return [row for row in rows if isinstance(row, dict)]


def existing_execution_freeze(
    decision_observation_id: str,
) -> dict[str, Any] | None:
    rows = supabase_get_rows(
        "alpha_hunter_execution_decision_freezes_v01",
        {
            "select": (
                "execution_event_id,decision_observation_id,symbol,direction,"
                "action,frozen_at_utc,trade_permission,order_path"
            ),
            "decision_observation_id": f"eq.{decision_observation_id}",
            "order": "frozen_at_utc.desc",
            "limit": "1",
        },
    )
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def freeze_execution_decision(
    decision_observation_id: str,
) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase environment variables are not configured")

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{EXECUTION_FREEZE_RPC}",
            headers=supabase_headers(),
            json={"p_decision_observation_id": decision_observation_id},
            timeout=SUPABASE_READ_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        # A transport failure can happen after Postgres committed the freeze.
        # Resolve that ambiguity by reading the append-only freeze ledger before
        # returning an error. Never retry this write blindly.
        existing = existing_execution_freeze(decision_observation_id)
        if existing is not None:
            recovered = dict(existing)
            recovered["fill_binding_status"] = (
                "WAITING_FOR_EXPLICIT_USER_CONFIRMED_FILL"
            )
            recovered["recovered_after_transport_error"] = True
            recovered["trade_permission"] = False
            recovered["order_path"] = "NONE"
            return recovered
        raise

    if response.status_code >= 400:
        detail = response.text or ""
        if "Decision is not a current prospective attribution candidate" in detail:
            raise StaleExecutionDecision(
                "Decision expired before the freeze was committed"
            )
        response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected freeze RPC response shape")

    payload["trade_permission"] = False
    payload["order_path"] = "NONE"
    return payload


def execution_freeze_by_id(execution_event_id: str) -> dict[str, Any] | None:
    rows = supabase_get_rows(
        "alpha_hunter_execution_decision_freezes_v01",
        {
            "select": "*",
            "execution_event_id": f"eq.{execution_event_id}",
            "limit": "1",
        },
    )
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def execution_binding_by_event(
    execution_event_id: str,
) -> dict[str, Any] | None:
    rows = supabase_get_rows(
        "alpha_hunter_execution_fill_bindings_v01",
        {
            "select": "*",
            "execution_event_id": f"eq.{execution_event_id}",
            "limit": "1",
        },
    )
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def compatible_execution_fills(
    frozen: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return only DB-verified current confirmation candidates for one freeze."""
    execution_event_id = str(frozen.get("execution_event_id") or "").strip()
    if not execution_event_id:
        return []

    rows = supabase_get_rows(
        "alpha_hunter_execution_fill_confirmation_candidates_v01",
        {
            "select": (
                "execution_event_id,fill_evidence_id,traceability_run_id,"
                "fill_time_utc,trade_id,order_id,symbol,side,trade_side,"
                "trade_scope,price,base_volume,quote_volume,fee_amount,fee_coin,"
                "cost_fields_complete,order_evidence_id,order_identity_sha256,"
                "order_type,order_state,order_created_at_utc,origin_consistent,"
                "freeze_to_order_seconds,order_to_fill_seconds,"
                "candidate_adverse_arrival_to_fill_bps,realized_fee_bps,"
                "fill_candidate_count,event_candidate_count,"
                "candidate_status,explicit_user_confirmation_required,"
                "automatic_binding_permitted"
            ),
            "execution_event_id": f"eq.{execution_event_id}",
            "order": "freeze_to_order_seconds.asc,fill_time_utc.asc",
            "limit": "50",
        },
    )

    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["_trace_complete"] = True
        item["_binding_ready"] = (
            item.get("explicit_user_confirmation_required") is True
            and item.get("automatic_binding_permitted") is False
            and bool(item.get("order_evidence_id"))
            and bool(item.get("order_identity_sha256"))
            and item.get("origin_consistent") is True
        )
        item["_order"] = {
            "order_evidence_id": item.get("order_evidence_id"),
            "order_identity_sha256": item.get("order_identity_sha256"),
            "order_type": item.get("order_type"),
            "order_state": item.get("order_state"),
            "order_created_at_utc": item.get("order_created_at_utc"),
            "origin_consistent": item.get("origin_consistent"),
        }
        result.append(item)

    return result


def pending_execution_fill_confirmations() -> list[dict[str, Any]]:
    """Read-only queue. Never binds or resolves an ambiguous pair."""
    rows = supabase_get_rows(
        "alpha_hunter_execution_fill_confirmation_candidates_v01",
        {
            "select": (
                "execution_event_id,spec_id,symbol,strategy_id,direction,action,"
                "frozen_at_utc,planned_entry_price,reward_risk,best_bid,best_ask,"
                "entry_cross_price,fill_evidence_id,fill_time_utc,trade_id,order_id,"
                "side,price,base_volume,quote_volume,fee_amount,fee_coin,"
                "order_type,order_created_at_utc,freeze_to_order_seconds,"
                "order_to_fill_seconds,candidate_adverse_arrival_to_fill_bps,"
                "realized_fee_bps,fill_candidate_count,event_candidate_count,"
                "candidate_status,explicit_user_confirmation_required,"
                "automatic_binding_permitted,attribution_claim_permitted"
            ),
            "order": "fill_time_utc.desc,freeze_to_order_seconds.asc",
            "limit": "100",
        },
    )
    return [row for row in rows if isinstance(row, dict)]


def execution_fill_confirmation_status() -> dict[str, Any]:
    rows = supabase_get_rows(
        "alpha_hunter_execution_fill_confirmation_status_v01",
        {"select": "*", "limit": "1"},
    )
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return {}


def existing_execution_binding(
    execution_event_id: str,
    fill_evidence_id: str,
) -> dict[str, Any] | None:
    rows = supabase_get_rows(
        "alpha_hunter_execution_fill_bindings_v01",
        {
            "select": "*",
            "execution_event_id": f"eq.{execution_event_id}",
            "fill_evidence_id": f"eq.{fill_evidence_id}",
            "limit": "1",
        },
    )
    if rows and isinstance(rows[0], dict):
        return rows[0]
    return None


def bind_execution_fill(
    execution_event_id: str,
    fill_evidence_id: str,
) -> dict[str, Any]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase environment variables are not configured")

    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/{EXECUTION_BIND_RPC}",
            headers=supabase_headers(),
            json={
                "p_execution_event_id": execution_event_id,
                "p_fill_evidence_id": fill_evidence_id,
                "p_explicit_user_confirmation": True,
            },
            timeout=SUPABASE_READ_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        existing = existing_execution_binding(
            execution_event_id,
            fill_evidence_id,
        )
        if existing is not None:
            recovered = dict(existing)
            recovered["recovered_after_transport_error"] = True
            recovered["trade_permission"] = False
            recovered["production_promotion_permitted"] = False
            recovered["order_path"] = "NONE"
            return recovered
        raise

    if response.status_code >= 400:
        raise RuntimeError(response.text or "Explicit fill binding rejected")

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected fill-binding RPC response shape")

    payload["trade_permission"] = False
    payload["production_promotion_permitted"] = False
    payload["order_path"] = "NONE"
    return payload


class CanonicalSnapshotPublishing(RuntimeError):
    """A newly visible scan parent is still waiting for its child evidence."""


class CanonicalSnapshotIncomplete(RuntimeError):
    """A canonical parent is visible, but its evidence is not safe to display."""


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
        raise CanonicalSnapshotIncomplete("Compact canonical snapshot is missing run_id")
    if row.get("run_id") and row["run_id"] != run_id:
        raise CanonicalSnapshotIncomplete("Compact canonical parent identity mismatch")
    if row.get("error_count") not in (None, 0):
        raise CanonicalSnapshotIncomplete("Canonical scanner reported source errors")

    children = supabase_get_rows(
        "alpha_hunter_symbol_snapshots",
        {
            "select": "symbol,payload",
            "run_id": f"eq.{run_id}",
            "order": "symbol.asc",
            "limit": "2000",
        },
    )
    # A committed compact parent is not evidence that its child writes committed.
    # Never replace the parent stubs with an empty or partial child set and
    # silently classify that canonical scan as complete.
    expected_count = row.get("symbol_count")
    parent_stubs = snapshot.get("symbols")
    if expected_count is None and isinstance(parent_stubs, list):
        expected_count = len(parent_stubs)
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or not (1 <= expected_count <= 2000)
    ):
        raise CanonicalSnapshotIncomplete("Compact canonical parent symbol_count is invalid")
    if len(children) != expected_count:
        # Canonical scanner persists the parent before the child batch. A
        # short-lived, incomplete newest parent is a publishing state, not a
        # Supabase transport outage. Never show it as a completed scan.
        try:
            parent_created = datetime.fromisoformat(
                str(row.get("created_at") or "").replace("Z", "+00:00")
            )
            age_seconds = (
                datetime.now(timezone.utc) - parent_created.astimezone(timezone.utc)
            ).total_seconds()
        except (ValueError, TypeError):
            age_seconds = float("inf")
        if (
            len(children) < expected_count
            and -5 <= age_seconds <= 90
        ):
            raise CanonicalSnapshotPublishing(
                "Canonical scan child evidence is still publishing"
            )
        raise CanonicalSnapshotIncomplete("Incomplete compact canonical snapshot child evidence")

    by_symbol: dict[str, dict[str, Any]] = {}
    for child in children:
        if not isinstance(child, dict):
            raise CanonicalSnapshotIncomplete("Invalid compact canonical snapshot child row")
        symbol = child.get("symbol")
        detail = child.get("payload")
        if (
            not isinstance(symbol, str)
            or not symbol
            or not isinstance(detail, dict)
            or detail.get("symbol") != symbol
            or symbol in by_symbol
        ):
            raise CanonicalSnapshotIncomplete("Invalid or duplicate compact child symbol evidence")
        by_symbol[symbol] = detail
    if isinstance(parent_stubs, list):
        parent_symbols = [
            stub.get("symbol") if isinstance(stub, dict) else None
            for stub in parent_stubs
        ]
        if (
            len(parent_symbols) != expected_count
            or any(not isinstance(symbol, str) for symbol in parent_symbols)
            or set(parent_symbols) != set(by_symbol)
        ):
            raise CanonicalSnapshotIncomplete("Compact canonical parent and child symbol mismatch")
    snapshot["symbols"] = [by_symbol[symbol] for symbol in sorted(by_symbol)]
    return snapshot


def latest_snapshot() -> dict[str, Any]:
    params = {
        "select": "run_id,collected_at_utc,created_at,version,symbol_count,error_count,payload",
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
    engine: dict[str, Any] = {}
    successor_read_failed = False
    try:
        rows = supabase_get_rows(
            "alpha_hunter_paper_profitability_status_v09",
            {"select": "*", "limit": "1"},
        )
        if rows and isinstance(rows[0], dict):
            engine = dict(rows[0])
    except (requests.RequestException, RuntimeError, ValueError):
        successor_read_failed = True
    if not engine:
        try:
            rows = supabase_get_rows(
                "alpha_hunter_test_engine_latest_v01",
                {"select": "*", "limit": "1"},
            )
            if rows and isinstance(rows[0], dict):
                engine = dict(rows[0])
        except (requests.RequestException, RuntimeError, ValueError):
            return {}
    if not engine:
        return {}
    blockers = list(engine.get("blockers") or [])
    if successor_read_failed:
        blockers.append("SUCCESSOR_STATUS_UNAVAILABLE")
    try:
        rows = supabase_get_rows("alpha_hunter_paper_repair_status_v01",
                                 {"select": "*", "limit": "1"})
        repair = rows[0] if rows and isinstance(rows[0], dict) else {}
    except (requests.RequestException, RuntimeError, ValueError):
        repair = {}
    if not repair:
        blockers.append("REPAIR_DIAGNOSTICS_UNAVAILABLE")
    else:
        if repair.get("unresolved_entry_orders", 0) > 0:
            blockers.append("UNRESOLVED_PAPER_ENTRY_REQUIRES_REPAIR")
        if repair.get("open_positions_over_24h", 0) > 0:
            blockers.append("OPEN_PAPER_POSITIONS_EXCEED_24H")
    engine["repair_status"] = repair
    engine["blockers"] = list(dict.fromkeys(blockers))
    engine["collection_status"] = engine.get("operational_status", "UNKNOWN")
    # This is a display overlay. The immutable scientific evaluation is untouched.
    if any(b in blockers for b in (
        "UNRESOLVED_PAPER_ENTRY_REQUIRES_REPAIR", "OPEN_PAPER_POSITIONS_EXCEED_24H",
        "REPAIR_DIAGNOSTICS_UNAVAILABLE", "SUCCESSOR_STATUS_UNAVAILABLE",
    )):
        engine["operational_status"] = "REVIEW_REQUIRED"
    return engine

def latest_paper_lifecycle_status() -> dict[str, Any]:
    """Return clean execution-lifecycle evidence separately from sealed science."""
    try:
        rows = supabase_get_rows(
            "alpha_hunter_paper_lifecycle_status_v05",
            {"select": "*", "limit": "1"},
        )
        if rows and isinstance(rows[0], dict):
            return rows[0]
    except (requests.RequestException, RuntimeError, ValueError):
        return {}
    return {}


def latest_control_tower_status() -> dict[str, Any]:
    try:
        rows = supabase_get_rows(
            "alpha_hunter_v14_watchdog_status_v01",
            {"select": "*", "limit": "1"},
        )
        if rows and isinstance(rows[0], dict):
            return rows[0]
    except (requests.RequestException, RuntimeError, ValueError):
        app.logger.warning(
            "V14 watchdog aggregate unavailable; using lightweight R8 fallback",
            exc_info=True,
        )

    engine = latest_test_engine_status()
    if not engine:
        raise RuntimeError("V14 control-tower status is unavailable")

    source_status = engine.get("source_status")
    if not isinstance(source_status, dict):
        source_status = {}

    deployment = {}
    try:
        deployment_rows = supabase_get_rows(
            "alpha_hunter_production_deployment_runtime_status_v03",
            {"select": "*", "limit": "1"},
        )
        if deployment_rows and isinstance(deployment_rows[0], dict):
            deployment = deployment_rows[0]
    except (requests.RequestException, RuntimeError, ValueError):
        deployment = {}

    minimum_days = int(engine.get("minimum_test_days") or 30)
    minimum_trades = int(engine.get("minimum_completed_paper_trades") or 100)
    test_days_elapsed = safe_float(engine.get("test_days_elapsed"))
    completed_trades = int(engine.get("completed_paper_trades") or 0)

    latest_scan_at = parse_utc(engine.get("latest_live_scan_at_utc"))
    latest_scan_age_seconds = None
    if latest_scan_at is not None:
        latest_scan_age_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - latest_scan_at).total_seconds(),
        )

    baseline_started_at = parse_utc(
        engine.get("real_counted_baseline_started_at_utc")
    )
    earliest_duration_gate = None
    if baseline_started_at is not None:
        earliest_duration_gate = (
            baseline_started_at + timedelta(days=minimum_days)
        ).isoformat()

    critical_alerts: list[str] = []
    warning_alerts: list[str] = []
    expected_gates: list[str] = []

    if str(engine.get("operational_status") or "") != "PASS":
        critical_alerts.append("TEST_ENGINE_OPERATIONAL_BLOCKED")
    if source_status.get("cadence_integrity_ok") is not True:
        critical_alerts.append("CADENCE_INTEGRITY_FAILED")
    if int(source_status.get("identity_drift_scans") or 0) > 0:
        critical_alerts.append("SCIENTIFIC_IDENTITY_DRIFT")
    if bool(deployment.get("deployment_drift")):
        warning_alerts.append("RENDER_CRON_DEPLOYMENT_DRIFT")
    if engine.get("cost_model_validated") is not True:
        warning_alerts.append("EXECUTION_COST_MODEL_NOT_VALIDATED")

    economics = engine.get("economics")
    if not isinstance(economics, dict):
        economics = {}
    if economics.get("duration_gate_met") is not True:
        expected_gates.append("MINIMUM_30_DAY_DURATION_NOT_MET")
    if economics.get("sample_gate_met") is not True:
        expected_gates.append("MINIMUM_100_PAPER_TRADES_NOT_MET")
    if engine.get("realistic_net_r_claim_permitted") is not True:
        expected_gates.append("REALISTIC_NET_R_CLAIM_NOT_YET_PERMITTED")

    watchdog_status = (
        "CRITICAL"
        if critical_alerts
        else "WARNING"
        if warning_alerts
        else "HEALTHY"
    )

    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "spec_id": engine.get("spec_id"),
        "engine_version": engine.get("engine_version"),
        "operational_status": engine.get("operational_status"),
        "profitability_status": engine.get("profitability_status"),
        "verdict": engine.get("verdict"),
        "watchdog_status": watchdog_status,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "expected_gates": expected_gates,
        "latest_live_scan_at_utc": engine.get("latest_live_scan_at_utc"),
        "latest_live_scan_age_seconds": latest_scan_age_seconds,
        "completed_paper_trades": completed_trades,
        "minimum_completed_paper_trades": minimum_trades,
        "paper_trades_remaining": max(minimum_trades - completed_trades, 0),
        "test_days_elapsed": test_days_elapsed,
        "minimum_test_days": minimum_days,
        "test_days_remaining": max(minimum_days - test_days_elapsed, 0.0),
        "earliest_duration_gate_at_utc": earliest_duration_gate,
        "post_start_scans": int(source_status.get("post_start_scans") or 0),
        "identity_drift_scans": int(
            source_status.get("identity_drift_scans") or 0
        ),
        "cadence_integrity_status": source_status.get(
            "cadence_integrity_status"
        ),
        "too_frequent_scan_intervals": 0,
        "excessive_gap_intervals": 0,
        "identity_mismatch_scan_count": int(
            source_status.get("identity_drift_scans") or 0
        ),
        "expected_schedule": "RENDER_CRON_ALIGNED_00_20_40",
        "cost_scientific_status": (
            "VALIDATED"
            if engine.get("cost_model_validated") is True
            else "R8_EXECUTED_PAPER_COST_VALIDATION_PENDING"
        ),
        "cost_next_gate": source_status.get("cost_validation_next_gate"),
        "account_identity_probe_status": None,
        "historical_fill_continuity_conflict": False,
        "historical_fill_rows_same_window": None,
        "database_size_pretty": None,
        "live_toast_review_tables": None,
        "legacy_control_plane_status": None,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }


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


def parse_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def snapshot_action_blockers(
    snapshot: dict[str, Any],
    *,
    observed_at: datetime | None = None,
) -> list[str]:
    """Return global fail-closed blockers for a paper-action decision."""
    blockers: list[str] = []
    freshness = snapshot.get("canonical_market_freshness")
    if not isinstance(freshness, dict) or freshness.get("verified") is not True:
        blockers.append("CANONICAL_MARKET_FRESHNESS_UNVERIFIED")

    collected_at = parse_utc(snapshot.get("collected_at_utc"))
    now = observed_at or datetime.now(timezone.utc)
    if collected_at is None:
        blockers.append("SNAPSHOT_TIMESTAMP_MISSING")
    else:
        age_seconds = (now - collected_at).total_seconds()
        if age_seconds < -300:
            blockers.append("SNAPSHOT_TIMESTAMP_IN_FUTURE")
        elif age_seconds > MAXIMUM_ACTION_SNAPSHOT_AGE_SECONDS:
            blockers.append("SNAPSHOT_STALE_FOR_ACTION")
    return blockers


def _price_tick(instrument: dict[str, Any]) -> Decimal | None:
    try:
        places = int(instrument.get("price_place"))
        end_step = Decimal(str(instrument.get("price_end_step")))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if places < 0 or end_step <= 0:
        return None
    tick = end_step * (Decimal(10) ** -places)
    return tick if tick > 0 else None


def normalize_price(value: Any, instrument: dict[str, Any]) -> float | None:
    number = safe_optional_float(value)
    tick = _price_tick(instrument)
    if number is None or tick is None:
        return None
    try:
        decimal_value = Decimal(str(number))
        ticks = (decimal_value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return float(ticks * tick)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _action_market_row(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("_market_row")
    return source if isinstance(source, dict) else row


def action_quality_blockers(row: dict[str, Any]) -> list[str]:
    """Validate final paper-action geometry, cost floor and venue precision."""
    action = row.get("_action")
    if not isinstance(action, dict):
        return ["ACTION_PAYLOAD_MISSING"]

    direction = str(action.get("direction") or "").upper()
    entry = safe_optional_float(action.get("entry"))
    stop = safe_optional_float(action.get("stop"))
    target = safe_optional_float(action.get("target"))
    declared_rr = safe_optional_float(action.get("rr"))
    blockers: list[str] = []

    if direction not in {"LONG", "SHORT"}:
        blockers.append("DIRECTION_INVALID")
    if None in (entry, stop, target, declared_rr):
        blockers.append("EXECUTION_GEOMETRY_MISSING")
        return blockers
    assert entry is not None and stop is not None and target is not None
    assert declared_rr is not None

    if not all(math.isfinite(value) and value > 0 for value in (entry, stop, target, declared_rr)):
        blockers.append("EXECUTION_GEOMETRY_NON_FINITE")
        return blockers

    if direction == "LONG":
        geometry_ok = stop < entry < target
        risk = entry - stop
        reward = target - entry
    else:
        geometry_ok = target < entry < stop
        risk = stop - entry
        reward = entry - target
    if not geometry_ok or risk <= 0:
        blockers.append("EXECUTION_GEOMETRY_INVALID")
        return blockers

    calculated_rr = reward / risk
    rr_error = abs(declared_rr - calculated_rr) / calculated_rr
    if rr_error > 0.02:
        blockers.append("DECLARED_RR_MISMATCH")
    if calculated_rr > MAXIMUM_ACTION_RR:
        blockers.append("EXECUTION_RR_OUTLIER")

    market = _action_market_row(row)
    instrument = market.get("instrument_constraints")
    if not isinstance(instrument, dict) or _price_tick(instrument) is None:
        blockers.append("BITGET_PRICE_PRECISION_MISSING")
    else:
        normalized = {
            name: normalize_price(action.get(name), instrument)
            for name in ("entry", "stop", "target")
        }
        if any(value is None for value in normalized.values()):
            blockers.append("BITGET_PRICE_NORMALIZATION_FAILED")
        else:
            action.update(normalized)
            entry = normalized["entry"]
            stop = normalized["stop"]
            target = normalized["target"]
            assert entry is not None and stop is not None and target is not None
            normalized_geometry_ok = (
                stop < entry < target
                if direction == "LONG"
                else target < entry < stop
            )
            if not normalized_geometry_ok:
                blockers.append("BITGET_NORMALIZED_GEOMETRY_INVALID")

    bid = safe_optional_float(market.get("bid_price"))
    ask = safe_optional_float(market.get("ask_price"))
    taker_fee_bps = safe_optional_float(
        instrument.get("public_taker_fee_bps")
        if isinstance(instrument, dict)
        else None
    )
    if bid is None or ask is None or bid <= 0 or ask < bid or taker_fee_bps is None:
        blockers.append("EXECUTION_COST_EVIDENCE_MISSING")
    else:
        midpoint = (bid + ask) / 2.0
        spread_pct = (ask - bid) / midpoint * 100.0
        round_trip_fee_pct = 2.0 * taker_fee_bps / 100.0
        cost_floor_pct = spread_pct + round_trip_fee_pct
        risk_pct = risk / entry * 100.0
        action["cost_floor_pct"] = cost_floor_pct
        action["risk_pct"] = risk_pct
        action["cost_to_stop_ratio"] = cost_floor_pct / risk_pct if risk_pct > 0 else None
        if cost_floor_pct >= risk_pct:
            blockers.append("EXECUTION_COST_FLOOR_CONSUMES_STOP")

    return list(dict.fromkeys(blockers))


def _blocked_copy(row: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    blocked = dict(row)
    action = dict(row.get("_action") or {})
    action.update(
        status="BLOCKED",
        label="BLOCKED — SAFETY GATE",
        priority=0,
        reason="Blocked: " + ", ".join(blockers),
        blockers=list(blockers),
        execution_authority=False,
    )
    blocked["_action"] = action
    return blocked


def canonicalize_action_queue(
    rows: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce one fail-closed paper decision per symbol without losing evidence."""
    global_blockers = snapshot_action_blockers(snapshot)
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for row in rows:
        action = row.get("_action")
        if not isinstance(action, dict):
            blocked.append(_blocked_copy(row, ["ACTION_PAYLOAD_MISSING"]))
            continue
        raw_status = str(action.get("status") or "")
        if raw_status == "RETEST_PLAN":
            if global_blockers:
                blocked.append(_blocked_copy(row, list(global_blockers)))
                continue
            action = dict(action)
            action.update(
                status="WAIT_FOR_TRIGGER",
                label="WAIT FOR TRIGGER",
                priority=1,
                execution_authority=False,
            )
            row = dict(row)
            row["_action"] = action
            eligible.append(row)
            continue

        blockers = list(global_blockers)
        blockers.extend(action_quality_blockers(row))
        if blockers:
            blocked.append(_blocked_copy(row, list(dict.fromkeys(blockers))))
            continue

        action = dict(row["_action"])
        if raw_status in {"READY_NOW", "STRATEGY_READY_NOW"}:
            action.update(
                status="EXECUTE_NOW_PAPER",
                label="PAPER — EXECUTE NOW",
                execution_authority=False,
            )
        elif raw_status == "STRATEGY_LIMIT_READY":
            action.update(
                status="PLACE_LIMIT_PAPER",
                label="PAPER — PLACE LIMIT",
                execution_authority=False,
            )
        row = dict(row)
        row["_action"] = action
        eligible.append(row)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        grouped.setdefault(str(row.get("symbol") or ""), []).append(row)

    canonical: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for symbol, candidates in grouped.items():
        executable = [
            row for row in candidates
            if row["_action"].get("status") in {
                "EXECUTE_NOW_PAPER",
                "PLACE_LIMIT_PAPER",
            }
        ]
        directions = {
            str(row["_action"].get("direction") or "").upper()
            for row in executable
        }
        if len(directions) > 1:
            for row in candidates:
                blocked.append(_blocked_copy(row, ["DIRECTION_CONFLICT"]))
            continue

        ranked = sorted(
            candidates,
            key=lambda row: (
                safe_float(row["_action"].get("priority")),
                -safe_float(row["_action"].get("distance_pct")),
                safe_float(row.get("_behaviour")),
                safe_float(row.get("_score")),
            ),
            reverse=True,
        )
        canonical.append(ranked[0])
        for row in ranked[1:]:
            suppressed.append(_blocked_copy(row, ["SUPERSEDED_BY_CANONICAL_SYMBOL_DECISION"]))

    canonical.sort(
        key=lambda row: (
            safe_float(row["_action"].get("priority")),
            -safe_float(row["_action"].get("distance_pct")),
            safe_float(row.get("_behaviour")),
            safe_float(row.get("_score")),
        ),
        reverse=True,
    )
    blocked.sort(key=lambda row: str(row.get("symbol") or ""))
    return canonical, blocked, suppressed


def symbol_label(value: Any) -> str:
    """Make leading-zero Bitget contract symbols unambiguous on small screens."""
    symbol = str(value or "")
    if (
        symbol.startswith("0")
        and symbol.endswith("USDT")
        and len(symbol) > len("0USDT")
    ):
        base = symbol[:-4]
        remainder = base[1:] or "?"
        return f"{symbol} (ZERO-{remainder})"
    return symbol


app.jinja_env.filters["symbol_label"] = symbol_label


def position_protection_view(
    position: dict[str, Any],
    observed_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a truthful operator view of exchange protection evidence.

    Blank TP/SL fields are never interpreted as "no protection" unless the
    dedicated Bitget protection observer completed successfully.
    """
    row = dict(position)
    observation_status = str(
        position.get("protection_observation_status") or "UNKNOWN"
    ).upper()
    raw_orders = position.get("protection_orders")
    orders = raw_orders if isinstance(raw_orders, list) else []

    def present(value: Any) -> bool:
        return value is not None and str(value).strip() != ""

    def unique_levels(plan_types: set[str], scalar: Any) -> list[str]:
        levels: list[str] = []
        if present(scalar):
            levels.append(str(scalar).strip())
        for order in orders:
            if not isinstance(order, dict):
                continue
            plan_type = str(order.get("plan_type") or "").strip().lower()
            trigger = order.get("trigger_price")
            if plan_type in plan_types and present(trigger):
                value = str(trigger).strip()
                if value not in levels:
                    levels.append(value)
        return levels

    tp_levels = unique_levels({"profit_plan", "pos_profit"}, position.get("take_profit"))
    sl_levels = unique_levels({"loss_plan", "pos_loss"}, position.get("stop_loss"))

    observer_complete = observation_status == "CONNECTED"
    any_protection = bool(tp_levels or sl_levels)

    if not observer_complete:
        protection_state = "UNKNOWN"
        protection_warning = "Protection observation unavailable — do not infer no SL/TP."
    elif any_protection:
        protection_state = "OBSERVED"
        if not tp_levels or not sl_levels:
            protection_warning = "Partial protection observed."
        else:
            protection_warning = None
    else:
        protection_state = "NONE_OBSERVED"
        protection_warning = "Observer completed and no active TP/SL was observed."

    row.update(
        {
            "_protection_state": protection_state,
            "_protection_observation_status": observation_status,
            "_protection_observed_at_utc": observed_at_utc,
            "_take_profit_levels": tp_levels,
            "_stop_loss_levels": sl_levels,
            "_take_profit_display": ", ".join(tp_levels)
            if tp_levels
            else ("None observed" if observer_complete else "Unknown"),
            "_stop_loss_display": ", ".join(sl_levels)
            if sl_levels
            else ("None observed" if observer_complete else "Unknown"),
            "_protection_warning": protection_warning,
        }
    )
    return row


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


# Release 2.1 makes the dashboard and persistence job consume one shared gate.
# These imports intentionally replace the legacy local definitions above while
# keeping the surrounding dashboard diff small and regression-friendly.
from alpha_hunter.action_queue import (  # noqa: E402
    build_money_action,
    build_strategy_money_action,
    canonicalize_action_queue,
)


def dashboard_payload(
    snapshot: dict[str, Any],
    test_engine: dict[str, Any] | None = None,
    paper_lifecycle: dict[str, Any] | None = None,
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
    market_rows_by_symbol = {
        str(row.get("symbol") or ""): row
        for row in discovery_symbols
    }

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

    # The matrix is diagnostic evidence, not the final action queue. Make
    # conflicting symbol directions and WATCH-only setup intent explicit so the
    # operator cannot mistake raw per-strategy intent for a canonical decision.
    strategy_directions_by_symbol: dict[str, set[str]] = {}
    for item in strategy_shadow:
        if str(item.get("status") or "") != "SHADOW_CANDIDATE":
            continue
        direction = str(item.get("direction") or "").upper()
        action = str(item.get("action") or "").upper()
        if direction in {"LONG", "SHORT"} and action in {"EXECUTE_NOW", "PLACE_LIMIT"}:
            strategy_directions_by_symbol.setdefault(
                str(item.get("symbol") or ""), set()
            ).add(direction)

    for item in strategy_shadow:
        symbol = str(item.get("symbol") or "")
        status = str(item.get("status") or "")
        action = str(item.get("action") or "").upper()
        proposed = str(item.get("proposed_action") or action).upper()
        item["_symbol_direction_conflict"] = (
            len(strategy_directions_by_symbol.get(symbol, set())) > 1
        )
        # Only the final canonicalized action queue may supply the gate verdict.
        # An S1-S10 raw EXECUTE_NOW is uncalibrated SHADOW intent, not permission.
        item["_display_gate_action"] = (
            action
            if status != "SHADOW_CANDIDATE"
            and action not in {"EXECUTE_NOW", "PLACE_LIMIT"}
            else "NOT_APPROVED"
        )
        item["_display_setup_intent"] = (
            f"SHADOW_{proposed}"
            if proposed in {"EXECUTE_NOW", "PLACE_LIMIT"}
            else proposed
        )
        item["_display_warning"] = (
            "Shadow setup intent only; await the final canonical safety verdict."
            if proposed in {"EXECUTE_NOW", "PLACE_LIMIT"}
            else ""
        )
        if item["_symbol_direction_conflict"]:
            item["_display_gate_action"] = "BLOCKED_CONFLICT"
            item["_display_setup_intent"] = "NO_ACTION"
            item["_display_warning"] = (
                "Symbol has opposing LONG/SHORT executable strategy candidates; "
                "final action queue fails closed."
            )
        elif status != "SHADOW_CANDIDATE" and proposed in {"EXECUTE_NOW", "PLACE_LIMIT"}:
            item["_display_setup_intent"] = "WATCH_ONLY"
            item["_display_warning"] = (
                f"Raw setup intent {proposed} is not executable because strategy "
                f"status is {status or 'UNKNOWN'}."
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
            "_market_row": market_rows_by_symbol.get(
                str(item.get("symbol") or "")
            ),
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

    combined_actionable, blocked_actions, suppressed_actions = canonicalize_action_queue(
        actionable + strategy_ready,
        snapshot,
    )

    # Reflect the same final paper-action gate in the S1-S10 diagnostic matrix.
    # Match by the original strategy dictionary reference, not merely by symbol:
    # opposing or parallel strategies for one symbol have different verdicts.
    # Never alter source strategy action/status, paper positions or test evidence.
    for gate_rows, visible_status in (
        (blocked_actions, "BLOCKED"),
        (suppressed_actions, "SUPPRESSED"),
        (combined_actionable, "PAPER_SIGNAL_ONLY"),
    ):
        for gated_row in gate_rows:
            strategy_item = gated_row.get("_strategy_payload")
            if not isinstance(strategy_item, dict):
                continue
            decision = gated_row.get("_action") or {}
            if not isinstance(decision, dict):
                continue
            gate_status = str(decision.get("status") or "")
            strategy_item["_display_gate_action"] = (
                "BLOCKED_CONFLICT"
                if strategy_item.get("_symbol_direction_conflict")
                and visible_status == "BLOCKED"
                else "WAIT_FOR_TRIGGER"
                if visible_status == "PAPER_SIGNAL_ONLY"
                and gate_status == "WAIT_FOR_TRIGGER"
                else visible_status
            )
            reason = str(decision.get("reason") or "")
            if visible_status in {"BLOCKED", "SUPPRESSED"}:
                strategy_item["_display_warning"] = (
                    reason
                    or "Blocked by the final canonical paper execution gate."
                )
            else:
                strategy_item["_display_warning"] = (
                    "Canonical paper decision support only. No exchange order "
                    "authority; scientific admissions remain independently gated."
                )
    trade_ready = [
        row for row in combined_actionable
        if row["_action"]["status"] == "EXECUTE_NOW_PAPER"
    ]
    retest_plans = [
        row for row in combined_actionable
        if row["_action"]["status"] == "WAIT_FOR_TRIGGER"
    ]
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
        "blocked_actions": blocked_actions[:25],
        "suppressed_actions": suppressed_actions[:25],
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
        "positions": [
            position_protection_view(position, snapshot.get("collected_at_utc"))
            for position in account.get("open_positions", [])
            if isinstance(position, dict)
        ],
        "account_status": account.get("status", "UNKNOWN"),
        "universe": universe,
        "updated": snapshot.get("collected_at_utc"),
        "btc_change_24h": safe_float(snapshot.get("btc_change_24h_pct")),
        "minimum_execution_rr": MINIMUM_EXECUTION_RR,
        "discovery_summary": snapshot.get("discovery_summary", {}),
        "build": build_identity(),
        "test_engine": test_engine or {},
        "paper_lifecycle": paper_lifecycle or {},
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
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<!-- V8: avoid forced timed page refresh. User controls when evidence reloads. -->
<title>Alpha Hunter V8 — Research Terminal</title>
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
.v8-overview-preview .v8-preview-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.v8-overview-preview .v8-preview-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid #294155;min-width:0;overflow-wrap:anywhere}
.v8-overview-preview .v8-preview-item:last-child{border-bottom:0}
.v8-overview-preview .v8-preview-meta{text-align:right;color:#ffca6c;font-size:14px}
.v8-overview-preview .v8-preview-meta .small{color:#b2c6d5}
@media(max-width:430px){.v8-overview-preview .v8-preview-item{align-items:flex-start;flex-direction:column;gap:5px}.v8-overview-preview .v8-preview-meta{text-align:left}}
</style>
<link rel="stylesheet" href="{{ url_for('static', filename='v8.css') }}">
</head>
<body class="v8-body">
<div class="v8-shell">
  <aside class="v8-rail" aria-label="Primary workspace navigation">
    <div class="v8-brand">ALPHA HUNTER <span>V8</span></div>
    <div class="v8-brand-note">Research terminal</div>
    <nav class="v8-rail-nav" aria-label="Workspace">
      <button type="button" class="v8-tab" data-v8-tab="overview" aria-current="page"><span class="v8-nav-icon" aria-hidden="true">▦</span>Overview</button>
      <button type="button" class="v8-tab" data-v8-tab="research"><span class="v8-nav-icon" aria-hidden="true">⌕</span>Research</button>
      <button type="button" class="v8-tab" data-v8-tab="results"><span class="v8-nav-icon" aria-hidden="true">▥</span>Paper Results</button>
      <button type="button" class="v8-tab" data-v8-tab="system"><span class="v8-nav-icon" aria-hidden="true">⚙</span>System</button>
    </nav>
    <div class="v8-rail-foot"><strong>No real-money orders</strong>Paper and shadow research only. Research scores are not probabilities.</div>
  </aside>
  <div class="v8-content">
    <div class="v8-mobile-head"><strong>Alpha Hunter <span>V8</span></strong><span class="v8-kicker">Research only · No orders</span></div>
    <div class="wrap">
  <div class="top">
    <div><h1>Alpha Hunter V8 · Market Intelligence</h1><div class="sub">Evidence-first market research. Paper-only, with real-order execution disabled.</div><div class="v8-runtime-note">Underlying engine {{ data.build.version }} · Build {{ data.build.git_commit_short }} · {{ data.build.git_branch }} · {{ data.build.deployed_at_utc }}{% if data.build.deployed_at_source == 'process_start_fallback' %} (instance-start timestamp){% endif %}</div></div>
    <div><div class="toolbar"><div class="status">Latest accepted scan: {{ data.updated or 'Unavailable' }}</div><a class="v8-reset" href="/" aria-label="Refresh dashboard from the latest accepted canonical scan">Refresh view</a></div><div class="v8-runtime-note">Refresh reads saved canonical evidence only. The protected scanner runs separately; there is no manual scanner action in V8.</div></div>
  </div>

  <div class="v8-workspace" id="v8-workspace">
    <section id="v8-view-overview" class="v8-view" aria-labelledby="v8-overview-title">
      <div class="v8-view-heading"><h2 id="v8-overview-title">Overview</h2><p>Source health and market context</p></div>
    </section>
    <section id="v8-view-research" class="v8-view" aria-labelledby="v8-research-title" hidden>
      <div class="v8-view-heading"><h2 id="v8-research-title">Research watchlist</h2><p>WATCH and shadow evidence are not trading instructions</p></div>
    </section>
    <section id="v8-view-results" class="v8-view" aria-labelledby="v8-results-title" hidden>
      <div class="v8-view-heading"><h2 id="v8-results-title">Paper Results</h2><p>Scientific and operational evidence · unproven until validated</p></div>
    </section>
    <section id="v8-view-system" class="v8-view" aria-labelledby="v8-system-title" hidden>
      <div class="v8-view-heading"><h2 id="v8-system-title">System &amp; diagnostics</h2><p>Preserved evidence and operational routes</p></div>

      <section class="v8-trust-panel" aria-labelledby="v8-trust-title">
        <div class="v8-trust-head">
          <div><span class="v8-kicker">Product transparency</span><h3 id="v8-trust-title">What Alpha Hunter does—and does not prove</h3>
            <p>A read-only research terminal for market observations, historical paper evidence and system diagnostics. Displayed information is not an instruction to trade.</p>
          </div>
        </div>
        <div class="v8-trust-grid">
          <div class="v8-trust-item"><h4>Research provenance</h4><p>Current observations appear only when canonical source checks pass. Historical records never replace incomplete or unavailable current evidence.</p></div>
          <div class="v8-trust-item"><h4>Paper performance</h4><p>Paper results and shadow scores are not verified live returns, probability forecasts or a claim of scientific profitability.</p></div>
          <div class="v8-trust-item"><h4>Execution and release</h4><p>Real-money order authority is disabled. Browser checks are not an independent security certification or production-release approval.</p></div>
        </div>
        <div class="v8-share-tools">
          <button class="v8-reset" id="v8-copy-view-link" type="button">Copy link to this view</button>
          <p class="v8-share-feedback" id="v8-share-feedback" role="status" aria-live="polite">You can share this read-only system overview without sharing credentials or private records.</p>
          <input id="v8-share-manual" class="v8-share-input" type="text" readonly hidden aria-label="Select and copy this page link manually">
        </div>
      </section>
    </section>
  </div>
  <div class="v8-shell-status" data-v8-section="overview" aria-label="Evidence and permissions">
    <div class="v8-status-card v8-source">
      <span class="v8-status-icon" aria-hidden="true">✓</span>
      <div><span class="v8-kicker">Canonical source</span><h2>Latest symbol evidence loaded</h2><p>Scan: {{ data.updated or 'Timestamp unavailable' }}. Research is not independently verified as profitable.</p></div>
    </div>
    <div class="v8-status-card">
      <span class="v8-status-icon" aria-hidden="true">◇</span>
      <div><span class="v8-kicker">Paper research</span><h2>Execution not authorised</h2><p>WATCH, raw R:R and score do not grant paper or exchange-order permission.</p></div>
    </div>
    <div class="v8-status-card">
      <span class="v8-status-icon" aria-hidden="true">⌁</span>
      <div><span class="v8-kicker">Scanner continuity</span><h2>Protected separate process</h2><p>Web design does not launch a second scanner or alter source records.</p></div>
    </div>
  </div>
  <div class="v8-system-links" data-v8-section="system" aria-label="Existing system routes">
    <a href="/control-tower">V14 Control Tower</a>
    <a href="/performance">Performance report</a>
    <a href="/api/build">Build provenance</a>
    <a href="/api/historical-status">Historical evidence</a>
    <a href="/execution-freeze">Restricted evidence · operator login required</a>
  </div>
  <div class="cards" data-v8-section="overview">
    <div class="card"><div class="label">Universe</div><div class="value">{{ data.universe.get('selected_count',0) }}</div><div class="small">deep-scanned</div></div>
    <div class="card"><div class="label">Strict paper gate</div><div class="value ready">{{ data.trade_ready|length }}</div><div class="small">strict execution</div></div>
    <div class="card"><div class="label">Retest plans</div><div class="value warning">{{ data.retest_plans|length }}</div><div class="small">price must come to us</div></div>
    <div class="card"><div class="label">Minimum R:R</div><div class="value">{{ '%.1f'|format(data.minimum_execution_rr) }}R</div><div class="small">not relaxed</div></div>
    <div class="card"><div class="label">BTC 24H</div><div class="value {{ 'long' if data.btc_change_24h>0 else 'short' if data.btc_change_24h<0 else '' }}">{{ '%.2f'|format(data.btc_change_24h) }}%</div><div class="small">regime reference</div></div>
    <div class="card"><div class="label">Strategies</div><div class="value">{{ data.strategy_summary.get('configured_strategy_count',0) }}</div><div class="small">S1-S10 shadow · {{ data.strategy_summary.get('shadow_candidate_count',0) }} candidates</div></div>
    <div class="card"><div class="label">Microstructure</div><div class="value">{{ data.microstructure_summary.get('complete_count',0) }}/{{ data.microstructure_summary.get('eligible_symbol_count',0) }}</div><div class="small">Bitget depth + public trades</div></div>
    <div class="card"><div class="label">Persistent</div><div class="value">{{ data.strategy_summary.get('persistent_continuing_count',0) }}</div><div class="small">strategy signals continuing</div></div>
    <div class="card"><div class="label">Catalysts</div><div class="value">{{ data.catalyst_summary.get('fresh_bound_symbol_count',0) }}</div><div class="small">fresh official Bitget matches</div></div>
  </div>

  <div class="panel" data-v8-section="results">
    <h2 style="margin-top:0">Real-Time Profitability Test Engine</h2>
    {% if data.test_engine %}
      <div class="action-grid">
        <div class="metric"><span class="label">System integrity</span><b>{{ data.test_engine.get('operational_status','UNKNOWN') }}</b></div>
        <div class="metric"><span class="label">Verdict</span><b>{{ data.test_engine.get('verdict','NOT_PROVEN') }}</b></div>
        <div class="metric"><span class="label">Real scans</span><b>{{ data.test_engine.get('real_scans_since_registration','Unavailable') }}</b></div>
        <div class="metric"><span class="label">Current cohort completions</span><b>{{ data.test_engine.get('completed_paper_trades','Unavailable') }}/{{ data.test_engine.get('minimum_completed_paper_trades',100) }}</b></div>
        <div class="metric"><span class="label">Historical lifecycle exits</span><b>{{ data.paper_lifecycle.get('valid_completed_trades','Unavailable') }}</b></div>
        <div class="metric"><span class="label">Test days</span><b>{{ '%.2f'|format(data.test_engine.get('test_days_elapsed',0) or 0) }}/{{ data.test_engine.get('minimum_test_days',30) }}</b></div>
        <div class="metric"><span class="label">Separate 24H signal outcomes</span><b>{{ data.test_engine.get('real_24h_forward_outcomes_since_registration','Unavailable') }}</b></div>
      </div>
      <div class="reason">
        <b>Real-time:</b> {{ data.test_engine.get('evaluated_at_utc') }}<br>
        <b>Test identity:</b> {{ data.test_engine.get('spec_id','Unavailable') }}<br>
        <b>Latest market scan:</b> {{ data.test_engine.get('latest_live_scan_at_utc') }}<br>
        <b>Profitability status:</b> {{ data.test_engine.get('profitability_status') }}<br>
        <b>Blockers:</b> {{ (data.test_engine.get('blockers') or [])|join(', ') if data.test_engine.get('blockers') else 'NONE' }}<br>
        <b>Historical lifecycle totals:</b> {{ data.paper_lifecycle.get('valid_completed_trades','Unavailable') }} closed · {{ data.paper_lifecycle.get('active_valid_positions','Unavailable') }} active · {{ data.paper_lifecycle.get('invalid_geometry_quarantined','Unavailable') }} geometry-quarantined<br>
        <span class="small">Current cohort completions, historical lifecycle exits and 24H signal outcomes are separate evidence streams and are never added together. Collection activity does not prove profitability. Forward-only real market evidence; historical replay/backtest is not counted. Paper-only; no order authority.</span>
      </div>
    {% else %}
      <div class="empty">No test-engine evaluation has been persisted yet. The hourly real-time test runner will populate this panel.</div>
    {% endif %}
  </div>

  {% if data.best_action %}
    {% set row=data.best_action %}{% set a=row._action %}
    <div class="panel {{ 'action-ready' if a.status in ['READY_NOW','STRATEGY_READY_NOW','STRATEGY_LIMIT_READY'] else 'action-retest' }}" data-v8-section="overview">
      <div class="action-title retest">PAPER CANDIDATE — {{ a.label }}</div>
      <div class="small">Simulated decision support. Profitability is unproven; this is not an exchange order instruction.</div>
      <h2 style="margin:8px 0 0">{{ row.symbol|symbol_label }} {{ a.direction }}</h2>
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
    <div class="panel action-none" data-v8-section="overview">
      <div class="action-title">FINAL PAPER EXECUTION GATE</div>
      <h2 style="margin:8px 0">NO VALID EXECUTION YET</h2>
      <div class="reason">A discovery symbol is not a trade recommendation. The protected scanner runs independently; a paper candidate may appear only after the final evidence gates are satisfied.</div>
    </div>
  {% endif %}

  <section class="v8-overview-preview panel" data-v8-section="overview" aria-label="Top research observations">
    <div class="v8-preview-heading">
      <h2 style="margin:0">Top research observations</h2>
      <button class="v8-reset" type="button" data-v8-tab="research">View all research</button>
    </div>
    <p class="small muted">Research observations from the accepted canonical scan. WATCH never authorises exchange execution or proves profitability.</p>
    {% for s in data.strategy_shadow[:3] %}
    <div class="v8-preview-item">
      <div><strong>{{ s.symbol|symbol_label }}</strong><div class="small muted">{{ s.strategy_id }} {{ s.strategy_name }}</div></div>
      <div class="v8-preview-meta"><strong>{{ s.status }}</strong><div class="small">Direction {{ s.direction or '—' }} · Raw R:R {{ '%.2f'|format(s.rr) if s.rr is not none else '—' }}</div></div>
    </div>
    {% else %}
    <p class="small muted">No strategy research observations in this accepted snapshot.</p>
    {% endfor %}
  </section>

  <div class="panel v8-strategy-panel" data-v8-section="research">
    <h2 style="margin-top:0">S1-S10 Strategy Matrix — Shadow</h2>
    <div class="small" style="margin-bottom:10px">S1-S10 scores and setup intents are uncalibrated shadow evidence, never exchange instructions. The Gate action column reflects the FINAL canonical paper safety gate, not the raw strategy intent. Candidate status and 10/10 scores do not override blocks. Coverage: {{ data.strategy_summary.get('total_evaluations',0) }} evaluations across {{ data.strategy_summary.get('covered_symbol_count',0) }} symbols. Previous canonical context: {{ data.previous_snapshot_context.get('source','NONE') }}{% if data.previous_snapshot_context.get('collected_at_utc') %} · {{ data.previous_snapshot_context.get('collected_at_utc') }}{% endif %}.</div>
    <details class="v8-coverage"><summary>Strategy coverage and diagnostic counts</summary><div class="toolbar">
      {% for row in data.strategy_coverage %}
      <span class="badge badge-research">{{ row.strategy_id }}: {{ row.evaluations }} eval / {{ row.candidates }} cand</span>
      {% endfor %}
    </div></details>
    <div class="v8-research-controls" aria-label="Research filters">
      <label class="v8-filter-wrap v8-search-wrap">Search symbol or strategy<input type="search" id="v8-search" placeholder="e.g. BEAMUSDT" autocomplete="off"></label>
      <label class="v8-filter-wrap">Research status<select id="v8-status"><option value="">All statuses</option></select></label>
      <label class="v8-filter-wrap">Direction<select id="v8-side"><option value="">All sides</option></select></label>
      <label class="v8-filter-wrap">Strategy<select id="v8-strategy"><option value="">All strategies</option></select></label>
      <label class="v8-filter-wrap">Sort research<select id="v8-sort"><option value="canonical">Canonical order</option><option value="symbol">Symbol A–Z</option><option value="rr">Raw R:R (highest)</option><option value="persistence">Consecutive scans (highest)</option></select></label>
      <button class="v8-reset" id="v8-reset" type="button">Reset filters</button>
    </div>
    <span class="v8-count" id="v8-result-count" role="status" aria-live="polite"></span>
    <div class="v8-mobile-cards" id="v8-mobile-cards" aria-label="Expandable mobile research entries"></div>
    {% if data.strategy_shadow %}
    <table class="v8-strategy-table" aria-label="S1-S10 research comparison"><thead><tr><th>Symbol</th><th>Strategy</th><th>Status</th><th>Persistence · scans</th><th>Scans</th><th>Side</th><th>Final paper gate</th><th>Raw shadow intent (not executable)</th><th>Score</th><th>Entry</th><th>Stop</th><th>Target</th><th>Raw R:R</th><th>Why / blocker</th></tr></thead><tbody>
    {% for s in data.strategy_shadow %}
      <tr>
        <td><button type="button" class="v8-open-research" aria-label="View research details for {{ s.symbol|e }}">{{ s.symbol|symbol_label }}</button></td>
        <td><b>{{ s.strategy_id }}</b> {{ s.strategy_name }}</td>
        <td><span class="badge {{ 'badge-retest' if s.status in ('SHADOW_CANDIDATE','WATCH') else 'badge-research' }}">{{ s.status }}</span></td>
        <td>{{ s._persistence_state }}</td>
        <td>{{ s._consecutive_scans }}</td>
        <td class="{{ 'long' if s.direction=='LONG' else 'short' if s.direction=='SHORT' else '' }}">{{ s.direction or '—' }}</td>
        <td>{{ s._display_gate_action }}</td>
        <td>{{ s._display_setup_intent }}</td>
        <td>{{ '%.2f'|format(s.signal_score or 0) }}</td>
        <td>{{ s.entry if s.entry is not none else '—' }}</td>
        <td>{{ s.stop if s.stop is not none else '—' }}</td>
        <td>{{ s.target if s.target is not none else '—' }}</td>
        <td>{{ '%.2f'|format(s.rr) if s.rr is not none else '—' }}</td>
        <td class="wrap-cell muted">{{ s._display_warning or ((s.reasons or [])|join('; ')) }}</td>
      </tr>
    {% endfor %}
    </tbody></table>
    <div class="v8-detail-panel" id="v8-detail-panel" role="region" aria-label="Selected strategy research details" hidden></div>
    {% else %}
      <div class="empty">No S1-S10 observations are available in this accepted snapshot.</div>
    {% endif %}
    <button type="button" class="v8-load-more" id="v8-load-more" hidden>Show more research</button>
  </div>

  <div class="layout">
    <main>
      <div class="panel" data-v8-section="results">
        <h2 style="margin-top:0">Paper Action Queue</h2>
        <div class="small" style="margin-bottom:10px">PAPER ONLY · NO ORDER AUTHORITY · Canonical snapshot {{ data.updated or 'timestamp unavailable' }}</div>
        {% if data.actionable %}
        <table><thead><tr><th>Symbol</th><th>Action</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th><th>Distance</th><th>Reason</th></tr></thead><tbody>
        {% for row in data.actionable %}{% set a=row._action %}
        <tr><td><b>{{ row.symbol|symbol_label }}</b></td><td><span class="badge {{ 'badge-ready' if a.status in ['EXECUTE_NOW_PAPER','PLACE_LIMIT_PAPER'] else 'badge-retest' }}">{{ a.status }}</span></td><td class="{{ 'long' if a.direction=='LONG' else 'short' }}">{{ a.direction }}</td><td>{{ a.entry }}</td><td>{{ a.stop }}</td><td>{{ a.target }}</td><td>{{ '%.2f'|format(a.rr or 0) }}</td><td>{{ '%.2f'|format(a.distance_pct or 0) }}%</td><td class="wrap-cell muted">{{ a.reason }}</td></tr>
        {% endfor %}</tbody></table>
        {% else %}<div class="empty">NO SAFE PAPER TRADE in the current canonical snapshot.</div>{% endif %}
      </div>

      <div class="panel" data-v8-section="system">
        <h2 style="margin-top:0">Safety Blocks</h2>
        {% if data.blocked_actions %}
        <table><thead><tr><th>Symbol</th><th>Side</th><th>State</th><th>Reason</th></tr></thead><tbody>
        {% for row in data.blocked_actions %}{% set a=row._action %}
        <tr><td><b>{{ row.symbol|symbol_label }}</b></td><td class="{{ 'long' if a.direction=='LONG' else 'short' }}">{{ a.direction or '—' }}</td><td><span class="badge badge-research">BLOCKED</span></td><td class="wrap-cell muted">{{ a.reason }}</td></tr>
        {% endfor %}</tbody></table>
        {% else %}<div class="empty">No final action-gate blocks in this snapshot.</div>{% endif %}
      </div>

      <div class="panel" data-v8-section="research">
        <h2 style="margin-top:0">Research / Discovery Radar</h2>
        <div class="small" style="margin-bottom:10px">These rows are information, not trade recommendations. They become actionable only through the Money Action block above.</div>
        <table><thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>Phase</th><th>Timing</th><th>Behaviour</th><th>State</th><th>R:R</th><th>Execution</th><th>Reason</th></tr></thead><tbody>
        {% for row in data.research %}
        <tr><td>{{ loop.index }}</td><td><b>{{ row.symbol|symbol_label }}</b></td><td>{{ row.last_price }}</td><td>{{ row._phase }}</td><td>{{ row._timing }}</td><td>{{ '%.2f'|format(row._behaviour) }}</td><td class="{{ 'long' if 'LONG' in row.state else 'short' if 'SHORT' in row.state else '' }}">{{ row.state }}</td><td>{{ '%.2f'|format(row._rr) if row._rr is not none else '—' }}</td><td><span class="badge {{ 'badge-ready' if row._action.status=='READY_NOW' else 'badge-retest' if row._action.status=='RETEST_PLAN' else 'badge-research' }}">{{ row._action.label }}</span></td><td class="wrap-cell muted">{{ row._action.reason }}</td></tr>
        {% endfor %}</tbody></table>
      </div>

      <div class="panel" data-v8-section="system"><h2 style="margin-top:0">Bitget Open Positions</h2>
      {% if data.positions %}<table><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Mark</th><th>Leverage</th><th>Unrealized P/L</th><th>SL</th><th>TP</th><th>Protection</th></tr></thead><tbody>
      {% for p in data.positions %}<tr><td><b>{{ p.symbol|symbol_label }}</b></td><td>{{ p.hold_side }}</td><td>{{ p.total }}</td><td>{{ p.open_price_avg }}</td><td>{{ p.mark_price }}</td><td>{{ p.leverage }}×</td><td>{{ p.unrealized_pl }}</td><td>{{ p._stop_loss_display }}</td><td>{{ p._take_profit_display }}</td><td><span class="badge {{ 'badge-ready' if p._protection_state=='OBSERVED' else 'badge-research' }}">{{ p._protection_state }}</span>{% if p._protection_warning %}<div class="small warning">{{ p._protection_warning }}</div>{% endif %}<div class="small muted">observer={{ p._protection_observation_status }} · {{ p._protection_observed_at_utc or 'time unavailable' }}</div></td></tr>{% endfor %}
      </tbody></table>
      {% elif data.account_status == 'CONNECTED' %}<div class="empty">No open Bitget positions observed in the completed account snapshot.</div>
      {% else %}<div class="warning">Open-position observation unavailable (account status: {{ data.account_status }}). Do not infer that no position exists.</div>{% endif %}</div>
    </main>

    <aside>
      <div class="panel" data-v8-section="overview"><h2 style="margin-top:0">Reference / Regime</h2>{% for row in data.references %}<div class="side-row"><span><b>{{ row.symbol|symbol_label }}</b></span><span>{{ row.last_price }}</span></div>{% else %}<div class="empty">No reference assets.</div>{% endfor %}</div>
      <div class="panel" data-v8-section="system"><h2 style="margin-top:0">Product Contract</h2><div class="small">Discovery ≠ recommendation.<br><br>EXECUTE_NOW_PAPER and PLACE_LIMIT_PAPER require canonical freshness, one direction per symbol, valid bounded geometry, public fee/spread evidence and Bitget price precision.<br><br>WAIT_FOR_TRIGGER is monitoring only. BLOCKED rows retain their evidence and state the failed gate.<br><br>No screen grants real-order authority and no threshold is relaxed.</div></div>
    </aside>
  </div>
</div>
</div>
<nav class="v8-bottom-nav" aria-label="Mobile workspace navigation">
  <button type="button" class="v8-tab" data-v8-tab="overview" aria-current="page"><span class="v8-nav-icon" aria-hidden="true">▦</span>Overview</button>
  <button type="button" class="v8-tab" data-v8-tab="research"><span class="v8-nav-icon" aria-hidden="true">⌕</span>Research</button>
  <button type="button" class="v8-tab" data-v8-tab="results"><span class="v8-nav-icon" aria-hidden="true">▥</span>Results</button>
  <button type="button" class="v8-tab" data-v8-tab="system"><span class="v8-nav-icon" aria-hidden="true">⚙</span>System</button>
</nav>
</div>
<!-- Manual scanner JavaScript intentionally absent from the public V8 UI.
     The legacy backend endpoint is a separate security review item. -->
<script src="{{ url_for('static', filename='v8.js') }}" defer></script>
</body>
</html>
"""


EXECUTION_FREEZE_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="8">
  <title>Alpha Hunter — Freeze Decision</title>
  <style>
    :root{--bg:#071018;--panel:#0d1822;--line:#1d2e3a;--text:#e8f0f6;--muted:#91a3b1;--ok:#2bd39a;--warn:#ffbf47;--bad:#ff6474;--blue:#4db6ff}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
    .wrap{max-width:760px;margin:auto;padding:14px}.top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}
    h1{font-size:25px;margin:0 0 5px}.small,.muted{color:var(--muted)}.small{font-size:12px}.link{color:var(--blue);text-decoration:none}
    .notice,.candidate,.empty{background:rgba(13,24,34,.97);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
    .notice{border-color:#6f5b2a}.symbol{font-size:24px;font-weight:900}.side-long{color:var(--ok)}.side-short{color:var(--bad)}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.metric{background:#09131c;border:1px solid #162734;border-radius:10px;padding:9px}
    .label{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.value{font-weight:800;margin-top:3px;overflow-wrap:anywhere}
    button{width:100%;border:0;border-radius:12px;padding:15px;font-size:16px;font-weight:900;background:#24d18f;color:#03120d;cursor:pointer}
    button:disabled{opacity:.5;cursor:not-allowed}.status{margin-top:9px;font-size:13px;line-height:1.4}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
  </style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div><h1>Freeze Decision</h1><div class="small">Phone-first prospective evidence capture</div></div>
    <a class="link" href="/">Money Action</a>
  </div>

  <div class="notice small">
    A tap freezes only the exact current decision shown below. It does not place,
    modify or cancel a Bitget order. Expired decisions fail closed. No automatic
    substitution is permitted.
  </div>

  {% if candidates %}
    {% for c in candidates %}
    <div class="candidate">
      <div class="symbol">{{ c.symbol|symbol_label }}</div>
      <div class="{{ 'side-long' if c.direction=='LONG' else 'side-short' }}">
        <b>{{ c.direction }}</b> · {{ c.action }} · {{ c.strategy_id }}
      </div>

      <div class="grid">
        <div class="metric"><div class="label">Entry</div><div class="value">{{ c.planned_entry_price }}</div></div>
        <div class="metric"><div class="label">Stop</div><div class="value">{{ c.stop_price }}</div></div>
        <div class="metric"><div class="label">Target</div><div class="value">{{ c.target_price }}</div></div>
        <div class="metric"><div class="label">R:R</div><div class="value">{{ '%.2f'|format(c.reward_risk or 0) }}</div></div>
        <div class="metric"><div class="label">Observed UTC</div><div class="value">{{ c.decision_observed_at_utc }}</div></div>
        <div class="metric"><div class="label">Quote</div><div class="value">{{ 'COMPLETE' if c.quote_complete else 'INCOMPLETE' }}</div></div>
      </div>

      <button
        id="freeze-{{ c.decision_observation_id }}"
        onclick="freezeDecision('{{ c.decision_observation_id }}','{{ c.symbol }}')">
        FREEZE {{ c.symbol|symbol_label }} DECISION
      </button>
      <div class="status" id="status-{{ c.decision_observation_id }}"></div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">
      <b>No current freeze-eligible candidate.</b>
      <div class="small" style="margin-top:6px">This page refreshes every 8 seconds.</div>
    </div>
  {% endif %}

  <div class="small">
    <a class="link" href="/execution-confirmations">Pending exact fill confirmations</a><br>
    Safety: shadow_only=true · trade_permission=false ·
    production_promotion_permitted=false · order_path=NONE
  </div>
</div>
<script>
async function freezeDecision(id,symbol){
  const button=document.getElementById('freeze-'+id);
  const status=document.getElementById('status-'+id);
  button.disabled=true;
  status.className='status warn';
  status.textContent='Freezing exact '+symbol+' decision...';
  try{
    const response=await fetch('/api/execution-freeze/'+encodeURIComponent(id),{
      method:'POST',
      headers:{
        'Content-Type':'application/json',
        'X-Alpha-Hunter-Freeze-Confirm':id
      },
      body:JSON.stringify({decision_observation_id:id})
    });
    const payload=await response.json();
    if(response.status===409){
      status.className='status bad';
      status.textContent='EXPIRED — candidate changed before freeze. Nothing was frozen.';
      setTimeout(()=>location.reload(),1200);
      return;
    }
    if(!response.ok){
      throw new Error(payload.message||payload.error||'Freeze failed');
    }
    status.className='status ok';
    status.innerHTML='FROZEN · '+payload.execution_event_id+
      ' · <a style="color:#4db6ff" href="/execution-bind/'+
      encodeURIComponent(payload.execution_event_id)+
      '">Continue to exact fill binding</a>';
    document.querySelectorAll('button').forEach(x=>x.disabled=true);
  }catch(error){
    status.className='status bad';
    status.textContent='Freeze failed: '+error.message;
    button.disabled=false;
  }
}
</script>
</body>
</html>
"""


EXECUTION_CONFIRMATION_QUEUE_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="12">
  <title>Alpha Hunter — Exact Fill Confirmation Queue</title>
  <style>
    :root{--bg:#071018;--panel:#0d1822;--line:#1d2e3a;--text:#e8f0f6;--muted:#91a3b1;--ok:#2bd39a;--warn:#ffbf47;--bad:#ff6474;--blue:#4db6ff}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
    .wrap{max-width:820px;margin:auto;padding:14px}.panel{background:rgba(13,24,34,.97);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
    h1{font-size:25px;margin:0 0 5px}.small{font-size:12px;color:var(--muted);line-height:1.5}.link{color:var(--blue);text-decoration:none}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.metric{background:#09131c;border:1px solid #162734;border-radius:10px;padding:9px}
    .label{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.value{font-weight:800;margin-top:3px;overflow-wrap:anywhere}
    .ok{color:var(--ok)}.warn{color:var(--warn)}.unique{border-color:#21634e}.ambiguous{border-color:#6f5b2a}
    .button{display:block;text-align:center;text-decoration:none;width:100%;border-radius:12px;padding:14px;font-size:15px;font-weight:900;background:#24d18f;color:#03120d;margin-top:12px}
  </style>
</head>
<body>
<div class="wrap">
  <h1>Exact Fill Confirmation Queue</h1>
  <div class="small" style="margin-bottom:12px">
    Evidence-complete candidate pairs only. A candidate is not attribution.
    Nothing is bound until you compare the exact Bitget trade/order identity and confirm it.
  </div>

  <div class="panel">
    <div class="grid">
      <div class="metric"><div class="label">Candidate pairs</div><div class="value">{{ status.candidate_pair_count or 0 }}</div></div>
      <div class="metric"><div class="label">Unique pairs</div><div class="value">{{ status.unique_candidate_pairs or 0 }}</div></div>
      <div class="metric"><div class="label">Ambiguous pairs</div><div class="value">{{ status.ambiguous_candidate_pairs or 0 }}</div></div>
      <div class="metric"><div class="label">Verified executions</div><div class="value">{{ status.verified_alpha_hunter_executions or 0 }}</div></div>
    </div>
  </div>

  {% if candidates %}
    {% for c in candidates %}
    <div class="panel {{ 'unique' if c.candidate_status=='UNIQUE_EVIDENCE_COMPLETE_MATCH' else 'ambiguous' }}">
      <div class="value">{{ c.symbol|symbol_label }} · {{ c.direction }} · {{ c.action }} · {{ c.strategy_id }}</div>
      <div class="{{ 'ok' if c.candidate_status=='UNIQUE_EVIDENCE_COMPLETE_MATCH' else 'warn' }}" style="margin-top:5px">
        {{ c.candidate_status }}
      </div>
      <div class="grid">
        <div class="metric"><div class="label">Frozen UTC</div><div class="value">{{ c.frozen_at_utc }}</div></div>
        <div class="metric"><div class="label">Order UTC</div><div class="value">{{ c.order_created_at_utc }}</div></div>
        <div class="metric"><div class="label">Fill UTC</div><div class="value">{{ c.fill_time_utc }}</div></div>
        <div class="metric"><div class="label">Freeze → order</div><div class="value">{{ '%.1f'|format(c.freeze_to_order_seconds or 0) }}s</div></div>
        <div class="metric"><div class="label">Trade ID</div><div class="value">{{ c.trade_id }}</div></div>
        <div class="metric"><div class="label">Order ID</div><div class="value">{{ c.order_id }}</div></div>
        <div class="metric"><div class="label">Decision cross</div><div class="value">{{ c.entry_cross_price }}</div></div>
        <div class="metric"><div class="label">Fill price</div><div class="value">{{ c.price }}</div></div>
        <div class="metric"><div class="label">Candidate slippage</div><div class="value">{{ '%.3f'|format(c.candidate_adverse_arrival_to_fill_bps or 0) }} bps</div></div>
        <div class="metric"><div class="label">Realized fee</div><div class="value">{{ '%.3f'|format(c.realized_fee_bps or 0) }} bps</div></div>
      </div>
      {% if (c.fill_candidate_count or 0)>1 or (c.event_candidate_count or 0)>1 %}
      <div class="small warn" style="margin-top:8px">
        Ambiguity: fill matches {{ c.fill_candidate_count }} frozen decisions; event has {{ c.event_candidate_count }} candidate fills.
        Exact operator review is mandatory.
      </div>
      {% endif %}
      <a class="button" href="/execution-bind/{{ c.execution_event_id }}">REVIEW EXACT FILL</a>
    </div>
    {% endfor %}
  {% else %}
    <div class="panel">
      <b>No evidence-complete real fill is waiting for confirmation.</b>
      <div class="small" style="margin-top:7px">
        This is expected until a real Bitget OPEN order is created inside a fresh frozen Alpha Hunter decision window.
      </div>
    </div>
  {% endif %}

  <div class="small">
    automatic_binding_permitted=false · attribution_claim_permitted=false ·
    trade_permission=false · order_path=NONE.
    <br><a class="link" href="/execution-freeze">Freeze Decision</a> ·
    <a class="link" href="/">Money Action</a>
  </div>
</div>
</body>
</html>
"""


EXECUTION_BIND_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="refresh" content="10">
  <title>Alpha Hunter — Bind Exact Fill</title>
  <style>
    :root{--bg:#071018;--panel:#0d1822;--line:#1d2e3a;--text:#e8f0f6;--muted:#91a3b1;--ok:#2bd39a;--warn:#ffbf47;--bad:#ff6474;--blue:#4db6ff}
    *{box-sizing:border-box}body{margin:0;background:linear-gradient(180deg,#050b11,#09131c);color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif}
    .wrap{max-width:760px;margin:auto;padding:14px}.panel{background:rgba(13,24,34,.97);border:1px solid var(--line);border-radius:16px;padding:15px;margin-bottom:12px}
    h1{font-size:25px;margin:0 0 5px}.small{font-size:12px;color:var(--muted);line-height:1.5}.link{color:var(--blue);text-decoration:none}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.metric{background:#09131c;border:1px solid #162734;border-radius:10px;padding:9px}
    .label{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}.value{font-weight:800;margin-top:3px;overflow-wrap:anywhere}
    .fill{border-color:#284355}.ready{border-color:#21634e}.blocked{border-color:#6f5b2a}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
    button{width:100%;border:0;border-radius:12px;padding:15px;font-size:15px;font-weight:900;background:#24d18f;color:#03120d;cursor:pointer;margin-top:12px}
    button:disabled{opacity:.45;cursor:not-allowed}.status{margin-top:9px;font-size:13px;line-height:1.4}
  </style>
</head>
<body>
<div class="wrap">
  <h1>Bind Exact Bitget Fill</h1>
  <div class="small" style="margin-bottom:12px">
    This page never chooses a fill for you. Compare the exact Bitget trade/order ID
    with your order history, then explicitly confirm one record.
  </div>

  <div class="panel">
    <div class="label">Frozen decision</div>
    <div class="value">{{ frozen.symbol|symbol_label }} · {{ frozen.direction }} · {{ frozen.action }}</div>
    <div class="grid">
      <div class="metric"><div class="label">Execution event</div><div class="value">{{ frozen.execution_event_id }}</div></div>
      <div class="metric"><div class="label">Frozen UTC</div><div class="value">{{ frozen.frozen_at_utc }}</div></div>
      <div class="metric"><div class="label">Entry</div><div class="value">{{ frozen.planned_entry_price }}</div></div>
      <div class="metric"><div class="label">Decision cross</div><div class="value">{{ frozen.entry_cross_price }}</div></div>
    </div>
  </div>

  {% if existing %}
  <div class="panel ready">
    <b class="ok">ALREADY BOUND</b>
    <div class="small" style="margin-top:7px">
      Binding {{ existing.binding_id }} · fill {{ existing.fill_evidence_id }}
    </div>
  </div>
  {% elif fills %}
    {% for f in fills %}
    <div class="panel fill {{ 'ready' if f._binding_ready else 'blocked' }}">
      <div class="value">{{ f.symbol|symbol_label }} · {{ f.side }} · {{ f.trade_side }}</div>
      <div class="grid">
        <div class="metric"><div class="label">Trade ID</div><div class="value">{{ f.trade_id }}</div></div>
        <div class="metric"><div class="label">Order ID</div><div class="value">{{ f.order_id }}</div></div>
        <div class="metric"><div class="label">Fill UTC</div><div class="value">{{ f.fill_time_utc }}</div></div>
        <div class="metric"><div class="label">Price</div><div class="value">{{ f.price }}</div></div>
        <div class="metric"><div class="label">Base size</div><div class="value">{{ f.base_volume }}</div></div>
        <div class="metric"><div class="label">Fee</div><div class="value">{{ f.fee_amount }} {{ f.fee_coin or '' }}</div></div>
      </div>
      {% if f._binding_ready %}
      <button onclick="bindExact(
        '{{ frozen.execution_event_id }}',
        '{{ f.fill_evidence_id }}',
        '{{ f.trade_id }}',
        '{{ f.order_id }}'
      )">I CONFIRM THIS EXACT BITGET FILL</button>
      {% else %}
      <div class="status warn">
        Not binding-ready yet: waiting for complete traceability and exact read-only order detail.
      </div>
      {% endif %}
      <div class="status" id="status-{{ f.fill_evidence_id }}"></div>
    </div>
    {% endfor %}
  {% else %}
  <div class="panel">
    <b>No compatible unbound fill evidence yet.</b>
    <div class="small" style="margin-top:7px">
      Read-only Bitget evidence will appear here after collection. Refresh is automatic.
    </div>
  </div>
  {% endif %}

  <div class="small">
    Compatibility filtering is not attribution. Binding occurs only after your exact
    confirmation and a second database validation. trade_permission=false · order_path=NONE.
    <br><a class="link" href="/execution-confirmations">Confirmation Queue</a> ·
    <a class="link" href="/execution-freeze">Back to Freeze Decision</a>
  </div>
</div>
<script>
async function bindExact(executionId,fillId,tradeId,orderId){
  const ok=confirm(
    'Confirm exact Bitget fill?\n\nTrade ID: '+tradeId+
    '\nOrder ID: '+orderId+
    '\n\nThis records evidence only. It does not place an order.'
  );
  if(!ok)return;
  const status=document.getElementById('status-'+fillId);
  status.className='status warn';
  status.textContent='Binding exact fill...';
  const confirmToken=executionId+':'+fillId;
  try{
    const response=await fetch(
      '/api/execution-bind/'+encodeURIComponent(executionId)+'/'+encodeURIComponent(fillId),
      {
        method:'POST',
        headers:{
          'Content-Type':'application/json',
          'X-Alpha-Hunter-Bind-Confirm':confirmToken
        },
        body:JSON.stringify({
          execution_event_id:executionId,
          fill_evidence_id:fillId,
          explicit_user_confirmation:true
        })
      }
    );
    const payload=await response.json();
    if(!response.ok)throw new Error(payload.message||payload.error||'Binding rejected');
    status.className='status ok';
    status.textContent='BOUND · '+payload.binding_id+' · attribution verification available';
    document.querySelectorAll('button').forEach(x=>x.disabled=true);
  }catch(error){
    status.className='status bad';
    status.textContent='Binding failed: '+error.message;
  }
}
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
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <!-- V8: retry reloads are user-controllable; no unpausable meta refresh. -->
  <title>Alpha Hunter V8 — Source Integrity</title>
  <style>
    :root{color-scheme:dark}
    *{box-sizing:border-box}
    body{margin:0;background:radial-gradient(1100px 700px at 85% 0%,#153047 0%,transparent 72%),#07111c;color:#eef5fb;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}
    .wrap{max-width:1040px;margin:0 auto;padding:24px clamp(12px,3vw,32px) 38px;min-width:0}
    .card{margin-top:14px;background:#101e2c;border:1px solid #294155;border-radius:16px;padding:clamp(14px,2vw,22px);max-width:100%;min-width:0;overflow-wrap:anywhere}
    h1{margin:0 0 8px;font-size:clamp(23px,3vw,30px);letter-spacing:-.5px}.muted{color:#b2c6d5;line-height:1.55}
    .warn{color:#ffca6c;font-weight:750;font-size:16px}.ok{color:#3be4aa}
    .v8-banner{margin:0 0 14px;color:#b2c6d5;font-size:14px;letter-spacing:.01em}
    .v8-banner strong{color:#3be4aa}
    .card h2{color:#eef5fb}
    .v8-retry-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .v8-retry-controls a,.v8-retry-controls button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;border:1px solid #3b6985;border-radius:10px;padding:10px 14px;background:#183247;color:#eef5fb;font:inherit;text-decoration:none;cursor:pointer}
    .v8-retry-controls a:focus-visible,.v8-retry-controls button:focus-visible{outline:3px solid #6bc0ff;outline-offset:3px}
    @media(min-width:900px){.wrap{padding-top:38px}.card{padding:24px}}
    @media(max-width:400px){.wrap{padding:16px 11px 32px}.card{padding:15px}}
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

    .v8-recovery-intro{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap;margin-bottom:12px}
    .v8-recovery-intro h1{margin:0;font-size:clamp(23px,3vw,30px)}
    .v8-recovery-intro .v8-banner{margin:5px 0 0}
    .v8-recovery-hint{font-size:13px;color:#b2c6d5;padding:7px 11px;border-radius:10px;border:1px solid #41596e}
    .v8-recovery-info{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
    .v8-recovery-info .card{margin:0}
    .v8-recovery-info p{margin:8px 0 0;font-size:14px}
    .v8-body .v8-view-heading h2{font-size:21px}
    .v8-body .v8-retry-controls a,.v8-body .v8-retry-controls button{font-size:14px}
    .v8-body .v8-view .card{margin-bottom:14px}
    @media(max-width:899px){.v8-recovery-info{grid-template-columns:1fr}}
    @media(max-width:390px){.v8-body .v8-retry-controls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
      .v8-body .v8-retry-controls a,.v8-body .v8-retry-controls button{padding:10px 8px;text-align:center;font-size:13px}}
  </style>
  <link rel="stylesheet" href="{{ url_for('static', filename='v8.css') }}">
</head>
<body class="v8-body">
<div class="v8-shell">
  <aside class="v8-rail" aria-label="Primary workspace navigation">
    <div class="v8-brand">ALPHA HUNTER <span>V8</span></div>
    <div class="v8-brand-note">Research terminal</div>
    <nav class="v8-rail-nav" aria-label="Workspace">
      <button type="button" class="v8-tab" data-v8-tab="overview" aria-current="page"><span class="v8-nav-icon" aria-hidden="true">▦</span>Overview</button>
      <button type="button" class="v8-tab" data-v8-tab="research"><span class="v8-nav-icon" aria-hidden="true">⌕</span>Research</button>
      <button type="button" class="v8-tab" data-v8-tab="results"><span class="v8-nav-icon" aria-hidden="true">▥</span>Paper Results</button>
      <button type="button" class="v8-tab" data-v8-tab="system"><span class="v8-nav-icon" aria-hidden="true">⚙</span>System</button>
    </nav>
    <div class="v8-rail-foot"><strong>Evidence first</strong>Current signals are unavailable when the canonical scan is incomplete. Real-order execution is disabled.</div>
  </aside>
  <div class="v8-content">
    <div class="v8-mobile-head"><strong>Alpha Hunter <span>V8</span></strong><span class="v8-kicker">Research only · No orders</span></div>
    <div class="wrap">
      <div class="v8-recovery-intro">
        <div><h1>Market intelligence</h1>
        <div class="v8-banner">Source integrity · Paper-only research · Real orders disabled</div></div>
        <div class="v8-recovery-hint">Web service online · Current research restricted</div>
      </div>
      <div class="v8-workspace" id="v8-workspace">
        <section id="v8-view-overview" class="v8-view" aria-labelledby="v8-overview-title">
          <div class="v8-view-heading"><h2 id="v8-overview-title">Overview</h2><p>Current evidence and market reference</p></div>
        </section>
        <section id="v8-view-research" class="v8-view" aria-labelledby="v8-research-title" hidden>
          <div class="v8-view-heading"><h2 id="v8-research-title">Research</h2><p>Historical storage only · no current strategy setup</p></div>
          <div class="card"><h2>Current signals withheld</h2>
            <p class="muted">The latest canonical scan has not passed symbol-evidence verification. There are no current Alpha Hunter entry, stop, target or research recommendations to display.</p>
            <p class="muted">Previous complete storage runs may be described below solely as historical evidence. They are not promoted into live signals.</p>
          </div>
        </section>
        <section id="v8-view-results" class="v8-view" aria-labelledby="v8-results-title" hidden>
          <div class="v8-view-heading"><h2 id="v8-results-title">Paper Results</h2><p>Scientific performance requires independently verified data</p></div>
          <div class="card"><h2>Performance evidence temporarily unavailable</h2>
            <p class="muted">This recovery screen cannot establish a current scientific profitability result. A scanner, performance or database fault must not be mistaken for positive trading performance.</p>
            <p class="muted">Paper/shadow-only operation is preserved. No exchange-order authority or profitability promotion is granted.</p>
            <a href="/performance" class="v8-report-link">View historical performance report <span aria-hidden="true">↗</span></a><p class="v8-report-disclaimer muted">Report may be unavailable during a source outage. Historical figures are not verified live returns.</p>
          </div>
        </section>
        <section id="v8-view-system" class="v8-view" aria-labelledby="v8-system-title" hidden>
          <div class="v8-view-heading"><h2 id="v8-system-title">System</h2><p>Build provenance and operational diagnostics</p></div>
      <section class="v8-trust-panel" aria-labelledby="v8-trust-title">
        <div class="v8-trust-head">
          <div><span class="v8-kicker">Product transparency</span><h3 id="v8-trust-title">What Alpha Hunter does—and does not prove</h3>
            <p>A read-only research terminal for market observations, historical paper evidence and system diagnostics. Displayed information is not an instruction to trade.</p>
          </div>
        </div>
        <div class="v8-trust-grid">
          <div class="v8-trust-item"><h4>Research provenance</h4><p>Current observations appear only when canonical source checks pass. Historical records never replace incomplete or unavailable current evidence.</p></div>
          <div class="v8-trust-item"><h4>Paper performance</h4><p>Paper results and shadow scores are not verified live returns, probability forecasts or a claim of scientific profitability.</p></div>
          <div class="v8-trust-item"><h4>Execution and release</h4><p>Real-money order authority is disabled. Browser checks are not an independent security certification or production-release approval.</p></div>
        </div>
        <div class="v8-share-tools">
          <button class="v8-reset" id="v8-copy-view-link" type="button">Copy link to this view</button>
          <p class="v8-share-feedback" id="v8-share-feedback" role="status" aria-live="polite">You can share this read-only system overview without sharing credentials or private records.</p>
          <input id="v8-share-manual" class="v8-share-input" type="text" readonly hidden aria-label="Select and copy this page link manually">
        </div>
      </section>
          <div class="card"><h2>System status</h2>
            <p class="muted">Web application responding. Current scanner evidence is not fully verified. This page does not prove scanner or database health.</p>
            <p class="muted">Build {{ build.git_commit_short }} · {{ build.git_branch }}</p>
            <div class="v8-retry-controls">
              <a href="/api/build">Build provenance</a>
              <a href="/api/historical-status">Historical storage status</a>
              <a href="/control-tower">Control Tower (may be unavailable)</a>
            </div>
          </div>
        </section>
      </div>
    <div class="card v8-recovery-card" data-v8-section="overview" aria-labelledby="v8-scan-warning">
      <div class="warn" id="v8-scan-warning">LIVE DATA TEMPORARILY UNAVAILABLE</div>
      <p class="muted v8-recovery-summary">The web service is running, but current canonical Supabase evidence could not be read after bounded retries.</p>
      <p class="muted v8-recovery-limits">Trading actions are intentionally hidden until live data is available again. No stale snapshot is promoted as current evidence.</p>
      <div class="v8-retry-controls" role="group" aria-label="Dashboard recovery">
        <a href="/" aria-label="Check latest canonical scan again">Check latest scan</a>
        <button type="button" id="v8-auto-retry" data-v8-retry-ms="75000" aria-pressed="false">Enable auto retry</button>
      </div>
      <details class="v8-recovery-details">
        <summary>Recovery and retry details</summary>
        <p class="muted">You can refresh saved evidence now or enable automatic retries every 75 seconds. Auto retry can be paused at any time.</p>
        <p class="muted">The warning remains visible until the latest complete canonical scan is verified.</p>
      </details>
    </div>
    <div class="card" data-v8-section="overview" aria-label="Bitget public reference market">
      <h2 style="margin:0 0 10px;font-size:21px">Bitget public market prices</h2>
      <p class="muted" style="margin-top:0">Independent USDT-futures reference quotes. Not Alpha Hunter verified signals, not paper-test evidence, and not trading authorization.</p>
      <div id="public-market-state" class="muted" role="status" aria-live="polite">Checking fresh exchange quotes…</div>
      <div id="public-market-list" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:10px;margin-top:12px"></div>
      <p id="public-market-time" class="muted" style="font-size:13px"></p>
    </div>
    </div>
  </div>
  <nav class="v8-bottom-nav" aria-label="Mobile workspace navigation">
    <button type="button" class="v8-tab" data-v8-tab="overview" aria-current="page"><span class="v8-nav-icon" aria-hidden="true">▦</span>Overview</button>
    <button type="button" class="v8-tab" data-v8-tab="research"><span class="v8-nav-icon" aria-hidden="true">⌕</span>Research</button>
    <button type="button" class="v8-tab" data-v8-tab="results"><span class="v8-nav-icon" aria-hidden="true">▥</span>Results</button>
    <button type="button" class="v8-tab" data-v8-tab="system"><span class="v8-nav-icon" aria-hidden="true">⚙</span>System</button>
  </nav>
</div>
  <script>
  (function () {
    const button = document.getElementById("v8-auto-retry");
    if (!button) return;
    let enabled = false;
    try { enabled = sessionStorage.getItem("alpha-v8-auto-retry") === "enabled"; } catch (_) {}
    let refreshTimer = null;
    // The browser must not hammer a degraded Supabase service. The outage
    // page waits out the server circuit cooldown before another read.
    const configuredRetryMs = Number(button.dataset.v8RetryMs);
    const retryMs = [15000, 60000, 75000].includes(configuredRetryMs)
      ? configuredRetryMs : 75000;
    function update() {
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.textContent = enabled ? "Pause auto retry" : "Enable auto retry";
      if (refreshTimer) clearTimeout(refreshTimer);
      if (enabled) refreshTimer = setTimeout(() => location.reload(), retryMs);
    }
    button.addEventListener("click", () => {
      enabled = !enabled;
      try { sessionStorage.setItem("alpha-v8-auto-retry", enabled ? "enabled" : "paused"); } catch (_) {}
      update();
    });
    update();
  }());
  (async function () {
    const state = document.getElementById("public-market-state");
    const list = document.getElementById("public-market-list");
    const timeElement = document.getElementById("public-market-time");
    try {
      const abort = new AbortController();
      const timeout = setTimeout(() => abort.abort(), 6000);
      let response;
      try {
        response = await fetch("/api/public-market", {cache:"no-store", signal:abort.signal});
      } finally {
        clearTimeout(timeout);
      }
      if (!response.ok) throw new Error("Public quote feed unavailable");
      const data = await response.json();
      if (!Array.isArray(data.quotes) || data.quotes.length !== 4
          || data.canonical_evidence !== false || data.trade_permission !== false) {
        throw new Error("Public quote feed not verified");
      }
      for (const item of data.quotes) {
        const age = Date.now() - Number(item.timestamp_ms);
        if (!Number.isFinite(age) || age < -5000 || age > 90000) {
          throw new Error("Exchange quote is stale");
        }
      }
      state.textContent = "Public exchange quotes — recent, independently sourced";
      for (const item of data.quotes) {
        const tile = document.createElement("div");
        tile.style.cssText = "padding:12px;border:1px solid #254153;border-radius:10px;background:#0a1520";
        const symbol = document.createElement("div");
        symbol.textContent = item.symbol;
        symbol.style.cssText = "color:#91a3b1;font-size:13px;margin-bottom:6px";
        const price = document.createElement("div");
        price.textContent = item.last_price + " USDT";
        price.style.cssText = "font-weight:700;font-size:18px;overflow-wrap:anywhere";
        tile.append(symbol, price);
        list.append(tile);
      }
      const oldestMs = Math.min(...data.quotes.map(x => Number(x.timestamp_ms)));
      timeElement.textContent = "Exchange quote timestamp: " + new Date(oldestMs).toLocaleString()
        + " (your local time). Public market prices only; do not trade from this screen.";
    } catch (_) {
      list.replaceChildren();
      state.textContent = "Public exchange quotes unavailable. No price is shown without a fresh source.";
      timeElement.textContent = "";
    }
  }());
  </script>
  <script src="{{ url_for('static', filename='v8.js') }}" defer></script>
</body>
</html>
"""


def dashboard_read_circuit_open() -> bool:
    """Production-only fast failure for repeated browser refreshes during an outage."""
    if not os.getenv("RENDER_SERVICE_ID"):
        return False
    with _DASHBOARD_READ_FAILURE_LOCK:
        return time.monotonic() < _DASHBOARD_READ_UNAVAILABLE_UNTIL


def _record_dashboard_read_failure() -> None:
    if not os.getenv("RENDER_SERVICE_ID"):
        return
    global _DASHBOARD_READ_UNAVAILABLE_UNTIL
    with _DASHBOARD_READ_FAILURE_LOCK:
        _DASHBOARD_READ_UNAVAILABLE_UNTIL = (
            time.monotonic() + DASHBOARD_READ_FAILURE_COOLDOWN_SECONDS
        )


def bounded_dashboard_payload() -> dict[str, Any]:
    """Fail closed before Gunicorn can kill a stalled dashboard worker."""
    if dashboard_read_circuit_open():
        raise RuntimeError("Dashboard read recovery cooldown is active")
    token = _DASHBOARD_READ_DEADLINE.set(
        time.monotonic() + DASHBOARD_READ_BUDGET_SECONDS
    )
    try:
        snapshot = latest_snapshot()
        test_status = latest_test_engine_status()
        lifecycle_status = latest_paper_lifecycle_status()
        if not test_status:
            raise RuntimeError("Paper execution status unavailable")
        if time.monotonic() >= _DASHBOARD_READ_DEADLINE.get():
            raise RuntimeError("Dashboard Supabase read budget exhausted")
        return dashboard_payload(snapshot, test_status, lifecycle_status)
    except (CanonicalSnapshotPublishing, CanonicalSnapshotIncomplete):
        # The database responded, but the latest canonical evidence is not
        # publishable. Do not arm the 75-second transport outage circuit;
        # a later complete scan must be able to recover immediately.
        raise
    except Exception:
        _record_dashboard_read_failure()
        raise
    finally:
        _DASHBOARD_READ_DEADLINE.reset(token)


# Same independent public quote widget, but accurately label the short,
# read-only publication window instead of reporting a database outage.
DASHBOARD_PUBLISHING_PAGE = (
    DASHBOARD_RECOVERY_PAGE
    .replace("LIVE DATA TEMPORARILY UNAVAILABLE", "LATEST SCAN IS PUBLISHING")
    .replace("every 75 seconds", "every 15 seconds")
    .replace('data-v8-retry-ms="75000"', 'data-v8-retry-ms="15000"')
    .replace(
        "The web service is running, but current canonical Supabase evidence could not be read after bounded retries.",
        "The newest canonical scan has arrived, but its per-symbol evidence is still being committed. Trading decisions remain hidden until the complete scan is verified.",
    )
)


DASHBOARD_INCOMPLETE_PAGE = (
    DASHBOARD_RECOVERY_PAGE
    .replace("LIVE DATA TEMPORARILY UNAVAILABLE", "LATEST CANONICAL SCAN INCOMPLETE")
    .replace("every 75 seconds", "every 60 seconds")
    .replace('data-v8-retry-ms="75000"', 'data-v8-retry-ms="60000"')
    .replace(
        "The web service is running, but current canonical Supabase evidence could not be read after bounded retries.",
        "The scanner reported a canonical run, but its verified symbol evidence did not finish publishing. No trade signals or execution recommendations are available from this run.",
    )
    .replace(
        "Trading actions are intentionally hidden until live data is available again. No stale snapshot is promoted as current evidence.",
        "Alpha Hunter signals are withheld. The public reference prices below are not verified trading signals, and no earlier scan is substituted as current.",
    )
)


# Historical-only research summary: deliberately separate from /api/latest,
# which must keep blocking invalid canonical evidence.
ARCHIVED_RESEARCH_CARD = """
    <div class="card" data-v8-section="research" aria-label="Historical Alpha Hunter research status">
      <h2 style="margin:0 0 8px;font-size:21px">Last stored complete scan</h2>
      <p class="muted" style="margin:0 0 12px">Historical research status only. This does not indicate that the latest scan succeeded, and no historical pair can be traded from this panel.</p>
      <div id="historical-data-status" class="muted" role="status" aria-live="polite">Checking recent verified storage records…</div>
      <div id="historical-data-details" class="muted" style="margin-top:12px"></div>
      <p class="muted" style="font-size:13px">All trade and exchange permissions remain disabled. No entry, target, stop or current trading signal is supplied.</p>
    </div>
    <script>
    (async function () {
      const status = document.getElementById("historical-data-status");
      const details = document.getElementById("historical-data-details");
      if (!status || !details) return;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 9500);
      try {
        const response = await fetch("/api/historical-status", {cache:"no-store", signal:controller.signal});
        if (!response.ok) throw new Error("Archive status unavailable");
        const data = await response.json();
        if (data.mode !== "HISTORICAL_STORAGE_STATUS_ONLY" ||
            data.historical_only !== true ||
            data.trade_permission !== false ||
            data.verified_live_trade_signal !== false ||
            data.source_run_not_substituted !== true) {
          throw new Error("Archive status did not prove its non-trading scope");
        }
        status.textContent = "Latest reported scan: " + new Date(data.latest_reported_scan_at_utc).toLocaleString()
          + " — " + data.latest_reported_declared_symbols + " symbols reported (not proof of saving).";
        const archived = data.historical_completed_scan;
        if (!archived) {
          details.textContent = "No fully persisted scan was verified in the recent historical window. Live Alpha Hunter signals remain unavailable.";
          return;
        }
        const collected = new Date(archived.collected_at_utc);
        if (!Number.isFinite(collected.getTime()) ||
            archived.storage_integrity !== "MATCHING_PARENT_CHILD_FEATURE_COUNTS" ||
            archived.declared_symbols !== archived.persisted_symbols ||
            archived.declared_symbols !== archived.persisted_features) {
          throw new Error("Archive counts or timestamps were not complete");
        }
        const age = Math.max(0, Math.round((Date.now() - collected.getTime()) / 60000));
        details.textContent = "Previous complete stored scan: " + collected.toLocaleString()
          + " (" + age + " minutes old). "
          + archived.persisted_symbols + "/" + archived.declared_symbols + " symbol rows and "
          + archived.persisted_features + "/" + archived.declared_symbols + " feature rows were found. "
          + "HISTORICAL ONLY — NOT A CURRENT TRADE SIGNAL.";
      } catch (_) {
        status.textContent = "Historical research verification is temporarily unavailable.";
        details.textContent = "No stored information is presented as a current Alpha Hunter signal.";
      } finally {
        clearTimeout(timer);
      }
    }());
    </script>
"""
ARCHIVE_INSERT_ANCHOR = '    <div class="card" data-v8-section="overview" aria-label="Bitget public reference market">'
def _attach_historical_status(page: str) -> str:
    return page.replace(ARCHIVE_INSERT_ANCHOR, ARCHIVED_RESEARCH_CARD + ARCHIVE_INSERT_ANCHOR, 1)


def _dashboard_publishing_response():
    response = app.make_response((render_template_string(
        _attach_historical_status(DASHBOARD_PUBLISHING_PAGE), build=build_identity(),
    ), 202))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Retry-After"] = "10"
    return response


def _dashboard_incomplete_response():
    # A working status page is useful during an incomplete scan, but must
    # never look like an operationally healthy signal endpoint. The JSON API
    # still returns 503 and monitoring can inspect this explicit header.
    response = app.make_response((render_template_string(
        _attach_historical_status(DASHBOARD_INCOMPLETE_PAGE), build=build_identity(),
    ), 200))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Alpha-Hunter-Evidence-State"] = "INCOMPLETE"
    response.headers["X-Robots-Tag"] = "noindex"
    response.headers["Retry-After"] = "10"
    return response


def _dashboard_recovery_response():
    response = app.make_response((render_template_string(
        DASHBOARD_RECOVERY_PAGE, build=build_identity(),
    ), 503))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Retry-After"] = "10"
    return response


@app.get("/")
def dashboard():
    if dashboard_read_circuit_open():
        return _dashboard_recovery_response()
    try:
        return render_template_string(
            PAGE,
            data=bounded_dashboard_payload(),
        )
    except CanonicalSnapshotPublishing:
        app.logger.info("Newest canonical scan is publishing child evidence")
        return _dashboard_publishing_response()
    except CanonicalSnapshotIncomplete:
        app.logger.warning("Newest canonical scan failed evidence-integrity checks")
        return _dashboard_incomplete_response()
    except Exception:
        app.logger.exception("Dashboard live-data read failed")
        return _dashboard_recovery_response()


# Web-only bounded GET cache. Refresh no more than once per 60 seconds even
# while iPhone browsers reload the safe recovery page every 10 seconds.
_HISTORICAL_STATUS_LOCK = threading.Lock()
_HISTORICAL_STATUS_UNTIL = 0.0
_HISTORICAL_STATUS_CACHE: dict[str, Any] | None = None


def cached_historical_status() -> dict[str, Any]:
    global _HISTORICAL_STATUS_CACHE, _HISTORICAL_STATUS_UNTIL
    with _HISTORICAL_STATUS_LOCK:
        now = time.monotonic()
        if now < _HISTORICAL_STATUS_UNTIL:
            if _HISTORICAL_STATUS_CACHE is None:
                raise RuntimeError("Historical source unavailable during bounded recovery")
            return dict(_HISTORICAL_STATUS_CACHE)
        token = _DASHBOARD_READ_DEADLINE.set(time.monotonic() + 8.0)
        try:
            result = archived_storage_summary(supabase_get_rows, now_utc=datetime.now(timezone.utc))
        except Exception:
            _HISTORICAL_STATUS_CACHE = None
            _HISTORICAL_STATUS_UNTIL = time.monotonic() + 15.0
            raise
        finally:
            _DASHBOARD_READ_DEADLINE.reset(token)
        _HISTORICAL_STATUS_CACHE = result
        _HISTORICAL_STATUS_UNTIL = time.monotonic() + 60.0
        return dict(result)


@app.get("/api/historical-status")
def api_historical_status():
    try:
        result = cached_historical_status()
    except Exception:
        # Do not disclose database/HTTP tracebacks or expose stale fallback
        # claims when source verification cannot be completed.
        return jsonify({
            "error": "historical_storage_evidence_unavailable",
            "historical_only": True,
            "trade_permission": False,
            "verified_live_trade_signal": False,
        }), 503, {"Cache-Control": "no-store", "Retry-After": "15"}
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Alpha-Hunter-Evidence-State"] = "HISTORICAL_ONLY"
    return response


@app.get("/api/latest")
def api_latest():
    if not dashboard_read_circuit_open():
        try:
            return jsonify(bounded_dashboard_payload())
        except CanonicalSnapshotPublishing:
            response = jsonify({
                "error": "canonical_scan_publishing",
                "retry_after_seconds": 10,
                "build": build_identity(),
            })
            response.status_code = 503
            response.headers["Cache-Control"] = "no-store"
            response.headers["Retry-After"] = "10"
            return response
        except CanonicalSnapshotIncomplete:
            response = jsonify({
                "error": "canonical_scan_incomplete",
                "retry_after_seconds": 10,
                "signals_available": False,
                "trade_permission": False,
                "build": build_identity(),
            })
            response.status_code = 503
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Alpha-Hunter-Evidence-State"] = "INCOMPLETE"
            response.headers["Retry-After"] = "10"
            return response
        except Exception:
            app.logger.exception("API latest live-data read failed")
    response = jsonify({
        "error": "live_data_unavailable",
        "retry_after_seconds": 10,
        "build": build_identity(),
    })
    response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    response.headers["Retry-After"] = "10"
    return response



# Public Bitget reference quotes are deliberately separate from the sealed
# canonical Supabase and paper-execution evidence pipeline.
PUBLIC_MARKET_URL = "https://api.bitget.com/api/v3/market/tickers"
PUBLIC_MARKET_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT")
PUBLIC_MARKET_CACHE_SECONDS = 15.0
PUBLIC_MARKET_MAX_QUOTE_AGE_MS = 90_000
_PUBLIC_MARKET_CACHE_LOCK = threading.Lock()
_PUBLIC_MARKET_CACHE_UNTIL = 0.0
_PUBLIC_MARKET_CACHE: dict[str, Any] | None = None

def public_market_reference() -> dict[str, Any]:
    """Independently sourced read-only exchange quotes, NEVER strategy evidence."""
    global _PUBLIC_MARKET_CACHE, _PUBLIC_MARKET_CACHE_UNTIL
    with _PUBLIC_MARKET_CACHE_LOCK:
        now = time.monotonic()
        if now < _PUBLIC_MARKET_CACHE_UNTIL:
            if _PUBLIC_MARKET_CACHE is None:
                raise RuntimeError("Public market feed temporarily unavailable")
            return dict(_PUBLIC_MARKET_CACHE)
        # Bound the upstream query to protect the web service under failure.
        _PUBLIC_MARKET_CACHE_UNTIL = now + PUBLIC_MARKET_CACHE_SECONDS
        _PUBLIC_MARKET_CACHE = None
        try:
            response = requests.get(
                PUBLIC_MARKET_URL,
                params={"category": "USDT-FUTURES"},
                timeout=(1.5, 3.0),
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("code") != "00000":
                raise RuntimeError("Bitget public feed did not confirm success")
            source_rows = payload.get("data")
            if not isinstance(source_rows, list):
                raise RuntimeError("Bitget public feed has no ticker list")
            server_ms = int(time.time() * 1000)
            validated: dict[str, dict[str, Any]] = {}
            for item in source_rows:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol")
                if symbol not in PUBLIC_MARKET_SYMBOLS or symbol in validated:
                    continue
                if item.get("category") not in (None, "USDT-FUTURES"):
                    continue
                try:
                    quote_ms = int(item.get("ts"))
                    last = Decimal(str(item.get("lastPrice")))
                except (TypeError, ValueError, InvalidOperation):
                    continue
                if (
                    not last.is_finite() or last <= 0
                    or quote_ms <= 0
                    or not (-5_000 <= server_ms - quote_ms <= PUBLIC_MARKET_MAX_QUOTE_AGE_MS)
                ):
                    continue
                validated[symbol] = {
                    "symbol": symbol,
                    "last_price": str(last),
                    "timestamp_ms": quote_ms,
                }
            if len(validated) != len(PUBLIC_MARKET_SYMBOLS):
                raise RuntimeError("Incomplete or stale public market quote set")
            result = {
                "source": "Bitget public USDT-FUTURES v3 tickers",
                "market_status": "PUBLIC_QUOTES_ONLY",
                "canonical_evidence": False,
                "paper_test_evidence": False,
                "trade_permission": False,
                "quotes": [validated[symbol] for symbol in PUBLIC_MARKET_SYMBOLS],
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            _PUBLIC_MARKET_CACHE = result
            _PUBLIC_MARKET_CACHE_UNTIL = time.monotonic() + PUBLIC_MARKET_CACHE_SECONDS
            return dict(result)
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            _PUBLIC_MARKET_CACHE_UNTIL = time.monotonic() + PUBLIC_MARKET_CACHE_SECONDS
            raise RuntimeError("Public market feed temporarily unavailable") from None


@app.get("/api/public-market")
def api_public_market():
    try:
        response = jsonify(public_market_reference())
    except Exception:
        response = jsonify({
            "error": "public_market_unavailable",
            "canonical_evidence": False,
            "paper_test_evidence": False,
            "trade_permission": False,
        })
        response.status_code = 503
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/api/build")
def api_build():
    return jsonify(build_identity())


@app.post("/api/run-scan")
def api_run_scan():
    # V8 release-safety boundary: this public web service is a reader,
    # never a scheduler. The protected hourly scanner runs independently
    # as a Render Cron Job. No public request may launch run.py.
    #
    # The old HTTP path is retained as a fail-closed compatibility response
    # so existing clients get an explicit refusal rather than a surprise
    # 404 or an accidental scan. The inactive optional Supabase fast-scan
    # schedule must remain inactive until separately re-engineered.
    response = jsonify({
        "error": "manual_web_scanning_disabled",
        "message": "Web scanning is disabled; the independent scheduled scanner is unchanged.",
        "scanner_started": False,
        "trade_permission": False,
        "order_path": "NONE",
    })
    response.status_code = 403
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/scan-status")
def api_scan_status():
    with scan_lock:
        return jsonify(dict(scan_state))


@app.get("/execution-freeze")
def execution_freeze_page():
    auth_failure = None if operator_authorized() else operator_auth_response()
    if auth_failure is not None:
        return auth_failure

    try:
        response = app.make_response(
            render_template_string(
                EXECUTION_FREEZE_PAGE,
                candidates=execution_freeze_candidates(),
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        app.logger.exception("Execution-freeze candidate read failed")
        return jsonify({"error": "execution_freeze_unavailable"}), 503


@app.post("/api/execution-freeze/<decision_observation_id>")
def api_execution_freeze(decision_observation_id: str):
    auth_failure = None if operator_authorized() else operator_auth_response()
    if auth_failure is not None:
        return auth_failure

    if (
        len(decision_observation_id) != 32
        or any(ch not in "0123456789abcdef" for ch in decision_observation_id.lower())
    ):
        return jsonify({"error": "invalid_decision_observation_id"}), 400

    if request.headers.get(EXECUTION_FREEZE_CONFIRM_HEADER) != decision_observation_id:
        return jsonify({"error": "explicit_freeze_confirmation_required"}), 400

    body = request.get_json(silent=True) or {}
    if body.get("decision_observation_id") != decision_observation_id:
        return jsonify({"error": "decision_identity_mismatch"}), 400

    try:
        current = {
            row.get("decision_observation_id"): row
            for row in execution_freeze_candidates()
        }
        if decision_observation_id not in current:
            return jsonify({
                "error": "decision_expired",
                "message": (
                    "Candidate is no longer current. Nothing was frozen and "
                    "no substitute candidate was selected."
                ),
                "trade_permission": False,
                "order_path": "NONE",
            }), 409

        result = freeze_execution_decision(decision_observation_id)
        result["trade_permission"] = False
        result["production_promotion_permitted"] = False
        result["order_path"] = "NONE"
        return jsonify(result), 200
    except StaleExecutionDecision:
        return jsonify({
            "error": "decision_expired",
            "message": (
                "Candidate expired during the freeze transaction. Nothing was "
                "backdated and no substitute candidate was selected."
            ),
            "trade_permission": False,
            "order_path": "NONE",
        }), 409
    except Exception:
        app.logger.exception("Execution-decision freeze failed")
        return jsonify({
            "error": "execution_freeze_failed",
            "trade_permission": False,
            "order_path": "NONE",
        }), 503


@app.get("/execution-confirmations")
def execution_confirmation_queue_page():
    auth_failure = None if operator_authorized() else operator_auth_response()
    if auth_failure is not None:
        return auth_failure

    try:
        response = app.make_response(
            render_template_string(
                EXECUTION_CONFIRMATION_QUEUE_PAGE,
                candidates=pending_execution_fill_confirmations(),
                status=execution_fill_confirmation_status(),
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        app.logger.exception("Execution confirmation queue failed")
        return jsonify({"error": "execution_confirmation_queue_unavailable"}), 503


@app.get("/execution-bind/<execution_event_id>")
def execution_bind_page(execution_event_id: str):
    auth_failure = None if operator_authorized() else operator_auth_response()
    if auth_failure is not None:
        return auth_failure

    try:
        frozen = execution_freeze_by_id(execution_event_id)
        if frozen is None:
            return jsonify({"error": "frozen_execution_event_not_found"}), 404

        response = app.make_response(
            render_template_string(
                EXECUTION_BIND_PAGE,
                frozen=frozen,
                existing=execution_binding_by_event(execution_event_id),
                fills=compatible_execution_fills(frozen),
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        app.logger.exception("Execution-fill binding page failed")
        return jsonify({"error": "execution_binding_unavailable"}), 503


@app.post("/api/execution-bind/<execution_event_id>/<fill_evidence_id>")
def api_execution_bind(execution_event_id: str, fill_evidence_id: str):
    auth_failure = None if operator_authorized() else operator_auth_response()
    if auth_failure is not None:
        return auth_failure

    expected_confirm = f"{execution_event_id}:{fill_evidence_id}"
    if request.headers.get(EXECUTION_BIND_CONFIRM_HEADER) != expected_confirm:
        return jsonify({"error": "explicit_exact_fill_confirmation_required"}), 400

    body = request.get_json(silent=True) or {}
    if (
        body.get("execution_event_id") != execution_event_id
        or body.get("fill_evidence_id") != fill_evidence_id
        or body.get("explicit_user_confirmation") is not True
    ):
        return jsonify({"error": "exact_fill_identity_confirmation_mismatch"}), 400

    try:
        frozen = execution_freeze_by_id(execution_event_id)
        if frozen is None:
            return jsonify({"error": "frozen_execution_event_not_found"}), 404

        compatible = {
            str(row.get("fill_evidence_id")): row
            for row in compatible_execution_fills(frozen)
            if row.get("_binding_ready") is True
        }
        if fill_evidence_id not in compatible:
            return jsonify({
                "error": "fill_not_binding_ready",
                "message": (
                    "Exact fill is not currently eligible for binding. "
                    "No substitute fill was selected."
                ),
                "trade_permission": False,
                "order_path": "NONE",
            }), 409

        result = bind_execution_fill(execution_event_id, fill_evidence_id)
        result["trade_permission"] = False
        result["production_promotion_permitted"] = False
        result["order_path"] = "NONE"
        return jsonify(result), 200
    except Exception:
        app.logger.exception("Explicit execution-fill binding failed")
        return jsonify({
            "error": "execution_fill_binding_rejected",
            "message": (
                "Binding was rejected by the exact evidence gate. "
                "Refresh the page and verify the Bitget trade/order identity."
            ),
            "trade_permission": False,
            "order_path": "NONE",
        }), 409


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
