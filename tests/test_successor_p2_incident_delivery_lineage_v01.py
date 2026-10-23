"""No-network red-team: connect synthetic source/quote/position to mock inbox.

Independent live custody and delivery always remain FALSE. All inputs are
local fixture bytes; NO production role, external sender, DB, venue or funds.
"""
import copy
import sys
from pathlib import Path

REVIEWS=Path(__file__).resolve().parents[1]/"ops"/"reviews"
sys.path.insert(0,str(REVIEWS))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_successor_p2_source_quote_provenance_contract_v01 import (
    fixture, K_SOURCE, K_QUOTE, K_MONITOR, NOW)
from successor_p2_source_quote_provenance_contract_v01 import (
    accept, seal, digest)
from successor_p2_offline_alert_delivery_gate_v01 import (
    make_alert, SyntheticJournal)
from successor_p2_incident_delivery_lineage_v01 import check_lineage, REASON

K_INCIDENT=b"I"*32
K_JOURNAL=b"J"*32


def sample(gap=2101):
    bundle=fixture(n_managed=1,gap=gap)
    evidence=accept(bundle["source"],bundle["quotes"],bundle["previous"],bundle["current"],
        source_key=K_SOURCE,quote_key=K_QUOTE,custody_key=K_MONITOR,
        now_utc=NOW.isoformat())
    src=bundle["source"]
    quote=bundle["quotes"][0]
    previous=bundle["previous"][0]
    current=bundle["current"][0]
    eid="synthetic-p2-alert-lineage-001"
    evidence_digest=digest(bundle)
    payload={
        "event_id":eid,
        "reason":"35M_BREACH",
        "provenance_blocker":REASON,
        "source_run_id":src["payload"]["run_id"],
        "entry_order_id":current["payload"]["entry_order_id"],
        "symbol":current["payload"]["symbol"],
        "source_receipt_digest":src["digest_sha256"],
        "quote_receipt_digest":quote["digest_sha256"],
        "prior_receipt_digest":previous["digest_sha256"],
        "position_receipt_digest":current["digest_sha256"],
        "evidence_bundle_digest":evidence_digest,
        "verdict_digest":digest(evidence),
        "observed_at_utc":current["payload"]["observed_at_utc"],
        "paper_only":True,"trade_permission":False,
        "exchange_authority":False,"scientific_pass_permitted":False,
    }
    incident=seal("ISOLATED_MONITORING_INCIDENT",payload,K_INCIDENT)
    row={
        "record_id":"synthetic-journal-local-001",
        "event_id":eid,
        "incident_digest":incident["digest_sha256"],
        "evidence_bundle_digest":evidence_digest,
    }
    jr=seal("ISOLATED_JOURNAL_RECEIPT",row,K_JOURNAL)
    alert=make_alert(eid,"synthetic-destination-lineage-test","35M_BREACH")
    alert.update(
        incident_digest_sha256=incident["digest_sha256"],
        journal_receipt_digest_sha256=jr["digest_sha256"],
        evidence_bundle_digest=evidence_digest,
    )
    j=SyntheticJournal(alert)
    j.add("ENQUEUED",10,{
        "id":"synthetic-outbox-local-001",
        "incident_digest":incident["digest_sha256"],
        "journal_digest":jr["digest_sha256"],
    })
    j.add("PROVIDER_ACCEPTED",11,{
        "id":"provider-accept-001",
        "provider_message_id":"mock-msg-001",
    })
    j.add("RECIPIENT_CONFIRMED",12,{
        "id":"inbox-receipt-001",
        "provider_message_id":"mock-msg-001",
        "inbox_receipt_id":"mock-inbox-001",
    })
    return {
        "bundle":bundle,
        "incident":incident,
        "journal_receipt":jr,
        "recovered_row":row,
        "alert":alert,
        "delivery_receipts":j.receipts,
    }


def verify(x,**override):
    obj=dict(x)
    obj.update(override)
    return check_lineage(
        **obj,source_key=K_SOURCE,quote_key=K_QUOTE,monitor_key=K_MONITOR,
        incident_key=K_INCIDENT,journal_key=K_JOURNAL,now_utc=NOW.isoformat())


def refused(x):
    result=verify(x)
    assert result["status"]=="FAIL_CLOSED_EVIDENCE_LINKAGE_UNKNOWN",result
    assert result["blockers"],result
    assert result["actual_inbox_delivery_verified"] is False
    assert result["scientific_pass_permitted"] is False
    assert result["trade_permission"] is False
    return result


