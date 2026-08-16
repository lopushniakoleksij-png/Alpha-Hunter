from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from production_health import (
    ProductionHealthClient,
    safe_persist_report,
)


ROOT = Path(__file__).resolve().parent
LOCK_PATH = ROOT / ".alpha-hunter-production.lock"
RUN_DIRECTORY = ROOT / "data" / "production-runs"

PRODUCTION_VERSION = "production-hardening-v1"

_HEALTH_CLIENT_INITIALIZED = False
_HEALTH_CLIENT: ProductionHealthClient | None = None
_HEALTH_CLIENT_SETUP_ERROR: str | None = None


@dataclass(frozen=True)
class Step:
    name: str
    script: str
    timeout_seconds: int


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def build_run_id(
    started_at: datetime,
) -> str:
    return (
        started_at.strftime(
            "%Y%m%dT%H%M%SZ"
        )
        + "-"
        + uuid.uuid4().hex[:10]
    )


def process_is_alive(
    pid: int,
) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)

    except ProcessLookupError:
        return False

    except PermissionError:
        return True

    return True


def read_lock_pid() -> int | None:
    if not LOCK_PATH.exists():
        return None

    try:
        payload = json.loads(
            LOCK_PATH.read_text(
                encoding="utf-8"
            )
        )

        return int(
            payload.get("pid")
        )

    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def acquire_lock(
    run_id: str,
    started_at: datetime,
) -> tuple[bool, int | None]:

    if LOCK_PATH.exists():
        existing_pid = read_lock_pid()

        if (
            existing_pid is not None
            and process_is_alive(
                existing_pid
            )
        ):
            return (
                False,
                existing_pid,
            )

        try:
            LOCK_PATH.unlink()

        except FileNotFoundError:
            pass

    payload = {
        "pid": os.getpid(),
        "run_id": run_id,
        "started_at_utc":
            started_at.isoformat(),
    }

    try:
        fd = os.open(
            LOCK_PATH,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY,
        )

    except FileExistsError:
        return (
            False,
            read_lock_pid(),
        )

    with os.fdopen(
        fd,
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            separators=(",", ":"),
        )

    return (
        True,
        None,
    )


def release_lock() -> None:
    if not LOCK_PATH.exists():
        return

    current_pid = read_lock_pid()

    if current_pid != os.getpid():
        return

    try:
        LOCK_PATH.unlink()

    except FileNotFoundError:
        pass


def git_value(
    *args: str,
) -> str | None:
    try:
        result = subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ):
        return None

    if result.returncode != 0:
        return None

    return (
        result.stdout.strip()
        or None
    )


def get_health_client(
) -> tuple[
    ProductionHealthClient | None,
    str | None,
]:
    global _HEALTH_CLIENT_INITIALIZED
    global _HEALTH_CLIENT
    global _HEALTH_CLIENT_SETUP_ERROR

    if _HEALTH_CLIENT_INITIALIZED:
        return (
            _HEALTH_CLIENT,
            _HEALTH_CLIENT_SETUP_ERROR,
        )

    _HEALTH_CLIENT_INITIALIZED = True

    try:
        _HEALTH_CLIENT = (
            ProductionHealthClient
            .from_environment(
                ROOT
            )
        )

    except Exception as exc:
        _HEALTH_CLIENT = None
        _HEALTH_CLIENT_SETUP_ERROR = str(
            exc
        )

    return (
        _HEALTH_CLIENT,
        _HEALTH_CLIENT_SETUP_ERROR,
    )


def save_report(
    report: dict[str, Any],
) -> Path:

    RUN_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = str(
        report["production_run_id"]
    )

    final_path = (
        RUN_DIRECTORY
        / f"{run_id}.json"
    )

    temporary_path = (
        RUN_DIRECTORY
        / f".{run_id}.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        final_path
    )

    health_state = report.setdefault(
        "health_persistence",
        {
            "configured": None,
            "attempts": 0,
            "last_success": None,
            "last_error": None,
            "last_attempt_at_utc": None,
        },
    )

    health_state["attempts"] = (
        int(
            health_state.get(
                "attempts",
                0,
            )
            or 0
        )
        + 1
    )

    health_state[
        "last_attempt_at_utc"
    ] = now_utc().isoformat()

    client, setup_error = (
        get_health_client()
    )

    health_state["configured"] = (
        client is not None
    )

    if setup_error is not None:
        health_state["last_success"] = (
            False
        )

        health_state["last_error"] = (
            setup_error
        )

    else:
        ok, error = safe_persist_report(
            client,
            report,
        )

        health_state["last_success"] = ok
        health_state["last_error"] = error

    # Rewrite local report once so it also contains
    # the result of the Supabase health checkpoint.
    temporary_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        final_path
    )

    return final_path


