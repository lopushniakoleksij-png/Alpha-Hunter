"""R11 isolated prospective 3-scan contract tests. All synthetic, no network."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import json

FILE=(Path(__file__).resolve().parents[1]/
      "ops/reviews/p03_r11_attested_forward_3scan_pilot_v01.py")
spec=importlib.util.spec_from_file_location("r11_future_pilot",FILE)
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

NOW=datetime(2026,11,3,12,0,0,tzinfo=timezone.utc)


def fixture():
    schedule=v.make_schedule(NOW,"876543")
    events,raw={},{}
    events=[]
    previous="GENESIS"
    for index,plan in enumerate(schedule["required_runs"]):
        when=v.parse_time(plan["scheduled_at_utc"])+timedelta(seconds=4)
        ticker=json.dumps({"code":"00000","data":[{"symbol":"BTCUSDT"}]}).encode()
        book=json.dumps({"code":"00000","data":{"a":[["70001","1"]],"b":[["70000","1"]]}}).encode()
        cap={
          "ticker":{"raw":ticker,"parsed":{"source_timestamp_ms":1793700000000}},
          "orderbook":{"raw":book,"parsed":{"source_timestamp_ms":1793700000000}},
        }
        event=v.build_event(schedule,index,cap,when,previous)
        raw[plan["run_id"]]={"ticker":ticker,"orderbook":book}
        events.append(event)
        previous=v.sha(v.canonical(event))
    return schedule,events,raw


class R11ForwardPilotTests(TestCase):
    def assert_no_go(self,reason,mutator,repair_hash_chain=False):
        schedule,events,raw=fixture()
        mutator(schedule,events,raw)
        if repair_hash_chain:
            previous="GENESIS"
            for e in events:
                e["previous_event_sha256"]=previous
                previous=v.sha(v.canonical(e))
        with self.assertRaisesRegex(v.EvidenceNoGo,reason):
            v.validate_events(schedule,events,raw)

    def test_valid_three_actual_packet_structures_for_synthetic_fixture(self):
        s,e,raw=fixture()
        out=v.validate_events(s,e,raw)
        self.assertEqual(out["observed_runs"],3)
        self.assertEqual(out["synthetic_diagnostic_receipts"],3)
        self.assertFalse(out["continuous_long_term_monitoring_proven"])
        self.assertEqual(out["prospective_dual_human_signer_gate"],"NO_GO")
        self.assertEqual(out["real_paper_positions_observed"],0)
        self.assertFalse(out["trade_permission"])
        self.assertFalse(out["production_release_authorized"])
        self.assertEqual(out["legacy_evidence_status"],"EVIDENCE_NO_GO")

    def test_schedule_is_forward_75_second_intervals(self):
        s,_,_=fixture()
        self.assertEqual(len(s["required_runs"]),3)
        times=[v.parse_time(x["scheduled_at_utc"]) for x in s["required_runs"]]
        self.assertEqual((times[1]-times[0]).total_seconds(),75)
        self.assertEqual((times[2]-times[1]).total_seconds(),75)
        self.assertLess((times[-1]-times[0]).total_seconds(),35*60)

    def test_missing_middle_run_fails(self):
        self.assert_no_go("REQUIRED_RUNS_MISSING",lambda s,e,r:e.pop(1))

    def test_missing_diagnostic_probe_receipt_fails(self):
        self.assert_no_go("DIAGNOSTIC_POSITION_RECEIPT_MISSING",
                          lambda s,e,r:e[1].update(position_receipts=[]),True)

    def test_wrong_probe_identity_fails(self):
        self.assert_no_go("DIAGNOSTIC_POSITION_RECEIPT_MISSING",
                          lambda s,e,r:e[0]["position_receipts"][0].update(entry_order_id="legacy"),True)

    def test_mismatched_position_receipt_run_fails(self):
        self.assert_no_go("DIAGNOSTIC_POSITION_RECEIPT_MISSING",
                          lambda s,e,r:e[2]["position_receipts"][0].update(source_run_id="bad"),True)

    def test_probe_is_not_real_position(self):
        self.assert_no_go("DIAGNOSTIC_POSITION_RECEIPT_MISSING",
                          lambda s,e,r:e[1]["position_receipts"][0].update(no_actual_alpha_hunter_position=False),True)

    def test_position_40min_gap_cannot_be_healed_by_next_scan(self):
        def shift(s,e,r):
            for i in (1,2):
                when=v.parse_time(e[i]["observed_at_utc"])+timedelta(minutes=40)
                e[i]["observed_at_utc"]=v.utc(when)
                e[i]["position_receipts"][0]["observed_at_utc"]=v.utc(when)
        self.assert_no_go("LATE_OR_EARLY_SCAN_OUTSIDE_35M",shift,True)

    def test_exact_35min_gap_boundary_fails_if_scan_late(self):
        def delay(s,e,r):
            target=v.parse_time(s["required_runs"][1]["scheduled_at_utc"])+timedelta(seconds=2101)
            e[1]["observed_at_utc"]=v.utc(target)
            e[1]["position_receipts"][0]["observed_at_utc"]=v.utc(target)
        self.assert_no_go("LATE_OR_EARLY_SCAN_OUTSIDE_35M",delay,True)

    def test_schedule_36min_gap_fails(self):
        def shift(s,e,r):
            s["required_runs"][1]["scheduled_at_utc"]=v.utc(
                v.parse_time(s["required_runs"][0]["scheduled_at_utc"])+timedelta(minutes=36))
        self.assert_no_go("SCHEDULE_GAP_OVER_35M",shift)

    def test_raw_quote_change_fails(self):
        def mutate(s,e,r):
            r[s["required_runs"][1]["run_id"]]["ticker"]=b'{"modified":true}'
        self.assert_no_go("RAW_SOURCE_SHA256_MISMATCH",mutate)

    def test_wrong_child_identity_fails(self):
        self.assert_no_go("CHILD_EVIDENCE_MISSING_OR_DIFFERENT",
                          lambda s,e,r:e[0]["persisted_children"][0].update(symbol="ETHUSDT"),True)

    def test_child_repeated_instead_of_missing_fails(self):
        self.assert_no_go("CHILD_EVIDENCE_MISSING_OR_DIFFERENT",
                          lambda s,e,r:e[1]["persisted_children"].append(deepcopy(e[1]["persisted_children"][0])),True)

    def test_damaged_event_hash_chain_fails(self):
        self.assert_no_go("RUN_ID_OR_EVENT_HASH_CHAIN_INVALID",
                          lambda s,e,r:e[1].update(previous_event_sha256="0"*64))

    def test_legacy_outcomes_cannot_be_promoted(self):
        self.assert_no_go("AUTHORITY_OR_LEGACY_INVALID",
                          lambda s,e,r:s.update(legacy_history_reclassified=True))

    def test_trade_permission_never_granted(self):
        self.assert_no_go("AUTHORITY_OR_LEGACY_INVALID",
                          lambda s,e,r:s.update(trade_permission=True))

    def test_approval_cannot_be_forged_as_human(self):
        self.assert_no_go("AUTHORITY_OR_LEGACY_INVALID",
                          lambda s,e,r:s.update(independent_human_controller_approved=True))

    def test_missing_captured_raw_is_rejected(self):
        self.assert_no_go("RAW_SOURCE_CAPTURE_MISSING",
                          lambda s,e,r:r.pop(s["required_runs"][1]["run_id"]))

    def test_no_pre_genesis_paper_entry(self):
        self.assert_no_go("PROBE_ENTRY_ORIGIN_INVALID",
                          lambda s,e,r:s["diagnostic_position"].update(
                              entry_at_utc=s["genesis_utc"]))

    def test_extra_capture_cannot_count_as_valid(self):
        self.assert_no_go("EXTRA_OR_MISSING_CAPTURE",
                          lambda s,e,r:r.update(extra={"ticker":b"1","orderbook":b"2"}))

    def test_market_bytes_are_only_of_public_source(self):
        source=FILE.read_text(encoding="utf-8")
        self.assertNotIn("place-order",source)
        self.assertNotIn("create_order",source)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY)",source)

if __name__=="__main__":
    import unittest
    unittest.main()
