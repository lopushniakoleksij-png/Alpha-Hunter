"""P0 E8: opt-in storage readback with synthetic in-memory HTTP only."""
import json
from unittest.mock import Mock
import pytest
from alpha_hunter.storage import SupabaseConfig, SupabaseStorage, SupabaseStorageError

TABLES = (
    "alpha_hunter_snapshots", "alpha_hunter_symbol_snapshots",
    "alpha_hunter_signals", "alpha_hunter_signal_features",
    "alpha_hunter_readiness_observations_v01",
)

class Response:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data
        self.text = ""

    def json(self):
        return self._data

class Session:
    def __init__(self, *, missing=None, duplicate=None, wrong=None,
                 http_error=None, malformed=None):
        self.saved, self.posts, self.gets = {}, [], []
        self.missing, self.duplicate = missing, duplicate
        self.wrong, self.http_error, self.malformed = wrong, http_error, malformed

    def post(self, url, **kwargs):
        table = url.rsplit("/", 1)[-1]
        self.posts.append(table)
        if table in TABLES:
            self.saved[table] = json.loads(kwargs["data"])
        return Response(201)

    def get(self, url, **kwargs):
        table = url.rsplit("/", 1)[-1]
        self.gets.append(table)
        if table == self.http_error:
            return Response(503)
        if table == self.malformed:
            resp = Response(200)
            resp.json = Mock(side_effect=ValueError("bad JSON"))
            return resp
        params = kwargs["params"]
        cols = params["select"].split(",")
        run_id = params["run_id"][3:]
        rows = [{key: row.get(key) for key in cols}
                for row in self.saved.get(table, [])
                if row.get("run_id") == run_id]
        if table == self.missing:
            rows = []
        if table == self.duplicate:
            rows = rows + rows
        if table == self.wrong and rows:
            rows[0]["run_id"] = "OTHER_QA_RUN"
        return Response(200, rows[:int(params["limit"])])

def snapshot():
    return {
        "version": "isolated-qa", "product_type": "usdt-futures",
        "collected_at_utc": "2026-11-18T00:00:00+00:00",
        "symbols": [{
            "symbol": "BTCUSDT", "state": "WATCH_LONG", "last_price": 60000.0,
            "trade_permission": False, "execution_setup": {"direction": None, "rr": None},
        }],
    }

def run(session, verify=True):
    settings = SupabaseConfig(
        url="https://synthetic.invalid", key="TEST_ONLY",
        verify_core_scan_readback=verify, max_retries=0,
    )
    return SupabaseStorage(settings, session=session).save_snapshot(snapshot())

def test_default_flag_does_not_fetch():
    session = Session()
    assert len(run(session, verify=False)) == 32
    assert session.gets == []
    assert session.posts == list(TABLES)

def test_optin_exact_five_family_readback():
    session = Session()
    assert len(run(session)) == 32
    assert session.gets == list(TABLES)
    assert session.posts == list(TABLES)

@pytest.mark.parametrize("family", TABLES)
def test_missing_family_fails_closed(family):
    session = Session(missing=family)
    with pytest.raises(SupabaseStorageError, match="Independent core scan readback mismatch"):
        run(session)
    assert session.posts == list(TABLES)

@pytest.mark.parametrize("family", TABLES)
def test_duplicate_family_fails_closed(family):
    session = Session(duplicate=family)
    with pytest.raises(SupabaseStorageError, match="Independent core scan readback mismatch"):
        run(session)

@pytest.mark.parametrize("family", TABLES)
def test_cross_run_family_fails_closed(family):
    session = Session(wrong=family)
    with pytest.raises(SupabaseStorageError, match="Independent core scan readback mismatch"):
        run(session)

def test_http_503_fails_closed():
    with pytest.raises(SupabaseStorageError, match="HTTP 503"):
        run(Session(http_error="alpha_hunter_symbol_snapshots"))

def test_malformed_json_fails_closed():
    with pytest.raises(SupabaseStorageError, match="invalid JSON"):
        run(Session(malformed="alpha_hunter_signals"))

def test_explicit_config_optin_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://synthetic.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "TEST_ONLY")
    assert SupabaseConfig.from_environment({"supabase": {"enabled": True}}).verify_core_scan_readback is False
    assert SupabaseConfig.from_environment({"supabase": {
        "enabled": True, "verify_core_scan_readback": True
    }}).verify_core_scan_readback is True

@pytest.mark.parametrize("failure", ["http_error", "malformed"])
def test_readback_transport_failure_aborts_before_paper_side_effects(monkeypatch, failure):
    """An unsuccessful independent GET must never allow downstream writes."""
    session = Session(**{failure: "alpha_hunter_symbol_snapshots"})
    downstream = Mock(side_effect=AssertionError("paper side effect after failed readback"))
    monkeypatch.setattr(SupabaseStorage, "_insert_immutable", downstream)
    monkeypatch.setattr(SupabaseStorage, "_reconcile_paper_stages", downstream)
    with pytest.raises(SupabaseStorageError):
        run(session)
    assert session.posts == list(TABLES)
    assert session.gets == list(TABLES[:2])
    downstream.assert_not_called()
