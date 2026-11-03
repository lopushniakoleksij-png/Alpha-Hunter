"""P0.3 quote-to-monitor-to-alert chain; no I/O, only admission evaluation.

Cross-system **links** are distinct from independently authenticated provider
evidence. Nothing here can issue a production authorization or backfill
historical same-snapshot stop/target ordering.
"""
from __future__ import annotations
import hashlib
from datetime import datetime,timezone


def _ms(value):
    if isinstance(value, bool) or not isinstance(value, int) or value<1000000000000:
        raise ValueError("invalid precise UTC milliseconds")
    return value


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def verify_chain(*,monitor,provider_raw,provider_witness,alert,ack,publication):
    blockers=[]
    if not isinstance(provider_witness,dict): provider_witness={}
    if not isinstance(provider_raw,bytes) or not provider_raw:
        blockers.append("RAW_PROVIDER_RESPONSE_MISSING")
    elif (provider_witness or {}).get("body_sha256") != _sha256(provider_raw):
        blockers.append("PROVIDER_BODY_SHA256_MISMATCH")
    if not isinstance(monitor,dict): monitor={}
    if not isinstance(provider_witness,dict): provider_witness={}
    if not isinstance(alert,dict): alert={}
    if not isinstance(ack,dict): ack={}
    if not isinstance(publication,dict): publication={}

    ids=[monitor.get("source_run_id"),monitor.get("position_id"),
         monitor.get("monitor_receipt_id")]
    if any(not isinstance(x,str) or not x for x in ids):
        blockers.append("MISSING_MONITOR_IDENTITY")
    if monitor.get("source_run_id") != publication.get("run_id") or publication.get("publication_state")!="VERIFIED":
        blockers.append("CANONICAL_PARENT_NOT_VERIFIED")
    if provider_witness.get("symbol") != monitor.get("symbol"):
        blockers.append("QUOTE_SYMBOL_MISMATCH")
    if monitor.get("quote_body_sha256") != provider_witness.get("body_sha256"):
        blockers.append("MONITOR_WITNESS_NOT_BOUND")
    if provider_witness.get("observer_role") in (None,"","SCANNER","RENDER_CRON"):
        blockers.append("NO_SEPARATE_OBSERVER")
    if provider_witness.get("exchange_attestation_verified_by_independent_authority") is not True:
        blockers.append("EXCHANGE_ORIGIN_INDEPENDENTLY_UNVERIFIED")
    if provider_witness.get("custody_storage_immutable_independently_verified") is not True:
        blockers.append("EVIDENCE_IMMUTABILITY_UNPROVEN")
    if provider_witness.get("transport") != "HTTPS_CA_VALIDATED":
        blockers.append("PROVIDER_TRANSPORT_UNVERIFIED")
    try:
        quote=_ms(provider_witness.get("provider_ts_ms"))
        captured=_ms(provider_witness.get("capture_ts_ms"))
        observed=_ms(monitor.get("observed_ts_ms"))
        if not (quote<=captured<=observed) or observed-quote>90000:
            blockers.append("QUOTE_CAPTURE_MONITOR_TEMPORAL_MISMATCH")
    except ValueError:
        blockers.append("TIMESTAMP_PROOF_MISSING")

    if (alert.get("run_id"),alert.get("position_id"),alert.get("monitor_receipt_id")) != tuple(ids):
        blockers.append("ALERT_NOT_BOUND_TO_MONITOR")
    if (ack.get("alert_id") != alert.get("alert_id")
        or not alert.get("alert_id")
        or ack.get("recipient_id") != alert.get("recipient_id")
        or not alert.get("recipient_id")):
        blockers.append("ALERT_RECIPIENT_ACK_LINK_INVALID")
    if ack.get("recipient_confirmed_delivery") is not True:
        blockers.append("ALERT_RECIPIENT_DELIVERY_UNPROVEN")
    if ack.get("independent_delivery_provider_evidence_verified") is not True:
        blockers.append("ALERT_DELIVERY_PROVIDER_EVIDENCE_UNVERIFIED")
    try:
        created=_ms(alert.get("created_ts_ms"))
        delivered=_ms(ack.get("delivered_ts_ms"))
        if delivered < created:
            blockers.append("ALERT_DELIVERY_CLOCK_INVALID")
    except ValueError:
        blockers.append("ALERT_DELIVERY_CLOCK_MISSING")

    if (monitor.get("paper_only") is not True
        or monitor.get("trade_permission") is not False
        or monitor.get("order_path")!="NONE"):
        blockers.append("LIVE_TRADE_PERMISSION_NOT_DENIED")
    if monitor.get("first_entry_ordering_ambiguous") is not False:
        blockers.append("FIRST_ENTRY_ORDERING_UNRESOLVED")

    return {
        "status":"SOURCE_AND_ALERT_UNVERIFIED" if blockers else
                 "LINKED_EVIDENCE_REQUIRES_INDEPENDENT_HUMAN_REVIEW",
        "blockers":sorted(set(blockers)),
        "quote_and_alert_links_pass":not blockers,
        "provider_signature_assumed_from_https":False,
        "historical_outcome_backfill_permitted":False,
        "first_entry_exception_cleared":False,
        "production_release_permitted":False,
        "real_order_permission":False,
    }
