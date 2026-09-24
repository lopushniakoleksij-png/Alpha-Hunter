from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_SCAN_INTERVAL_MINUTES = 20


def _validated_interval_minutes(value: int) -> int:
    interval = int(value)
    if interval <= 0 or interval > 60 or 60 % interval != 0:
        raise ValueError(
            "scan interval must be a positive divisor of 60 minutes"
        )
    return interval


def next_scan_at(
    now: datetime | None = None,
    interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
) -> datetime:
    """Return the next aligned UTC scanner boundary.

    A 20-minute cadence produces :00, :20 and :40. The function always returns
    a future boundary, including when called exactly on one, so the daemon
    cannot immediately double-run after completing a scan.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

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
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    return max(
        0.0,
        (next_scan_at(current, interval_minutes) - current).total_seconds(),
    )


def seconds_until_next_hour(now: datetime | None = None) -> float:
    """Backward-compatible helper retained for existing tooling/tests."""
    return seconds_until_next_interval(now, 60)


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

    Intermediate 20-minute cycles run only run.py. The top-of-hour cycle keeps
    the existing performance/feature/outcome auxiliary jobs. run.py already
    persists canonical snapshots, signals and signal features, so intermediate
    cycles still provide the full discovery/S1-S10 evidence surface without
    multiplying slower downstream maintenance work.
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
                "to the :00 cycle.",
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
        help="Run one full scanner + auxiliary cycle and exit",
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

    if args.once:
        return run_once(
            project_root,
            args.config,
            run_auxiliary_jobs=True,
        )

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

        # Preserve expensive auxiliary maintenance at the protected top-of-hour
        # cycle while giving discovery/S1-S10 a 20-minute observation cadence.
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
