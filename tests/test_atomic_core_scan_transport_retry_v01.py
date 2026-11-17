"""Harada E2/E3: transport-level mock contract tests for opt-in atomic core RPC.

The server's database commit is emulated. These tests DO NOT provide real
network-fault or authentic production-trigger evidence. PostgreSQL 17's
separate-session lost-response and concurrency tests provide server-side QA.
"""
import json

import pytest
import requests

from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError


class QAResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.payload = payload
        self.text = ""

    def json(self):
        return self.payload


class CommittedButResponseLostSession:
    """Pretend server accepted first request, but caller lost its response."""

    def __init__(self, *, exception_factory, lose_all=False):
        self.exception_factory = exception_factory
        self.lose_all = lose_all
        self.calls = []
        self.first_committed_payload = None

    def post(self, url, **kwargs):
        assert url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
        assert kwargs["headers"]["Prefer"] == "return=representation"
        request = json.loads(kwargs["data"])
        self.calls.append((url, request))
        if self.first_committed_payload is None:
            # This models the server commit, NOT actual PostgreSQL execution.
            self.first_committed_payload = request
            raise self.exception_factory("QA connection dropped after simulated commit")
        if self.lose_all:
            raise self.exception_factory("QA repeat acknowledgement lost")
        result = {
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        }
        return QAResponse(result)


def sample_snapshot():
    return {
        "version": "isolated-transport-contract",
        "collected_at_utc": "2026-11-08T12:00:00+00:00",
        "product_type": "usdt-futures",
        "symbols": [{
            "symbol": "BTCUSDT",
            "last_price": 65000.0,
            "trade_permission": False,
            "state": "WATCH",
            "execution_setup": {"direction": None, "rr": None},
        }],
    }


def atomic_config():
    return SupabaseConfig(
        url="https://example.supabase.co",
        key="SYNTHETIC_TEST_KEY_ONLY",
        atomic_core_scan_writes=True,
        max_retries=1,
        retry_backoff_seconds=0,
    )


@pytest.mark.parametrize("exception_factory", [requests.ConnectionError, requests.Timeout])
def test_same_run_id_and_identical_payload_after_ambiguous_transport_failure(exception_factory):
    session = CommittedButResponseLostSession(exception_factory=exception_factory)
    run_id = SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())

    assert len(session.calls) == 2
    first_url, first_request = session.calls[0]
    second_url, second_request = session.calls[1]
    assert first_url == second_url
    assert first_request == second_request
    assert first_request == session.first_committed_payload
    assert first_request["p_parent"][0]["run_id"] == run_id
    assert first_request["p_readiness"][0]["run_id"] == run_id
    assert all(not row["trade_permission"] for row in first_request["p_children"])
    assert all(not row["trade_permission"] for row in first_request["p_readiness"])


@pytest.mark.parametrize("exception_factory", [requests.ConnectionError, requests.Timeout])
def test_exhausted_ambiguous_ack_retries_fail_closed_without_legacy_upsert(exception_factory):
    session = CommittedButResponseLostSession(exception_factory=exception_factory, lose_all=True)
    with pytest.raises(SupabaseStorageError, match="after 2 attempts"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())

    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    # A transport error is AMBIGUOUS: caller cannot assume rollback or commit.
    # No independent REST family fallback must run.
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)


class TransientHttpFailureSession:
    """Simulate an ambiguous gateway response; no actual network is contacted."""

    def __init__(self, *, status_code, fail_all=False):
        self.status_code = status_code
        self.fail_all = fail_all
        self.calls = []

    def post(self, url, **kwargs):
        request = json.loads(kwargs["data"])
        self.calls.append((url, request))
        if self.fail_all or len(self.calls) == 1:
            response = QAResponse({"error": "synthetic gateway failure"})
            response.status_code = self.status_code
            response.text = "synthetic gateway failure"
            return response
        return QAResponse({
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        })


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_atomic_rpc_retryable_http_status_preserves_exact_identity(status_code):
    session = TransientHttpFailureSession(status_code=status_code)
    run_id = SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    assert session.calls[0][1]["p_parent"][0]["run_id"] == run_id
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
def test_atomic_rpc_exhausted_retryable_http_status_fails_closed(status_code):
    session = TransientHttpFailureSession(status_code=status_code, fail_all=True)
    with pytest.raises(SupabaseStorageError, match=f"HTTP {status_code}"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)


