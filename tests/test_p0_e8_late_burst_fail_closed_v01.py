"""E8 offline fail-closed regression for late/missed Render burst boundaries.

Mock-only: no canonical scanner invocation, network, database, or schedules.
"""
from datetime import datetime, timedelta, timezone

import hourly


def test_late_initial_scan_is_not_backfilled_and_later_failure_exits_nonzero(monkeypatch, tmp_path):
    start = datetime(2026, 11, 23, 2, 17, tzinfo=timezone.utc)

    class Clock:
        @staticmethod
        def now(tz=None):
            return start

    calls = []
    monkeypatch.setattr(hourly, "datetime", Clock)
    monkeypatch.setattr(hourly, "should_run_initial_burst_scan", lambda *_: False)
    monkeypatch.setattr(
        hourly, "remaining_burst_boundaries",
        lambda *_: [start - timedelta(minutes=1), start + timedelta(minutes=3)],
    )
    monkeypatch.setattr(hourly.time, "sleep", lambda *_: None)

    def run_once(*args, **kwargs):
        calls.append(kwargs)
        return 7

    monkeypatch.setattr(hourly, "run_once", run_once)
    monkeypatch.setattr(hourly, "run_auxiliary_jobs_with_deadline", lambda *_: None)

    assert hourly.run_render_cron_burst(tmp_path, "config.json") == 7
    assert len(calls) == 1
    assert calls[0]["run_auxiliary_jobs"] is False
    assert calls[0]["run_source_override"] == "RENDER_CRON"


def test_unhandled_scanner_exception_cannot_report_success(monkeypatch, tmp_path):
    start = datetime(2026, 11, 23, 2, 1, tzinfo=timezone.utc)

    class Clock:
        @staticmethod
        def now(tz=None):
            return start

    monkeypatch.setattr(hourly, "datetime", Clock)
    monkeypatch.setattr(hourly, "should_run_initial_burst_scan", lambda *_: True)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic scanner failure")

    monkeypatch.setattr(hourly, "run_once", fail)
    try:
        hourly.run_render_cron_burst(tmp_path, "config.json")
    except RuntimeError as exc:
        assert "synthetic scanner failure" in str(exc)
    else:
        raise AssertionError("scanner exception was incorrectly treated as success")
