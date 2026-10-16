"""P2 offline alert-delivery and external-sentinel acceptance contract.

ZERO NETWORK, ZERO real addresses, ZERO production imports or credentials.
Keys, inbox acknowledgements and endpoints in tests are purely synthetic.
A local test can NEVER establish actual provider, inbox, delivery or liveness
availability. The return value always forbids operational/scientific promotion.
"""
from __future__ import annotations

from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json

MAX_MONITOR_GAP_SECONDS = 2100  # Immutable R10 ceiling
TYPES = ("ENQUEUED", "PROVIDER_ACCEPTED", "PROVIDER_REPORTED_DELIVERED",
         "RECIPIENT_CONFIRMED", "HUMAN_ACKNOWLEDGED", "DISPATCH_FAILED")
ACTORS = {
    "ENQUEUED": "isolated_outbox",
    "PROVIDER_ACCEPTED": "mock_provider",
    "PROVIDER_REPORTED_DELIVERED": "mock_provider",
    "RECIPIENT_CONFIRMED": "mock_independent_inbox",
    "HUMAN_ACKNOWLEDGED": "mock_human",
    "DISPATCH_FAILED": "isolated_dispatcher",
}
# Distinct TEST keys. These have no relationship to live provider credentials.
KEYS = {actor: (b"TEST_ONLY_" + actor.encode() + b"_not_real_credentials")
        for actor in set(ACTORS.values())}
EMPTY_SHA = "0" * 64

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",",":"),ensure_ascii=False).encode()

def digest(value):
    return sha256(canonical(value)).hexdigest()

def make_alert(event_id, recipient_token, reason):
    # No plaintext recipient/credential in payload, files, logs or artifacts.
    if not isinstance(recipient_token,str) or not recipient_token.startswith("synthetic-destination-"):
        raise ValueError("Only synthetic destination tokens permitted")
    if not isinstance(event_id,str) or not event_id.startswith("synthetic-p2-alert-"):
        raise ValueError("Only synthetic event IDs permitted")
    if reason not in ("35M_BREACH","JOURNAL_DOWN","WORKER_DEAD","SOURCE_UNKNOWN"):
        raise ValueError("Only explicitly scoped synthetic alarm reason")
    return {"event_id":event_id,"recipient_token":recipient_token,
            "reason":reason,"severity":"CRITICAL",
            "paper_only":True,"trade_permission":False,
            "exchange_authority":False,"scientific_pass_permitted":False}

def seal(kind, alert, at_second, evidence, predecessor, *, actor=None, key=None):
    if kind not in TYPES or not isinstance(at_second,int) or at_second<0:
        raise ValueError("invalid synthetic receipt type/clock")
    actor = actor if actor is not None else ACTORS[kind]
    key = key if key is not None else KEYS[actor]
    body = {"kind":kind,"event_id":alert["event_id"],
            "recipient_token":alert["recipient_token"],"alert_digest":digest(alert),
            "at_second":at_second,"actor":actor,"evidence":evidence,
            "previous_digest":predecessor}
    return {"body":body,"digest":digest(body),
            "mac":hmac_new(key,canonical(body),"sha256").hexdigest()}

class SyntheticJournal:
    def __init__(self,alert):
        self.alert=alert
        self.receipts=[]

    def add(self,kind,at_second,evidence):
        previous=self.receipts[-1]["digest"] if self.receipts else EMPTY_SHA
        row=seal(kind,self.alert,at_second,evidence,previous)
        # An exact replay is idempotent, never another custody event.
        same=[p for p in self.receipts
              if p["body"]["kind"]==kind
              and p["body"]["evidence"].get("id")==evidence.get("id")]
        if same:
            # Same event/kind/ID with a different clock is a conflicting
            # custody record, NOT a harmless exact replay.
            if (same[0]["body"]["evidence"]==evidence
                and same[0]["body"]["at_second"]==at_second):
                return False
            raise ValueError("CONFLICTING_DELIVERY_RECEIPT_REPLAY")
        self.receipts.append(row)
        return True