class InvalidReceiptSession:
    """HTTP success is not proof of an atomic commit without an exact receipt."""

    def __init__(self, mutation):
        self.mutation = mutation
        self.calls = []

    def post(self, url, **kwargs):
        request = json.loads(kwargs["data"])
        self.calls.append((url, request))
        receipt = {
            "committed": True,
            "run_id": request["p_parent"][0]["run_id"],
            "parent_count": len(request["p_parent"]),
            "symbol_count": len(request["p_children"]),
            "signal_count": len(request["p_signals"]),
            "feature_count": len(request["p_features"]),
            "readiness_count": len(request["p_readiness"]),
        }
        if self.mutation == "wrong_run":
            receipt["run_id"] = "OTHER_RUN"
        elif self.mutation == "boolean_count":
            receipt["symbol_count"] = True  # bool is a subclass of int
        elif self.mutation == "missing_readiness":
            del receipt["readiness_count"]
        elif self.mutation == "extra_symbol":
            receipt["symbol_count"] += 1
        elif self.mutation == "not_committed":
            receipt["committed"] = False
        elif self.mutation == "list_receipt":
            receipt = [receipt]
        elif self.mutation == "string_count":
            receipt["symbol_count"] = str(receipt["symbol_count"])
        elif self.mutation == "float_count":
            receipt["symbol_count"] = float(receipt["symbol_count"])
        elif self.mutation == "null_count":
            receipt["symbol_count"] = None
        elif self.mutation == "string_commit":
            receipt["committed"] = "true"
        elif self.mutation.startswith("boolean_"):
            receipt[self.mutation.removeprefix("boolean_")] = True
        return QAResponse(receipt)


@pytest.mark.parametrize(
    "mutation",
    ["wrong_run", "boolean_count", "missing_readiness",
     "extra_symbol", "not_committed", "list_receipt",
     "string_count", "float_count", "null_count", "string_commit"],
)
def test_atomic_rpc_success_http_requires_exact_receipt_and_never_falls_back(mutation):
    session = InvalidReceiptSession(mutation)
    with pytest.raises(SupabaseStorageError, match="confirmation did not match payload"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1
    assert session.calls[0][0].endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")


@pytest.mark.parametrize("count_field", [
    "parent_count", "symbol_count", "signal_count",
    "feature_count", "readiness_count",
])
def test_atomic_rpc_rejects_boolean_in_every_count_field(count_field):
    """E2: JSON true must never be accepted as integer 1 in any family."""
    session = InvalidReceiptSession("boolean_" + count_field)
    with pytest.raises(SupabaseStorageError, match="confirmation did not match payload"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1
    assert all("/rpc/alpha_hunter_commit_core_scan_v01" in url for url, _ in session.calls)



@pytest.mark.parametrize("invalid_payload", ["", "{truncated", "not-json"])
def test_atomic_rpc_http_200_invalid_json_fails_closed_without_fallback(invalid_payload):
    """E2: successful HTTP status without parseable receipt is not a commit proof."""
    class InvalidJsonSession:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs["data"]))
            class Response:
                status_code = 200
                text = invalid_payload

                def json(self):
                    raise ValueError("synthetic malformed JSON receipt")
            return Response()

    session = InvalidJsonSession()
    with pytest.raises(SupabaseStorageError, match="returned invalid JSON"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())
    assert len(session.calls) == 1
    assert session.calls[0][0].endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")



