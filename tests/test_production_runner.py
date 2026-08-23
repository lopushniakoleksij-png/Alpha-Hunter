from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import production_runner as runner


UTC = timezone.utc


class TestProductionLock(unittest.TestCase):

    def test_active_lock_blocks_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "production.lock"

            with patch.object(
                runner,
                "LOCK_PATH",
                lock_path,
            ):
                acquired, pid = runner.acquire_lock(
                    "run-1",
                    datetime.now(UTC),
                )

                self.assertTrue(acquired)
                self.assertIsNone(pid)

                acquired_again, existing_pid = (
                    runner.acquire_lock(
                        "run-2",
                        datetime.now(UTC),
                    )
                )

                self.assertFalse(
                    acquired_again
                )

                self.assertEqual(
                    existing_pid,
                    os.getpid(),
                )

                runner.release_lock()

                self.assertFalse(
                    lock_path.exists()
                )

    def test_stale_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "production.lock"

            lock_path.write_text(
                json.dumps(
                    {
                        "pid": 99999999,
                        "run_id": "stale",
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(
                    runner,
                    "LOCK_PATH",
                    lock_path,
                ),
                patch.object(
                    runner,
                    "process_is_alive",
                    return_value=False,
                ),
            ):
                acquired, existing_pid = (
                    runner.acquire_lock(
                        "run-new",
                        datetime.now(UTC),
                    )
                )

                self.assertTrue(acquired)
                self.assertIsNone(
                    existing_pid
                )

                payload = json.loads(
                    lock_path.read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(
                    payload["run_id"],
                    "run-new",
                )

                self.assertEqual(
                    payload["pid"],
                    os.getpid(),
                )

                runner.release_lock()


class TestProductionStepExecution(
    unittest.TestCase
):

    def test_successful_step_passes(self):
        step = runner.Step(
            "TEST STEP",
            "fake.py",
            30,
        )

        with patch.object(
            runner.subprocess,
            "run",
            return_value=
                SimpleNamespace(
                    returncode=0
                ),
        ) as mocked:

            result = runner.run_step(
                step,
                production_run_id=
                    "prod-123",
            )

        self.assertEqual(
            result["status"],
            "PASS",
        )

        self.assertEqual(
            result["exit_code"],
            0,
        )

        kwargs = mocked.call_args.kwargs

        self.assertEqual(
            kwargs["timeout"],
            30,
        )

        self.assertEqual(
            kwargs["env"][
                "ALPHA_HUNTER_PRODUCTION_RUN_ID"
            ],
            "prod-123",
        )

        self.assertEqual(
            kwargs["env"][
                "ALPHA_HUNTER_PRODUCTION_VERSION"
            ],
            runner.PRODUCTION_VERSION,
        )

    def test_nonzero_step_fails(self):
        step = runner.Step(
            "TEST STEP",
            "fake.py",
            30,
        )

        with patch.object(
            runner.subprocess,
            "run",
            return_value=
                SimpleNamespace(
                    returncode=7
                ),
        ):
            result = runner.run_step(
                step,
                production_run_id=
                    "prod-123",
            )

        self.assertEqual(
            result["status"],
            "FAILED",
        )

        self.assertEqual(
            result["exit_code"],
            7,
        )

    def test_timeout_is_explicit(self):
        step = runner.Step(
            "TEST STEP",
            "fake.py",
            30,
        )

        with patch.object(
            runner.subprocess,
            "run",
            side_effect=
                subprocess.TimeoutExpired(
                    cmd=["python", "fake.py"],
                    timeout=30,
                ),
        ):
            result = runner.run_step(
                step,
                production_run_id=
                    "prod-123",
            )

        self.assertEqual(
            result["status"],
            "TIMEOUT",
        )

        self.assertEqual(
            result["exit_code"],
            124,
        )

        self.assertIn(
            "30s",
            result["error"],
        )


class TestProductionPipeline(
    unittest.TestCase
):

    def run_main_with_statuses(
        self,
        status_by_script,
        *,
        guardrail_status="PASS",
        guardrail_ledger_trustworthy=True,
    ):
        calls = []
        saved_reports = []

        def fake_run_step(
            step,
            *,
            production_run_id,
        ):
            calls.append(
                step.script
            )

            status = (
                status_by_script.get(
                    step.script,
                    "PASS",
                )
            )

            return {
                "name": step.name,
                "script": step.script,
                "status": status,
                "exit_code":
                    0
                    if status == "PASS"
                    else 1,
                "timeout_seconds":
                    step.timeout_seconds,
                "started_at_utc":
                    datetime.now(
                        UTC
                    ).isoformat(),
                "finished_at_utc":
                    datetime.now(
                        UTC
                    ).isoformat(),
                "duration_seconds":
                    0.01,
                "error":
                    None
                    if status == "PASS"
                    else "test failure",
            }

        def fake_run_guardrail_step(
            step,
            *,
            production_run_id,
        ):
            calls.append(
                step.script
            )

            required_names = [
                "universe_ledger_presence",
                "universe_ledger_coverage",
                "universe_symbol_uniqueness",
                "universe_hour_bucket",
                "ledger_selection_context",
                "ledger_freshness",
                "ledger_source",
                "ledger_measurement_quality",
                "v79_trade_permission",
            ]

            checks = []

            for name in required_names:
                status = "PASS"

                if (
                    not guardrail_ledger_trustworthy
                    and name
                    == "universe_ledger_coverage"
                ):
                    status = "FAIL"

                checks.append(
                    {
                        "name": name,
                        "status": status,
                        "critical": True,
                        "detail": "test",
                        "metrics": {},
                    }
                )

            guardrail_result = {
                "status":
                    guardrail_status,
                "checked_at_utc":
                    datetime.now(
                        UTC
                    ).isoformat(),
                "snapshot_path":
                    "/tmp/test-snapshot.json",
                "scan_run_id":
                    production_run_id,
                "checks":
                    checks,
                "metrics":
                    {},
            }

            step_status = (
                "PASS"
                if guardrail_status
                in {
                    "PASS",
                    "DEGRADED",
                }
                else "FAILED"
            )

            result = {
                "name": step.name,
                "script": step.script,
                "status": step_status,
                "exit_code":
                    0
                    if step_status == "PASS"
                    else 1,
                "timeout_seconds":
                    step.timeout_seconds,
                "started_at_utc":
                    datetime.now(
                        UTC
                    ).isoformat(),
                "finished_at_utc":
                    datetime.now(
                        UTC
                    ).isoformat(),
                "duration_seconds":
                    0.01,
                "error":
                    None
                    if step_status == "PASS"
                    else (
                        "guardrail_status="
                        f"{guardrail_status}"
                    ),
                "guardrail_status":
                    guardrail_status,
                "snapshot_path":
                    "/tmp/test-snapshot.json",
            }

            return (
                result,
                guardrail_result,
            )

        def fake_save_report(
            report,
        ):
            saved_reports.append(
                json.loads(
                    json.dumps(
                        report
                    )
                )
            )

            return Path(
                "/tmp/test-production.json"
            )

        with (
            patch.object(
                runner,
                "acquire_lock",
                return_value=(
                    True,
                    None,
                ),
            ),
            patch.object(
                runner,
                "release_lock",
            ),
            patch.object(
                runner,
                "git_value",
                side_effect=[
                    "abc123",
                    "feature/test",
                ],
            ),
            patch.object(
                runner,
                "run_step",
                side_effect=
                    fake_run_step,
            ),
            patch.object(
                runner,
                "run_guardrail_step",
                side_effect=
                    fake_run_guardrail_step,
            ),
            patch.object(
                runner,
                "save_report",
                side_effect=
                    fake_save_report,
            ),
        ):
            exit_code = runner.main()

        return (
            exit_code,
            calls,
            saved_reports[-1],
        )

    def test_guardrail_runs_before_model_chain(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {}
            )
        )

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            calls[:5],
            [
                "run.py",
                "v79_universe_hourly_collector.py",
                "production_guardrails.py",
                "v710_money_queue_forward_ledger.py",
                "v74_tracking_job.py",
            ],
        )

        self.assertEqual(
            report["guardrail"]["status"],
            "PASS",
        )

    def test_guardrail_degraded_continues_pipeline(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {},
                guardrail_status=
                    "DEGRADED",
            )
        )

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            report["overall_status"],
            "DEGRADED",
        )

        self.assertEqual(
            report["guardrail"]["status"],
            "DEGRADED",
        )

        self.assertIn(
            "v74_tracking_job.py",
            calls,
        )

        self.assertIn(
            "v79_missed_mover_recall_auditor.py",
            calls,
        )

    def test_guardrail_fail_blocks_models_but_preserves_trusted_audit(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {},
                guardrail_status=
                    "FAIL",
                guardrail_ledger_trustworthy=
                    True,
            )
        )

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertEqual(
            report["overall_status"],
            "FAILED",
        )

        self.assertNotIn(
            "v74_tracking_job.py",
            calls,
        )

        self.assertIn(
            "v79_missed_mover_recall_auditor.py",
            calls,
        )

        model_rows = [
            row
            for row in report["steps"]
            if row["script"]
            == "v74_tracking_job.py"
        ]

        self.assertEqual(
            model_rows[0]["status"],
            "SKIPPED",
        )

        self.assertEqual(
            model_rows[0]["error"],
            "DATA_GUARDRAIL_FAILED",
        )

    def test_untrustworthy_ledger_blocks_recall_audit(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {},
                guardrail_status=
                    "FAIL",
                guardrail_ledger_trustworthy=
                    False,
            )
        )

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertNotIn(
            "v79_missed_mover_recall_auditor.py",
            calls,
        )

        audit_rows = [
            row
            for row in report["steps"]
            if row["script"]
            == "v79_missed_mover_recall_auditor.py"
        ]

        self.assertEqual(
            audit_rows[0]["status"],
            "SKIPPED",
        )

        self.assertEqual(
            audit_rows[0]["error"],
            "UNTRUSTWORTHY_UNIVERSE_LEDGER",
        )

    def test_universe_ledger_runs_immediately_after_scan(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {}
            )
        )

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            calls[0],
            "run.py",
        )

        self.assertEqual(
            calls[1],
            "v79_universe_hourly_collector.py",
        )

        self.assertEqual(
            report["overall_status"],
            "PASS",
        )

    def test_money_queue_failure_is_non_blocking(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {
                    "v710_money_queue_forward_ledger.py":
                        "FAILED",
                }
            )
        )

        self.assertEqual(
            exit_code,
            0,
        )

        self.assertEqual(
            report["overall_status"],
            "PASS",
        )

        self.assertIn(
            "v710_early_execution_rr_shadow.py",
            calls,
        )

        rows = [
            row
            for row in report["steps"]
            if row["script"]
            == "v710_money_queue_forward_ledger.py"
        ]

        self.assertEqual(
            len(rows),
            1,
        )

        self.assertEqual(
            rows[0]["status"],
            "FAILED",
        )

        self.assertTrue(
            rows[0]["non_blocking"]
        )


    def test_model_failure_does_not_lose_final_audit(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {
                    "v76_direction_shadow.py":
                        "FAILED",
                }
            )
        )

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertIn(
            "v79_universe_hourly_collector.py",
            calls,
        )

        self.assertIn(
            "v79_missed_mover_recall_auditor.py",
            calls,
        )

        self.assertEqual(
            report["overall_status"],
            "FAILED",
        )

        step_status = {
            row["script"]:
                row["status"]
            for row in report["steps"]
        }

        self.assertEqual(
            step_status[
                "v76_direction_shadow.py"
            ],
            "FAILED",
        )

        self.assertEqual(
            step_status[
                "v76_post_confirmation_tracker.py"
            ],
            "SKIPPED",
        )

        self.assertEqual(
            step_status[
                "v79_missed_mover_recall_auditor.py"
            ],
            "PASS",
        )

    def test_ledger_failure_blocks_recall_audit(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {
                    "v79_universe_hourly_collector.py":
                        "FAILED",
                }
            )
        )

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertNotIn(
            "v79_missed_mover_recall_auditor.py",
            calls,
        )

        audit_rows = [
            row
            for row in report["steps"]
            if row["script"]
            == "v79_missed_mover_recall_auditor.py"
        ]

        self.assertEqual(
            len(audit_rows),
            1,
        )

        self.assertEqual(
            audit_rows[0]["status"],
            "SKIPPED",
        )

        self.assertEqual(
            audit_rows[0]["error"],
            "UNIVERSE_LEDGER_NOT_CAPTURED",
        )

    def test_live_scan_failure_stops_dependent_pipeline(
        self,
    ):
        exit_code, calls, report = (
            self.run_main_with_statuses(
                {
                    "run.py":
                        "FAILED",
                }
            )
        )

        self.assertEqual(
            exit_code,
            1,
        )

        self.assertEqual(
            calls,
            [
                "run.py",
            ],
        )

        statuses = [
            row["status"]
            for row in report["steps"]
        ]

        self.assertEqual(
            statuses[0],
            "FAILED",
        )

        self.assertTrue(
            all(
                status == "SKIPPED"
                for status
                in statuses[1:]
            )
        )

    def test_shadow_invariants_are_frozen(
        self,
    ):
        _, _, report = (
            self.run_main_with_statuses(
                {}
            )
        )

        self.assertFalse(
            report["invariants"][
                "automatic_trade_execution"
            ]
        )

        self.assertFalse(
            report["invariants"][
                "shadow_trade_permission"
            ]
        )


