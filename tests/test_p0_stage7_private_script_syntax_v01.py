"""Static safety checks for private Stage 7 QA scripts; never execute private DB work."""
import ast
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "ops/local/qa_stage7_committed_disposable_61_v01.py",
    "ops/local/qa_stage7_61_rpc_rollback_benchmark_v01.py",
    "ops/local/qa_stage7_failed_view_474_inspect_v01.py",
    "ops/local/qa_stage7_physical_template_61_v01.py",
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
            "5124; 3466 23484 EVENT TRIGGER - issue_pg_cron_access supabase_admin",
        )
        retained = (
            "9799; 1255 17049 FUNCTION extensions grant_pg_cron_access() supabase_admin",
            "9679; 0 0 COMMENT extensions FUNCTION grant_pg_cron_access() supabase_admin",
            "5124; 826 24384 EVENT TRIGGER - unrelated_app_event supabase_admin",
            "5124; 826 24384 EVENT TRIGGER - issue_pg_cron_access_other supabase_admin",
            "701; 1259 1009 TABLE public alpha_hunter_snapshots postgres",
            "; Archive dump header",
        )
        for row in cron_owned:
            with self.subTest(exclude=row):
                self.assertTrue(excluded(row))
        for row in retained:
            with self.subTest(preserve=row):
                self.assertFalse(excluded(row))


    def test_restore_failure_diagnostic_never_leaks_sql(self):
        path = ROOT / "ops/local/qa_stage7_committed_disposable_61_v01.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                  and node.name == "restore_failure_evidence")
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        scope = {"re": re}
        exec(compile(module, str(path), "exec"), scope)
        diagnostic = scope["restore_failure_evidence"]
        toc = ["5993; 0 0 ACL - TABLE private_sensitive_table postgres"]
        stderr = ("pg_restore: from TOC entry 5993; 0 0 ACL ...\\n"
                  "Command was: PRIVATE SQL MUST NEVER BE PRINTED\\n"
                  'ERROR: relation "cron.job" does not exist\\n')
        self.assertEqual(diagnostic(stderr, toc), ("5993", "ACL"))
        self.assertEqual(diagnostic("unexpected failure", toc),
                         ("UNKNOWN", "UNKNOWN"))
        self.assertEqual(diagnostic(
            "pg_restore: processing item 5993 0 0 ACL private...",
            toc), ("5993", "ACL"))
        self.assertNotIn("PRIVATE SQL", str(diagnostic(stderr, toc)))
        self.assertNotIn("private_sensitive_table",
                         str(diagnostic(stderr, toc)))


    def test_failed_view_inspector_only_accepts_simple_view_474_metadata(self):
        path = ROOT / "ops/local/qa_stage7_failed_view_474_inspect_v01.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        pieces = [node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "Blocked"
                  or isinstance(node, ast.FunctionDef) and node.name == "parse_view_toc"]
        self.assertEqual(len(pieces), 2)
        module = ast.fix_missing_locations(ast.Module(body=pieces, type_ignores=[]))
        scope = {"re": re}
        exec(compile(module, str(path), "exec"), scope)
        parse = scope["parse_view_toc"]
        self.assertEqual(
            parse("474; 1259 17234 VIEW public internal_cron_status supabase_admin"),
            ("public", "internal_cron_status"),
        )
        for row in (
            "474; 1259 17234 TABLE public internal_cron_status supabase_admin",
            "475; 1259 17234 VIEW public internal_cron_status supabase_admin",
            "474; 1259 17234 VIEW public bad'name supabase_admin",
            "474; 1259 17234 VIEW public internal_cron_status supabase_admin more",
        ):
            with self.subTest(rejected=row):
                with self.assertRaises(scope["Blocked"]):
                    parse(row)


    def test_physical_template_probe_preserves_cron_and_fails_closed(self):
        path = ROOT / "ops/local/qa_stage7_physical_template_61_v01.py"
        content = path.read_text(encoding="utf-8")
        self.assertIn("CREATE DATABASE", content)
        self.assertIn(" TEMPLATE ", content)
        self.assertIn("OWNER supabase_admin", content)
        self.assertIn("pg_stat_activity", content)
        self.assertIn("pid<>pg_backend_pid()", content)
        self.assertIn("cron.database_name", content)
        self.assertIn("SELECT count(*) FROM cron.job", content)
        self.assertIn("to_regclass('cron.job')", content)
        self.assertIn("DISPOSABLE_DB_REMOVED=PASS", content)
        self.assertIn("NO_PRODUCTION_FALLBACK", content)
        self.assertIn("NO_INDEPENDENT_DBA_SECURITY_APPROVAL", content)
        self.assertNotIn("pg_restore", content)
        self.assertNotIn("pg_dump", content)
        self.assertNotIn("DROP EXTENSION pg_cron", content)
        self.assertNotIn("SET cron.database_name", content)
        self.assertNotIn("pg_terminate_backend", content)
        self.assertNotIn("pg_cancel_backend", content)


if __name__ == "__main__":
    unittest.main()