def test_atomic_rpc_real_loopback_socket_drop_replays_identical_body(monkeypatch):
    """E2: real TCP disconnect before HTTP acknowledgement, isolated loopback only.

    The local server models a commit receipt; it is NOT PostgreSQL or a
    production-equivalent network partition.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(body)
            if len(received) == 1:
                # Actual socket closes with no status line or response body.
                self.close_connection = True
                return
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
            data = json.dumps(receipt).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from dataclasses import replace
        config = replace(atomic_config(), url=f"http://127.0.0.1:{server.server_port}")
        run_id = SupabaseStorage(config, session=requests.Session()).save_snapshot(sample_snapshot())
        assert len(received) == 2
        assert received[0] == received[1]
        assert json.loads(received[0])["p_parent"][0]["run_id"] == run_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("disconnects", [1, 2])
def test_atomic_rpc_real_loopback_socket_disconnect_exhaustion_fails_closed(disconnects):
    """E2: real loopback socket failures must never trigger legacy writes.

    This is transport-only QA; no real PostgreSQL commit is asserted.
    """
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, body))
            # Close before sending a status line: the client cannot know if a
            # transaction committed, and must not switch to independent writes.
            self.close_connection = True

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = replace(
            atomic_config(),
            url=f"http://127.0.0.1:{server.server_port}",
            max_retries=disconnects - 1,
        )
        with pytest.raises(SupabaseStorageError, match=f"after {disconnects} attempts"):
            SupabaseStorage(config, session=requests.Session()).save_snapshot(sample_snapshot())
        assert len(received) == disconnects
        assert all(item == received[0] for item in received)
        assert all(path.endswith("/rpc/alpha_hunter_commit_core_scan_v01") for path, _ in received)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_atomic_rpc_concurrent_identical_writers_with_lost_first_ack():
    """E3/E6 transport integration: two callers, same run, one lost response.

    Server-side commit-once is EMULATED under a lock; authentic PostgreSQL
    advisory locking and trigger side effects are tested separately.
    """
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Lock, Thread

    observed = []
    state = {"commits": 0}
    lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            request = json.loads(body)
            with lock:
                observed.append(body)
                if state["commits"] == 0:
                    state["commits"] = 1
                    lost_ack = True
                else:
                    lost_ack = False
            if lost_ack:
                self.close_connection = True
                return
            receipt = {
                "committed": True,
                "run_id": request["p_parent"][0]["run_id"],
                "parent_count": len(request["p_parent"]),
                "symbol_count": len(request["p_children"]),
                "signal_count": len(request["p_signals"]),
                "feature_count": len(request["p_features"]),
                "readiness_count": len(request["p_readiness"]),
            }
            data = json.dumps(receipt).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        config = replace(atomic_config(), url=f"http://127.0.0.1:{server.server_port}")
        def publish():
            # Separate clients; identical source identity and immutable run_id.
            return SupabaseStorage(config, session=requests.Session()).save_snapshot(sample_snapshot())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: publish(), range(2)))
        assert results[0] == results[1]
        assert state["commits"] == 1
        assert len(observed) == 3
        assert observed[0] == observed[1] == observed[2]
        assert json.loads(observed[0])["p_parent"][0]["run_id"] == results[0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_atomic_rpc_truncated_success_body_after_lost_ack_fails_closed():
    """E2: a committed-looking HTTP 200 with truncated JSON is not a receipt.

    Uses a real loopback TCP server, but NOT a PostgreSQL commit or a
    production-equivalent partition. No independent family writes are allowed.
    """
    from dataclasses import replace
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/rest/v1/rpc/alpha_hunter_commit_core_scan_v01"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, body))
            if len(received) == 1:
                # First attempt: ambiguous commit, acknowledgement lost.
                self.close_connection = True
                return
            # Second attempt: HTTP success, but no valid commit receipt.
            data = b'{"committed":true,"run_id":'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
        assert all(path.endswith("/rpc/alpha_hunter_commit_core_scan_v01") for path, _ in received)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_lost_ack_followed_by_conflicting_run_http_409_fails_closed():
    """E3: an ambiguous first ACK followed by a conflict is never success.

    Mock transport only: neither a real PostgreSQL commit nor an authenticated
    server-side conflict is established by this test.
    """
    class AmbiguousThenConflictSession:
        def __init__(self):
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs["data"]))
            if len(self.calls) == 1:
                raise requests.ConnectionError("synthetic lost acknowledgement")
            response = QAResponse({"error": "synthetic run identity conflict"})
            response.status_code = 409
            response.text = "synthetic run identity conflict"
            return response

    session = AmbiguousThenConflictSession()
    with pytest.raises(SupabaseStorageError, match="HTTP 409"):
        SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot())

    assert len(session.calls) == 2
    assert session.calls[0] == session.calls[1]
    assert all(
        url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01")
        for url, _ in session.calls
    )


def test_atomic_rpc_concurrent_identical_callers_one_conflict_fails_closed():
    """E6: concurrent same-run clients must not interpret HTTP 409 as success.

    A synthetic shared transport assigns one success and one conflict. This
    does not establish authentic PostgreSQL locking, trigger side effects,
    or production idempotency.
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    barrier = Barrier(2)
    lock = Lock()
    calls = []

    class SharedConflictSession:
        def post(self, url, **kwargs):
            body = kwargs["data"]
            with lock:
                calls.append((url, body))
                ordinal = len(calls)
            if ordinal == 1:
                request = json.loads(body)
                response = QAResponse({
                    "committed": True,
                    "run_id": request["p_parent"][0]["run_id"],
                    "parent_count": len(request["p_parent"]),
                    "symbol_count": len(request["p_children"]),
                    "signal_count": len(request["p_signals"]),
                    "feature_count": len(request["p_features"]),
                    "readiness_count": len(request["p_readiness"]),
                })
                return response
            response = QAResponse({"error": "synthetic concurrent identity conflict"})
            response.status_code = 409
            response.text = "synthetic concurrent identity conflict"
            return response

    session = SharedConflictSession()

    def publish():
        barrier.wait(timeout=5)
        try:
            return ("ok", SupabaseStorage(atomic_config(), session=session).save_snapshot(sample_snapshot()))
        except SupabaseStorageError as exc:
            return ("error", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: publish(), range(2)))

    assert sorted(kind for kind, _ in outcomes) == ["error", "ok"]
    assert "HTTP 409" in next(detail for kind, detail in outcomes if kind == "error")
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert all(url.endswith("/rest/v1/rpc/alpha_hunter_commit_core_scan_v01") for url, _ in calls)
