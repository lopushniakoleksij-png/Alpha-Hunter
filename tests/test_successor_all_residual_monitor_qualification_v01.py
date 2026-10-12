"""Research-only P2 proof: quote identity, 35m continuity, and quarantines."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path,key):
    s=spec_from_file_location(key,ROOT/path)
    m=module_from_spec(s);s.loader.exec_module(m);return m
mod=load("ops/reviews/successor_all_residual_monitor_qualification_v01.py","p2monitor")
prev=load("tests/test_successor_forward_asof_inventory_v01.py","p2sourcefixtures")
RUN="synthetic-p2-qual"
SOURCE="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"

def fixture():
    inv=prev.build()
    scan={"run_id":RUN,"collected_at_utc":"2026-10-12T12:00:00Z",
     "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
       "scientific_fingerprint_sha256":"a"*64}}
    states=[{"entry_order_id":o,"state":"MANAGED_PROTECTED","protection_count":2}
            for o in ("nmr-old-partial","q-new")]
    attempts=[{"entry_order_id":oid,"source_run_id":RUN,"symbol":symbol,
      "direction":"LONG","attempt_id":"attempt-"+oid,"outcome":"NO_TRIGGER",
      "observed_at_utc":"2026-10-12T12:00:04Z","best_bid":"1",
      "best_ask":"1.01","best_bid_size":"10","best_ask_size":"8",
      "blockers":[],"evidence":{"quote_source":SOURCE}}
      for oid,symbol in (("nmr-old-partial","NMRUSDT"),("q-new","QUSDT"))]
    prior=[{"entry_order_id":"nmr-old-partial","symbol":"NMRUSDT",
      "direction":"LONG","observed_at_utc":"2026-10-12T11:45:00Z",
      "previous_sealed_run_id":"synthetic-previous-run","seal_verified":True}]
    return [inv,scan,states,attempts,prior]

def score(data):
    return mod.score_monitoring_coverage(*data,
      approved_quote_sources=frozenset({SOURCE}),quote_window_seconds=30)

def blockers(result):
    return {b for p in result["positions"] for b in p["blockers"]}

def test_full_supplied_proof_remains_research_only():
    a=score(fixture())
    assert a["managed_locally_qualified"]==2
    assert not a["scientific_pass_permitted"] and not a["exchange_authority"]
    assert not a["independently_authenticated_source"]

def test_missing_old_residual_attempt_refused():
    a=fixture();a[3]=a[3][1:]
    result=score(a)
    assert result["expected_residuals"]==2
    assert "POSITION_MONITOR_ATTEMPT_COUNT_NOT_ONE" in blockers(result)

def test_source_label_missing_or_quote_too_late_refused():
    a=fixture();a[3][0]["evidence"]={}
    assert "QUOTE_SOURCE_UNLABELED" in blockers(score(a))
    a=fixture();a[3][0]["observed_at_utc"]="2026-10-12T12:00:40Z"
    assert "QUOTE_OUTSIDE_POLICY_WINDOW" in blockers(score(a))

def test_frozen_35min_exact_boundary_and_violation():
    a=fixture();a[4][0]["observed_at_utc"]="2026-10-12T11:25:04Z"
    assert score(a)["managed_locally_qualified"]==2
    a[4][0]["observed_at_utc"]="2026-10-12T11:25:03Z"
    assert "FROZEN_35M_POSITION_CONTINUITY_BREACH" in blockers(score(a))

def test_historic_fill_without_prior_observation_cannot_substitute():
    a=fixture();a[4]=[]
    assert "FROZEN_35M_POSITION_CONTINUITY_BREACH" in blockers(score(a))

def test_quarantined_and_unprotected_residuals_block_scientific_claim():
    a=fixture();a[2][0]={"entry_order_id":"nmr-old-partial","state":"UNPROTECTED_INCIDENT"}
    r=score(a)
    assert "UNPROTECTED_FILLED_RESIDUAL_INCIDENT" in blockers(r)
    assert r["quarantined_or_unprotected"]==1
    a=fixture();a[2][0]={"entry_order_id":"nmr-old-partial",
        "state":"QUARANTINED_UNVERIFIED","quarantine_case_id":"synthetic-case"}
    assert "QUARANTINED_RESIDUAL_UNMONITORED" in blockers(score(a))

def test_duplicate_attempt_or_missing_disposition_cannot_pass():
    a=fixture();a[3].append(dict(a[3][0]))
    assert "POSITION_MONITOR_ATTEMPT_COUNT_NOT_ONE" in blockers(score(a))
    a=fixture();a[2]=a[2][:1]
    assert "RESIDUAL_DISPOSITION_COVERAGE_MISMATCH" in score(a)["run_blockers"]

def test_fabricated_source_completeness_not_accepted_as_real_proof():
    a=fixture();a[0]["status"]="SOURCE_EVIDENCE_UNKNOWN_OR_INVALID"
    assert score(a)["status"]=="SOURCE_INCOMPLETE"


def test_tampered_source_residual_manifest_refused_even_when_attempts_match():
    a=fixture()
    a[0]["positions"][0]["residual_qty"]="999"
    result=score(a)
    assert result["status"]=="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    assert "SOURCE_RESIDUAL_MANIFEST_DIGEST_MISMATCH" in result["run_blockers"]

def test_empty_supplied_inventory_cannot_claim_absence_of_live_positions():
    a=fixture()
    a[0]["positions"]=[]
    a[0]["manifest_sha256"]=mod.sha256(
      mod.dumps([],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()
    a[2]=[]
    a[3]=[]
    a[4]=[]
    result=score(a)
    assert result["status"]=="EMPTY_SOURCE_INVENTORY_UNAUTHENTICATED_NO_LIVE_POSITION_CLAIM"
    assert not result["independently_authenticated_source"]
    assert not result["scientific_pass_permitted"]
