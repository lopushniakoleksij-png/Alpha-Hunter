"""E3/E6: disposable PG17 commit-once behind a real loopback HTTP lost ACK.

Synthetic RPC fixture and test-only HTTP adapter, NOT Supabase/PostgREST,
production private triggers, or an authentic production latency benchmark.
"""
import json
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import RemoteDisconnected
from urllib.request import Request, urlopen

CASE = "SIXTY_ONE_LOST_ACK"
RUN = "QA_61_LOST_ACK"


def sql(query):
    p = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-c", query],
        check=True, capture_output=True, text=True, timeout=40,
    )
    return p.stdout.strip()


def main():
    if not (
        os.getenv("GITHUB_ACTIONS") == "true"
        and os.getenv("GITHUB_REF_NAME") == "fix/supabase-write-timeout-qa"
        and os.getenv("PGHOST") == "127.0.0.1"
        and os.getenv("PGDATABASE") == "isolated_atomic_scan_qa"
        and os.getenv("PGUSER") == "postgres"
    ):
        raise SystemExit("REFUSED: disposable GitHub Actions PostgreSQL only")

    sql("SELECT 1 FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_LOST_ACK'")
    # A separate unique fixture is necessary; never reuse a previously committed run.
    sql("""INSERT INTO public.qa_atomic_scale_fixtures_v01
        (case_name,parent_rows,children_rows,signals_rows,features_rows,readiness_rows)
        SELECT 'SIXTY_ONE_HTTP_PG',
          replace(parent_rows::text,'QA_61_LOST_ACK','QA_61_HTTP_PG')::jsonb,
          replace(children_rows::text,'QA_61_LOST_ACK','QA_61_HTTP_PG')::jsonb,
          replace(replace(signals_rows::text,'QA_61_LOST_ACK','QA_61_HTTP_PG'),
                  'QA61_ACK_SIGNAL_','QA61_HTTP_SIGNAL_')::jsonb,
          replace(replace(features_rows::text,'QA_61_LOST_ACK','QA_61_HTTP_PG'),
                  'QA61_ACK_SIGNAL_','QA61_HTTP_SIGNAL_')::jsonb,
          replace(readiness_rows::text,'QA_61_LOST_ACK','QA_61_HTTP_PG')::jsonb
        FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_LOST_ACK'""")
    state = {"requests": [], "dropped": False}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/test-only-atomic-rpc":
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if json.loads(body) != {"run_id": "QA_61_HTTP_PG"}:
                self.send_error(400)
                return
            with lock:
                state["requests"].append(body)
            receipt = json.loads(sql("""SELECT public.alpha_hunter_commit_core_scan_v01(
              parent_rows,children_rows,signals_rows,features_rows,readiness_rows)::text
              FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_HTTP_PG'"""))
            with lock:
                drop = not state["dropped"]
                if drop:
                    state["dropped"] = True
            if drop:
                self.close_connection = True
                return
            data = json.dumps(receipt).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload = json.dumps({"run_id": "QA_61_HTTP_PG"}, separators=(",", ":")).encode()

    def client():
        for _ in range(2):
            try:
                req = Request(f"http://127.0.0.1:{server.server_port}/test-only-atomic-rpc",
                              data=payload, headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=35) as response:
                    receipt = json.load(response)
                assert receipt["committed"] is True
                assert receipt["run_id"] == "QA_61_HTTP_PG"
                assert all(receipt[f"{family}_count"] == count for family, count in
                           [("parent", 1), ("symbol", 61), ("signal", 61),
                            ("feature", 61), ("readiness", 61)])
                return
            except (RemoteDisconnected, ConnectionResetError):
                continue
        raise AssertionError("no valid receipt after retry")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: client(), range(2)))
        assert len(state["requests"]) == 3, state["requests"]
        assert len(set(state["requests"])) == 1
        counts = sql("""SELECT
          (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_61_HTTP_PG'),
          (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_61_HTTP_PG'),
          (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='QA_61_HTTP_PG'),
          (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_61_HTTP_PG'),
          (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_61_HTTP_PG'),
          (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_HTTP_PG')""")
        assert counts == "1|61|61|61|61|306", counts
        print("PASS: synthetic PG17 commit-once under two HTTP clients and one lost ACK")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
