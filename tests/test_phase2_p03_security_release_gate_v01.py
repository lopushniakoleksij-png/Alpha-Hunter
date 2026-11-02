"""P0.3 negative-release acceptance contract; 100% offline and read-only."""
import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("p03_security_gate",
    ROOT/"ops/reviews/phase2_p03_security_release_gate_v01.py")
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
BASE=json.loads((ROOT/"ops/reviews/p03_live_prod_security_baseline_20261102.json").read_text())


class P03SafetyTests(unittest.TestCase):
    def audit(self, doc=None):
        report=gate.assess(BASE if doc is None else doc)
        self.assertEqual(report["status"],"PRODUCTION_NO_GO")
        self.assertFalse(report["release_action_permitted"])
        self.assertFalse(report["branch_merge_permitted"])
        self.assertFalse(report["production_sql_permitted"])
        self.assertFalse(report["real_trade_permission"])
        return report

    def test_frozen_actual_catalog_is_no_go_but_invariants_intact(self):
        result=self.audit()
        self.assertEqual(result["critical_invariants"],[])
        self.assertIn("MAIN_BRANCH_NOT_ENFORCEABLY_PROTECTED",result["blockers"])
        self.assertIn("PRIVILEGED_SERVICE_ROLE_REQUIRES_INDEPENDENT_API_AUTHZ",result["blockers"])

    def test_real_service_bypass_is_not_a_security_approval(self):
        self.assertIn("PRIVILEGED_SERVICE_ROLE_REQUIRES_INDEPENDENT_API_AUTHZ",self.audit()["blockers"])

    def test_public_sql_grants_do_not_automatically_mean_allowed_rows(self):
        r=self.audit()
        self.assertIn("OVERBROAD_SQL_PUBLIC_WRITE_GRANT:alpha_hunter_snapshots",r["blockers"])
        self.assertNotIn("RLS_NOT_VERIFIED:alpha_hunter_snapshots",r["critical_invariants"])

    def test_disabling_rls_fails_critical_guard(self):
        b=copy.deepcopy(BASE)
        b["relations"]["alpha_hunter_snapshots"]["rls_enabled"]=False
        self.assertIn("RLS_NOT_VERIFIED:alpha_hunter_snapshots",self.audit(b)["critical_invariants"])

    def test_public_definer_exec_fails_critical_guard(self):
        b=copy.deepcopy(BASE)
        b["functions"]["public_security_definer_anon_executable"]=1
        self.assertIn("PUBLIC_EXECUTABLE_SECURITY_DEFINER",self.audit(b)["critical_invariants"])

    def test_private_schema_usage_exposure_fails_critical_guard(self):
        b=copy.deepcopy(BASE)
        b["functions"]["private_schema_authenticated_usage"]=True
        self.assertIn("PRIVATE_SCHEMA_PUBLIC_USAGE",self.audit(b)["critical_invariants"])

    def test_any_public_bypass_rls_is_never_permitted(self):
        b=copy.deepcopy(BASE)
        b["roles"]["anon"]["bypassrls"]=True
        self.assertIn("UNSAFE_ANONYMOUS_RLS_BYPASS",self.audit(b)["critical_invariants"])

    def test_quote_custody_and_alert_ack_are_independent_gates(self):
        r=self.audit()
        self.assertIn("LEGACY_MONITORING_RECEIPTS_NOT_VERIFIED",r["blockers"])
        self.assertIn("UNSIGNED_OR_UNATTESTED_PROVIDER_QUOTE_CUSTODY",r["blockers"])
        self.assertIn("DURABLE_ALERT_RECIPIENT_CONFIRMATION_UNPROVEN",r["blockers"])

    def test_main_auto_deploy_and_unprotected_branch_block_release(self):
        r=self.audit()
        self.assertIn("PROTECTED_MAIN_AUTO_DEPLOY_ENABLED",r["blockers"])
        self.assertIn("MAIN_BRANCH_NOT_ENFORCEABLY_PROTECTED",r["blockers"])

    def test_same_protected_cron_target_always_blocked(self):
        b=copy.deepcopy(BASE)
        b["release_surface"]["protected_cron"]["service_id"]="protected-cron"
        b["release_surface"]["approved_isolated_successor_service"]={
            "service_id":"protected-cron","isolated":True,"source_branch":"successor/review",
            "auto_deploy":False}
        self.assertIn("RELEASE_TARGET_IS_PROTECTED_CRON",self.audit(b)["critical_invariants"])

    def test_target_tracking_main_or_auto_deploy_blocked(self):
        for source,auto in (("main",False),("successor/review",True)):
            with self.subTest(source=source,auto=auto):
                b=copy.deepcopy(BASE)
                b["release_surface"]["approved_isolated_successor_service"]={
                    "service_id":"isolated-staging","isolated":True,
                    "source_branch":source,"auto_deploy":auto}
                self.assertIn("RELEASE_TARGET_CAN_TRIGGER_MAIN_OR_UNATTENDED_DEPLOY",
                              self.audit(b)["critical_invariants"])

    def test_signoffs_cannot_be_self_issued(self):
        for key in gate.REQUIRED_APPROVALS:
            self.assertIn("HUMAN_RELEASE_APPROVAL_MISSING:"+key,
                          self.audit()["blockers"])
        b=copy.deepcopy(BASE)
        for key in gate.REQUIRED_APPROVALS:
            b["release_surface"][key]=True
        self.audit(b)
        self.assertFalse(gate.assess(b)["release_action_permitted"])

    def test_historical_ambiguous_first_entries_are_not_reclassified(self):
        r=self.audit()
        self.assertIn("FIRST_ENTRY_ORDERING_STILL_UNRESOLVED",r["blockers"])

    def test_no_trading_authority_change(self):
        b=copy.deepcopy(BASE)
        b["immutable_positions"]["real_order_permission"]=True
        self.assertIn("REAL_ORDER_AUTHORITY_NOT_DENIED",self.audit(b)["critical_invariants"])

    def test_missing_evidence_denied(self):
        b=copy.deepcopy(BASE)
        b["source_custody"].pop("verified_parent_receipts")
        self.assertIn("SOURCE_CUSTODY_COUNTS_MISSING",self.audit(b)["critical_invariants"])

if __name__=="__main__":
    unittest.main()
