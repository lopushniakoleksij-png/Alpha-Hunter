"""No-network regression tests for isolated DBA clone DSN guard."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("clone_guard", Path(__file__).with_name("p0_verify_isolated_production_catalog_clone_20261105.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CloneDsnGuardTests(unittest.TestCase):
    def test_allowed_local_keyword_dsn(self):
        self.assertEqual(module.validate_isolated_dsn("host=127.0.0.1 port=5432 dbname=isolated_research user=postgres")["host"], "127.0.0.1")

    def test_remote_host_with_localhost_text_in_password_rejected(self):
        with self.assertRaises(RuntimeError):
            module.validate_isolated_dsn("host=remote.example dbname=isolated_research password='host=127.0.0.1'")

    def test_uri_query_hostaddr_override_rejected(self):
        with self.assertRaises(RuntimeError):
            module.validate_isolated_dsn("postgresql://user@127.0.0.1/isolated_research?hostaddr=203.0.113.10")

    def test_service_and_options_rejected(self):
        for dsn in ("service=production host=127.0.0.1 dbname=isolated_research",
                    "host=127.0.0.1 dbname=isolated_research options='-c search_path=public'"):
            with self.subTest(dsn=dsn), self.assertRaises(RuntimeError):
                module.validate_isolated_dsn(dsn)

    def test_wrong_port_and_database_rejected(self):
        for dsn in ("host=127.0.0.1 port=6543 dbname=isolated_research",
                    "host=127.0.0.1 dbname=production"):
            with self.subTest(dsn=dsn), self.assertRaises(RuntimeError):
                module.validate_isolated_dsn(dsn)

if __name__ == "__main__":
    unittest.main()
