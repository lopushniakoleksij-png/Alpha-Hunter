"""Real-source DB census archive contract: NO-GO until full independent custody.

No database/exchange/network access. This checks the pinned aggregate archive
but does NOT pretend a database-derived hash is provider authentication.
"""
import base64
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import re
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = (ROOT / "ops/reviews/20261103_p03_readonly_historical_census_no_go.json")
VAL = ROOT / "ops/reviews/p03_isolated_signed_history_postgrest_v01.py"
spec = spec_from_file_location("p03_local_history_reader", VAL)
validator = module_from_spec(spec)
spec.loader.exec_module(validator)


class ArchivedRealCensusNO_GO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(ARCHIVE.read_text(encoding="utf-8"))

    def test_pinned_31day_census_is_well_formed(self):
        x = self.data
        days = x["days"]
        self.assertEqual(len(days), 31)
        self.assertEqual(len(set(d["utc_date"] for d in days)), 31)
        self.assertEqual(days[0]["utc_date"], "2026-10-04")
        self.assertEqual(days[-1]["utc_date"], "2026-11-03")
        for day in days:
            self.assertRegex(day["census_sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(day["parent_runs"], 0)
            self.assertGreaterEqual(day["advertised_symbols"], day["persisted_child_rows"])

    def test_no_go_is_not_weakened_by_partial_archive(self):
        x = self.data
        self.assertEqual(x["totals"]["parent_runs"], 2160)
        self.assertEqual(x["totals"]["zero_child_runs"], 259)
        self.assertEqual(x["totals"]["incomplete_child_runs"], 259)
        self.assertEqual(x["totals"]["verified_pub_markers"], 0)
        self.assertEqual(x["totals"]["advertised_symbols"], 129372)
        self.assertEqual(x["totals"]["saved_children"], 113846)
        for field in ("manifest_is_independently_authenticated",
                      "provider_quote_source_verified",
                      "original_run_schedule_completeness_attested",
                      "original_expected_universe_attested",
                      "historical_raw_receipts_archived",
                      "first_entry_origin_signed",
                      "trade_permission", "production_release_authorized"):
            self.assertIs(self.data[field], False)
        self.assertEqual(x["real_historical_gate_result"], "EVIDENCE_NO_GO")

    def test_day_totals_agree_with_reported_grand_totals(self):
        days = self.data["days"]
        pairs = (
            ("parent_runs", "parent_runs"),
            ("zero_child_runs", "zero_children_parent_runs"),
            ("incomplete_child_runs", "incomplete_parent_runs"),
            ("advertised_symbols", "advertised_symbols"),
            ("saved_children", "persisted_child_rows"),
            ("verified_pub_markers", "verified_parent_runs"),
            ("zero_error_parents", "zero_error_parent_runs"),
        )
        for total_field, day_field in pairs:
            self.assertEqual(self.data["totals"][total_field],
                             sum(row[day_field] for row in days))

    def test_real_unsigned_archive_fails_new_signed_validator(self):
        output = validator.evaluate_local_signed_history(
            manifest=self.data,
            signature_b64="",
            trusted_ed25519_public_hex="",
        )
        self.assertEqual(output["status"], "EVIDENCE_NO_GO")
        self.assertIn("DETACHED_MANIFEST_SIGNATURE_INVALID", output["blockers"])
        self.assertFalse(output["trade_permission"])
        self.assertFalse(output["production_release_authorized"])

    def test_even_self_signed_census_is_not_an_authenticated_raw_manifest(self):
        """Ephemeral key is only a test tool; signing aggregates cannot invent rows."""
        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        ).hex()
        sig = base64.b64encode(
            key.sign(validator.canonical(self.data))
        ).decode("ascii")
        result = validator.evaluate_local_signed_history(
            manifest=self.data,
            signature_b64=sig,
            trusted_ed25519_public_hex=pub,
        )
        self.assertEqual(result["status"], "EVIDENCE_NO_GO")
        self.assertIn("SIGNED_MANIFEST_COVERAGE_INVALID", result["blockers"])
        self.assertFalse(result["historical_evidence_complete"])
        self.assertFalse(result["source_market_quotes_authenticated"])

    def test_capture_is_not_a_production_release_or_history_repair(self):
        self.assertEqual(self.data["archive_kind"],
                         "DAILY_DATABASE_CENSUS_HASH_LEDGER_NOT_RAW_HISTORY")
        self.assertEqual(self.data["real_historical_gate_result"], "EVIDENCE_NO_GO")
        self.assertNotIn("service_role", self.data["source_filter"].lower())


if __name__ == "__main__":
    unittest.main()
