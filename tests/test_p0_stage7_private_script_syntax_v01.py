"""Static safety checks for private Stage 7 QA scripts; never execute private DB work."""
import ast
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


if __name__ == "__main__":
    unittest.main()
