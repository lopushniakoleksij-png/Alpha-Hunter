"""Static safety checks for private Stage 7 QA scripts; never execute private DB work."""
import ast
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "ops/local/qa_stage7_committed_disposable_61_v01.py",
    "ops/local/qa_stage7_61_rpc_rollback_benchmark_v01.py",
)


class Stage7PrivateScriptSyntaxTests(unittest.TestCase):
    def test_private_scripts_parse_without_execution(self):
        for relative in SCRIPTS:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                ast.parse(source, filename=relative)

    def test_only_one_entrypoint_and_private_environment_guard(self):
        for relative in SCRIPTS:
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
                entrypoints = [node for node in tree.body
                               if isinstance(node, ast.If)
                               and isinstance(node.test, ast.Compare)
                               and isinstance(node.test.left, ast.Name)
                               and node.test.left.id == "__name__"]
                self.assertEqual(len(entrypoints), 1)
                self.assertIn("CODESPACES", source)
                self.assertIn("GITHUB_ACTIONS", source)
                self.assertIn("NetworkMode", source)


    def test_pg_cron_restore_toc_filter_is_targeted(self):
        path = ROOT / "ops/local/qa_stage7_committed_disposable_61_v01.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef)
                  and node.name == "excluded_pg_cron_toc")
        # Compile only the pure classifier: no private DB or Docker execution.
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        scope = {"re": re}
        exec(compile(module, str(path), "exec"), scope)
        excluded = scope["excluded_pg_cron_toc"]
        cron_owned = (
            "2; 3079 16672 EXTENSION - pg_cron",
            "9660; 0 0 COMMENT - EXTENSION pg_cron",
            "9661; 0 0 ACL - SCHEMA cron supabase_admin",
            "9672; 0 0 ACL cron FUNCTION alter_job(jobid bigint) supabase_admin",
            "9720; 0 0 ACL cron TABLE job supabase_admin",
            "5129; 0 0 TABLE DATA cron job supabase_admin",
            "10017; 0 0 SEQUENCE SET cron jobid_seq supabase_admin",
            "3908; 826 16720 DEFAULT ACL cron DEFAULT PRIVILEGES FOR SEQUENCES supabase_admin",
        )
        retained = (
            "9799; 1255 17049 FUNCTION extensions grant_pg_cron_access() supabase_admin",
            "9679; 0 0 COMMENT extensions FUNCTION grant_pg_cron_access() supabase_admin",
            "5124; 826 24384 EVENT TRIGGER - issue_pg_cron_access supabase_admin",
            "701; 1259 1009 TABLE public alpha_hunter_snapshots postgres",
            "; Archive dump header",
        )
        for row in cron_owned:
            with self.subTest(exclude=row):
                self.assertTrue(excluded(row))
        for row in retained:
            with self.subTest(preserve=row):
                self.assertFalse(excluded(row))


if __name__ == "__main__":
    unittest.main()
