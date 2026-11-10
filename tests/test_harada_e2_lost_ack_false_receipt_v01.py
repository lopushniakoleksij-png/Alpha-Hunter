"""Harada E2: reject a false positive receipt after an ambiguous lost ACK.

Isolated loopback transport only: server-side PostgreSQL commits are emulated.
This does not certify production trigger graph, idempotency or network partitions.
"""
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from alpha_hunter.storage import SupabaseStorage, SupabaseStorageError
from test_atomic_core_scan_transport_retry_v01 import atomic_config, sample_snapshot


def test_lost_ack_then_http_200_wrong_run_receipt_never_falls_back():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, body))
            if len(received) == 1:
                # Ambiguous acknowledgement: no response proves whether commit happened.
                self.close_connection = True
                return
            request = json.loads(body)
            receipt = {
                "committed": True,
                "run_id": "UNRELATED_RUN_ID",
                "parent_count": len(request["p_parent"]),
                "symbol_count": len(request["p_children"]),
                "signal_count": len(request["p_signals"]),
                "feature_count": len(request["p_features"]),
                "readiness_count": len(request["p_readiness"]),
            }
            payload = json.dumps(receipt).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = replace(atomic_config(), url=f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(SupabaseStorageError):
            SupabaseStorage(config, session=requests.Session()).save_snapshot(sample_snapshot())
        assert len(received) == 2
        assert received[0] == received[1]
        assert all(path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
                   for path, _ in received)
        assert json.loads(received[0][1])["p_parent"][0]["run_id"] != "UNRELATED_RUN_ID"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
