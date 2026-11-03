"""P0 forward-only dual-witness synthetic contract. No network/DB/producer I/O."""
import base64
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

import pytest
pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SRC = Path(__file__).resolve().parents[1] / "ops/reviews/p03_prospective_dual_witness_chain_v01.py"
spec = spec_from_file_location("prospective_evidence_guard", SRC)
guard = module_from_spec(spec)
spec.loader.exec_module(guard)


def signing_key():
    key = Ed25519PrivateKey.generate()  # synthetic in-memory only
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    return key, pub


def sig(key, item):
    return base64.b64encode(key.sign(guard.canonical(item))).decode("ascii")


def fixture():
    signed_schedule = {
        "cohort_id": "R11-ISOLATED-FUTURE",
        "legacy_census_head": guard.LEGACY_FROZEN_CENSUS_HEAD,
        "legacy_acceptance": "EVIDENCE_NO_GO",
        "genesis_utc": "2026-11-03T10:40:00Z",
        "active_positions": [
            {"entry_order_id": "pos-new-1", "entry_at_utc": "2026-11-03T10:40:30Z"}],
        "expected_runs": [
            {"run_id": f"new{i}", "scheduled_utc": f"2026-11-03T{clock}:00Z",
             "expected_symbols": ["SOONUSDT", "NIGHTUSDT"]}
            for i, clock in [(1,"10:41"),(2,"11:01"),(3,"11:21")]],
    }
    events = []
    previous = "GENESIS"
    for i, time in [(1, "10:42"), (2, "11:02"), (3, "11:22")]:
        event = {
            "cohort_id": "R11-ISOLATED-FUTURE",
            "run_id": f"new{i}",
            "previous_event_sha256": previous,
            "observed_at_utc": f"2026-11-03T{time}:00Z",
            "persisted_children": [
                {"run_id": f"new{i}", "symbol": symbol,
                 "payload": {"symbol": symbol}}
                for symbol in ("SOONUSDT", "NIGHTUSDT")],
            "position_receipts": [{
                "entry_order_id": "pos-new-1", "source_run_id": f"new{i}",
                "observed_at_utc": f"2026-11-03T{time}:00Z",
                "outcome": "NO_TRIGGER", "blockers": [],
                "paper_only": True, "trade_permission": False,
                "exchange_authority": False, "order_path": "NONE",
            }],
        }
        previous = guard.digest(event)
        events.append(event)
    return signed_schedule, events


def run(modifier=None, same_signer=False):
    schedule, events = fixture()
    if modifier:
        modifier(schedule, events)
    schedule_key, schedule_pub = signing_key()
    event_key, event_pub = (schedule_key, schedule_pub) if same_signer else signing_key()
    envelopes = [{"event": event, "signature_b64": sig(event_key, event)}
                 for event in events]
    return guard.validate_forward_history(
        schedule=schedule,
        schedule_signature_b64=sig(schedule_key, schedule),
        trusted_schedule_public_hex=schedule_pub,
        event_envelopes=envelopes,
        trusted_event_public_hex=event_pub,
    )


