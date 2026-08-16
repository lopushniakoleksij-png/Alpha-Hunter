from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import production_health as health


def sample_report():
    return {
        "production_run_id": "prod-123",
        "production_version":
            "production-hardening-v1",
        "mode": "SHADOW_PRODUCTION",
        "started_at_utc":
            "2026-08-15T20:00:00+00:00",
        "finished_at_utc":
            "2026-08-15T20:02:30+00:00",
        "duration_seconds": 150.0,
        "overall_status": "PASS",
        "code_commit": "abc123",
        "git_branch":
            "feature/production-hardening-v1",
        "pid": 1234,
        "invariants": {
            "automatic_trade_execution":
                False,
            "shadow_trade_permission":
                False,
        },
        "steps": [
            {
                "name": "STEP 1",
                "script": "run.py",
                "status": "PASS",
                "exit_code": 0,
                "timeout_seconds": 300,
                "started_at_utc":
                    "2026-08-15T20:00:00+00:00",
                "finished_at_utc":
                    "2026-08-15T20:01:00+00:00",
                "duration_seconds": 60.0,
                "error": None,
            },
            {
                "name": "STEP 2",
                "script": "two.py",
                "status": "FAILED",
                "exit_code": 7,
                "timeout_seconds": 120,
                "started_at_utc":
                    "2026-08-15T20:01:00+00:00",
                "finished_at_utc":
                    "2026-08-15T20:01:10+00:00",
                "duration_seconds": 10.0,
                "error": "exit_code=7",
            },
            {
                "name": "STEP 3",
                "script": "three.py",
                "status": "TIMEOUT",
                "exit_code": 124,
                "timeout_seconds": 120,
                "started_at_utc":
                    "2026-08-15T20:01:10+00:00",
                "finished_at_utc":
                    "2026-08-15T20:03:10+00:00",
                "duration_seconds": 120.0,
                "error": "timeout",
            },
            {
                "name": "STEP 4",
                "script": "four.py",
                "status": "SKIPPED",
                "exit_code": None,
                "timeout_seconds": 120,
                "started_at_utc":
                    "2026-08-15T20:03:10+00:00",
                "finished_at_utc":
                    "2026-08-15T20:03:10+00:00",
                "duration_seconds": 0.0,
                "error": "upstream failed",
            },
        ],
    }


class TestStatusCounts(unittest.TestCase):

    def test_all_statuses_are_counted(self):
        counts = health.status_counts(
            sample_report()
        )

        self.assertEqual(
            counts["step_count"],
            4,
        )

        self.assertEqual(
            counts["passed_steps"],
            1,
        )

        self.assertEqual(
            counts["failed_steps"],
            1,
        )

        self.assertEqual(
            counts["timeout_steps"],
            1,
        )

        self.assertEqual(
            counts["skipped_steps"],
            1,
        )


class TestRunRow(unittest.TestCase):

    def test_run_row_contains_health_summary(self):
        row = health.build_run_row(
            sample_report()
        )

        self.assertEqual(
            row["production_run_id"],
            "prod-123",
        )

        self.assertEqual(
            row["overall_status"],
            "PASS",
        )

        self.assertEqual(
            row["step_count"],
            4,
        )

        self.assertFalse(
            row["automatic_trade_execution"]
        )

        self.assertFalse(
            row["shadow_trade_permission"]
        )

        self.assertEqual(
            row["payload"][
                "production_run_id"
            ],
            "prod-123",
        )

    def test_shadow_flags_are_not_invented_true(self):
        report = sample_report()
        report["invariants"] = {}

        row = health.build_run_row(
            report
        )

        self.assertFalse(
            row["automatic_trade_execution"]
        )

        self.assertFalse(
            row["shadow_trade_permission"]
        )


class TestStepRows(unittest.TestCase):

    def test_step_order_is_stable(self):
        rows = health.build_step_rows(
            sample_report()
        )

        self.assertEqual(
            len(rows),
            4,
        )

        self.assertEqual(
            [
                row["step_order"]
                for row in rows
            ],
            [1, 2, 3, 4],
        )

        self.assertEqual(
            rows[0][
                "production_run_id"
            ],
            "prod-123",
        )

        self.assertEqual(
            rows[1]["status"],
            "FAILED",
        )


class TestClientUpsert(unittest.TestCase):

    def client(self):
        return health.ProductionHealthClient(
            url="https://example.supabase.co",
            key="SECRET_TEST_KEY",
            timeout_seconds=9,
        )

    def test_successful_upsert(self):
        response = SimpleNamespace(
            status_code=204,
            text="",
        )

        with patch.object(
            health.requests,
            "post",
            return_value=response,
        ) as mocked:
            self.client().upsert(
                "test_table",
                [{"id": 1}],
                on_conflict="id",
            )

        kwargs = mocked.call_args.kwargs

        self.assertEqual(
            kwargs["params"][
                "on_conflict"
            ],
            "id",
        )

        self.assertEqual(
            kwargs["timeout"],
            9,
        )

        self.assertEqual(
            kwargs["headers"]["apikey"],
            "SECRET_TEST_KEY",
        )

    def test_failed_upsert_raises(self):
        response = SimpleNamespace(
            status_code=500,
            text="database unavailable",
        )

        with patch.object(
            health.requests,
            "post",
            return_value=response,
        ):
            with self.assertRaises(
                health.ProductionHealthError
            ):
                self.client().upsert(
                    "test_table",
                    [{"id": 1}],
                    on_conflict="id",
                )


class TestPersistence(unittest.TestCase):

    def test_persist_writes_run_before_steps(self):
        client = SimpleNamespace()
        calls = []

        def fake_upsert(
            table,
            rows,
            *,
            on_conflict,
        ):
            calls.append(
                (
                    table,
                    on_conflict,
                    len(rows),
                )
            )

        client.upsert = fake_upsert

        health.persist_report(
            client,
            sample_report(),
        )

        self.assertEqual(
            calls[0][0],
            health.RUN_TABLE,
        )

        self.assertEqual(
            calls[0][1],
            "production_run_id",
        )

        self.assertEqual(
            calls[1][0],
            health.STEP_TABLE,
        )

        self.assertEqual(
            calls[1][1],
            (
                "production_run_id,"
                "step_order"
            ),
        )

    def test_not_configured_is_nonfatal(self):
        ok, error = (
            health.safe_persist_report(
                None,
                sample_report(),
            )
        )

        self.assertFalse(ok)

        self.assertEqual(
            error,
            "NOT_CONFIGURED",
        )

    def test_supabase_failure_is_nonfatal(self):
        client = SimpleNamespace()

        with patch.object(
            health,
            "persist_report",
            side_effect=
                RuntimeError(
                    "network down"
                ),
        ):
            ok, error = (
                health.safe_persist_report(
                    client,
                    sample_report(),
                )
            )

        self.assertFalse(ok)

        self.assertIn(
            "network down",
            error,
        )

    def test_success_is_reported(self):
        client = SimpleNamespace()

        with patch.object(
            health,
            "persist_report",
        ):
            ok, error = (
                health.safe_persist_report(
                    client,
                    sample_report(),
                )
            )

        self.assertTrue(ok)
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
