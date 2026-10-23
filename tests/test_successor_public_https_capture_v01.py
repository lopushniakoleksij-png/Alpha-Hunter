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
