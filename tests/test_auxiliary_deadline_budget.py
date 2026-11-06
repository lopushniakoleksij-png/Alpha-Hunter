"""Regression: auxiliary subprocesses must not overrun the cron exit budget.

Synthetic clock and subprocess only; never invokes scanner or network.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import hourly


def test_subsecond_auxiliary_budget_does_not_launch_process(capsys):
    fixed = datetime(2026, 11, 6, 0, 40, tzinfo=timezone.utc)
    real_datetime = datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is not None else fixed.replace(tzinfo=None)

    deadline = fixed + timedelta(seconds=90.5)
    with patch.object(hourly, "datetime", FrozenDateTime), patch.object(
        hourly.subprocess, "run"
    ) as run:
        hourly.run_auxiliary_jobs_with_deadline(
            Path("/unused-synthetic-project"),
            deadline,
            exit_buffer_seconds=90,
        )
    run.assert_not_called()
    assert "deadline reached" in capsys.readouterr().out


def test_one_second_auxiliary_budget_remains_executable():
    fixed = datetime(2026, 11, 6, 0, 40, tzinfo=timezone.utc)
    real_datetime = datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is not None else fixed.replace(tzinfo=None)

    deadline = fixed + timedelta(seconds=91)
    class Completed:
        returncode = 0

    with patch.object(hourly, "datetime", FrozenDateTime), patch.object(
        hourly.subprocess, "run", return_value=Completed()
    ) as run:
        hourly.run_auxiliary_jobs_with_deadline(
            Path("/unused-synthetic-project"),
            deadline,
            exit_buffer_seconds=90,
        )
    assert run.call_count == 3
    assert all(call.kwargs["timeout"] == 1.0 for call in run.call_args_list)
