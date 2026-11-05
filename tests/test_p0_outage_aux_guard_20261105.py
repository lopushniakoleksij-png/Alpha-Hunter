"""Offline-only regression tests for the protected hourly burst's outage guard.

No network, Supabase, Bitget, cron, data files or real scanner processes.
This draft branch must never be merged or deployed without P0 review.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import hourly


def _simulate(monkeypatch, codes, *, initial=True, boundaries=0):
    calls = []
    results = iter(codes)
    times = [datetime.now(timezone.utc) + timedelta(minutes=2 * (i + 1))
             for i in range(boundaries)]
    monkeypatch.setattr(hourly, "should_run_initial_burst_scan",
                        lambda *_: initial)
    monkeypatch.setattr(hourly, "remaining_burst_boundaries",
                        lambda *_: times)
    monkeypatch.setattr(hourly.time, "sleep", lambda _: None)

    def fake_scan(root, config, *, run_auxiliary_jobs, run_source_override):
        assert root == Path("/tmp/synthetic-no-scanner")
        assert config == "synthetic-config"
        assert run_auxiliary_jobs is False
        assert run_source_override == "RENDER_CRON"
        calls.append("canonical")
        return next(results)

    def fake_aux(root, deadline_utc):
        assert root == Path("/tmp/synthetic-no-scanner")
        assert deadline_utc.tzinfo is not None
        calls.append("auxiliary")

    monkeypatch.setattr(hourly, "run_once", fake_scan)
    monkeypatch.setattr(hourly, "run_auxiliary_jobs_with_deadline", fake_aux)
    result = hourly.run_render_cron_burst(
        Path("/tmp/synthetic-no-scanner"),
        "synthetic-config",
    )
    return result, calls


def test_all_canonical_failures_defer_secondary_reads_but_keep_failure(monkeypatch, capsys):
    code, calls = _simulate(monkeypatch, [2, 2, 2], boundaries=2)
    assert code == 2
    assert calls == ["canonical", "canonical", "canonical"]
    assert "Auxiliary evidence deferred" in capsys.readouterr().err


def test_successful_burst_keeps_original_auxiliary_schedule(monkeypatch):
    code, calls = _simulate(monkeypatch, [0, 0, 0], boundaries=2)
    assert code == 0
    assert calls == ["canonical", "canonical", "canonical", "auxiliary"]


def test_mixed_burst_with_later_success_keeps_aux_and_reports_first_failure(monkeypatch):
    code, calls = _simulate(monkeypatch, [2, 0], boundaries=1)
    assert code == 2
    assert calls == ["canonical", "canonical", "auxiliary"]


def test_late_run_without_any_scan_does_not_launch_auxiliary(monkeypatch, capsys):
    code, calls = _simulate(monkeypatch, [], initial=False, boundaries=0)
    assert code == 4  # Missing canonical scan must fail closed.
    assert calls == []
    stderr = capsys.readouterr().err
    assert "Auxiliary evidence deferred" in stderr
    assert "Canonical scan absent" in stderr
