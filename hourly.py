from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def seconds_until_next_hour(now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(0.0, (next_hour - current).total_seconds())


def acquire_lock(lock_path: Path) -> bool:
    """Create an exclusive PID lock to prevent overlapping hourly collectors."""
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


def run_once(project_root: Path, config: str) -> int:
    lock_path = project_root / ".alpha-hunter.lock"
    if not acquire_lock(lock_path):
        print("Alpha Hunter run skipped: another run is already active", file=sys.stderr, flush=True)
        return 3
    try:
        command = [sys.executable, str(project_root / "run.py"), "--config", config]
        completed = subprocess.run(command, cwd=project_root, check=False)
        return completed.returncode
    finally:
        release_lock(lock_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Alpha Hunter at the top of every UTC hour")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent

    if args.once:
        return run_once(project_root, args.config)

    while True:
        delay = seconds_until_next_hour()
        print(f"Next Alpha Hunter run in {delay:.0f} seconds", flush=True)
        time.sleep(delay)
        code = run_once(project_root, args.config)
        if code != 0:
            print(f"Alpha Hunter run finished with exit code {code}", file=sys.stderr, flush=True)
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
