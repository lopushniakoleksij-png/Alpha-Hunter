"""P0.2 pure offline negative tests; production services are never contacted."""
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "ops" / "reviews"
sys.path.insert(0, str(REVIEWS))
source = importlib.import_module("successor_public_https_capture_v01")


def quote_row(age_seconds=1):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {"symbol": "BTCUSDT", "ts": str(now_ms - age_seconds * 1000),
            "bidPr": "1.00", "askPr": "1.01",
            "bidSz": "10", "askSz": "8"}


class FakeReply:
    status = 200
    def __init__(self, body, url=None, mime="application/json"):
        self.body = body
        self.url = url or source.URL
        self.headers = type("Headers", (), {"get_content_type": lambda _: mime})()
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def geturl(self):
        return self.url
    def read(self, n):
        return self.body


def set_response(monkeypatch, payload, **kwargs):
    raw = json.dumps(payload).encode()
    reply = FakeReply(raw, **kwargs)
    class FakeOpener:
        def open(self, request, timeout):
            assert timeout == 8
            assert request.get_method() == "GET"
            assert request.full_url == source.URL
            return reply
    monkeypatch.setattr(source, "build_opener", lambda *a: FakeOpener())


def test_exact_public_endpoint_and_no_production_runtime_imports():
    assert source.URL == ("https://api.bitget.com/api/v2/mix/market/ticker"
                          "?symbol=BTCUSDT&productType=USDT-FUTURES")
    text = (REVIEWS / "successor_public_https_capture_v01.py").read_text()
    for forbidden in ("place-order", "cancel-order", "SUPABASE_SERVICE_ROLE_KEY",
                      "BITGET_SECRET_KEY", "paper_exit", "alpha_hunter.storage"):
        assert forbidden not in text
    assert "ssl.create_default_context()" in text


def test_http_success_still_not_exchange_signed_or_scientific_pass(monkeypatch):
    set_response(monkeypatch, {"code": "00000", "data": [quote_row()]})
    evidence = source.capture_public_quote("synthetic-p02-unit")
    assert evidence["tls_host_checked"] is True
    assert evidence["venue_price_signature_verified"] is False
    assert evidence["source_inventory_authenticated"] is False
    assert evidence["scientific_pass_permitted"] is False
    assert evidence["trade_permission"] is False


def test_wrong_endpoint_or_response_contract_fails_closed(monkeypatch):
    set_response(monkeypatch, {"code": "00000", "data": [quote_row()]},
                 url="https://another.example/path")
    with pytest.raises(ValueError, match="VENUE_ENDPOINT_UNVERIFIED"):
        source.capture_public_quote("synthetic")

    set_response(monkeypatch, {"code": "99999", "data": [quote_row()]})
    with pytest.raises(ValueError, match="VENUE_RESPONSE_UNVERIFIED"):
        source.capture_public_quote("synthetic")


def test_stale_or_incorrect_symbol_quote_rejected(monkeypatch):
    set_response(monkeypatch, {"code": "00000", "data": [quote_row(age_seconds=130)]})
    with pytest.raises(ValueError, match="EXCHANGE_QUOTE_NOT_FRESH"):
        source.capture_public_quote("synthetic")

    row = quote_row()
    row["symbol"] = "OTHERUSDT"
    set_response(monkeypatch, {"code": "00000", "data": [row]})
    with pytest.raises(ValueError, match="SOURCE_REQUEST_SYMBOL_OR_IDENTITY_INVALID"):
        source.capture_public_quote("synthetic")


def test_opt_in_raw_public_response_bytes_exact_digest(monkeypatch):
    import hashlib
    row=quote_row()
    payload={"code":"00000","data":[row]}
    set_response(monkeypatch,payload)
    capture, raw=source.capture_public_quote(
        "synthetic-one-shot-artifact", include_raw_bytes=True)
    assert raw==json.dumps(payload).encode()
    assert hashlib.sha256(raw).hexdigest()==capture["response_sha256"]
    assert capture["source_inventory_authenticated"] is False
    assert capture["venue_price_signature_verified"] is False
    assert capture["scientific_pass_permitted"] is False
    assert capture["trade_permission"] is False
    assert capture["exchange_authority"] is False


def test_raw_capture_opt_in_must_be_exact_boolean(monkeypatch):
    set_response(monkeypatch,{"code":"00000","data":[quote_row()]})
    with pytest.raises(ValueError,match="RAW_CAPTURE_FLAG_INVALID"):
        source.capture_public_quote("synthetic-unit",include_raw_bytes="yes")


