"""Offline P0 negative-custody and first-entry regression coverage."""
import importlib.util
import unittest
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "ops/reviews/phase2_source_custody_and_baseline_v01.py"
spec = importlib.util.spec_from_file_location("source_custody",source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fixture():
    fp = "test-frozen-fingerprint"
    parent = dict(
        run_id="prior-001",symbol_count=1,collected_at_utc="2026-11-02T09:20:00Z",
        payload={"_canonical_publication_state":"VERIFIED",
                 "validation_identity":{
                     "run_source":"RENDER_CRON", "runtime_role":"RENDER_CRON",
                     "scientific_fingerprint_sha256":fp}},
    )
    children=[dict(run_id="prior-001",symbol="BTCUSDT",
                   payload={"symbol":"BTCUSDT"})]
    receipt=dict(source_run_id="prior-001",symbol="BTCUSDT",
                 observed_at_utc="2026-11-02T09:21:00Z",paper_only=True,
                 exchange_authority=False,trade_permission=False)
    pos=dict(entry_order_id="order-1",decision_id="decision-1",
             symbol="BTCUSDT", entry_completed_source_run_id="prior-001",
             entry_completed_at_utc="2026-11-02T09:21:00Z",
             protection_count=2,stop_protective_order_id="stop-1",
             target_protective_order_id="tp-1",horizon_integrity_failed=False,
             unresolved_protective_evidence=False,paper_only=True)
    fill=dict(order_id="order-1",source_run_id="prior-001",quantity=4.0,
              paper_only=True,exchange_authority=False)
    first=dict(entry_order_id="order-1",decision_id="decision-1",
               symbol="BTCUSDT",observed_at_utc="2026-11-02T09:41:00Z",
               source_run_id="monitor-2",outcome="NO_TRIGGER",blockers=[],
               paper_only=True,exchange_authority=False,trade_permission=False,
               order_path="NONE")
    return dict(fp=fp,parent=parent,children=children,receipt=receipt,
                pos=pos,fill=fill,first=first)

class SourceCustodyTests(unittest.TestCase):
    def source(self, **kw):
        v=fixture()
        return m.attest_previous_source(
            receipt=kw.get("receipt",v["receipt"]),
            parent=kw.get("parent",v["parent"]),
            children=kw.get("children",v["children"]),
            expected_fingerprint=kw.get("fp",v["fp"]))

    def baseline(self, **kw):
        v=fixture()
        return m.assess_first_entry_baseline(
            position=kw.get("pos",v["pos"]),entry_fills=kw.get("fills",[v["fill"]]),
            entry_parent=kw.get("parent",v["parent"]),
            entry_children=kw.get("children",v["children"]),
            first_observation=kw.get("first",v["first"]),
            expected_fingerprint=kw.get("fp",v["fp"]))

    def test_valid_db_custody_is_not_independent_authentication(self):
        r=self.source()
        self.assertEqual(r["status"],"DB_CUSTODY_LINKED_NOT_INDEPENDENTLY_AUTHENTICATED")
        self.assertFalse(r["independently_authenticated"])
        self.assertFalse(r["trade_permission"])

    def test_unmarked_legacy_parent_rejected(self):
        v=fixture();v["parent"]["payload"].pop("_canonical_publication_state")
        self.assertIn("SOURCE_PARENT_NOT_VERIFIED",self.source(parent=v["parent"])["blockers"])

    def test_missing_parent_rejected(self):
        self.assertIn("SOURCE_OR_RECEIPT_MISSING",self.source(parent=None)["blockers"])

    def test_false_run_source_and_fingerprint_rejected(self):
        v=fixture();v["parent"]["payload"]["validation_identity"]["run_source"]="WEB"
        self.assertIn("SOURCE_RUNTIME_IDENTITY_UNVERIFIED",self.source(parent=v["parent"])["blockers"])
        self.assertIn("SOURCE_SCIENTIFIC_FINGERPRINT_MISMATCH",self.source(fp="other")["blockers"])

    def test_mismatched_parent_and_receipt_run_rejected(self):
        v=fixture();v["receipt"]["source_run_id"]="unrelated"
        self.assertIn("SOURCE_RUN_PARENT_MISMATCH",self.source(receipt=v["receipt"])["blockers"])

    def test_zero_or_wrong_source_children_rejected(self):
        self.assertIn("SOURCE_CHILD_CENSUS_INCOMPLETE",self.source(children=[])["blockers"])
        v=fixture();v["children"][0]["payload"]["symbol"]="FAKEUSDT"
        self.assertIn("SOURCE_CHILD_IDENTITY_INVALID",self.source(children=v["children"])["blockers"])

    def test_invalid_observation_clock_rejected(self):
        v=fixture();v["receipt"]["observed_at_utc"]="2026-11-02T09:19:00Z"
        self.assertIn("SOURCE_OBSERVATION_CLOCK_INVALID",self.source(receipt=v["receipt"])["blockers"])
        v=fixture();v["receipt"]["observed_at_utc"]="2026-11-02T09:21:00"
        self.assertIn("SOURCE_TIMESTAMP_MISSING",self.source(receipt=v["receipt"])["blockers"])

    def test_no_live_order_permission(self):
        v=fixture();v["receipt"]["trade_permission"]=True
        self.assertIn("RECEIPT_PERMISSION_INVALID",self.source(receipt=v["receipt"])["blockers"])

    def test_first_entry_is_only_candidate_even_if_complete(self):
        r=self.baseline()
        self.assertEqual(r["status"],"CANDIDATE_NEEDS_INDEPENDENT_PROVIDER_AND_PROTECTION_ATTESTATION")
        self.assertFalse(r["monitoring_baseline_authorized"])
        self.assertFalse(r["trade_permission"])

    def test_initial_36_minute_gap_rejected(self):
        v=fixture();v["first"]["observed_at_utc"]="2026-11-02T09:57:01Z"
        self.assertIn("INITIAL_ENTRY_TO_MONITORING_GAP_INVALID",self.baseline(first=v["first"])["blockers"])

    def test_recorded_protection_not_unresolved(self):
        v=fixture();v["pos"]["unresolved_protective_evidence"]=True
        self.assertIn("ENTRY_PROTECTIVE_ACKNOWLEDGEMENT_UNVERIFIED",self.baseline(pos=v["pos"])["blockers"])

    def test_missing_or_mismatched_fill(self):
        self.assertIn("ENTRY_FILL_CUSTODY_UNVERIFIED",self.baseline(fills=[])["blockers"])
        v=fixture();v["fill"]["source_run_id"]="other"
        self.assertIn("ENTRY_FILL_CUSTODY_UNVERIFIED",self.baseline(fills=[v["fill"]])["blockers"])

    def test_first_entry_missing_parent_is_not_a_baseline(self):
        self.assertIn("SOURCE_OR_RECEIPT_MISSING",self.baseline(parent=None)["blockers"])

    def test_first_observation_identity_mismatch(self):
        v=fixture();v["first"]["entry_order_id"]="other"
        self.assertIn("FIRST_OBSERVATION_POSITION_IDENTITY_INVALID",self.baseline(first=v["first"])["blockers"])


    def test_ambiguous_first_receipt_is_hard_blocker_even_with_valid_quantities(self):
        v=fixture()
        v["first"]["outcome"]="AMBIGUOUS"
        v["first"]["blockers"]=["ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT"]
        self.assertIn("FIRST_OBSERVATION_AMBIGUOUS_OR_BLOCKED",self.baseline(first=v["first"])["blockers"])

    def test_initial_receipt_missing_or_nonpaper_authority_is_invalid(self):
        v=fixture();v["first"].pop("source_run_id")
        self.assertIn("FIRST_OBSERVATION_SOURCE_UNVERIFIED",self.baseline(first=v["first"])["blockers"])
        v=fixture();v["first"]["exchange_authority"]=True
        self.assertIn("FIRST_OBSERVATION_AUTHORITY_UNVERIFIED",self.baseline(first=v["first"])["blockers"])

if __name__ == "__main__":
    unittest.main()
