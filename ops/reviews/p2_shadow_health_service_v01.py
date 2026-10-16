#!/usr/bin/env python3
"""Inert, isolated P2 deployment-boundary probe. NOT a scanner or paper monitor.

This public health-only service may be deployed on a DEDICATED NON-MAIN Render
branch with autoDeploy OFF. It refuses all app/Bitget/Supabase credentials.
It has no outbound HTTP, database, order or scheduler code. A health response
is evidence of deployment isolation ONLY, never of operational quote custody.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

VERSION = "P2_INERT_SHADOW_ISOLATION_V0.1"
REQUIRED = {
    "AH_P2_SHADOW_ISOLATION": "ONLY_HEALTH_NO_TRADE",
    "AH_P2_SHADOW_PRODUCTION_ACCESS": "DENIED",
}
FORBIDDEN = (
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY",
    "DATABASE_URL", "DIRECT_URL", "BITGET_API_KEY", "BITGET_SECRET_KEY",
    "BITGET_API_PASSPHRASE", "BITGET_PASSPHRASE",
    "TRADING_ENABLED", "REAL_ORDER_AUTHORITY",
    "PAPER_ORDER_AUTHORITY", "RENDER_CRON_SERVICE_ID",
)
HEALTH = {
    "service": "alpha-hunter-p2-isolated-shadow",
    "status": "INERT_ISOLATED_HEALTH_ONLY",
    "version": VERSION,
    "active_scanner": False,
    "scheduler_active": False,
    "source_quote_authenticated": False,
    "live_source_snapshot_verified": False,
    "paper_monitoring_proven": False,
    "real_order_authority": False,
    "paper_admission_authority": False,
    "database_write_authority": False,
    "scientific_pass_permitted": False,
}

def verify_isolation(env: Mapping[str, str]) -> None:
    if any(env.get(name) != value for name, value in REQUIRED.items()):
        raise RuntimeError("P2_SHADOW_ISOLATION_GUARD_REQUIRED")
    present = [name for name in FORBIDDEN if env.get(name)]
    if present:
        raise RuntimeError("P2_SHADOW_FORBIDDEN_AUTHORITY_ENVIRONMENT: " + ",".join(present))
    for name, value in env.items():
        if value and (
            name.startswith("SUPABASE_")
            or name.startswith("BITGET_")
            or name in ("PGHOST", "PGPASSWORD", "PGUSER", "PGDATABASE")
        ):
            raise RuntimeError("P2_SHADOW_UNEXPECTED_EXTERNAL_CONNECTION_CONFIG: " + name)

def make_handler():
    class ShadowHandler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _json(self, status: int, body: dict) -> None:
            data = json.dumps(body, separators=(",",":"), sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/healthz":
                self._json(200, HEALTH)
            else:
                self._json(404, {"error": "P2_HEALTH_ONLY_NO_TRADING_API"})

        def do_HEAD(self):
            if self.path == "/healthz":
                self.send_response(200)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def do_POST(self):
            self._json(405, {"error": "P2_INERT_SERVICE_MUTATION_PROHIBITED"})
        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

    return ShadowHandler

def main():
    verify_isolation(os.environ)
    port=int(os.environ.get("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise RuntimeError("P2_SHADOW_INVALID_PORT")
    with ThreadingHTTPServer(("0.0.0.0", port), make_handler()) as server:
        print("P2_SHADOW_HEALTH_ONLY_LISTENING", flush=True)
        server.serve_forever()

if __name__ == "__main__":
    main()
