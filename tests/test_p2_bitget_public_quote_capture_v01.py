"""P2 real-public collector contract, local fixtures ONLY and no external API."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import json
import os
from urllib.request import Request

import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"ops/reviews/p2_bitget_public_quote_capture_v01.py"
spec=spec_from_file_location("p2_public_market",SCRIPT)
m=module_from_spec(spec);spec.loader.exec_module(m)
NOW=datetime(2026,10,12,16,0,tzinfo=timezone.utc)
SYMBOL="BTCUSDT"

def body(symbol=SYMBOL,age=1,mutations=None):
    row={"symbol":symbol,"ts":str(int((NOW-timedelta(seconds=age)).timestamp()*1000)),
         "bidPr":"60543.20","askPr":"60543.30","bidSz":"1.25","askSz":"0.72"}
    if mutations:row.update(mutations)
    return json.dumps({"code":"00000","msg":"success","data":[row]},
                      separators=(",",":")).encode("utf-8")

class Stub:
    def __init__(self,req,raw,headers=None,status=200,url=None):
        self.status=status
        self.raw=raw
        self.headers=headers or {"Content-Type":"application/json"}
        self.url=url or req.full_url
        self.method=req.get_method()
        self.read_limit=None
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,n):
        self.read_limit=n
        return self.raw[:n]

def stubbed(raw=None,status=200,content_type="application/json",url=None):
    calls=[]
    def opener(req,*,timeout):
        assert isinstance(req,Request)
        assert timeout==8
        calls.append((req.get_method(),req.full_url,dict(req.header_items())))
        if url:
            return Stub(req,raw or body(),status=status,
                        headers={"Content-Type":content_type},url=url)
        return Stub(req,raw if raw is not None else body(),status=status,
                    headers={"Content-Type":content_type})
    return opener,calls

@pytest.fixture(autouse=True)
def clear_external_proxy_and_secrets(monkeypatch):
    for var in m.FORBIDDEN_ENV+(
     "HTTPS_PROXY","https_proxy","HTTP_PROXY","http_proxy","ALL_PROXY","all_proxy"):
        monkeypatch.delenv(var,raising=False)

def collect(raw=None,**kwargs):
    opener,calls=stubbed(raw,**kwargs)
    capture=m.collect_once(SYMBOL,transport=opener,now=lambda:NOW)
    return capture,calls

def test_only_one_get_to_exact_bitget_public_usdt_m_contract():
    a,calls=collect()
    assert len(calls)==1 and calls[0][0]=="GET"
    assert calls[0][1]==(
      "https://api.bitget.com/api/v2/mix/market/ticker"
      "?symbol=BTCUSDT&productType=USDT-FUTURES")
    assert all("auth" not in k.lower() and "key" not in k.lower()
               for k in calls[0][2])
    assert a["quote"]["bid_price"]=="60543.20"
    assert a["quote"]["bid_size"]=="1.25"
    assert a["quote"]["exchange_age_at_capture_seconds"]==1
    assert a["source_api_host"]=="api.bitget.com"
    assert a["status"]=="PUBLIC_TLS_QUOTE_CAPTURED_NOT_EXCHANGE_SIGNED"
    assert a["paper_monitoring_proven"] is False
    assert a["independent_journal_receipt_committed"] is False
    assert a["authenticated_exchange_signature"] is False
    assert m.verify_receipt(a) is True
    assert a["response_body_sha256"]==sha256(a["raw_response_body_utf8"].encode()).hexdigest()

@pytest.mark.parametrize("symbol",["ETHUSDT-PERP","BTCUSD","BTCUSDT&secret=1",
    "SUIUSDT","btcUSDT","","BTCUSDT\nHeader: foo"])
def test_request_symbol_not_allowlisted(symbol):
    with pytest.raises(m.CaptureRejected,match="NOT_ALLOWLISTED"):
        m.collect_once(symbol,transport=lambda *a,**kw:None,now=lambda:NOW)

@pytest.mark.parametrize("bad", [
 {"bidPr":"0"},{"askPr":"-1"},{"bidSz":"0"},{"askSz":"NaN"},
 {"bidPr":"60000","askPr":"50000"},{"symbol":"ETHUSDT"},
 {"ts":"0"},{"ts":"garbage"}
])
def test_refuse_invalid_raw_venue_quote(bad):
    with pytest.raises(m.CaptureRejected):
        collect(body(mutations=bad))

def test_api_failure_wrong_shape_stale_future_json_and_empty():
    for raw in (
       body(age=121),body(age=-61),b"",b"not-json",
       b'{"code":"12345","data":[]}',
       b'{"code":"00000","data":[]}',
       b'{"code":"00000","data":[{},{}]}',
    ):
        with pytest.raises(m.CaptureRejected):
            collect(raw)

def test_non_json_content_type_wrong_http_status_redirect_or_overlong_rejected():
    for kwargs in (
       {"status":503},{"content_type":"text/html"},
       {"url":"https://evil.example/api/v2/mix/market/ticker"},
       {"raw":b"A"*65537},
    ):
        with pytest.raises(m.CaptureRejected):
            collect(**kwargs)

def test_environment_secrets_and_proxies_explicitly_fail_closed(monkeypatch):
    for key in ("BITGET_API_KEY","SUPABASE_URL","DATABASE_URL",
                "REAL_ORDER_AUTHORITY","HTTPS_PROXY"):
        monkeypatch.setenv(key,"should-not-be-read")
        with pytest.raises(m.CaptureRejected):
            m.collect_once(SYMBOL,transport=stubbed()[0],now=lambda:NOW)
        monkeypatch.delenv(key)

def test_modified_receipt_and_modified_raw_bytes_rejected():
    original,_=collect()
    modified=deepcopy(original)
    modified["quote"]["ask_price"]="9999"
    with pytest.raises(m.CaptureRejected,match="FINGERPRINT_MISMATCH"):
        m.verify_receipt(modified)
    tampered=deepcopy(original)
    tampered["raw_response_body_utf8"]=tampered["raw_response_body_utf8"].replace("60543.20","60543.22")
    tampered["evidence_sha256"]=sha256(m.canonical({k:v for k,v in tampered.items()
                                         if k!="evidence_sha256"})).hexdigest()
    with pytest.raises(m.CaptureRejected,match="RAW_HTTP_BYTES_DIGEST_MISMATCH"):
        m.verify_receipt(tampered)
    fabricated=deepcopy(original)
    fabricated["independent_journal_receipt_committed"]=True
    fabricated["evidence_sha256"]=sha256(m.canonical({k:v for k,v in fabricated.items()
                                         if k!="evidence_sha256"})).hexdigest()
    with pytest.raises(m.CaptureRejected,match="MANUFACTURE_INDEPENDENT_CUSTODY"):
        m.verify_receipt(fabricated)

def test_ephemeral_artifact_created_once_mode_0600_no_overwrite(tmp_path):
    capture,_=collect()
    filename=tmp_path/"p2-readonly-capture.json"
    m.save_local_artifact(capture,str(filename))
    assert filename.exists() and (filename.stat().st_mode & 0o777)==0o600
    assert m.verify_receipt(json.loads(filename.read_text()))
    with pytest.raises(FileExistsError):
        m.save_local_artifact(capture,str(filename))
    with pytest.raises(m.CaptureRejected,match="ONLY_TEMPORARY"):
        m.save_local_artifact(capture,"/mnt/prod/p2.json")
    with pytest.raises(m.CaptureRejected,match="ABSOLUTE"):
        m.save_local_artifact(capture,"p2.json")

def test_service_stays_inert_no_collector_import_or_trading_path():
    web=(ROOT/"ops/reviews/p2_shadow_health_service_v01.py").read_text()
    assert "p2_bitget_public_quote_capture_v01" not in web
    assert "urlopen" not in web
    src=SCRIPT.read_text()
    for token in ("import supabase","import psycopg",
                  "from alpha_hunter","requests.post(","place_order(",
                  "submit_order(","api/v2/mix/order/"):
        assert token not in src
    assert 'PRODUCT_TYPE="USDT-FUTURES"' in src
    assert 'MAX_AGE_SECONDS=120' in src