def test_ci_artifact_is_explicitly_temporary_and_never_a_live_monitor():
    workflow=(ROOT/".github/workflows/successor-p02-public-venue-custody-review-v01.yml").read_text()
    capture_file=(REVIEWS/"successor_public_https_pg16_custody_v01.py").read_text()
    assert "permissions:\n  contents: read" in workflow
    assert "AH_P02_EXPORT_PUBLIC_QUOTE_PROOF: EPHEMERAL_CI_ARTIFACT_ONLY" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "retention-days: 30" in workflow
    assert "retention-days: 90" not in workflow
    assert "actual_paper_inventory_authenticated\": False" in capture_file
    assert "persistent_independent_journal\": False" in capture_file
    assert "real_alert_delivery\": False" in capture_file
    assert "source_inventory_authenticated" in capture_file


def _load_selected_quote_probe():
    from importlib.util import spec_from_file_location, module_from_spec
    file=REVIEWS/"successor_selected_public_quote_artifact_20261023.py"
    spec=spec_from_file_location("selected_public_quote_probe",file)
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_selected_probe_env(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS","true")
    monkeypatch.setenv("AH_P02_SYMBOL_PROBE_APPROVAL","EPHEMERAL_CI_PUBLIC_GET_ONLY")
    for k in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","DATABASE_URL",
              "BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_API_PASSPHRASE"):
        monkeypatch.delenv(k,raising=False)


def test_selected_public_symbol_probe_saves_exact_bytes_without_live_authority(monkeypatch,tmp_path):
    import hashlib
    probe=_load_selected_quote_probe()
    _set_selected_probe_env(monkeypatch)
    monkeypatch.setattr(probe,"OUT",tmp_path/"public-proof")
    seen=[]
    def fake(run_id,*,include_raw_bytes,symbol):
        assert include_raw_bytes is True
        seen.append(symbol)
        raw=json.dumps({"code":"00000","data":[{"symbol":symbol}]}).encode()
        return {
            "response_sha256":hashlib.sha256(raw).hexdigest(),
            "raw_response_row_sha256":"a"*64,
            "capture_manifest_sha256":"b"*64,
            "exchange_timestamp_ms":1780000000000,
            "transport_captured_at_utc":"2026-10-23T13:00:00+00:00",
            "source_run_id":run_id,"request_id":"synthetic-"+symbol,
        }, raw
    monkeypatch.setattr(probe,"capture_public_quote",fake)
    probe.main()
    assert seen==["NIGHTUSDT","SOONUSDT"]
    result=json.loads((probe.OUT/"selected-symbols-manifest.json").read_text())
    assert result["public_quote_captured_count"]==2
    for row in result["quote_receipts"]:
        raw=(probe.OUT/row["raw_response_file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row["raw_response_sha256"]
        assert row["venue_signed_price"] is False
    for flag in ("operational_position_inventory_authenticated",
                 "source_run_and_paper_position_bound",
                 "independent_position_observation",
                 "actual_durable_alert_delivered",
                 "verified_recipient_delivery",
                 "continuous_35_minute_monitoring",
                 "permanent_independent_journal","scientific_test_pass",
                 "production_modified","live_exchange_authority"):
        assert result[flag] is False,flag


def test_selected_public_symbol_missing_quote_fails_and_retains_failure_manifest(monkeypatch,tmp_path):
    probe=_load_selected_quote_probe()
    _set_selected_probe_env(monkeypatch)
    monkeypatch.setattr(probe,"OUT",tmp_path/"public-proof")
    def unavailable(*args,**kwargs):
        raise ValueError("PUBLIC_QUOTE_STALE_OR_UNAVAILABLE")
    monkeypatch.setattr(probe,"capture_public_quote",unavailable)
    with pytest.raises(RuntimeError,match="PUBLIC_SYMBOL_QUOTE_PROBE_INCOMPLETE_FAIL_CLOSED"):
        probe.main()
    result=json.loads((probe.OUT/"selected-symbols-manifest.json").read_text())
    assert result["public_quote_captured_count"]==0
    assert all(row["status"]=="PUBLIC_QUOTE_UNKNOWN_FAIL_CLOSED"
               for row in result["quote_receipts"])
    assert result["actual_durable_alert_delivered"] is False


def test_selected_public_symbol_probe_cannot_run_outside_approved_ci(monkeypatch,tmp_path):
    probe=_load_selected_quote_probe()
    monkeypatch.setattr(probe,"OUT",tmp_path/"public-proof")
    monkeypatch.delenv("AH_P02_SYMBOL_PROBE_APPROVAL",raising=False)
    with pytest.raises(RuntimeError,match="NOT_AUTHORIZED_OUTSIDE_ISOLATED_CI"):
        probe.main()
    assert not probe.OUT.exists()


def test_public_symbol_allowlist_blocks_arbitrary_requests_without_network():
    assert source.ALLOWED_INDEPENDENT_PUBLIC_SYMBOLS==frozenset(
        {"BTCUSDT","NIGHTUSDT","SOONUSDT"})
    with pytest.raises(ValueError,match="UNAPPROVED_INDEPENDENT_SYMBOL_PROBE"):
        source.capture_public_quote("synthetic-invalid",symbol="OTHERUSDT")
