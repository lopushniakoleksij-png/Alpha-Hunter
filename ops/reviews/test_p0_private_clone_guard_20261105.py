"""No-network defensive tests for DBA-only clone workload harness."""
import ast
import subprocess
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
spec = importlib.util.spec_from_file_location(
    "p0_private_bench",ROOT/"p0_private_clone_actual_trigger_benchmark_20261105.py"
)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def fixture(size=3):
    run_id = "PRIVATE-DISPOSABLE-TEST"
    parent = {"run_id":run_id,"symbol_count":size,"payload":{"run_id":run_id}}
    groups = {}
    for name in bench.GROUPS[1:]:
        groups[name] = [
            {"run_id":run_id,"symbol":f"TEST{i:03d}USDT",
             "trade_permission":False,"signal_id":f"SIG{i:03d}"}
            for i in range(size)
        ]
    return {"p_parent":parent,**groups}


class PrivateCloneGuardTests(unittest.TestCase):
    def test_percentiles(self):
        self.assertEqual(bench.percentile([1,2,3,4],50),2.5)
        self.assertEqual(bench.percentile([1,2,3,4],95),3.85)
        self.assertEqual(bench.percentile([1,2,3,4],99),3.97)

    def test_atomic_readiness_timestamp_matches_live_column_default(self):
        """Static parity guard; NOT a substitute for exact-clone SQL execution."""
        source = (
            ROOT.parent.parent
            / "research"
            / "p0_successor_atomic_canonical_v03_PRODUCTION_SCHEMA_REVIEW_ONLY.sql"
        ).read_text(encoding="utf-8")
        readiness_section = source.split("INTO v_features_normalized", 1)[1].split(
            "INTO v_readiness_normalized", 1
        )[0]
        self.assertIn("'v7_trade_ready', false, 'created_at', clock_timestamp()", readiness_section)
        self.assertNotIn("'v7_trade_ready', false, 'created_at', now()", readiness_section)
        self.assertIn("SECURITY INVOKER", source)
        self.assertIn("REVOKE ALL ON FUNCTION", source)

    def test_valid_fixture_only(self):
        self.assertEqual(bench.validate_fixture(fixture(),3),
                         "PRIVATE-DISPOSABLE-TEST")

    def test_refuse_enabled_trade(self):
        v=fixture()
        v["p_signals"][0]["trade_permission"]=True
        with self.assertRaises(RuntimeError):
            bench.validate_fixture(v,3)

    def test_refuse_mismatched_or_duplicate_signal_ids(self):
        v=fixture()
        v["p_features"][0]["signal_id"]="NON_MATCHING"
        with self.assertRaisesRegex(RuntimeError,"signal IDs"):
            bench.validate_fixture(v,3)
        v=fixture()
        v["p_signals"][1]["signal_id"]=v["p_signals"][0]["signal_id"]
        with self.assertRaisesRegex(RuntimeError,"signal IDs"):
            bench.validate_fixture(v,3)
        v=fixture()
        del v["p_signals"][0]["signal_id"]
        with self.assertRaisesRegex(RuntimeError,"signal_id"):
            bench.validate_fixture(v,3)

    def test_reject_swapped_signal_ids_even_when_the_id_sets_match(self):
        sample = fixture()
        a = sample["p_features"][0]["signal_id"]
        b = sample["p_features"][1]["signal_id"]
        sample["p_features"][0]["signal_id"] = b
        sample["p_features"][1]["signal_id"] = a
        with self.assertRaisesRegex(RuntimeError, "signal IDs"):
            bench.validate_fixture(sample, 3)

    def test_transaction_write_destination_manifest_covers_candidate_graph(self):
        allowed = bench.declared_write_destinations()
        self.assertGreaterEqual(len(allowed), 20)
        self.assertTrue(all("public." + table in allowed for table in bench.STAGES))
        self.assertTrue(all("private." + table in allowed for table in bench.PAPER))

    def test_transaction_write_footprint_accepts_declared_tables(self):
        records = [
            ("public", name, 61 if name != bench.STAGES[0] else 1, 0, 0)
            for name in bench.STAGES
        ]
        records.append(("private", bench.PAPER[0], 4, 0, 0))
        observed = bench.verify_transaction_write_destinations(records)
        self.assertEqual(set(observed), {
            *("public." + name for name in bench.STAGES),
            "private." + bench.PAPER[0],
        })
        self.assertEqual(observed["private." + bench.PAPER[0]]["inserted"], 4)

    def test_transaction_write_footprint_blocks_undeclared_side_effect(self):
        records = [
            ("public", name, 1, 0, 0) for name in bench.STAGES
        ]
        records.append(("private", "alpha_hunter_undocumented_order_table", 1, 0, 0))
        with self.assertRaisesRegex(RuntimeError, "Undeclared transitive write"):
            bench.verify_transaction_write_destinations(records)

    def test_transaction_write_footprint_blocks_missing_canonical_stage(self):
        records = [
            ("public", name, 1, 0, 0) for name in bench.STAGES[:-1]
        ]
        with self.assertRaisesRegex(RuntimeError, "Five canonical publication stages"):
            bench.verify_transaction_write_destinations(records)

    def test_transaction_write_footprint_rejects_negative_counters(self):
        records = [
            ("public", name, 1, 0, 0) for name in bench.STAGES
        ]
        records[0] = ("public", bench.STAGES[0], -1, 0, 0)
        with self.assertRaisesRegex(RuntimeError, "Invalid transaction"):
            bench.verify_transaction_write_destinations(records)

    def test_refuse_inconsistent_stage_symbol_sets(self):
        v=fixture()
        v["p_children"][0]["symbol"]="MISMATCHUSDT"
        with self.assertRaises(RuntimeError):
            bench.validate_fixture(v,3)

    def test_refuse_unsafe_parent_and_partial_groups(self):
        v=fixture()
        v["p_parent"]["payload"]["_canonical_publication_state"]="VERIFIED"
        with self.assertRaises(RuntimeError):
            bench.validate_fixture(v,3)
        v=fixture()
        v["p_readiness"].pop()
        with self.assertRaises(RuntimeError):
            bench.validate_fixture(v,3)

    def test_wrong_postgresql_major_refused_before_any_writes(self):
        class FakeCursor:
            def __init__(self,value):
                self.value=value
            def fetchone(self):
                return (self.value,)
        class FakeWrongVersion:
            def execute(self,query,params=None):
                q=str(query)
                if "SHOW session_replication_role" in q:
                    return FakeCursor("origin")
                if "SELECT current_database()" in q:
                    return FakeCursor("isolated_research")
                if "SHOW server_version_num" in q:
                    return FakeCursor(180000)
                raise AssertionError("Unexpected operation after version rejection")
        with self.assertRaisesRegex(RuntimeError,"major version 17"):
            bench.check_clone_preflight(FakeWrongVersion(),{})

    def test_missing_clone_only_sentinel_fails_before_any_writes(self):
        class SafeCursor:
            def __init__(self, value):
                self.value = value

            def fetchone(self):
                return (self.value,)

        class FakeReadonlyClone:
            def execute(self, query, params=None):
                value = str(query)
                if "SHOW session_replication_role" in value:
                    return SafeCursor("origin")
                if "SELECT current_database()" in value:
                    return SafeCursor("isolated_research")
                if "SHOW server_version_num" in value:
                    return SafeCursor(170000)
                if "to_regclass('ah_p0_isolated.clone_attestation')" in value:
                    return SafeCursor(None)
                raise AssertionError("Unexpected SQL past missing-sentinel gate")
        with self.assertRaisesRegex(RuntimeError,"sentinel absent"):
            bench.check_clone_preflight(FakeReadonlyClone(),{})

    def test_no_assert_statements_in_dba_benchmark(self):
        # All authorization, measured-count and rollback guards must execute
        # even if a reviewer mistakenly runs Python with -O / PYTHONOPTIMIZE.
        filename = ROOT/"p0_private_clone_actual_trigger_benchmark_20261105.py"
        tree = ast.parse(filename.read_text(encoding="utf-8"))
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.Assert)])

    def test_runtime_safety_guard_active_under_python_optimize(self):
        run = subprocess.run(
            [sys.executable,"-O","-c",
             "from p0_private_clone_actual_trigger_benchmark_20261105 import require; "
             "require(False,'optimisation guard remains active')"],
            cwd=ROOT, capture_output=True,text=True,check=False,timeout=15)
        self.assertNotEqual(run.returncode,0)
        self.assertIn("optimisation guard remains active",run.stderr)

    def test_refuse_missing_approval_before_any_connection(self):
        with patch.dict(os.environ,{
            "AH_P0_PRIVATE_CLONE_APPROVED":"",
            "AH_P0_EGRESS_BLOCKED":"",
            "AH_P0_LOCAL_POSTGREST_ONLY":"",
        }):
            with self.assertRaises(RuntimeError):
                bench.gate()

    def test_refuse_broad_permissions_and_path_inside_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            p.chmod(0o755)
            with self.assertRaises(RuntimeError):
                bench.private_dir(str(p),require_permissions=True)
            p.chmod(0o700)
            self.assertEqual(bench.private_dir(str(p),require_permissions=True),p)

    def test_refuse_world_readable_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            folder.chmod(0o700)
            for size in bench.SIZES:
                data=fixture(size)
                data["p_parent"]["run_id"]=f"PRIVATE-DISPOSABLE-{size}"
                data["p_parent"]["payload"]["run_id"]=f"PRIVATE-DISPOSABLE-{size}"
                for group in bench.GROUPS[1:]:
                    for item in data[group]:
                        item["run_id"]=f"PRIVATE-DISPOSABLE-{size}"
                p=folder/f"sanitized_{size}.json"
                p.write_text(__import__("json").dumps(data))
                p.chmod(0o600)
            values=bench.load_private_fixtures(folder)
            self.assertEqual(len(values[61]["p_children"]),61)
            (folder/"sanitized_61.json").chmod(0o644)
            with self.assertRaises(RuntimeError):
                bench.load_private_fixtures(folder)


if __name__=="__main__":
    unittest.main()
