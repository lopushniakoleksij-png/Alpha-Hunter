from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import production_runner as runner


UTC = timezone.utc


def minimal_report():
    return {
        "production_run_id":
            "prod-health-test",

        "production_version":
            "production-hardening-v1",

        "mode":
            "SHADOW_PRODUCTION",

        "started_at_utc":
            datetime.now(
                UTC
            ).isoformat(),

        "finished_at_utc":
            None,

        "duration_seconds":
            None,

        "overall_status":
            "RUNNING",

        "code_commit":
            "abc123",

        "git_branch":
            "feature/test",

        "pid":
            1234,

        "steps":
            [],

        "invariants": {
            "automatic_trade_execution":
                False,

            "shadow_trade_permission":
                False,
        },
    }


class TestHealthCheckpointPersistence(
    unittest.TestCase
):

    def test_success_is_recorded_locally(self):
        with tempfile.TemporaryDirectory() as tmp:

            run_dir = Path(tmp)

            with (
                patch.object(
                    runner,
                    "RUN_DIRECTORY",
                    run_dir,
                ),
                patch.object(
                    runner,
                    "get_health_client",
                    return_value=(
                        SimpleNamespace(),
                        None,
                    ),
                ),
                patch.object(
                    runner,
                    "safe_persist_report",
                    return_value=(
                        True,
                        None,
                    ),
                ) as mocked_persist,
            ):
                report = minimal_report()

                path = runner.save_report(
                    report
                )

            self.assertTrue(
                path.exists()
            )

            stored = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            health = stored[
                "health_persistence"
            ]

            self.assertTrue(
                health["configured"]
            )

            self.assertEqual(
                health["attempts"],
                1,
            )

            self.assertTrue(
                health["last_success"]
            )

            self.assertIsNone(
                health["last_error"]
            )

            mocked_persist.assert_called_once()

    def test_supabase_failure_is_nonfatal_and_local_survives(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:

            run_dir = Path(tmp)

            with (
                patch.object(
                    runner,
                    "RUN_DIRECTORY",
                    run_dir,
                ),
                patch.object(
                    runner,
                    "get_health_client",
                    return_value=(
                        SimpleNamespace(),
                        None,
                    ),
                ),
                patch.object(
                    runner,
                    "safe_persist_report",
                    return_value=(
                        False,
                        "database unavailable",
                    ),
                ),
            ):
                report = minimal_report()

                path = runner.save_report(
                    report
                )

            self.assertTrue(
                path.exists()
            )

            stored = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            health = stored[
                "health_persistence"
            ]

            self.assertTrue(
                health["configured"]
            )

            self.assertFalse(
                health["last_success"]
            )

            self.assertEqual(
                health["last_error"],
                "database unavailable",
            )

            self.assertEqual(
                stored["overall_status"],
                "RUNNING",
            )

    def test_client_setup_failure_is_nonfatal(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:

            run_dir = Path(tmp)

            with (
                patch.object(
                    runner,
                    "RUN_DIRECTORY",
                    run_dir,
                ),
                patch.object(
                    runner,
                    "get_health_client",
                    return_value=(
                        None,
                        "credential loader failed",
                    ),
                ),
                patch.object(
                    runner,
                    "safe_persist_report",
                ) as mocked_persist,
            ):
                report = minimal_report()

                path = runner.save_report(
                    report
                )

            stored = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            health = stored[
                "health_persistence"
            ]

            self.assertFalse(
                health["configured"]
            )

            self.assertFalse(
                health["last_success"]
            )

            self.assertEqual(
                health["last_error"],
                "credential loader failed",
            )

            mocked_persist.assert_not_called()


class TestPipelineIsolationFromHealthFailure(
    unittest.TestCase
):

    def test_health_database_failure_cannot_fail_pipeline(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:

            run_dir = Path(tmp)

            def fake_run_step(
                step,
                *,
                production_run_id,
            ):
                now = datetime.now(
                    UTC
                ).isoformat()

                return {
                    "name":
                        step.name,

                    "script":
                        step.script,

                    "status":
                        "PASS",

                    "exit_code":
                        0,

                    "timeout_seconds":
                        step.timeout_seconds,

                    "started_at_utc":
                        now,

                    "finished_at_utc":
                        now,

                    "duration_seconds":
                        0.01,

                    "error":
                        None,
                }

            now = runner.now_utc().isoformat()


            with (
                patch.object(
                    runner,
                    "RUN_DIRECTORY",
                    run_dir,
                ),
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
                    return_value=(
                        {
                            "name":
                                (
                                    "STEP 1C — PRODUCTION "
                                    "DATA GUARDRAILS"
                                ),
                            "script":
                                "production_guardrails.py",
                            "status":
                                "PASS",
                            "exit_code":
                                0,
                            "timeout_seconds":
                                120,
                            "started_at_utc":
                                now,
                            "finished_at_utc":
                                now,
                            "duration_seconds":
                                0.01,
                            "error":
                                None,
                            "guardrail_status":
                                "PASS",
                            "snapshot_path":
                                "/tmp/test-snapshot.json",
                        },
                        {
                            "status":
                                "PASS",
                            "checked_at_utc":
                                now,
                            "snapshot_path":
                                "/tmp/test-snapshot.json",
                            "scan_run_id":
                                "test-production-run",
                            "checks": [
                                {
                                    "name":
                                        name,
                                    "status":
                                        "PASS",
                                    "critical":
                                        True,
                                    "detail":
                                        "test",
                                    "metrics":
                                        {},
                                }
                                for name in [
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
                            ],
                            "metrics":
                                {},
                        },
                    ),
                ),
                patch.object(
                    runner,
                    "get_health_client",
                    return_value=(
                        SimpleNamespace(),
                        None,
                    ),
                ),
                patch.object(
                    runner,
                    "safe_persist_report",
                    return_value=(
                        False,
                        "simulated Supabase outage",
                    ),
                ),
            ):
                exit_code = (
                    runner.main()
                )

            self.assertEqual(
                exit_code,
                0,
            )

            reports = list(
                run_dir.glob(
                    "*.json"
                )
            )

            self.assertEqual(
                len(reports),
                1,
            )

            final_report = (
                json.loads(
                    reports[0]
                    .read_text(
                        encoding="utf-8"
                    )
                )
            )

            self.assertEqual(
                final_report[
                    "overall_status"
                ],
                "PASS",
            )

            health = final_report[
                "health_persistence"
            ]

            self.assertFalse(
                health[
                    "last_success"
                ]
            )

            self.assertEqual(
                health[
                    "last_error"
                ],
                "simulated Supabase outage",
            )

            self.assertFalse(
                final_report[
                    "invariants"
                ][
                    "automatic_trade_execution"
                ]
            )

            self.assertFalse(
                final_report[
                    "invariants"
                ][
                    "shadow_trade_permission"
                ]
            )


if __name__ == "__main__":
    unittest.main()
