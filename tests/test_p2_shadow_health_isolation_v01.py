"""P2 production-isolation checks. Does not call any live service."""
from __future__ import annotations

from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import json

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"ops/reviews/p2_shadow_health_service_v01.py"
spec=spec_from_file_location("p2_inert_shadow",SCRIPT)
shadow=module_from_spec(spec)
spec.loader.exec_module(shadow)

def env():
    return dict(shadow.REQUIRED)

@contextmanager
def localhost_server():
    with ThreadingHTTPServer(("127.0.0.1",0),shadow.make_handler()) as server:
        thread=Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=3)

def test_exact_isolation_environment_required_before_server_starts():
    shadow.verify_isolation(env())
    for name in shadow.REQUIRED:
        invalid=env();invalid.pop(name)
        with pytest.raises(RuntimeError,match="ISOLATION_GUARD"):
            shadow.verify_isolation(invalid)

@pytest.mark.parametrize("name", [
    "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "BITGET_API_KEY",
    "BITGET_SECRET_KEY", "DATABASE_URL", "PGHOST", "PGPASSWORD",
    "REAL_ORDER_AUTHORITY", "PAPER_ORDER_AUTHORITY",
])
def test_secret_or_execution_authority_variable_rejected(name):
    invalid=env();invalid[name]="FORBIDDEN_MARKER"
    with pytest.raises(RuntimeError,match="FORBIDDEN|UNEXPECTED"):
        shadow.verify_isolation(invalid)

def test_health_only_returns_no_data_or_authority():
    with localhost_server() as base:
        with urlopen(base+"/healthz",timeout=2) as resp:
            assert resp.status==200
            assert resp.headers["Cache-Control"]=="no-store"
            body=json.loads(resp.read())
        assert body==shadow.HEALTH
        assert body["status"]=="INERT_ISOLATED_HEALTH_ONLY"
        assert all(v is False for k,v in body.items()
                   if k not in ("service","status","version"))
        for route in ("/","/api/latest","/api/scan","/api/trade",
                      "/quote","/paper/open","/metrics","/healthz?secrets=1"):
            with pytest.raises(HTTPError) as err:
                urlopen(base+route,timeout=2)
            assert err.value.code==404

def test_all_mutating_methods_rejected():
    with localhost_server() as base:
        for method in ("POST","PUT","PATCH","DELETE"):
            with pytest.raises(HTTPError) as err:
                urlopen(Request(base+"/healthz",method=method),timeout=2)
            assert err.value.code==405

def test_health_script_never_imports_production_scanner_or_network_client():
    text=SCRIPT.read_text()
    for forbidden in ("import requests","from alpha_hunter","import psycopg",
      "import supabase","import subprocess","import socket","import urllib.request",
      "BITGET_API_KEY =","execute_order(","place_order(","requests.get(",
      "requests.post(","SUPABASE_URL ="):
        assert forbidden not in text
    assert "serve_forever()" in text

def test_render_specific_release_contract_is_explicit():
    # Inspect the intended exact service settings before any deployment.
    text=(ROOT/"ops/reviews/p2_shadow_render_deployment_gate_20261012.md").read_text()
    for phrase in ("autoDeploy: no","branch: p2-isolated-shadow-guard-20261012",
                   "runtime: python","plan: free",
                   "hourly.py --once", "NEVER MERGE"):
        assert phrase in text
