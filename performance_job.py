from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from alpha_hunter.env import load_env_file
from alpha_hunter.performance import extract_signal_rows
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.collector import load_config, load_previous_snapshot


COLLECTOR_TELEMETRY_TABLE = "alpha_hunter_execution_quality_collector_runs_v01"


def _align_render_cron_identity() -> str | None:
    """Restore canonical runtime identity for auxiliary Render cron subprocesses.

    hourly.py passes the RENDER_CRON override only to run.py. Auxiliary jobs are
    separate subprocesses and otherwise inherit the parent environment without
    ALPHA_HUNTER_RUN_SOURCE / ALPHA_HUNTER_RUNTIME_ROLE. Since snapshot loading
    is identity-strict, explicitly restoring those values here prevents a
    canonical RENDER_CRON snapshot from being rejected as incompatible.
    """
    if os.getenv("RENDER_SERVICE_NAME") and not os.getenv("PORT"):
        os.environ.setdefault("ALPHA_HUNTER_RUN_SOURCE", "RENDER_CRON")
        os.environ.setdefault("ALPHA_HUNTER_RUNTIME_ROLE", "RENDER_CRON")
        return "RENDER_CRON"
    return None


def _parse_collector_result(stdout: str) -> dict:
    text = str(stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return payload if isinstance(payload, dict) else {}


def _optional_int(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _persist_collector_telemetry(
    settings: SupabaseConfig,
    *,
    snapshot: dict,
    snapshot_source: str,
    collector_exists: bool,
    bitget_credentials_configured: bool,
    subprocess_started: bool,
    subprocess_exit_code: int | None,
    result: dict,
) -> None:
    checked_at = datetime.now(timezone.utc).isoformat()
    source_run_id = str(snapshot.get("run_id") or "") or None
    status = "COLLECTOR_NOT_FOUND"
    if collector_exists:
        if not subprocess_started:
            status = "RESULT_JSON_UNAVAILABLE"
        elif subprocess_exit_code == 0:
            status = "PASS"
        else:
            status = "DEGRADED"

    collector_run_id = hashlib.sha256(
        f"{source_run_id}|{checked_at}|{status}".encode("utf-8")
    ).hexdigest()[:32]

    row = {
        "collector_run_id": collector_run_id,
        "source_run_id": source_run_id,
        "checked_at_utc": checked_at,
        "snapshot_source": snapshot_source,
        "collector_exists": collector_exists,
        "bitget_credentials_configured": bitget_credentials_configured,
        "supabase_configured": True,
        "subprocess_started": subprocess_started,
        "subprocess_exit_code": subprocess_exit_code,
        "collector_status": status,
        "fills_considered": _optional_int(result.get("fills_considered")),
        "order_details_connected": _optional_int(
            result.get("order_details_connected")
        ),
        "order_detail_failures": _optional_int(
            result.get("order_detail_failures")
        ),
        "rows_persisted": _optional_int(result.get("rows_persisted")),
        "explicit_limit_benchmarks": _optional_int(
            result.get("explicit_limit_benchmarks")
        ),
        "market_slippage_withheld": _optional_int(
            result.get("market_slippage_withheld")
        ),
        "read_only_get": result.get("read_only_get"),
        "no_order_write_path": result.get("no_order_write_path"),
        "shadow_only": True,
        "trade_permission": False,
        "evidence": {
            "result_json_available": bool(result),
            "raw_stdout_persisted": False,
            "raw_stderr_persisted": False,
            "credential_values_persisted": False,
            "raw_order_ids_persisted_here": False,
            "raw_client_oids_persisted_here": False,
        },
    }

    headers = {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    response = requests.post(
        f"{settings.url}/rest/v1/{COLLECTOR_TELEMETRY_TABLE}",
        headers=headers,
        data=json.dumps(row, separators=(",", ":")),
        timeout=settings.timeout_seconds,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(
            "Collector telemetry persistence failed: "
            f"HTTP {response.status_code}"
        )


def _verify_canonical_signal_rows(
    settings: SupabaseConfig,
    snapshot: dict,
) -> dict:
    run_id = str(snapshot.get("run_id") or "")
    if not run_id:
        raise RuntimeError("Canonical snapshot is missing run_id")

    expected_rows = extract_signal_rows(snapshot)
    expected_ids = {
        str(row.get("signal_id") or "")
        for row in expected_rows
        if row.get("signal_id")
    }

    response = requests.get(
        f"{settings.url}/rest/v1/alpha_hunter_signals",
        params={
            "select": "signal_id",
            "run_id": f"eq.{run_id}",
            "limit": "2000",
        },
        headers={
            "apikey": settings.key,
            "Authorization": f"Bearer {settings.key}",
        },
        timeout=settings.timeout_seconds,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Canonical signal verification failed: "
            f"HTTP {response.status_code}"
        )

    try:
        rows = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Canonical signal verification returned invalid JSON"
        ) from exc

    if not isinstance(rows, list):
        raise RuntimeError(
            "Canonical signal verification returned unexpected shape"
        )

    observed_ids = {
        str(row.get("signal_id") or "")
        for row in rows
        if isinstance(row, dict) and row.get("signal_id")
    }
    missing_ids = expected_ids - observed_ids
    unexpected_ids = observed_ids - expected_ids

    result = {
        "run_id": run_id,
        "expected_count": len(expected_ids),
        "observed_count": len(observed_ids),
        "missing_count": len(missing_ids),
        "unexpected_count": len(unexpected_ids),
        "verified": not missing_ids and not unexpected_ids,
        "write_path": "NONE",
    }

    if not result["verified"]:
        raise RuntimeError(
            "Canonical signal verification mismatch: "
            f"expected={result['expected_count']} "
            f"observed={result['observed_count']} "
            f"missing={result['missing_count']} "
            f"unexpected={result['unexpected_count']}"
        )

    return result


def main() -> int:
    root = Path(__file__).resolve().parent
    load_env_file(root / ".env")
    config = load_config(root / "config.json")
    runtime_identity = _align_render_cron_identity()

    settings = SupabaseConfig.from_environment(config)
    if settings is None:
        raise SystemExit("Supabase is not configured")

    snapshot, snapshot_source = load_previous_snapshot(
        root / "config.json",
        config,
        cloud_settings=settings,
    )

    collector = root / "ops" / "collect_execution_quality_readonly.py"
    collector_exists = collector.exists()
    bitget_credentials_configured = bool(
        os.getenv("BITGET_API_KEY")
        and os.getenv("BITGET_SECRET_KEY")
        and os.getenv("BITGET_API_PASSPHRASE")
    )
    collector_result = {}
    subprocess_started = False
    subprocess_exit_code = None

    if collector_exists:
        completed = subprocess.run(
            [sys.executable, str(collector)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        subprocess_started = True
        subprocess_exit_code = completed.returncode
        collector_result = _parse_collector_result(completed.stdout)

        if completed.stdout:
            print(
                completed.stdout,
                end="" if completed.stdout.endswith("\n") else "\n",
            )
        if completed.returncode != 0:
            print(
                "READ-ONLY EXECUTION QUALITY COLLECTION DEGRADED: "
                f"exit code {completed.returncode}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(
                "READ-ONLY EXECUTION QUALITY COLLECTION: PASS",
                flush=True,
            )
    else:
        print(
            "READ-ONLY EXECUTION QUALITY COLLECTION DEGRADED: "
            "collector script not found",
            file=sys.stderr,
            flush=True,
        )

    try:
        _persist_collector_telemetry(
            settings,
            snapshot=snapshot or {},
            snapshot_source=(
                snapshot_source
                if snapshot
                else (runtime_identity or "NO_COMPATIBLE_SNAPSHOT")
            ),
            collector_exists=collector_exists,
            bitget_credentials_configured=bitget_credentials_configured,
            subprocess_started=subprocess_started,
            subprocess_exit_code=subprocess_exit_code,
            result=collector_result,
        )
    except Exception as exc:
        print(
            "READ-ONLY EXECUTION QUALITY TELEMETRY DEGRADED: "
            f"{exc.__class__.__name__}",
            file=sys.stderr,
            flush=True,
        )

    retention_collector = (
        root / "ops" / "collect_candidate_retention_shadow.py"
    )
    if retention_collector.exists():
        retention_completed = subprocess.run(
            [sys.executable, str(retention_collector)],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if retention_completed.stdout:
            print(
                retention_completed.stdout,
                end=(
                    ""
                    if retention_completed.stdout.endswith("\n")
                    else "\n"
                ),
            )
        if retention_completed.returncode != 0:
            print(
                "V15 CANDIDATE RETENTION SHADOW DEGRADED: "
                f"exit code {retention_completed.returncode}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(
                "V15 CANDIDATE RETENTION SHADOW: PASS",
                flush=True,
            )
    else:
        print(
            "V15 CANDIDATE RETENTION SHADOW DEGRADED: "
            "collector script not found",
            file=sys.stderr,
            flush=True,
        )

    if not snapshot:
        raise SystemExit("No latest snapshot found")

    print(f"PERFORMANCE SNAPSHOT SOURCE: {snapshot_source}")

    signal_verification = _verify_canonical_signal_rows(settings, snapshot)
    print(
        "PERFORMANCE SIGNALS VERIFIED: "
        f"{signal_verification['observed_count']}/"
        f"{signal_verification['expected_count']} "
        "write_path=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
