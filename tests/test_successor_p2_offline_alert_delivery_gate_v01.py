"""No-network P2 failure-alert dispatch/recipient negative acceptance.
No real email addresses, providers, user settings, production DB or live quotes.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ops"/"reviews"))
from successor_p2_offline_alert_delivery_gate_v01 import (
    MAX_MONITOR_GAP_SECONDS, EMPTY_SHA, SyntheticJournal, digest, evaluate,
    liveness, make_alert, seal
)

def setup():
    a=make_alert("synthetic-p2-alert-gap-001",
                 "synthetic-destination-private-test-token","35M_BREACH")
    j=SyntheticJournal(a)
    assert j.add("ENQUEUED",10,{"id":"outbox-1","journal_commit":"mock-only"})
    return a,j

def accepted(a,j):
    assert j.add("PROVIDER_ACCEPTED",11,{"id":"provider-a",
          "provider_message_id":"mock-msg-001"})
    return a,j

def inbox(a,j):
    assert j.add("RECIPIENT_CONFIRMED",12,{"id":"inbox-a",
          "provider_message_id":"mock-msg-001","inbox_receipt_id":"mock-inbox-001"})
    return a,j

def test_mock_outbox_cannot_claim_delivery():
    a,j=setup()
    v=evaluate(a,j.receipts,now_second=20)
    assert v["status"]=="FAIL_CLOSED_DELIVERY_UNKNOWN"
    assert "PROVIDER_ACCEPTANCE_MISSING" in v["blockers"]
    assert not v["actual_alert_delivery_verified"]

def test_provider_acceptance_is_not_recipient_delivery():
    a,j=accepted(*setup())
    v=evaluate(a,j.receipts,now_second=20)
    assert "INDEPENDENT_RECIPIENT_CONFIRMATION_MISSING" in v["blockers"]
    assert not v["offline_independent_recipient_fixture_verified"]

def test_provider_delivered_webhook_is_not_independent_inbox():
    a,j=accepted(*setup())
    j.add("PROVIDER_REPORTED_DELIVERED",12,{"id":"provider-delivered",
       "provider_message_id":"mock-msg-001"})
    v=evaluate(a,j.receipts,now_second=20)
    assert v["provider_delivered_claim_seen"]
    assert "INDEPENDENT_RECIPIENT_CONFIRMATION_MISSING" in v["blockers"]
    assert not v["actual_alert_delivery_verified"]

def test_complete_mock_receipt_sequence_is_never_live_delivery():
    a,j=inbox(*accepted(*setup()))
    v=evaluate(a,j.receipts,now_second=20)
    assert v["status"]=="OFFLINE_COMPLETE_SYNTHETIC_ONLY"
    assert v["offline_independent_recipient_fixture_verified"]
    assert not v["real_provider_acceptance_verified"]
    assert not v["real_inbox_delivery_verified"]
    assert not v["actual_alert_delivery_verified"]
    assert not v["science_or_trade_promotion_permitted"]

def test_human_ack_is_optional_and_never_real_without_external_proof():
    a,j=inbox(*accepted(*setup()))
    j.add("HUMAN_ACKNOWLEDGED",13,{"id":"mock-human-ack"})
    v=evaluate(a,j.receipts,now_second=20)
    assert v["synthetic_human_ack_seen"]
    assert not v["actual_alert_delivery_verified"]
    a,j=accepted(*setup())
    j.add("HUMAN_ACKNOWLEDGED",12,{"id":"ack-too-early"})
    assert "HUMAN_ACK_BEFORE_INBOX" in evaluate(a,j.receipts,now_second=20)["blockers"]

def test_wrong_event_and_wrong_recipient_fail_closed():
    a,j=inbox(*accepted(*setup()))
    for field,value in [("event_id","synthetic-p2-alert-other"),
                        ("recipient_token","synthetic-destination-wrong")]:
        bad=copy.deepcopy(j.receipts)
        bad[-1]["body"][field]=value
        assert "RECEIPT_EVENT_OR_RECIPIENT_MISMATCH" in evaluate(
            a,bad,now_second=20)["blockers"]

def test_tampered_signed_payload_and_chain_break_fail_closed():
    a,j=inbox(*accepted(*setup()))
    wrong=copy.deepcopy(j.receipts)
    wrong[0]["body"]["evidence"]["journal_commit"]="tampered"
    assert "CHAIN_INTEGRITY_INVALID" in evaluate(a,wrong,now_second=20)["blockers"]
    wrong=copy.deepcopy(j.receipts)
    wrong[1]["mac"]="0"*64
    assert "RECEIPT_SIGNATURE_UNVERIFIED" in evaluate(a,wrong,now_second=20)["blockers"]
    wrong=copy.deepcopy(j.receipts)
    wrong[1]["body"]["previous_digest"]=EMPTY_SHA
    assert "CHAIN_INTEGRITY_INVALID" in evaluate(a,wrong,now_second=20)["blockers"]

def test_provider_cannot_sign_as_independent_recipient():
    a,j=accepted(*setup())
    rogue=seal("RECIPIENT_CONFIRMED",a,12,
        {"id":"fake-inbox","provider_message_id":"mock-msg-001",
         "inbox_receipt_id":"mock-inbox-forgery"},j.receipts[-1]["digest"],
        actor="mock_provider")
    j.receipts.append(rogue)
    assert "RECEIPT_UNAUTHORISED_ACTOR" in evaluate(
        a,j.receipts,now_second=20)["blockers"]

def test_wrong_provider_id_or_missing_inbox_proof_fails():
    a,j=accepted(*setup())
    j.add("RECIPIENT_CONFIRMED",12,{"id":"inbox-unbound",
        "provider_message_id":"mock-msg-other","inbox_receipt_id":"mock-inbox-001"})
    assert "RECIPIENT_CONFIRMATION_UNBOUND" in evaluate(
        a,j.receipts,now_second=20)["blockers"]
    a,j=accepted(*setup())
    j.add("RECIPIENT_CONFIRMED",12,{"id":"inbox-no-proof",
        "provider_message_id":"mock-msg-001"})
    assert "RECIPIENT_CONFIRMATION_UNBOUND" in evaluate(
        a,j.receipts,now_second=20)["blockers"]

def test_idempotent_replay_and_conflicting_replay():
    a,j=accepted(*setup())
    assert not j.add("PROVIDER_ACCEPTED",11,{
        "id":"provider-a","provider_message_id":"mock-msg-001"})
    assert len(j.receipts)==2
    with pytest.raises(ValueError, match="CONFLICTING_DELIVERY_RECEIPT_REPLAY"):
        j.add("PROVIDER_ACCEPTED",11,{
           "id":"provider-a","provider_message_id":"mock-msg-mutation"})

def test_out_of_order_duplicate_and_future_timestamp_fail_closed():
    a,j=accepted(*setup())
    j.add("RECIPIENT_CONFIRMED",9,{"id":"inbox-before-accept-time",
        "provider_message_id":"mock-msg-001",
        "inbox_receipt_id":"mock-inbox-001"})
    assert "RECEIPT_CLOCK_INVALID" in evaluate(a,j.receipts,now_second=20)["blockers"]
    a,j=inbox(*accepted(*setup()))
    assert "RECEIPT_CLOCK_INVALID" in evaluate(a,j.receipts,now_second=11)["blockers"]
    dup=copy.deepcopy(j.receipts)
    # Bitwise duplicate cannot be appended as a second independently signed
    # event, even if it looks like a valid prior receipt.
    dup.append(copy.deepcopy(dup[-1]))
    assert "CHAIN_INTEGRITY_INVALID" in evaluate(a,dup,now_second=20)["blockers"]

def test_outbox_offline_or_dispatch_error_never_qualifies():
    a,j=inbox(*accepted(*setup()))
    assert "INDEPENDENT_JOURNAL_UNAVAILABLE" in evaluate(
        a,j.receipts,journal_available=False,now_second=20)["blockers"]
    a,j=accepted(*setup())
    j.add("DISPATCH_FAILED",12,{"id":"mock-dispatch-timeout"})
    v=evaluate(a,j.receipts,now_second=20)
    assert "DISPATCH_FAILED" in v["blockers"]
    assert not v["actual_alert_delivery_verified"]

def test_missing_initial_outbox_is_not_recognized_as_sent():
    a,j=setup()
    rows=[seal("PROVIDER_ACCEPTED",a,11,{"id":"provider-a",
         "provider_message_id":"mock-msg-001"},EMPTY_SHA)]
    assert "OUTBOX_SEQUENCE_INVALID" in evaluate(a,rows,now_second=20)["blockers"]

def test_sentinel_offline_proof_cannot_be_promoted_to_live():
    assert MAX_MONITOR_GAP_SECONDS==2100
    exact=liveness(2100,journal_reachable=True,dispatcher_reachable=True)
    assert not exact["critical"]
    breach=liveness(2101,journal_reachable=True,dispatcher_reachable=True)
    assert breach["critical"] and "FROZEN_35M_BREACH" in breach["reasons"]
    missing=liveness(2101,journal_reachable=False,dispatcher_reachable=False)
    assert "INDEPENDENT_JOURNAL_DOWN" in missing["reasons"]
    assert "DISPATCHER_DOWN" in missing["reasons"]
    assert "EXTERNAL_SENTINEL_RECEIPT_MISSING" in missing["reasons"]
    assert not liveness(2101,journal_reachable=False,
        dispatcher_reachable=False,
        external_sentinel_has_test_receipt=True)["operational_external_alert_delivered"]
    assert liveness(-1,journal_reachable=True,dispatcher_reachable=True)["critical"]

def test_no_plaintext_recipient_or_live_promotion_possible():
    with pytest.raises(ValueError):
        make_alert("synthetic-p2-alert-gap","somebody@example.com","35M_BREACH")
    with pytest.raises(ValueError):
        make_alert("synthetic-p2-alert-gap","synthetic-destination-test","NOT_APPROVED")
    a,j=inbox(*accepted(*setup()))
    v=evaluate(a,j.receipts,now_second=20)
    assert v["frozen_monitor_maximum_seconds"]==2100
    assert v["independent_long_term_durability_verified"] is False
    assert v["external_deadman_operational"] is False


def test_conflicting_receipt_timestamp_is_not_idempotent_replay():
    a,j=accepted(*setup())
    # Identical event/type/ID/evidence, but a conflicting timestamp must not
    # be swallowed as an exact replay by the append-only custody journal.
    with pytest.raises(ValueError, match="CONFLICTING_DELIVERY_RECEIPT_REPLAY"):
        j.add("PROVIDER_ACCEPTED",19,{
            "id":"provider-a","provider_message_id":"mock-msg-001"})
    assert len(j.receipts)==2
    assert evaluate(a,j.receipts,now_second=20)["status"]=="FAIL_CLOSED_DELIVERY_UNKNOWN"
    # The exact original timestamp remains idempotent with zero extra rows.
    assert j.add("PROVIDER_ACCEPTED",11,{
        "id":"provider-a","provider_message_id":"mock-msg-001"}) is False
    assert len(j.receipts)==2


def test_multiple_distinct_signed_inbox_confirmations_fail_closed():
    a,j=inbox(*accepted(*setup()))
    j.add("RECIPIENT_CONFIRMED",13,{
        "id":"inbox-second","provider_message_id":"mock-msg-001",
        "inbox_receipt_id":"mock-inbox-second"})
    verdict=evaluate(a,j.receipts,now_second=20)
    assert "RECIPIENT_CONFIRMATION_DUPLICATE" in verdict["blockers"]
    assert verdict["status"]=="FAIL_CLOSED_DELIVERY_UNKNOWN"
    assert verdict["offline_independent_recipient_fixture_verified"] is False
    assert verdict["real_inbox_delivery_verified"] is False


def test_duplicate_provider_delivery_claim_cannot_satisfy_independent_recipient():
    a,j=accepted(*setup())
    j.add("PROVIDER_REPORTED_DELIVERED",12,{
        "id":"provider-report-a","provider_message_id":"mock-msg-001"})
    j.add("PROVIDER_REPORTED_DELIVERED",13,{
        "id":"provider-report-b","provider_message_id":"mock-msg-001"})
    verdict=evaluate(a,j.receipts,now_second=20)
    assert "PROVIDER_REPORT_DUPLICATE" in verdict["blockers"]
    assert verdict["actual_alert_delivery_verified"] is False


def test_multiple_signed_human_acknowledgements_fail_closed():
    a,j=inbox(*accepted(*setup()))
    j.add("HUMAN_ACKNOWLEDGED",13,{"id":"mock-human-ack-1"})
    j.add("HUMAN_ACKNOWLEDGED",14,{"id":"mock-human-ack-2"})
    verdict=evaluate(a,j.receipts,now_second=20)
    assert "HUMAN_ACK_DUPLICATE" in verdict["blockers"]
    assert verdict["actual_alert_delivery_verified"] is False
