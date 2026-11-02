"""P0.3 isolated successor *inert* HTTP service.

Standalone Python stdlib only. No scanner, Supabase, exchanges, queues,
orders, background tasks, scheduled work or network clients. It accepts no
write requests and cannot certify real-life deployment readiness.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

FORBIDDEN_CREDENTIALS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
    "DATABASE_URL",
    "POSTGRES_URL",
    "BITGET_API_KEY",
    "BITGET_SECRET_KEY",
    "BITGET_API_PASSPHRASE",
    "RENDER_API_KEY",
    "OPENAI_API_KEY",
)

if os.environ.get("AH_P03_INERT_ONLY") != "1":
    raise SystemExit("P0.3 refuse to start without explicit inert-only flag")
if any(os.environ.get(key) for key in FORBIDDEN_CREDENTIALS):
    raise SystemExit("P0.3 refuse to start when production credentials exist")
if os.environ.get("TRADING_ENABLED", "false").lower() != "false":
    raise SystemExit("P0.3 trading must remain disabled")
if os.environ.get("PAPER_ONLY", "true").lower() != "true":
    raise SystemExit("P0.3 paper-only invariant violated")
if os.environ.get("ORDER_PATH", "NONE") != "NONE":
    raise SystemExit("P0.3 order path must be NONE")


class InertHandler(BaseHTTPRequestHandler):
    server_version = "AH-P03-Inert"
    sys_version = ""

    def _respond(self, status, body):
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/health", "/healthz"):
            self._respond(200, {
                "status": "NO_GO_INERT_ONLY",
                "service": "alpha-hunter-p03-successor-candidate",
                "paper_only": True,
                "trading_enabled": False,
                "source_or_position_access": False,
                "deployment_authorized": False,
            })
            return
        self._respond(503, {
            "status": "NO_GO",
            "reason": "ISOLATED_SUCCESSOR_NOT_APPROVED",
            "trading_enabled": False,
        })

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        self._respond(405, {"status": "NO_GO", "writes_permitted": False})

    def do_PUT(self):
        self.do_POST()

    def do_PATCH(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()

    def log_message(self, fmt, *args):
        return


def main():
    port = int(os.environ.get("PORT", "10000"))
    if port <= 0 or port > 65535:
        raise SystemExit("Invalid port")
    ThreadingHTTPServer(("0.0.0.0", port), InertHandler).serve_forever()


if __name__ == "__main__":
    main()