def run_step(
    step: Step,
    *,
    production_run_id: str,
) -> dict[str, Any]:

    started = now_utc()

    print()
    print("=" * 100)
    print(step.name)
    print("=" * 100)
    print(
        "Production run:",
        production_run_id,
    )
    print(
        "Timeout:",
        f"{step.timeout_seconds}s",
    )

    environment = os.environ.copy()

    environment[
        "ALPHA_HUNTER_PRODUCTION_RUN_ID"
    ] = production_run_id

    environment[
        "ALPHA_HUNTER_PRODUCTION_VERSION"
    ] = PRODUCTION_VERSION

    command = [
        sys.executable,
        step.script,
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            timeout=
                step.timeout_seconds,
            check=False,
        )

        exit_code = int(
            completed.returncode
        )

        status = (
            "PASS"
            if exit_code == 0
            else "FAILED"
        )

        error = None

        if exit_code != 0:
            error = (
                f"exit_code={exit_code}"
            )

    except subprocess.TimeoutExpired:
        exit_code = 124
        status = "TIMEOUT"
        error = (
            "step exceeded "
            f"{step.timeout_seconds}s"
        )

    except OSError as exc:
        exit_code = 125
        status = "FAILED"
        error = str(exc)

    finished = now_utc()

    duration = (
        finished - started
    ).total_seconds()

    result = {
        "name": step.name,
        "script": step.script,
        "status": status,
        "exit_code": exit_code,
        "timeout_seconds":
            step.timeout_seconds,
        "started_at_utc":
            started.isoformat(),
        "finished_at_utc":
            finished.isoformat(),
        "duration_seconds":
            round(duration, 3),
        "error": error,
    }

    print(
        f"{step.name}: {status} "
        f"({duration:.1f}s)"
    )

    return result


def skipped_step(
    step: Step,
    reason: str,
) -> dict[str, Any]:

    timestamp = now_utc()

    return {
        "name": step.name,
        "script": step.script,
        "status": "SKIPPED",
        "exit_code": None,
        "timeout_seconds":
            step.timeout_seconds,
        "started_at_utc":
            timestamp.isoformat(),
        "finished_at_utc":
            timestamp.isoformat(),
        "duration_seconds": 0.0,
        "error": reason,
    }



