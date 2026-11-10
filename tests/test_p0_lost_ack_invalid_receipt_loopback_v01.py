"""Harada E2/E3: real loopback lost acknowledgement followed by invalid commit receipt.

Transport-only isolated QA. The server emulates commits, NOT PostgreSQL or
private production trigger side effects. No external network or DB access.
"""
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from alpha_hunter.storage import SupabaseStorage, SupabaseStorageError
from test_atomic_core_scan_transport_retry_v01 import atomic_config, sample_snapshot


@pytest.mark.parametrize("invalid_receipt", ["wrong_run", "wrong_count", "not_committed"])
def test_lost_ack_then_false_success_receipt_fails_closed(invalid_receipt):
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            bodies.append((self.path, body))
            if len(bodies) == 1:
                # Real loopback TCP close; whether server committed is unknown.
                self.close_connection = True
                return
            payload = json.loads(body)
            receipt = {
                "committed": True,
                "run_id": payload["p_parent"][0]["run_id"],
                "parent_count": len(payload["p_parent"]),
                "symbol_count": len(payload["p_children"]),
                "signal_count": len(payload["p_signals"]),
                "feature_count": len(payload["p_features"]),
                "readiness_count": len(payload["p_readiness"]),
            }
            if invalid_receipt == "wrong_run":
                receipt["run_id"] = "DIFFERENT_RUN"
            elif invalid_receipt == "wrong_count":
                receipt["symbol_count"] += 1
            else:
                receipt["committed"] = False
            encoded = json.dumps(receipt).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = replace(atomic_config(), url=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(SupabaseStorageError, match="confirmation did not match payload"):
            SupabaseStorage(config, session=requests.Session()).save_snapshot(sample_snapshot())
        assert len(bodies) == 2
        assert bodies[0] == bodies[1]
        assert all(path.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01") for path, _ in bodies)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
