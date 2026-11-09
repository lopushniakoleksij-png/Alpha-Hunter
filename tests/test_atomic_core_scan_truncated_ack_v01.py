"""Harada E2: isolated truncated HTTP acknowledgement regression.

Real loopback HTTP framing is exercised, but the receipt is synthetic:
no PostgreSQL, production schema, or production network is contacted.
"""
import json
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
import requests

from alpha_hunter.storage import SupabaseStorage, SupabaseStorageError
from tests.test_atomic_core_scan_transport_retry_v01 import atomic_config, sample_snapshot


@pytest.mark.parametrize("all_responses_truncated", [False, True])
def test_atomic_rpc_truncated_http_200_receipt_retries_or_fails_closed(all_responses_truncated):
    """A 200 status with incomplete body is NOT a confirmed commit.

    The first HTTP response advertises a longer JSON body than transmitted.
    Requests must raise a transport error; a retry must reuse exact bytes.
    """
    requests_seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests_seen.append(body)
            request = json.loads(body)
            receipt = {
                "committed": True,
                "run_id": request["p_parent"][0]["run_id"],
                "parent_count": len(request["p_parent"]),
                "symbol_count": len(request["p_children"]),
                "signal_count": len(request["p_signals"]),
                "feature_count": len(request["p_features"]),
                "readiness_count": len(request["p_readiness"]),
            }
            encoded = json.dumps(receipt).encode("utf-8")
            truncated = all_responses_truncated or len(requests_seen) == 1
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded[: max(1, len(encoded) // 2)] if truncated else encoded)
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = replace(atomic_config(), url=f"http://127.0.0.1:{server.server_port}")
        storage = SupabaseStorage(config, session=requests.Session())
        if all_responses_truncated:
            with pytest.raises(SupabaseStorageError):
                storage.save_snapshot(sample_snapshot())
        else:
            run_id = storage.save_snapshot(sample_snapshot())
            assert json.loads(requests_seen[0])["p_parent"][0]["run_id"] == run_id
        assert len(requests_seen) == 2
        assert requests_seen[0] == requests_seen[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