def test_exact_synthetic_source_quote_position_incident_journal_mock_inbox_chain():
    r=verify(sample())
    assert r["status"]=="OFFLINE_INCIDENT_TO_MOCK_INBOX_LINKED_NOT_LIVE",r
    assert r["single_position_synthetic_chain_verified"]
    for field in (
        "actual_source_identity_authenticated","venue_price_signature_verified",
        "independently_persistent_journal_verified",
        "actual_provider_acceptance_verified","actual_inbox_delivery_verified",
        "external_deadman_verified","real_72h_monitoring_verified",
        "scientific_pass_permitted","production_authorized","trade_permission",
    ):
        assert r[field] is False,field
    assert r["new_spend_usd"]==0


def test_no_incident_without_real_scoped_violation():
    x=sample(gap=2100)
    r=refused(x)
    assert "INCIDENT_NOT_INDEPENDENTLY_REPRODUCED" in r["blockers"]


def test_tampered_quote_source_or_position_cannot_be_bound():
    for part in ("source","quotes","previous","current"):
        x=sample()
        if part=="source":
            x["bundle"]["source"]["payload"]["run_id"]="synthetic-p2-wrong"
        else:
            x["bundle"][part][0]["payload"]["symbol"]="WRONGUSDT"
        refused(x)


def test_resigned_incident_wrong_order_quote_or_evidence_digest_not_accepted():
    for field,new in (
        ("entry_order_id","synthetic-other-order"),
        ("quote_receipt_digest","0"*64),
        ("evidence_bundle_digest","f"*64),
        ("verdict_digest","f"*64),
        ("source_run_id","synthetic-unrelated-run"),
    ):
        x=sample()
        altered=dict(x["incident"]["payload"],**{field:new})
        x["incident"]=seal("ISOLATED_MONITORING_INCIDENT",altered,K_INCIDENT)
        refused(x)


def test_missing_or_replaced_independent_journal_readback_fails_closed():
    x=sample()
    x["recovered_row"]=None
    assert "INDEPENDENT_JOURNAL_READBACK_MISSING_OR_MISMATCHED" in refused(x)["blockers"]
    x=sample()
    x["recovered_row"]["incident_digest"]="1"*64
    refused(x)
    x=sample()
    x["journal_receipt"]=seal("ISOLATED_JOURNAL_RECEIPT",
        x["journal_receipt"]["payload"],b"WRONG_JOURNAL_SIGNER_TEST_ONLY_123456")
    refused(x)


def test_alert_cannot_be_rebound_to_different_incident_or_outbox():
    x=sample()
    x["alert"]["incident_digest_sha256"]="a"*64
    assert "ALERT_INCIDENT_OR_JOURNAL_LINK_MISMATCH" in refused(x)["blockers"]
    x=sample()
    x["delivery_receipts"][0]["body"]["evidence"]["incident_digest"]="a"*64
    refused(x)


def test_provider_acceptance_alone_is_not_recipient_confirmation():
    x=sample()
    x["delivery_receipts"]=x["delivery_receipts"][:2]
    assert "RECIPIENT_EVIDENCE_NOT_INDEPENDENTLY_CONFIRMED" in refused(x)["blockers"]


def test_wrong_recipient_or_provider_report_cannot_complete_chain():
    x=sample()
    x["alert"]["recipient_token"]="synthetic-destination-different"
    refused(x)
    x=sample()
    x["delivery_receipts"][2]["body"]["evidence"]["provider_message_id"]="mock-msg-other"
    refused(x)


def test_simulated_journal_failure_never_qualifies_delivery():
    x=sample()
    result=check_lineage(
        **x,source_key=K_SOURCE,quote_key=K_QUOTE,monitor_key=K_MONITOR,
        incident_key=K_INCIDENT,journal_key=K_JOURNAL,now_utc=NOW.isoformat(),
        journal_available=False)
    assert result["status"]=="FAIL_CLOSED_EVIDENCE_LINKAGE_UNKNOWN"
    assert not result["independently_persistent_journal_verified"]


def test_cross_alert_replay_and_omission_fail_closed():
    x=sample()
    x["delivery_receipts"]=[]
    refused(x)
    x=sample()
    x["journal_receipt"]["payload"]["event_id"]="synthetic-cross-incident"
    refused(x)
    x=sample()
    x["incident"]["payload"]["observed_at_utc"]="2026-10-16T12:00:00+00:00"
    refused(x)