def find_production_snapshot(
    production_run_id: str,
) -> Path | None:

    snapshots_dir = ROOT / "data" / "snapshots"

    if not snapshots_dir.exists():
        return None

    candidates = sorted(
        snapshots_dir.glob("snapshot-*.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )

    latest_path = snapshots_dir / "latest.json"

    if latest_path.exists():
        candidates.insert(0, latest_path)

    seen: set[Path] = set()

    for snapshot_path in candidates:

        if snapshot_path in seen:
            continue

        seen.add(snapshot_path)

        try:
            payload = json.loads(
                snapshot_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        if not isinstance(payload, dict):
            continue

        if (
            payload.get("production_run_id")
            == production_run_id
        ):
            return snapshot_path

    return None


def ledger_guardrail_trustworthy(
    guardrail_result: dict[str, Any],
) -> bool:

    required_checks = {
        "universe_ledger_presence",
        "universe_ledger_coverage",
        "universe_symbol_uniqueness",
        "universe_hour_bucket",
        "ledger_selection_context",
        "ledger_freshness",
        "ledger_source",
        "ledger_measurement_quality",
        "v79_trade_permission",
    }

    checks = {
        str(check.get("name")): check
        for check in guardrail_result.get(
            "checks",
            [],
        )
        if isinstance(check, dict)
    }

    if not required_checks.issubset(checks):
        return False

    for name in required_checks:

        check = checks[name]

        if (
            check.get("critical")
            and check.get("status") == "FAIL"
        ):
            return False

    return True


def run_guardrail_step(
    step: Step,
    *,
    production_run_id: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:

    started = now_utc()

    print()
    print("=" * 100)
    print(step.name)
    print("=" * 100)
    print(
        "Production run:",
        production_run_id,
    )

    snapshot_path = find_production_snapshot(
        production_run_id
    )

    try:

        if snapshot_path is None:
            raise RuntimeError(
                "exact production snapshot not found"
            )

        from production_guardrails import (
            ProductionHealthClient,
            evaluate,
            print_report,
        )

        client = ProductionHealthClient.from_environment(
            ROOT
        )

        if client is None:
            raise RuntimeError(
                "Supabase health client not configured"
            )

        guardrail_result = evaluate(
            snapshot_path=snapshot_path,
            client=client,
        )

        print_report(guardrail_result)

        guardrail_status = str(
            guardrail_result.get(
                "status",
                "FAIL",
            )
        ).upper()

        if guardrail_status not in {
            "PASS",
            "DEGRADED",
            "FAIL",
        }:
            raise RuntimeError(
                "invalid guardrail status: "
                f"{guardrail_status}"
            )

        step_status = (
            "PASS"
            if guardrail_status in {
                "PASS",
                "DEGRADED",
            }
            else "FAILED"
        )

        exit_code = (
            0
            if step_status == "PASS"
            else 1
        )

        error = (
            None
            if step_status == "PASS"
            else f"guardrail_status={guardrail_status}"
        )

    except Exception as exc:

        guardrail_status = "FAIL"
        step_status = "FAILED"
        exit_code = 125
        error = str(exc)

        guardrail_result = {
            "status": "FAIL",
            "checked_at_utc":
                now_utc().isoformat(),
            "snapshot_path":
                str(snapshot_path)
                if snapshot_path
                else None,
            "checks": [],
            "metrics": {},
            "error": str(exc),
        }

        print(
            "P0-3 guardrail error:",
            exc,
        )

    finished = now_utc()

    duration = (
        finished - started
    ).total_seconds()

    result = {
        "name": step.name,
        "script": step.script,
        "status": step_status,
        "exit_code": exit_code,
        "timeout_seconds":
            step.timeout_seconds,
        "started_at_utc":
            started.isoformat(),
        "finished_at_utc":
            finished.isoformat(),
        "duration_seconds":
            round(duration, 3),
        "error": error,
        "guardrail_status":
            guardrail_status,
        "snapshot_path":
            str(snapshot_path)
            if snapshot_path
            else None,
    }

    print(
        f"{step.name}: "
        f"{step_status} "
        f"(guardrail={guardrail_status}, "
        f"{duration:.1f}s)"
    )

    return result, guardrail_result


def main() -> int:

    started = now_utc()

    production_run_id = (
        build_run_id(
            started
        )
    )

    acquired, existing_pid = (
        acquire_lock(
            production_run_id,
            started,
        )
    )

    if not acquired:
        print(
            "Alpha Hunter production run "
            "SKIPPED: another production "
            "cycle is already active."
        )

        print(
            "Existing PID:",
            existing_pid,
        )

        return 3

    commit = git_value(
        "rev-parse",
        "HEAD",
    )

    branch = git_value(
        "branch",
        "--show-current",
    )

    report: dict[str, Any] = {
        "production_run_id":
            production_run_id,
        "production_version":
            PRODUCTION_VERSION,
        "mode": "SHADOW_PRODUCTION",
        "started_at_utc":
            started.isoformat(),
        "finished_at_utc": None,
        "duration_seconds": None,
        "overall_status":
            "RUNNING",
        "code_commit": commit,
        "git_branch": branch,
        "pid": os.getpid(),
        "steps": [],
        "guardrail": None,
        "invariants": {
            "automatic_trade_execution":
                False,
            "shadow_trade_permission":
                False,
        },
    }

    report_path = save_report(
        report
    )

    print()
    print("=" * 100)
    print(
        "ALPHA HUNTER "
        "SHADOW PRODUCTION "
        "— HARDENING V1"
    )
    print("=" * 100)

    print(
        "Production run ID:",
        production_run_id,
    )

    print(
        "Git branch:",
        branch,
    )

    print(
        "Code commit:",
        commit,
    )

    print(
        "Health report:",
        report_path,
    )

    live_scan = Step(
        "STEP 1 — LIVE MARKET SCAN",
        "run.py",
        300,
    )

    universe_ledger = Step(
        (
            "STEP 1B — V7.9 "
            "FULL-UNIVERSE HOURLY "
            "LEDGER SHADOW"
        ),
        "v79_universe_hourly_collector.py",
        120,
    )

    production_guardrail = Step(
        (
            "STEP 1C — PRODUCTION "
            "DATA GUARDRAILS"
        ),
        "production_guardrails.py",
        120,
    )

    model_steps = [
        Step(
            (
                "STEP 2 — V7.4 "
                "PERFORMANCE TRACKING"
            ),
            "v74_tracking_job.py",
            120,
        ),
        Step(
            (
                "STEP 3 — V7.5 "
                "OPPORTUNITY LIFECYCLE"
            ),
            "v75_lifecycle_job.py",
            120,
        ),
        Step(
            (
                "STEP 4 — V7.5 "
                "INDEPENDENT EPISODE "
                "TRACKER"
            ),
            "v75_episode_market_tracker.py",
            240,
        ),
        Step(
            (
                "STEP 5 — V7.5 "
                "24H EPISODE FINALIZER"
            ),
            "v75_episode_finalizer.py",
            120,
        ),
        Step(
            (
                "STEP 6 — V7.6 "
                "DIRECTION SHADOW"
            ),
            "v76_direction_shadow.py",
            240,
        ),
        Step(
            (
                "STEP 7 — V7.6 "
                "POST-CONFIRMATION "
                "OUTCOME TRACKER"
            ),
            "v76_post_confirmation_tracker.py",
            240,
        ),
        Step(
            (
                "STEP 8 — V7.7 "
                "HUGE-RR EXECUTION "
                "FEASIBILITY SHADOW"
            ),
            "v77_execution_feasibility_shadow.py",
            240,
        ),
        Step(
            (
                "STEP 9 — V7.8 "
                "TIMING & RR DECAY "
                "AUDITOR SHADOW"
            ),
            "v78_timing_rr_decay_shadow.py",
            240,
        ),
        Step(
            (
                "STEP 10 — V7.10 "
                "EARLY EXECUTION RR "
                "SHADOW"
            ),
            "v710_early_execution_rr_shadow.py",
            240,
        ),
    ]

    missed_mover_audit = Step(
        (
            "FINAL AUDIT — V7.9 "
            "MISSED-MOVER RECALL "
            "AUDITOR SHADOW"
        ),
        "v79_missed_mover_recall_auditor.py",
        180,
    )

    overall_status = "PASS"
    ledger_captured = False
    ledger_trustworthy = False

    try:
        result = run_step(
            live_scan,
            production_run_id=
                production_run_id,
        )

        report["steps"].append(
            result
        )

        save_report(
            report
        )

        if result["status"] != "PASS":
            overall_status = "FAILED"

            report["steps"].append(
                skipped_step(
                    universe_ledger,
                    "LIVE_SCAN_FAILED",
                )
            )

            report["steps"].append(
                skipped_step(
                    production_guardrail,
                    "LIVE_SCAN_FAILED",
                )
            )

            for step in model_steps:
                report["steps"].append(
                    skipped_step(
                        step,
                        "LIVE_SCAN_FAILED",
                    )
                )

            report["steps"].append(
                skipped_step(
                    missed_mover_audit,
                    "LIVE_SCAN_FAILED",
                )
            )

        else:
            ledger_result = run_step(
                universe_ledger,
                production_run_id=
                    production_run_id,
            )

            report["steps"].append(
                ledger_result
            )

            ledger_captured = (
                ledger_result[
                    "status"
                ]
                == "PASS"
            )

            if not ledger_captured:
                overall_status = "FAILED"

                report["steps"].append(
                    skipped_step(
                        production_guardrail,
                        (
                            "UNIVERSE_LEDGER_"
                            "NOT_CAPTURED"
                        ),
                    )
                )

                for step in model_steps:
                    report[
                        "steps"
                    ].append(
                        skipped_step(
                            step,
                            (
                                "DATA_GUARDRAIL_"
                                "UNAVAILABLE"
                            ),
                        )
                    )

                report[
                    "steps"
                ].append(
                    skipped_step(
                        missed_mover_audit,
                        (
                            "UNIVERSE_LEDGER_"
                            "NOT_CAPTURED"
                        ),
                    )
                )

                save_report(
                    report
                )

            else:
                (
                    guardrail_step_result,
                    guardrail_result,
                ) = run_guardrail_step(
                    production_guardrail,
                    production_run_id=
                        production_run_id,
                )

                report[
                    "steps"
                ].append(
                    guardrail_step_result
                )

                # Convert datetime values to strings
                # before placing the complete guardrail
                # result inside the JSON health report.
                report["guardrail"] = (
                    json.loads(
                        json.dumps(
                            guardrail_result,
                            default=str,
                        )
                    )
                )

                guardrail_status = str(
                    guardrail_result.get(
                        "status",
                        "FAIL",
                    )
                ).upper()

                ledger_trustworthy = (
                    ledger_guardrail_trustworthy(
                        guardrail_result
                    )
                )

                if (
                    guardrail_status
                    == "DEGRADED"
                    and overall_status
                    != "FAILED"
                ):
                    overall_status = (
                        "DEGRADED"
                    )

                elif (
                    guardrail_status
                    == "FAIL"
                ):
                    overall_status = (
                        "FAILED"
                    )

                save_report(
                    report
                )

                if (
                    guardrail_status
                    == "FAIL"
                ):
                    for step in model_steps:
                        report[
                            "steps"
                        ].append(
                            skipped_step(
                                step,
                                (
                                    "DATA_GUARDRAIL_"
                                    "FAILED"
                                ),
                            )
                        )

                else:
                    model_chain_failed = False

                    for step in model_steps:

                        if model_chain_failed:
                            report[
                                "steps"
                            ].append(
                                skipped_step(
                                    step,
                                    (
                                        "UPSTREAM_MODEL_"
                                        "STEP_FAILED"
                                    ),
                                )
                            )
                            continue

                        step_result = run_step(
                            step,
                            production_run_id=
                                production_run_id,
                        )

                        report[
                            "steps"
                        ].append(
                            step_result
                        )

                        if (
                            step_result[
                                "status"
                            ]
                            != "PASS"
                        ):
                            overall_status = (
                                "FAILED"
                            )

                            model_chain_failed = (
                                True
                            )

                        save_report(
                            report
                        )

                # V7.9 recall evidence is independent
                # of the model chain. Preserve it only
                # when its universe ledger passed the
                # relevant data-integrity checks.
                if ledger_trustworthy:
                    audit_result = run_step(
                        missed_mover_audit,
                        production_run_id=
                            production_run_id,
                    )

                    report[
                        "steps"
                    ].append(
                        audit_result
                    )

                    if (
                        audit_result[
                            "status"
                        ]
                        != "PASS"
                    ):
                        overall_status = (
                            "FAILED"
                        )

                else:
                    report[
                        "steps"
                    ].append(
                        skipped_step(
                            missed_mover_audit,
                            (
                                "UNTRUSTWORTHY_"
                                "UNIVERSE_LEDGER"
                            ),
                        )
                    )

    finally:
        finished = now_utc()

        report[
            "finished_at_utc"
        ] = finished.isoformat()

        report[
            "duration_seconds"
        ] = round(
            (
                finished
                - started
            ).total_seconds(),
            3,
        )

        report[
            "overall_status"
        ] = overall_status

        report_path = save_report(
            report
        )

        release_lock()

    print()
    print("=" * 100)
    print(
        "PRODUCTION HEALTH SUMMARY"
    )
    print("=" * 100)

    for step in report["steps"]:
        print(
            f"{step['status']:<8} "
            f"{step['name']}"
        )

    print()
    print(
        "Overall status:",
        report[
            "overall_status"
        ],
    )

    print(
        "Production run ID:",
        production_run_id,
    )

    print(
        "Health report:",
        report_path,
    )

    print(
        "Automatic trading:",
        "DISABLED",
    )

    print("=" * 100)

    return (
        0
        if overall_status
        in {
            "PASS",
            "DEGRADED",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