class ProspectiveWitnessTests(unittest.TestCase):
    def assert_blocked(self, code, modify):
        result = run(modify)
        self.assertEqual(result["status"], "PROSPECTIVE_EVIDENCE_NO_GO")
        self.assertIn(code, result["blockers"])
        self.assertFalse(result["trade_permission"])
        self.assertFalse(result["production_release_authorized"])

    def test_complete_two_signer_new_cohort_is_contract_only(self):
        result = run()
        self.assertEqual(result["status"], "ISOLATED_PROSPECTIVE_CONTRACT_PASS_ONLY")
        self.assertTrue(result["prospective_chain_shape_valid"])
        self.assertEqual(result["future_runs_checked"], 3)
        self.assertFalse(result["provider_quotes_independently_authenticated"])
        self.assertFalse(result["independent_human_approval"])
        self.assertFalse(result["production_release_authorized"])
        self.assertFalse(result["trade_permission"])

    def test_same_signer_is_not_independent_witnesses(self):
        self.assertIn("INDEPENDENT_WITNESS_KEYS_OR_DATA_MISSING",
                      run(same_signer=True)["blockers"])

    def test_legacy_acceptance_cannot_be_rewritten(self):
        self.assert_blocked("LEGACY_HISTORICAL_OUTCOME_REWRITE_ATTEMPT",
                            lambda s, e: s.update(legacy_acceptance="PASS"))

    def test_legacy_branch_anchor_cannot_be_swapped(self):
        self.assert_blocked("LEGACY_CENSUS_PIN_MISMATCH",
                            lambda s, e: s.update(legacy_census_head="0" * 40))

    def test_pre_genesis_cohort_rejected(self):
        self.assert_blocked("GENESIS_NOT_AFTER_FROZEN_ARCHIVE",
                            lambda s, e: s.update(genesis_utc="2026-11-03T10:30:00Z"))

    def test_legacy_position_cannot_migrate_into_successor(self):
        self.assert_blocked("LEGACY_OR_PRE_GENESIS_POSITION_FORBIDDEN",
                            lambda s, e: s["active_positions"][0].update(
                                entry_at_utc="2026-11-03T09:00:00Z"))

    def test_missing_run_rejected(self):
        self.assert_blocked("OBSERVATION_RUN_COUNT_MISMATCH",
                            lambda s, e: e.pop(1))

    def test_missing_child_never_passes_even_signed(self):
        self.assert_blocked("PROSPECTIVE_CHILD_CENSUS_INCOMPLETE",
                            lambda s, e: e[1]["persisted_children"].pop())

    def test_duplicate_child_rejected(self):
        self.assert_blocked("PROSPECTIVE_CHILD_CENSUS_INCOMPLETE",
                            lambda s, e: e[0]["persisted_children"].__setitem__(
                                1, deepcopy(e[0]["persisted_children"][0])))

    def test_missing_position_receipt_fails(self):
        self.assert_blocked("PROSPECTIVE_POSITION_RECEIPT_COVERAGE_FAILED",
                            lambda s, e: e[1].update(position_receipts=[]))

    def test_empty_signed_position_inventory_does_not_cover_held_receipt(self):
        self.assert_blocked("UNSCHEDULED_POSITION_RECEIPT",
                            lambda s, e: s.update(active_positions=[]))

    def test_new_run_cannot_erase_old_monitored_gap(self):
        def modify(s,e):
            s["expected_runs"][1]["scheduled_utc"] = "2026-11-03T11:31:00Z"
            s["expected_runs"][2]["scheduled_utc"] = "2026-11-03T11:51:00Z"
            e[1]["observed_at_utc"] = "2026-11-03T11:32:00Z"
            e[1]["position_receipts"][0]["observed_at_utc"] = "2026-11-03T11:32:00Z"
            e[2]["observed_at_utc"] = "2026-11-03T11:52:00Z"
            e[2]["position_receipts"][0]["observed_at_utc"] = "2026-11-03T11:52:00Z"
            # The hash-link needs to change after mutating the previous event.
            e[2]["previous_event_sha256"] = guard.digest(e[1])
        self.assert_blocked("PROSPECTIVE_POSITION_GAP_OVER_35M", modify)

    def test_missing_chain_link_detected_even_with_new_signatures(self):
        self.assert_blocked("OBSERVATION_CHAIN_BROKEN",
                            lambda s,e: e[1].update(previous_event_sha256="0"*64))

    def test_ambiguous_first_receipt_at_fill_time_rejected(self):
        def modify(s,e):
            s["active_positions"][0]["entry_at_utc"] = "2026-11-03T10:42:00Z"
        self.assert_blocked("FIRST_ENTRY_ORIGIN_GAP_OR_AMBIGUITY",modify)

    def test_r8_cohort_not_allowed(self):
        self.assert_blocked("NEW_SUCCESSOR_COHORT_ID_MISSING",
                            lambda s,e: s.update(cohort_id="R8"))

    def test_bad_timezone_rejected(self):
        self.assert_blocked("SCHEDULE_TIME_INVALID",
                            lambda s,e: s["expected_runs"][1].update(
                                scheduled_utc="2026-11-03T11:01:00"))

    def test_authority_never_permitted_even_in_observation(self):
        self.assert_blocked("PROSPECTIVE_RECEIPT_UNUSABLE",
                            lambda s,e: e[0]["position_receipts"][0].update(trade_permission=True))

    def test_missing_witness_keys_fails(self):
        schedule, events = fixture()
        result = guard.validate_forward_history(
            schedule=schedule,schedule_signature_b64="",
            trusted_schedule_public_hex="",
            event_envelopes=[],trusted_event_public_hex="")
        self.assertFalse(result["prospective_chain_shape_valid"])
        self.assertFalse(result["trade_permission"])


if __name__ == "__main__":
    unittest.main()
