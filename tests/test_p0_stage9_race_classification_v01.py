"""Offline Stage 9 race-result classification tests; no database access."""
import importlib.util
from pathlib import Path
import subprocess
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ops/local/qa_stage9_same_run_concurrency_v01.py"
spec = importlib.util.spec_from_file_location("qa_stage9_same_run", SOURCE)
stage9 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage9)


class Stage9RaceClassificationTests(unittest.TestCase):
    def test_three_successful_workers_keep_receipts(self):
        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                return ({"run_id": "fixture"}, 12.5)

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(len(result), stage9.WORKERS)
        self.assertTrue(all(kind == "PASS" for kind, _ in result))
        self.assertTrue(all(value[0]["run_id"] == "fixture" for _, value in result))

    def test_database_error_is_classified_without_exception_details(self):
        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                raise self.Stop("private SQL must not appear in output")

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(result, [("DB_RPC", None)] * stage9.WORKERS)

    def test_transport_timeout_is_classified(self):
        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                raise subprocess.TimeoutExpired("private command", 1)

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(result, [("TIMEOUT", None)] * stage9.WORKERS)

    def test_invalid_receipt_is_classified(self):
        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                raise ValueError("private malformed response")

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(result, [("RECEIPT", None)] * stage9.WORKERS)

    def test_unexpected_exception_is_fail_closed(self):
        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                raise RuntimeError("private exception")

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(result, [("OTHER", None)] * stage9.WORKERS)


    def test_mixed_worker_failures_are_all_collected_without_leaking_details(self):
        """A failed RPC must not suppress other concurrent worker outcomes."""
        import itertools
        outcomes = itertools.cycle(("success", "database", "timeout"))
        lock = threading.Lock()

        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                with lock:
                    outcome = next(outcomes)
                if outcome == "database":
                    raise self.Stop("private database error text")
                if outcome == "timeout":
                    raise subprocess.TimeoutExpired("private command", 1)
                return ({"run_id": "fixture"}, 3.0)

        result = stage9.bounded_race(Probe(), "disposable", "fixture")
        self.assertEqual(len(result), stage9.WORKERS)
        self.assertCountEqual([kind for kind, _ in result],
                              ["PASS", "DB_RPC", "TIMEOUT"])
        self.assertTrue(all(value is None for kind, value in result
                            if kind != "PASS"))

    def test_barrier_failure_fails_closed_without_entering_rpc(self):
        """A broken start barrier must never permit a database call."""
        original = stage9.threading.Barrier
        calls = []

        class BrokenBarrier:
            def __init__(self, parties, timeout):
                self.parties = parties

            def wait(self, timeout):
                raise threading.BrokenBarrierError()

        class Probe:
            class Stop(Exception):
                pass

            def rpc(self, db, args):
                calls.append(True)
                return ({"run_id": "fixture"}, 1.0)

        try:
            stage9.threading.Barrier = BrokenBarrier
            result = stage9.bounded_race(Probe(), "disposable", "fixture")
        finally:
            stage9.threading.Barrier = original
        self.assertEqual(result, [("BARRIER", None)] * stage9.WORKERS)
        self.assertEqual(calls, [])

    def test_clone_validation_rejects_missing_private_callbacks(self):
        """Never race a clone whose nested trigger topology is incomplete."""
        class Probe:
            def sql(self, db, query):
                if "current_database()" in query:
                    return db
                if "to_regclass" in query or "pg_extension" in query:
                    return "t"
                if "pg_trigger" in query:
                    return "4"
                return "0"

            def counts(self, db, rid):
                raise AssertionError("counts must not be inspected after topology failure")

        with self.assertRaises(stage9.Blocked):
            stage9.verify_clone(Probe(), "disposable", "fixture")

    def test_clone_validation_rejects_existing_run_records(self):
        """A nonempty disposable clone cannot be accepted as a fresh race."""
        class Probe:
            def sql(self, db, query):
                if "current_database()" in query:
                    return db
                if "to_regclass" in query or "pg_extension" in query:
                    return "t"
                if "pg_trigger" in query:
                    return "5"
                return "0"

            def counts(self, db, rid):
                return (1, 0, 0, 0, 0)

        with self.assertRaises(stage9.Blocked):
            stage9.verify_clone(Probe(), "disposable", "fixture")

if __name__ == "__main__":
    unittest.main()
