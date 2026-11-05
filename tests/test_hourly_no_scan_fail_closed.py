"""Synthetic no-network tests: no scan and missed aligned boundary are not success."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hourly

ROOT = Path("/tmp/alpha-hunter-synthetic-no-io")

def _exercise(monkeypatch, *, initial, boundaries, missed=False, codes=()):
    calls = []
    now = datetime.now(timezone.utc)
    schedule = [now - timedelta(seconds=1) if missed else now + timedelta(minutes=2)
                for _ in range(boundaries)]
    monkeypatch.setattr(hourly, "should_run_initial_burst_scan", lambda *_: initial)
    monkeypatch.setattr(hourly, "remaining_burst_boundaries", lambda *_: schedule)
    monkeypatch.setattr(hourly.time, "sleep", lambda _: None)
    responses = iter(codes)
    def scan(*args, **kwargs):
        calls.append("scan")
        return next(responses)
    monkeypatch.setattr(hourly, "run_once", scan)
    monkeypatch.setattr(hourly, "run_auxiliary_jobs_with_deadline",
                        lambda *a, **k: calls.append("aux"))
    return hourly.run_render_cron_burst(ROOT, "synthetic"), calls

def test_no_scan_hour_returns_nonzero_and_never_runs_auxiliary(monkeypatch, capsys):
    status, calls = _exercise(monkeypatch, initial=False, boundaries=0)
    assert status == 4
    assert calls == []
    assert "Canonical scan absent" in capsys.readouterr().err

def test_missed_only_boundary_returns_nonzero_without_backfill(monkeypatch, capsys):
    status, calls = _exercise(monkeypatch, initial=False, boundaries=1, missed=True)
    assert status == 4
    assert calls == []
    assert "cadence incomplete" in capsys.readouterr().err

def test_successful_initial_scan_does_not_hide_missed_boundary(monkeypatch):
    status, calls = _exercise(monkeypatch, initial=True, boundaries=1,
                              missed=True, codes=(0,))
    assert status == 4
    assert calls == ["scan", "aux"]

def test_original_scan_failure_takes_precedence_over_missed_boundary(monkeypatch):
    status, calls = _exercise(monkeypatch, initial=True, boundaries=1,
                              missed=True, codes=(2,))
    assert status == 2
    assert calls == ["scan"]

def test_normal_scan_keeps_success_status(monkeypatch):
    status, calls = _exercise(monkeypatch, initial=True, boundaries=0, codes=(0,))
    assert status == 0
    assert calls == ["scan", "aux"]
