"""Secret-free synthetic successor historical acceptance tests; no production I/O."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1]
          / "ops/reviews/p03_historical_successor_fail_closed_v01.py")
spec = spec_from_file_location("p03_history_guard", SOURCE)
guard = module_from_spec(spec)
spec.loader.exec_module(guard)


def sample():
    scans = [("r1", "2026-11-03T08:02:00Z"),
             ("r2", "2026-11-03T08:22:00Z"),
             ("r3", "2026-11-03T08:42:00Z")]
    parents = [
        {"run_id": rid, "collected_at_utc": at, "run_source": "RENDER_CRON",
         "publication_state": "VERIFIED", "symbol_count": 2, "error_count": 0,
         "expected_symbols": ["SOONUSDT", "NIGHTUSDT"]}
        for rid, at in scans
    ]
    children = [
        {"run_id": rid, "symbol": s, "payload": {"symbol": s}}
        for rid, _ in scans for s in ["SOONUSDT", "NIGHTUSDT"]
    ]
    position = {
        "entry_order_id": "entry-1", "decision_id": "decision-1",
        "symbol": "SOONUSDT", "direction": "SHORT",
        "entry_completed_at_utc": "2026-11-03T08:00:00Z",
    }
    receipts = [
        {"entry_order_id": "entry-1", "decision_id": "decision-1",
         "symbol": "SOONUSDT", "direction": "SHORT", "source_run_id": rid,
         "observed_at_utc": observed, "outcome": "NO_TRIGGER", "blockers": [],
         "paper_only": True, "exchange_authority": False,
         "trade_permission": False, "order_path": "NONE"}
        for rid, observed in [
            ("r1", "2026-11-03T08:03:00Z"),
            ("r2", "2026-11-03T08:23:00Z"),
            ("r3", "2026-11-03T08:43:00Z"),
        ]
    ]
    return dict(
        parents=parents, children=children, receipts=receipts,
        positions=[position], required_run_ids=["r1", "r2", "r3"],
        coverage_attested=True,
        origin_attestations={"entry-1": {"accepted": True,
                                         "artifact_sha256": "a" * 64}},
    )


class HistoricalGuardTests(unittest.TestCase):
    def verdict(self, **modifications):
        payload = sample()
        payload.update(modifications)
        return guard.evaluate_history(**payload)

    def blocked(self, expected, payload):
        old = deepcopy(payload)
        result = guard.evaluate_history(**payload)
        self.assertIn(expected, result["blockers"])
        self.assertFalse(result["successor_historical_evidence_pass"])
        self.assertFalse(result["trade_permission"])
        self.assertFalse(result["production_release_authorized"])
        self.assertEqual(old, payload, "historical inputs must be immutable")

    def test_valid_synthetic_history_evidence_is_not_trade_authority(self):
        result = self.verdict()
        self.assertTrue(result["successor_historical_evidence_pass"])
        self.assertEqual(result["blockers"], ())
        self.assertEqual(result["scans_checked"], 3)
        self.assertFalse(result["trade_permission"])
        self.assertFalse(result["production_release_authorized"])

    def test_real_failure_shape_61_advertised_zero_children_zero_errors(self):
        data = sample()
        data["parents"][1]["symbol_count"] = 61
        data["parents"][1]["expected_symbols"] = [f"S{i}" for i in range(61)]
        data["children"] = [r for r in data["children"] if r["run_id"] != "r2"]
        self.blocked("HISTORICAL_CHILDREN_INCOMPLETE", data)

    def test_historical_partial_child_record_is_rejected(self):
        data = sample()
        data["children"] = [c for c in data["children"] if not (
            c["run_id"] == "r1" and c["symbol"] == "NIGHTUSDT")]
        self.blocked("HISTORICAL_CHILDREN_INCOMPLETE", data)

    def test_same_count_with_wrong_child_identity_is_rejected(self):
        data = sample()
        data["children"][0]["symbol"] = "UNEXPECTED"
        data["children"][0]["payload"]["symbol"] = "UNEXPECTED"
        self.blocked("HISTORICAL_CHILDREN_INCOMPLETE", data)

    def test_mismatched_child_payload_is_rejected(self):
        data = sample()
        data["children"][0]["payload"]["symbol"] = "WRONG"
        self.blocked("CHILD_PAYLOAD_IDENTITY_MISMATCH", data)

    def test_legacy_unmarked_parent_not_retroactively_certified(self):
        data = sample()
        data["parents"][0]["publication_state"] = None
        self.blocked("HISTORICAL_PARENT_UNVERIFIED", data)

    def test_duplicate_parent_and_missing_manifest_are_rejected(self):
        data = sample()
        data["parents"].append(deepcopy(data["parents"][0]))
        self.blocked("DUPLICATE_PARENT_RUN_ID", data)
        data = sample()
        data["required_run_ids"] = ["r1", "r3"]
        self.blocked("REQUIRED_RUN_MANIFEST_MISMATCH", data)

    def test_unattested_coverage_fails_even_when_rows_look_valid(self):
        data = sample()
        data["coverage_attested"] = False
        self.blocked("INDEPENDENT_HISTORY_COVERAGE_NOT_ATTESTED", data)

    def test_no_origin_attestation_cannot_synthesize_first_baseline(self):
        data = sample()
        data["origin_attestations"]["entry-1"]["accepted"] = False
        self.blocked("FIRST_ENTRY_ORIGIN_NOT_ATTESTED", data)

    def test_invalid_origin_hash_and_extra_origin_are_rejected(self):
        data = sample()
        data["origin_attestations"]["entry-1"]["artifact_sha256"] = "test"
        self.blocked("FIRST_ENTRY_ORIGIN_NOT_ATTESTED", data)
        data = sample()
        data["origin_attestations"]["another"] = {"accepted": True,
                                                    "artifact_sha256": "b" * 64}
        self.blocked("ORIGIN_MANIFEST_MISMATCH", data)

    def test_ambiguous_first_same_snapshot_is_preserved_and_rejected(self):
        data = sample()
        data["receipts"][0]["observed_at_utc"] = (
            data["positions"][0]["entry_completed_at_utc"])
        self.blocked("AMBIGUOUS_FIRST_ENTRY_ORDERING", data)

    def test_unusable_first_receipt_is_not_reclassified(self):
        data = sample()
        data["receipts"][0]["outcome"] = "AMBIGUOUS"
        self.blocked("UNUSABLE_HISTORICAL_RECEIPT", data)

    def test_missing_middle_receipt_fails_despite_newer_good_receipt(self):
        data = sample()
        data["receipts"].pop(1)
        self.blocked("HISTORICAL_POSITION_RECEIPT_COVERAGE_FAILED", data)

    def test_earlier_420_minute_gap_cannot_be_healed_by_latest_receipt(self):
        data = sample()
        data["parents"][1]["collected_at_utc"] = "2026-11-03T15:22:00Z"
        data["parents"][2]["collected_at_utc"] = "2026-11-03T15:42:00Z"
        data["receipts"][1]["observed_at_utc"] = "2026-11-03T15:23:00Z"
        data["receipts"][2]["observed_at_utc"] = "2026-11-03T15:43:00Z"
        self.blocked("HISTORICAL_MONITORING_GAP_OVER_35M", data)

    def test_exact_35_minute_gap_passes_when_other_evidence_complete(self):
        data = sample()
        data["parents"][1]["collected_at_utc"] = "2026-11-03T08:37:00Z"
        data["receipts"][1]["observed_at_utc"] = "2026-11-03T08:38:00Z"
        data["parents"][2]["collected_at_utc"] = "2026-11-03T08:57:00Z"
        data["receipts"][2]["observed_at_utc"] = "2026-11-03T08:58:00Z"
        self.assertTrue(guard.evaluate_history(**data)["successor_historical_evidence_pass"])

    def test_over_35_minute_gap_rejected_to_second(self):
        data = sample()
        data["parents"][1]["collected_at_utc"] = "2026-11-03T08:37:01Z"
        data["receipts"][1]["observed_at_utc"] = "2026-11-03T08:38:01Z"
        data["parents"][2]["collected_at_utc"] = "2026-11-03T08:57:01Z"
        data["receipts"][2]["observed_at_utc"] = "2026-11-03T08:58:01Z"
        self.blocked("HISTORICAL_MONITORING_GAP_OVER_35M", data)

    def test_duplicate_receipt_cannot_erase_gap(self):
        data = sample()
        data["receipts"].append(deepcopy(data["receipts"][-1]))
        self.blocked("DUPLICATE_RECEIPT_FOR_RUN", data)

    def test_wrong_position_and_run_references_fail(self):
        data = sample()
        data["receipts"][0]["symbol"] = "NIGHTUSDT"
        self.blocked("RECEIPT_POSITION_IDENTITY_MISMATCH", data)
        data = sample()
        data["receipts"][0]["source_run_id"] = "invented"
        self.blocked("ORPHAN_RECEIPT", data)

    def test_missing_or_invalid_timezone_fails_closed(self):
        data = sample()
        data["receipts"][0]["observed_at_utc"] = "2026-11-03T08:03:00"
        self.blocked("RECEIPT_TIME_INVALID", data)

    def test_receipt_without_paper_only_constraints_fails(self):
        data = sample()
        data["receipts"][0]["trade_permission"] = True
        self.blocked("HISTORICAL_AUTHORITY_INVALID", data)

    def test_wrong_frozen_35_minute_parameter_rejected(self):
        data = sample()
        data["max_gap_minutes"] = 40
        self.blocked("FROZEN_35M_RULE_CHANGED", data)

    def test_untrusted_parent_run_source_rejected(self):
        data = sample()
        data["parents"][0]["run_source"] = "UNMARKED"
        self.blocked("UNTRUSTED_PARENT_SOURCE", data)

    def test_incomplete_data_never_passes(self):
        data = sample()
        data["parents"] = None
        self.blocked("HISTORY_DATASET_MISSING", data)

    def test_no_network_or_production_runtime_imports(self):
        text = SOURCE.read_text(encoding="utf-8")
        for forbidden in ("import requests", "import supabase", "from alpha_hunter",
                          "subprocess", "os.environ", "urllib.request"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
