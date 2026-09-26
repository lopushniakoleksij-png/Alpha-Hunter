from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping


DEFAULT_SCAN_INTERVAL_MINUTES = 20
DEFAULT_MINIMUM_BURST_START_GAP_MINUTES = 15
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _validated_interval_minutes(value: int) -> int:
    interval = int(value)
    if interval <= 0 or interval > 60 or 60 % interval != 0:
        raise ValueError(
            "scan interval must be a positive divisor of 60 minutes"
        )
    return interval


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def next_scan_at(
    now: datetime | None = None,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
) -> datetime:
    """Return the next aligned UTC scanner boundary."""
    current = _utc(now)
    interval = _validated_interval_minutes(interval_minutes)
    minute_bucket = (current.minute // interval) * interval
    boundary = current.replace(
        minute=minute_bucket,
        second=0,
        microsecond=0,
    )
    if boundary <= current:
        boundary += timedelta(minutes=interval)
    return boundary


def seconds_until_next_interval(
    now: datetime | None = None,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
) -> float:
    current = _utc(now)
    return max(
        0.0,
        (next_scan_at(current, interval_minutes) - current).total_seconds(),
    )


def seconds_until_next_hour(now: datetime | None = None) -> float:
    """Backward-compatible helper retained for existing tooling/tests."""
    return seconds_until_next_interval(now, 60)


def render_cron_burst_enabled(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Detect the Render cron job without enabling burst mode in the web app.

    The production Render cron job historically runs:
        python3 hourly.py --once

    Render cron jobs expose RENDER_SERVICE_NAME but do not need a web PORT.
    The dashboard web service has PORT, so it must remain single-scan when a
    human presses Run Fresh Scan.

    ALPHA_HUNTER_RENDER_BURST_MODE explicitly overrides auto-detection.
    """
    env = environ if environ is not None else os.environ
    override = str(
        env.get("ALPHA_HUNTER_RENDER_BURST_MODE", "")
    ).strip().lower()

    if override in _TRUE_VALUES:
        return True
    if override in _FALSE_VALUES:
        return False

    return bool(env.get("RENDER_SERVICE_NAME")) and not bool(env.get("PORT"))


def should_run_initial_burst_scan(
    now: datetime | None = None,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
    minimum_start_gap_minutes: int = DEFAULT_MINIMUM_BURST_START_GAP_MINUTES,
) -> bool:
    """Return whether an immediate cron scan leaves enough room to the next boundary.

    Render cron invocations can start late. An immediate scan is allowed only
    when the next aligned boundary is at least the sealed minimum interval away.
    Otherwise the process waits for that boundary instead of creating a
    too-frequent duplicate observation.
    """
    current = _utc(now)
    interval = _validated_interval_minutes(interval_minutes)
    minimum_gap = int(minimum_start_gap_minutes)
    if minimum_gap <= 0 or minimum_gap > interval:
        raise ValueError(
            "minimum burst start gap must be positive and no greater than interval"
        )
    seconds_to_next = (
        next_scan_at(current, interval) - current
    ).total_seconds()
    return seconds_to_next >= minimum_gap * 60.0


def remaining_burst_boundaries(
    now: datetime | None = None,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
) -> list[datetime]:
    """Return remaining aligned boundaries in the current UTC hour.

    The initial Render cron invocation performs the first full scan immediately.
    This helper returns only later boundaries, e.g. :20 and :40 for a 20-minute
    cadence. Missed boundaries are never backfilled with a late duplicate scan.
    """
    current = _utc(now)
    interval = _validated_interval_minutes(interval_minutes)
    hour = current.replace(minute=0, second=0, microsecond=0)

    boundaries: list[datetime] = []
    for minute in range(interval, 60, interval):
        candidate = hour + timedelta(minutes=minute)
        if candidate > current:
            boundaries.append(candidate)
    return boundaries


def acquire_lock(lock_path: Path) -> bool:
    """Create an exclusive PID lock to prevent overlapping collectors."""
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return True


def release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def run_once(
    project_root: Path,
    config: str,
    *,
    run_auxiliary_jobs: bool = True,
) -> int:
    """Run one canonical scanner cycle.

    Intermediate 20-minute cycles run only run.py. The first/top-of-hour cycle
    keeps the existing performance/feature/outcome auxiliary jobs. run.py
    persists canonical snapshots, signals and signal features on every cycle.
    """
    lock_path = project_root / ".alpha-hunter.lock"
    if not acquire_lock(lock_path):
        print(
            "Alpha Hunter run skipped: another run is already active",
            file=sys.stderr,
            flush=True,
        )
        return 3

    try:
        command = [
            sys.executable,
            str(project_root / "run.py"),
            "--config",
            config,
        ]
        completed = subprocess.run(
            command,
            cwd=project_root,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode

        if not run_auxiliary_jobs:
            print(
                "Fast canonical scan complete; hourly auxiliary jobs deferred "
                "to the first cycle.",
                flush=True,
            )
            return 0

        performance = subprocess.run(
            [sys.executable, str(project_root / "performance_job.py")],
            cwd=project_root,
            check=False,
        )
        if performance.returncode != 0:
            print(
                f"Performance signal save failed with exit code "
                f"{performance.returncode}",
                file=sys.stderr,
                flush=True,
            )

        features = subprocess.run(
            [sys.executable, str(project_root / "feature_job.py")],
            cwd=project_root,
            check=False,
        )
        if features.returncode != 0:
            print(
                f"Feature capture failed with exit code {features.returncode}",
                file=sys.stderr,
                flush=True,
            )

        outcomes = subprocess.run(
            [sys.executable, str(project_root / "outcome_job.py")],
            cwd=project_root,
            check=False,
        )
        if outcomes.returncode not in {0, 2}:
            print(
                f"Outcome evaluation failed with exit code "
                f"{outcomes.returncode}",
                file=sys.stderr,
                flush=True,
            )
        return 0
    finally:
        release_lock(lock_path)


def run_render_cron_burst(
    project_root: Path,
    config: str,
    *,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
) -> int:
    """Use one hourly Render cron invocation to produce :00/:20/:40 scans.

    The external Render schedule can remain hourly. The cron process stays
    alive for the current hour, runs the initial full cycle immediately, then
    scanner-only cycles at the remaining aligned boundaries. It exits before
    the next hourly invocation, avoiding overlap.

    A failed intermediate scan does not prevent later boundaries from running;
    the first non-zero return code is returned at the end for cron visibility.
    """
    interval = _validated_interval_minutes(interval_minutes)
    burst_started_at = datetime.now(timezone.utc)

    if should_run_initial_burst_scan(
        burst_started_at,
        interval,
    ):
        overall_code = run_once(
            project_root,
            config,
            run_auxiliary_jobs=True,
        )
    else:
        overall_code = 0
        print(
            "Render cron burst skipped late immediate scan; "
            "waiting for next aligned boundary.",
            flush=True,
        )

    for scheduled_at in remaining_burst_boundaries(
        burst_started_at,
        interval,
    ):
        current = datetime.now(timezone.utc)
        if current >= scheduled_at:
            print(
                "Render cron burst skipped missed boundary "
                f"{scheduled_at.isoformat()}; no late backfill.",
                flush=True,
            )
            continue

        delay = (scheduled_at - current).total_seconds()
        print(
            "Render cron burst next canonical scan at "
            f"{scheduled_at.isoformat()} "
            f"(in {delay:.0f} seconds)",
            flush=True,
        )
        time.sleep(delay)

        code = run_once(
            project_root,
            config,
            run_auxiliary_jobs=False,
        )
        if overall_code == 0 and code != 0:
            overall_code = code

    return overall_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Alpha Hunter on aligned UTC scanner boundaries. "
            "Default production cadence is every 20 minutes."
        )
    )
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run once and exit outside Render cron. In the Render cron runtime, "
            "automatically hold the job for aligned :20/:40 scanner-only cycles."
        ),
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
        help=(
            "Aligned scanner cadence. Must divide 60. "
            "Defaults to ALPHA_HUNTER_SCAN_INTERVAL_MINUTES or 20."
        ),
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent

    configured_interval = (
        args.interval_minutes
        if args.interval_minutes is not None
        else int(
            os.getenv(
                "ALPHA_HUNTER_SCAN_INTERVAL_MINUTES",
                str(DEFAULT_SCAN_INTERVAL_MINUTES),
            )
        )
    )
    interval = _validated_interval_minutes(configured_interval)

    if args.once:
        if render_cron_burst_enabled():
            print(
                "Render cron runtime detected: enabling aligned "
                f"{interval}-minute canonical burst.",
                flush=True,
            )
            return run_render_cron_burst(
                project_root,
                args.config,
                interval_minutes=interval,
            )

        return run_once(
            project_root,
            args.config,
            run_auxiliary_jobs=True,
        )

    while True:
        now = datetime.now(timezone.utc)
        scheduled_at = next_scan_at(now, interval)
        delay = max(0.0, (scheduled_at - now).total_seconds())
        print(
            "Next Alpha Hunter canonical scan at "
            f"{scheduled_at.isoformat()} "
            f"(in {delay:.0f} seconds)",
            flush=True,
        )
        time.sleep(delay)

        run_auxiliary = scheduled_at.minute == 0
        code = run_once(
            project_root,
            args.config,
            run_auxiliary_jobs=run_auxiliary,
        )
        if code != 0:
            print(
                f"Alpha Hunter run finished with exit code {code}",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
