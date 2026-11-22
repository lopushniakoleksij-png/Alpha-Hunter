"""P0 offline regression: a failed scan must fail the overall Render burst.

This only invokes hourly.run_render_cron_burst with mocked time, sleep and
scanner functions. It never launches a scanner, contacts Render or writes DB.
"""
from datetime import datetime, timezone, timedelta

import hourly
import pytest


@pytest.mark.parametrize(
    ("scan_codes", "expected"),
    [
        ((2, 0, 0), 2),
        ((0, 2, 0), 2),
        ((0, 0, 2), 2),
        ((0, 0, 0), 0),
        ((3, 2, 0), 3),
    ],
)
def test_render_burst_preserves_first_scan_failure(monkeypatch, tmp_path, scan_codes, expected):
    start = datetime(2026, 11, 22, 8, 1, tzinfo=timezone.utc)
    class FrozenDateTime:
        @staticmethod
        def now(tz=None):
            return start

    calls = []
    codes = iter(scan_codes)

    def fake_run_once(*args, **kwargs):
        calls.append(kwargs)
        return next(codes)

    monkeypatch.setattr(hourly, "datetime", FrozenDateTime)
    monkeypatch.setattr(hourly, "should_run_initial_burst_scan", lambda *_: True)
    monkeypatch.setattr(
        hourly, "remaining_burst_boundaries",
        lambda *_: [start + timedelta(minutes=19), start + timedelta(minutes=39)],
    )
    monkeypatch.setattr(hourly.time, "sleep", lambda *_: None)
    monkeypatch.setattr(hourly, "run_once", fake_run_once)
    monkeypatch.setattr(hourly, "run_auxiliary_jobs_with_deadline", lambda *_: None)

    assert hourly.run_render_cron_burst(tmp_path, "config.json") == expected
    assert len(calls) == 3
    assert all(call["run_auxiliary_jobs"] is False for call in calls)
    assert all(call["run_source_override"] == "RENDER_CRON" for call in calls)
