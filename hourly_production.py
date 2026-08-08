from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_step(
    name: str,
    command: list[str],
) -> None:
    print()
    print("=" * 90)
    print(name)
    print("=" * 90)

    result = subprocess.run(
        command,
        cwd=ROOT,
    )

    if result.returncode != 0:
        raise SystemExit(
            f"{name} FAILED "
            f"with exit code "
            f"{result.returncode}"
        )


def main() -> int:
    started = datetime.now(
        timezone.utc
    )

    print()
    print(
        "ALPHA HUNTER V7.4 "
        "HOURLY PRODUCTION CYCLE"
    )

    print(
        "Started:",
        started.isoformat(),
    )

    python = sys.executable

    run_step(
        "STEP 1 — LIVE MARKET SCAN",
        [
            python,
            "run.py",
        ],
    )

    run_step(
        "STEP 2 — V7.4 PERFORMANCE TRACKING",
        [
            python,
            "v74_tracking_job.py",
        ],
    )

    finished = datetime.now(
        timezone.utc
    )

    duration = (
        finished - started
    ).total_seconds()

    print()
    print("=" * 90)
    print(
        "ALPHA HUNTER V7.4 "
        "HOURLY PRODUCTION: PASS"
    )
    print(
        "Finished:",
        finished.isoformat(),
    )
    print(
        "Duration:",
        round(
            duration,
            1,
        ),
        "seconds",
    )
    print("=" * 90)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
