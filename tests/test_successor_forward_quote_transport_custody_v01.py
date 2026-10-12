"""Pure P2 forward-only source provenance: no Bitget keys or live orders."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=spec_from_file_location("p2_transport",ROOT/"ops/reviews/successor_forward_quote_transport_custody_v01.py")
s=module_from_spec(spec);spec.loader.exec_module(s)
monitor_spec=spec_from_file_location("p2_monitor",ROOT/"ops/reviews/successor_all_residual_monitor_qualification_v01.py")
m=module_from_spec(monitor_spec);monitor_spec.loader.exec_module(m)
base=datetime(2026,10,12,12,0,0,tzinfo=timezone.utc)
RUN="synthetic-p2-quote-custody"
EP="/api/v2/mix/market/ticker"
SOURCE="BITGET_V2_MIX_MARKET_TICKER_SYMBOL_CAPTURE"

def response(symbol="QUSDT",age_s=3):
    t=base-timedelta(seconds=age_s)
    return {"symbol":symbol,"ts":str(int(t.timestamp()*1000)),
       "bidPr":"0.90","askPr":"0.91","bidSz":"12","askSz":"11",
       "lastPr":"0.905"}

def capture(row=None,endpoint=EP,symbol="QUSDT",when=base):
    return s.build_transport_quote_capture(endpoint=endpoint,
       requested_symbol=symbol,observed_at_utc=when.isoformat(),
       transport_request_id="synthetic-bitget-response-id",source_run_id=RUN,
       raw_response_row=row if row is not None else response(symbol),
       upstream_call_succeeded=True)

def test_transport_label_derived_from_endpoint_not_downstream_price():
    obj=capture()
    assert obj["source"]==SOURCE
    assert obj["exchange_age_at_capture_seconds"]==3
    assert len(obj["raw_response_row_sha256"])==64
    assert obj["source_authentication"]=="SUPPLIED_TRANSPORT_METADATA_NOT_INDEPENDENTLY_VERIFIED"
    assert not obj["trade_permission"] and not obj["scientific_pass_permitted"]

def test_forward_capture_can_build_same_run_per_position_attempt_but_not_execution():
    obj=capture()
    attempt=s.build_shadow_quote_attempt(obj,entry_order_id="synthetic-position",
      symbol="QUSDT",direction="LONG",source_run_id=RUN,
      scan_collected_at_utc=base.isoformat())
    assert attempt["evidence"]["quote_source"]==SOURCE
    assert attempt["best_bid"]=="0.90"
    assert attempt["evidence"]["capture_manifest_sha256"]==obj["capture_manifest_sha256"]
    assert not attempt["scientific_pass_permitted"] and not attempt["exchange_authority"]

@pytest.mark.parametrize("bad",[
    {"symbol":"OTHERUSDT"},
    {"bidSz":"0"},
    {"askPr":"0.1"},
    {"ts":"0"},
    {"bidPr":None}
])
def test_bad_venue_row_cannot_be_relabelled_and_accepted(bad):
    row=response();row.update(bad)
    with pytest.raises(s.QuoteCustodyIncomplete):
        capture(row)

def test_freshness_and_missing_transport_context_fail_closed():
    with pytest.raises(s.QuoteCustodyIncomplete,match="EXCHANGE_QUOTE_NOT_FRESH"):
        capture(response(age_s=121))
    with pytest.raises(s.QuoteCustodyIncomplete,match="SOURCE_ENDPOINT_OR_TRANSPORT"):
        capture(endpoint="/api/v2/mix/order/place-order")
    with pytest.raises(s.QuoteCustodyIncomplete,match="SOURCE_ENDPOINT_OR_TRANSPORT"):
        s.build_transport_quote_capture(endpoint=EP,requested_symbol="QUSDT",
          observed_at_utc=base.isoformat(),transport_request_id="x",
          raw_response_row=response(),run_id=RUN,upstream_call_succeeded=False)

def test_mutated_book_and_hash_cannot_pass_same_raw_capture():
    obj=capture()
    altered=deepcopy(obj);altered["bid_size"]="9999"
    with pytest.raises(s.QuoteCustodyIncomplete,match="SOURCE_CAPTURE_MANIFEST_CHANGED"):
        s.build_shadow_quote_attempt(altered,entry_order_id="p",symbol="QUSDT",
          direction="LONG",source_run_id=RUN,scan_collected_at_utc=base.isoformat())

def test_wrong_symbol_run_and_old_capture_are_refused():
    obj=capture()
    for fields in (
       {"symbol":"BTCUSDT"},{"source_run_id":"other-run"},
       {"scan_collected_at_utc":(base+timedelta(seconds=121)).isoformat()}
    ):
        args=dict(entry_order_id="p",symbol="QUSDT",direction="LONG",
          source_run_id=RUN,scan_collected_at_utc=base.isoformat())
        args.update(fields)
        with pytest.raises(s.QuoteCustodyIncomplete):
            s.build_shadow_quote_attempt(obj,**args)

def test_monitoring_scoring_accepts_labelled_local_shape_but_never_authenticates():
    q=capture()
    a=s.build_shadow_quote_attempt(q,entry_order_id="forward-position",
      symbol="QUSDT",direction="LONG",source_run_id=RUN,
      scan_collected_at_utc=base.isoformat())
    source_positions=[{
       "entry_order_id":"forward-position","symbol":"QUSDT","direction":"LONG",
       "residual_qty":"1","latest_entry_fill_at_utc":
          (base-timedelta(minutes=8)).isoformat(),
    }]
    digest=m.sha256(m.dumps(source_positions,sort_keys=True,
       separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    inv={"status":"SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION",
         "positions":source_positions,"manifest_sha256":digest}
    parent={"run_id":RUN,"collected_at_utc":base.isoformat(),
      "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
      "scientific_fingerprint_sha256":"a"*64}}
    disp=[{"entry_order_id":"forward-position","state":"MANAGED_PROTECTED","protection_count":2}]
    qualified=m.score_monitoring_coverage(inv,parent,disp,[a],[],
      approved_quote_sources=frozenset({SOURCE}),quote_window_seconds=120)
    assert qualified["managed_locally_qualified"]==1
    assert qualified["status"]=="ALL_SUPPLIED_MANAGED_ATTEMPTS_LOCALLY_QUALIFIED_NOT_AUTHENTICATED"
    assert not qualified["independently_authenticated_source"]
    assert not qualified["scientific_pass_permitted"]
    a["evidence"]["quote_source"]=None
    refused=m.score_monitoring_coverage(inv,parent,disp,[a],[],
      approved_quote_sources=frozenset({SOURCE}),quote_window_seconds=120)
    assert refused["status"]=="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
