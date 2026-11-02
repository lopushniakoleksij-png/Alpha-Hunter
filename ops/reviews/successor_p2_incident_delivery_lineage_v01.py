"""Research-only, single-position P2 incident → outbox → mock recipient chain.

No network, production imports, real addresses, real provider or credentials.
All HMAC signers and DB read-back bytes must be verifier-held IN AN ACTUAL
deployment; fixtures below are synthetic. Return NEVER promotes monitoring,
delivery, durable custody, science or trade authority.
"""
from __future__ import annotations

from successor_p2_source_quote_provenance_contract_v01 import (
    accept as verify_position_evidence, digest, unseal, source_manifest, stamp,
    EvidenceRejected,
)
from successor_p2_offline_alert_delivery_gate_v01 import evaluate as verify_delivery

REASON = "FROZEN_35_MINUTE_MONITOR_GAP_BREACH"
SCOPED_ALERT = "35M_BREACH"


def _require(cond, reason):
    if not cond:
        raise EvidenceRejected(reason)


def check_lineage(
    bundle, incident, journal_receipt, recovered_row, alert, delivery_receipts, *,
    source_key, quote_key, monitor_key, incident_key, journal_key,
    now_utc, now_second=60, journal_available=True,
):
    """Check exact binding, not operational authenticity or persistent storage.

    Deliberately only one managed position: a single incident cannot conceal
    other source residuals. Multi-position operational acceptance must verify
    EACH position separately with source-complete identity and outage receipts.
    """
    blockers=[]
    try:
        _require(isinstance(bundle,dict), "EVIDENCE_BUNDLE_MISSING")
        _require(isinstance(alert,dict), "ALERT_MISSING")
        provenance=verify_position_evidence(
            bundle["source"],bundle["quotes"],bundle["previous"],bundle["current"],
            source_key=source_key,quote_key=quote_key,custody_key=monitor_key,
            now_utc=now_utc,
        )
        _require(provenance["status"]=="FAIL_CLOSED_UNKNOWN_OR_INCIDENT"
                 and provenance["blockers"]==[REASON],
                 "INCIDENT_NOT_INDEPENDENTLY_REPRODUCED")
        source,_,positions=source_manifest(
            bundle["source"],source_key,stamp(now_utc))
        _require(len(positions)==1 and positions[0]["state"]=="MANAGED_WITH_STOP_TP"
                 and provenance["expected_managed_count"]==1,
                 "SINGLE_POSITION_SOURCE_MANIFEST_NOT_COMPLETE")
        _require(all(len(bundle[x])==1 for x in ("quotes","previous","current")),
                 "SINGLE_POSITION_EVIDENCE_NOT_COMPLETE")
        # Verify signer ownership of every referenced envelope separately.
        quote=unseal(bundle["quotes"][0],quote_key,"PUBLIC_BITGET_QUOTE_BYTES")
        prior=unseal(bundle["previous"][0],monitor_key,"PAPER_POSITION_OBSERVATION")
        current=unseal(bundle["current"][0],monitor_key,"PAPER_POSITION_OBSERVATION")
        inc=unseal(incident,incident_key,"ISOLATED_MONITORING_INCIDENT")
        p=positions[0]
        source_receipt=bundle["source"]
        signed_evidence_digest=digest({
            "source":bundle["source"],"quotes":bundle["quotes"],
            "previous":bundle["previous"],"current":bundle["current"]})
        _require(
            inc.get("event_id")==alert.get("event_id")
            and inc.get("reason")==SCOPED_ALERT
            and inc.get("provenance_blocker")==REASON
            and inc.get("source_run_id")==source.get("run_id")
            and inc.get("entry_order_id")==p["entry_order_id"]
            and inc.get("symbol")==p["symbol"]
            and inc.get("source_receipt_digest")==source_receipt["digest_sha256"]
            and inc.get("quote_receipt_digest")==bundle["quotes"][0]["digest_sha256"]
            and inc.get("prior_receipt_digest")==bundle["previous"][0]["digest_sha256"]
            and inc.get("position_receipt_digest")==bundle["current"][0]["digest_sha256"]
            and inc.get("evidence_bundle_digest")==signed_evidence_digest
            and inc.get("verdict_digest")==digest(provenance)
            and inc.get("observed_at_utc")==current.get("observed_at_utc")
            and quote.get("symbol")==p["symbol"] and prior.get("symbol")==p["symbol"]
            and current.get("entry_order_id")==p["entry_order_id"]
            and inc.get("paper_only") is True
            and inc.get("trade_permission") is False
            and inc.get("exchange_authority") is False
            and inc.get("scientific_pass_permitted") is False,
            "INCIDENT_SOURCE_QUOTE_POSITION_BINDING_FAILED",
        )
        # An independent test journal signature, plus a separately supplied
        # recovered row; a signed 'stored=true' claim by itself is insufficient.
        jr=unseal(journal_receipt,journal_key,"ISOLATED_JOURNAL_RECEIPT")
        _require(isinstance(recovered_row,dict)
                 and jr.get("incident_digest")==incident["digest_sha256"]
                 and jr.get("event_id")==inc["event_id"]
                 and isinstance(jr.get("record_id"),str)
                 and jr["record_id"].startswith("synthetic-journal-")
                 and recovered_row=={
                     "record_id":jr["record_id"],"event_id":inc["event_id"],
                     "incident_digest":incident["digest_sha256"],
                     "evidence_bundle_digest":signed_evidence_digest,
                 },
                 "INDEPENDENT_JOURNAL_READBACK_MISSING_OR_MISMATCHED")
        _require(alert.get("reason")==SCOPED_ALERT
                 and alert.get("severity")=="CRITICAL"
                 and alert.get("paper_only") is True
                 and alert.get("trade_permission") is False
                 and alert.get("exchange_authority") is False
                 and alert.get("scientific_pass_permitted") is False
                 and alert.get("incident_digest_sha256")==incident["digest_sha256"]
                 and alert.get("journal_receipt_digest_sha256")==journal_receipt["digest_sha256"]
                 and alert.get("evidence_bundle_digest")==signed_evidence_digest,
                 "ALERT_INCIDENT_OR_JOURNAL_LINK_MISMATCH")
        _require(isinstance(delivery_receipts,list) and bool(delivery_receipts),
                 "OUTBOX_DELIVERY_CHAIN_MISSING")
        outbox=delivery_receipts[0].get("body",{})
        _require(outbox.get("kind")=="ENQUEUED" and isinstance(outbox.get("evidence"),dict)
                 and outbox["evidence"].get("incident_digest")==incident["digest_sha256"]
                 and outbox["evidence"].get("journal_digest")==journal_receipt["digest_sha256"],
                 "OUTBOX_INCIDENT_REFERENCE_MISMATCH")
        delivery=verify_delivery(
            alert,delivery_receipts,journal_available=journal_available,
            now_second=now_second)
        _require(delivery["status"]=="OFFLINE_COMPLETE_SYNTHETIC_ONLY"
                 and delivery["offline_independent_recipient_fixture_verified"] is True,
                 "RECIPIENT_EVIDENCE_NOT_INDEPENDENTLY_CONFIRMED")
    except (EvidenceRejected,KeyError,TypeError,ValueError,IndexError,AttributeError) as e:
        blockers.append(str(e) if isinstance(e,EvidenceRejected)
                        else "MALFORMED_OR_UNVERIFIABLE_LINKAGE")
    return {
        "status": "OFFLINE_INCIDENT_TO_MOCK_INBOX_LINKED_NOT_LIVE"
                  if not blockers else "FAIL_CLOSED_EVIDENCE_LINKAGE_UNKNOWN",
        "blockers":blockers,
        "single_position_synthetic_chain_verified":not blockers,
        "actual_source_identity_authenticated":False,
        "venue_price_signature_verified":False,
        "independently_persistent_journal_verified":False,
        "actual_provider_acceptance_verified":False,
        "actual_inbox_delivery_verified":False,
        "external_deadman_verified":False,
        "real_72h_monitoring_verified":False,
        "scientific_pass_permitted":False,
        "production_authorized":False,
        "trade_permission":False,
        "new_spend_usd":0,
    }