def evaluate(alert,receipts,*,journal_available=True,now_second=None):
    reasons=[]
    if not isinstance(alert,dict) or alert.get("paper_only") is not True or (
       alert.get("trade_permission") is not False or
       alert.get("exchange_authority") is not False or
       alert.get("scientific_pass_permitted") is not False):
        reasons.append("ALERT_SOURCE_OR_AUTHORITY_INVALID")
    if not journal_available:
        reasons.append("INDEPENDENT_JOURNAL_UNAVAILABLE")
    if not isinstance(receipts,list) or not receipts:
        reasons.append("NO_DURABLE_ALERT_RECORD")
        receipts=[]
    prior=EMPTY_SHA
    last_clock=-1
    accepted_id=None
    inbox=False
    provider_claim=False
    provider_delivered_count=0
    recipient_confirm_count=0
    human_ack_count=0
    human=False
    enqueued=False
    fatal=False
    seen=set()
    for r in receipts:
        if not isinstance(r,dict) or not isinstance(r.get("body"),dict):
            reasons.append("RECEIPT_MALFORMED");fatal=True;break
        b=r["body"]
        kind=b.get("kind")
        evidence=b.get("evidence")
        if kind not in TYPES or b.get("actor")!=ACTORS.get(kind):
            reasons.append("RECEIPT_UNAUTHORISED_ACTOR");fatal=True;break
        if not isinstance(evidence,dict) or not isinstance(evidence.get("id"),str):
            reasons.append("RECEIPT_IDENTITY_MISSING");fatal=True;break
        if (b.get("event_id")!=alert.get("event_id")
            or b.get("recipient_token")!=alert.get("recipient_token")
            or b.get("alert_digest")!=digest(alert)):
            reasons.append("RECEIPT_EVENT_OR_RECIPIENT_MISMATCH");fatal=True;break
        at=b.get("at_second")
        if not isinstance(at,int) or at<last_clock or (
            isinstance(now_second,int) and at>now_second):
            reasons.append("RECEIPT_CLOCK_INVALID");fatal=True;break
        last_clock=at
        if b.get("previous_digest")!=prior or r.get("digest")!=digest(b):
            reasons.append("CHAIN_INTEGRITY_INVALID");fatal=True;break
        expected=hmac_new(KEYS[b["actor"]],canonical(b),"sha256").hexdigest()
        if not isinstance(r.get("mac"),str) or not compare_digest(expected,r["mac"]):
            reasons.append("RECEIPT_SIGNATURE_UNVERIFIED");fatal=True;break
        identifier=(kind,evidence["id"])
        if identifier in seen:
            reasons.append("DUPLICATE_DELIVERY_RECEIPT");fatal=True;break
        seen.add(identifier)
        prior=r["digest"]
        if kind=="ENQUEUED":
            if enqueued or len(seen)!=1:
                reasons.append("OUTBOX_SEQUENCE_INVALID");fatal=True;break
            enqueued=True
        elif not enqueued:
            reasons.append("OUTBOX_SEQUENCE_INVALID");fatal=True;break
        elif kind=="PROVIDER_ACCEPTED":
            msg=evidence.get("provider_message_id")
            if accepted_id is not None or not isinstance(msg,str) or not msg.startswith("mock-msg-"):
                reasons.append("PROVIDER_ACCEPTANCE_UNVERIFIED");fatal=True;break
            accepted_id=msg
        elif kind=="PROVIDER_REPORTED_DELIVERED":
            if (accepted_id is None or evidence.get("provider_message_id")!=accepted_id
                or provider_delivered_count):
                reasons.append("PROVIDER_REPORT_UNBOUND_OR_DUPLICATE");fatal=True;break
            provider_delivered_count+=1
            provider_claim=True  # insufficient for independent receipt
        elif kind=="RECIPIENT_CONFIRMED":
            # The independent inbox, not the provider's webhook, signs proof.
            # One provider message cannot acquire multiple supposedly distinct
            # recipient-confirmation claims for the same immutable alert.
            if (accepted_id is None or evidence.get("provider_message_id")!=accepted_id
                or recipient_confirm_count or
                not isinstance(evidence.get("inbox_receipt_id"),str) or
                not evidence["inbox_receipt_id"].startswith("mock-inbox-")):
                reasons.append("RECIPIENT_CONFIRMATION_UNBOUND_OR_DUPLICATE");fatal=True;break
            recipient_confirm_count+=1
            inbox=True
        elif kind=="HUMAN_ACKNOWLEDGED":
            if not inbox or human_ack_count:
                reasons.append("HUMAN_ACK_BEFORE_INBOX_OR_DUPLICATE");fatal=True;break
            human_ack_count+=1
            human=True
        elif kind=="DISPATCH_FAILED":
            reasons.append("DISPATCH_FAILED")
    if not enqueued:
        reasons.append("OUTBOX_MISSING")
    if accepted_id is None:
        reasons.append("PROVIDER_ACCEPTANCE_MISSING")
    if not inbox:
        reasons.append("INDEPENDENT_RECIPIENT_CONFIRMATION_MISSING")
    # Any chain/identity/signature fault invalidates every downstream claim.
    structurally_complete=not reasons and not fatal and enqueued and bool(accepted_id) and inbox
    return {
        "status":("OFFLINE_COMPLETE_SYNTHETIC_ONLY" if structurally_complete
                  else "FAIL_CLOSED_DELIVERY_UNKNOWN"),
        "blockers":sorted(set(reasons)),
        "offline_independent_recipient_fixture_verified":structurally_complete,
        "provider_delivered_claim_seen":provider_claim,
        "synthetic_human_ack_seen":human and structurally_complete,
        "real_provider_acceptance_verified":False,
        "real_inbox_delivery_verified":False,
        "actual_alert_delivery_verified":False,
        "independent_long_term_durability_verified":False,
        "external_deadman_operational":False,
        "science_or_trade_promotion_permitted":False,
        "frozen_monitor_maximum_seconds":MAX_MONITOR_GAP_SECONDS,
    }

def liveness(age_seconds,*,journal_reachable,dispatcher_reachable,
             external_sentinel_has_test_receipt=False):
    if type(age_seconds) is not int or age_seconds<0:
        return {"status":"UNKNOWN_CLOCK","critical":True,
                "operational_external_alert_delivered":False}
    failures=[]
    if age_seconds>MAX_MONITOR_GAP_SECONDS:
        failures.append("FROZEN_35M_BREACH")
    if not journal_reachable: failures.append("INDEPENDENT_JOURNAL_DOWN")
    if not dispatcher_reachable: failures.append("DISPATCHER_DOWN")
    if failures and not external_sentinel_has_test_receipt:
        failures.append("EXTERNAL_SENTINEL_RECEIPT_MISSING")
    return {"status":"FAIL_CLOSED_ALERT_REQUIRED" if failures else "SYNTHETIC_ONLY",
            "reasons":failures,"critical":bool(failures),
            "operational_external_alert_delivered":False,
            "scientific_pass_permitted":False}
