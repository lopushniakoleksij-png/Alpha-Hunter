"""No-network defensive tests for DBA-only clone workload harness."""
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

    def test_valid_fixture_only(self):
        self.assertEqual(bench.validate_fixture(fixture(),3),
                         "PRIVATE-DISPOSABLE-TEST")

    def test_refuse_enabled_trade(self):
        v=fixture()
        v["p_signals"][0]["trade_permission"]=True
        with self.assertRaises(RuntimeError):
            bench.validate_fixture(v,3)

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