class TestProductionSnapshotBinding(
    unittest.TestCase
):

    def test_exact_production_run_snapshot_is_selected(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            snapshots = (
                root
                / "data"
                / "snapshots"
            )

            snapshots.mkdir(
                parents=True
            )

            (
                snapshots
                / "latest.json"
            ).write_text(
                json.dumps(
                    {
                        "production_run_id":
                            "other-run",
                    }
                ),
                encoding="utf-8",
            )

            target = (
                snapshots
                / "snapshot-target.json"
            )

            target.write_text(
                json.dumps(
                    {
                        "production_run_id":
                            "prod-123",
                    }
                ),
                encoding="utf-8",
            )

            (
                snapshots
                / "snapshot-other.json"
            ).write_text(
                json.dumps(
                    {
                        "production_run_id":
                            "prod-999",
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(
                runner,
                "ROOT",
                root,
            ):
                result = (
                    runner
                    .find_production_snapshot(
                        "prod-123"
                    )
                )

            self.assertEqual(
                result,
                target,
            )


class TestProductionOverlapMain(
    unittest.TestCase
):

    def test_main_returns_three_when_locked(
        self,
    ):
        with (
            patch.object(
                runner,
                "acquire_lock",
                return_value=(
                    False,
                    12345,
                ),
            ),
            patch.object(
                runner,
                "run_step",
            ) as mocked_run,
        ):
            result = runner.main()

        self.assertEqual(
            result,
            3,
        )

        mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
