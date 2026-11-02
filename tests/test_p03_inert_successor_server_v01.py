"""Standalone inert-only P0.3 endpoint acceptance. All HTTP is localhost only."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

SOURCE = Path(__file__).resolve().parents[1] / "ops/release_guard/p03_inert_successor_server.py"


def load_server():
    with patch.dict(os.environ, {"AH_P03_INERT_ONLY": "1", "TRADING_ENABLED": "false", "PAPER_ONLY": "true", "ORDER_PATH": "NONE"}):
        spec = importlib.util.spec_from_file_location("p03_inert_server_test", SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class InertServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_server()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), cls.module.InertHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def req(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            conn.request(method, path)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}, dict(resp.getheaders())
        finally:
            conn.close()

    def test_health_is_not_approval(self):
        status, obj, headers = self.req("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(obj["status"], "NO_GO_INERT_ONLY")
        self.assertFalse(obj["trading_enabled"])
        self.assertFalse(obj["deployment_authorized"])
        self.assertFalse(obj["source_or_position_access"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_other_routes_unavailable(self):
        for route in ("/", "/api/latest", "/api/build", "/api/trades", "/orders"):
            with self.subTest(route=route):
                status, obj, _ = self.req("GET", route)
                self.assertEqual(status, 503)
                self.assertEqual(obj["status"], "NO_GO")

    def test_never_accept_writes(self):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, obj, _ = self.req(method, "/api/order")
                self.assertEqual(status, 405)
                self.assertFalse(obj["writes_permitted"])

    def test_missing_flag_prevents_start(self):
        env = {k: v for k, v in os.environ.items() if k not in ("AH_P03_INERT_ONLY",)}
        env.pop("SUPABASE_URL", None)
        r = subprocess.run([sys.executable, str(SOURCE)], env=env, timeout=4, text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("explicit inert-only flag", r.stderr + r.stdout)

    def test_credentials_prevent_start(self):
        env = dict(os.environ, AH_P03_INERT_ONLY="1", SUPABASE_URL="https://example.invalid")
        r = subprocess.run([sys.executable, str(SOURCE)], env=env, timeout=4, text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("production credentials", r.stderr + r.stdout)

    def test_trading_enabled_prevents_start(self):
        env = dict(os.environ, AH_P03_INERT_ONLY="1", TRADING_ENABLED="true")
        for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "DATABASE_URL"):
            env.pop(k, None)
        r = subprocess.run([sys.executable, str(SOURCE)], env=env, timeout=4, text=True, capture_output=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("trading must remain disabled", r.stderr + r.stdout)


if __name__ == "__main__":
    unittest.main()
