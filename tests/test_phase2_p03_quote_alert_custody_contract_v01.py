"""Deterministic isolated quote/alert custody contract, zero network/secrets."""
import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/"ops/reviews/phase2_p03_quote_alert_custody_contract_v01.py"
spec=importlib.util.spec_from_file_location("p03_quote_alert_contract",path)
contract=importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)
RAW=b'{"source":"SYNTHETIC_P0_NEVER_HISTORIC","bid":"100","ask":"101"}'
HASH=hashlib.sha256(RAW).hexdigest()
T=1793619000000

def fixture():
    return {
      "monitor":{"source_run_id":"run-synthetic-1","position_id":"paper-position-1",
        "monitor_receipt_id":"synthetic-monitor-1","symbol":"BTCUSDT",
        "quote_body_sha256":HASH,"observed_ts_ms":T+3000,"paper_only":True,
        "trade_permission":False,"order_path":"NONE",
        "first_entry_ordering_ambiguous":False},
      "provider_raw":RAW,
      "provider_witness":{"symbol":"BTCUSDT","body_sha256":HASH,
        "observer_role":"SEPARATE_SYNTHETIC_WITNESS","provider_ts_ms":T,
        "capture_ts_ms":T+1000,"transport":"HTTPS_CA_VALIDATED",
        "exchange_attestation_verified_by_independent_authority":True,
        "custody_storage_immutable_independently_verified":True},
      "alert":{"run_id":"run-synthetic-1","position_id":"paper-position-1",
        "monitor_receipt_id":"synthetic-monitor-1","alert_id":"synthetic-alert-1",
        "recipient_id":"synthetic-recipient-1","created_ts_ms":T+5000},
      "ack":{"alert_id":"synthetic-alert-1","recipient_id":"synthetic-recipient-1",
        "recipient_confirmed_delivery":True,
        "independent_delivery_provider_evidence_verified":True,
        "delivered_ts_ms":T+6000},
      "publication":{"run_id":"run-synthetic-1","publication_state":"VERIFIED"}
    }

class P03QuoteAlertContract(unittest.TestCase):
    def check(self,d):
        x=contract.verify_chain(**d)
        self.assertFalse(x["production_release_permitted"])
        self.assertFalse(x["real_order_permission"])
        self.assertFalse(x["historical_outcome_backfill_permitted"])
        self.assertFalse(x["first_entry_exception_cleared"])
        return x

    def test_synthetic_complete_chain_still_requires_human_signoff(self):
        x=self.check(fixture())
        self.assertEqual(x["blockers"],[])
        self.assertEqual(x["status"],"LINKED_EVIDENCE_REQUIRES_INDEPENDENT_HUMAN_REVIEW")

    def test_current_realistic_transport_only_witness_unverified(self):
        d=fixture()
        d["provider_witness"]["exchange_attestation_verified_by_independent_authority"]=False
        d["provider_witness"]["custody_storage_immutable_independently_verified"]=False
        r=self.check(d)
        self.assertIn("EXCHANGE_ORIGIN_INDEPENDENTLY_UNVERIFIED",r["blockers"])
        self.assertIn("EVIDENCE_IMMUTABILITY_UNPROVEN",r["blockers"])

    def test_wrong_raw_body_hash(self):
        d=fixture();d["provider_raw"]=b"forged replacement"
        self.assertIn("PROVIDER_BODY_SHA256_MISMATCH",self.check(d)["blockers"])

    def test_old_parent_must_not_claim_verified(self):
        d=fixture();d["publication"]["publication_state"]="UNMARKED"
        self.assertIn("CANONICAL_PARENT_NOT_VERIFIED",self.check(d)["blockers"])

    def test_different_parent_run_id(self):
        d=fixture();d["publication"]["run_id"]="other-run"
        self.assertIn("CANONICAL_PARENT_NOT_VERIFIED",self.check(d)["blockers"])

    def test_wrong_quote_symbol_and_identity_binding(self):
        d=fixture();d["provider_witness"]["symbol"]="OTHERUSDT"
        self.assertIn("QUOTE_SYMBOL_MISMATCH",self.check(d)["blockers"])
        d=fixture();d["monitor"]["quote_body_sha256"]="0"*64
        self.assertIn("MONITOR_WITNESS_NOT_BOUND",self.check(d)["blockers"])

    def test_witness_cannot_be_the_scanner(self):
        for observer in ("SCANNER","RENDER_CRON",""):
            d=fixture();d["provider_witness"]["observer_role"]=observer
            self.assertIn("NO_SEPARATE_OBSERVER",self.check(d)["blockers"])

    def test_old_stale_or_future_quote_not_admissible(self):
        for offset in (-100000,5000):
            d=fixture();d["provider_witness"]["provider_ts_ms"]=T+offset
            self.assertIn("QUOTE_CAPTURE_MONITOR_TEMPORAL_MISMATCH",self.check(d)["blockers"])

    def test_forged_alert_run_or_position(self):
        for field,val in (("run_id","other"),("position_id","other"),
                          ("monitor_receipt_id","other")):
            d=fixture();d["alert"][field]=val
            self.assertIn("ALERT_NOT_BOUND_TO_MONITOR",self.check(d)["blockers"])

    def test_missing_confirmed_delivery(self):
        d=fixture();d["ack"]["recipient_confirmed_delivery"]=False
        self.assertIn("ALERT_RECIPIENT_DELIVERY_UNPROVEN",self.check(d)["blockers"])

    def test_delivery_self_assertion_not_independent(self):
        d=fixture();d["ack"]["independent_delivery_provider_evidence_verified"]=False
        self.assertIn("ALERT_DELIVERY_PROVIDER_EVIDENCE_UNVERIFIED",self.check(d)["blockers"])

    def test_mismatched_recipient(self):
        d=fixture();d["ack"]["recipient_id"]="other-recipient"
        self.assertIn("ALERT_RECIPIENT_ACK_LINK_INVALID",self.check(d)["blockers"])

    def test_missing_timestamps(self):
        d=fixture();d["ack"].pop("delivered_ts_ms")
        self.assertIn("ALERT_DELIVERY_CLOCK_MISSING",self.check(d)["blockers"])

    def test_late_alert_clock(self):
        d=fixture();d["ack"]["delivered_ts_ms"]=T+2000
        self.assertIn("ALERT_DELIVERY_CLOCK_INVALID",self.check(d)["blockers"])

    def test_historical_ambiguity_never_cleared(self):
        d=fixture();d["monitor"]["first_entry_ordering_ambiguous"]=True
        self.assertIn("FIRST_ENTRY_ORDERING_UNRESOLVED",self.check(d)["blockers"])

    def test_real_order_authority_never_allowed(self):
        d=fixture();d["monitor"]["trade_permission"]=True
        self.assertIn("LIVE_TRADE_PERMISSION_NOT_DENIED",self.check(d)["blockers"])

    def test_malformed_witness_is_blocked(self):
        d=fixture();d["provider_witness"]=None
        x=self.check(d)
        self.assertIn("PROVIDER_BODY_SHA256_MISMATCH",x["blockers"])

if __name__=="__main__":
    unittest.main()
