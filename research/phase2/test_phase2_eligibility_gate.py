import csv
import tempfile
import unittest
from pathlib import Path
from phase2_eligibility_gate import validate_row, validate_registry, REGISTER

def row(**overrides):
    data = {
        "symbol": "XRPUSDT", "product_type": "USDT-FUTURES",
        "target_window_start_utc": "2026-11-08T00:00:00Z",
        "target_window_end_utc": "2026-11-09T00:00:00Z",
        "current_catalogue": "YES", "current_symbol_status": "normal",
        "window_eligibility": "UNKNOWN", "listing_event_evidence": "UNKNOWN",
        "documented_event_type": "", "documented_effective_utc": "",
        "dated_official_source_url": "https://api.bitget.com/api/v2/mix/market/contracts?productType=USDT-FUTURES",
        "nov08_candles_status": "NOT_TESTED", "reason_code": "",
        "backfill_allowed": "NO", "catalogue_request_time_ms": "1794628383976",
        "listing_event_source_url": "", "listing_event_date_as_published": "",
    }
    data.update(overrides)
    return data

class EligibilityGateTests(unittest.TestCase):
    def test_sealed_register(self):
        counts = validate_registry(REGISTER)
        self.assertGreaterEqual(counts["UNKNOWN"], 885)
        self.assertGreaterEqual(counts["EXCLUDED"], 18)
        self.assertEqual(counts["VERIFIED"], 0)
    def test_unknown_passes(self): validate_row(row())
    def test_listing_evidence_not_window_certification(self):
        validate_row(row(symbol="DASHUSDT", listing_event_evidence="VERIFIED",
                         documented_event_type="OFFICIAL_LISTING_ANNOUNCEMENT",
                         dated_official_source_url="https://www.bitget.com/support/articles/12560603841543",
                         listing_event_source_url="https://www.bitget.com/support/articles/12560603841543",
                         listing_event_date_as_published="2025-11-04"))
    def test_excluded_with_official_date(self):
        validate_row(row(symbol="EPICUSDT",current_catalogue="NO",
                         window_eligibility="EXCLUDED",documented_event_type="DELISTED_FUTURES",
                         documented_effective_utc="2026-10-20T07:00:00Z",
                         dated_official_source_url="https://www.bitget.com/support/articles/12560603897724"))
    def test_exclusion_without_date_rejected(self):
        with self.assertRaises(ValueError): validate_row(row(window_eligibility="EXCLUDED"))
    def test_exclusion_future_date_rejected(self):
        with self.assertRaises(ValueError):
            validate_row(row(window_eligibility="EXCLUDED",current_catalogue="NO",
                             documented_event_type="DELISTED_FUTURES",
                             documented_effective_utc="2026-11-09T00:00:00Z",
                             dated_official_source_url="https://www.bitget.com/support/articles/12560603897724"))
    def test_current_list_conflict_rejected(self):
        with self.assertRaises(ValueError):
            validate_row(row(window_eligibility="EXCLUDED",documented_event_type="DELISTED_FUTURES",
                             documented_effective_utc="2026-10-20T07:00:00Z",
                             dated_official_source_url="https://www.bitget.com/support/articles/12560603897724"))
    def test_unreviewed_verified_rejected(self):
        with self.assertRaises(ValueError): validate_row(row(window_eligibility="VERIFIED"))
    def test_backfill_yes_rejected(self):
        with self.assertRaises(ValueError): validate_row(row(backfill_allowed="YES"))
    def test_fake_source_rejected(self):
        with self.assertRaises(ValueError):
            validate_row(row(symbol="EPICUSDT",current_catalogue="NO",
                             window_eligibility="EXCLUDED",documented_event_type="DELISTED_FUTURES",
                             documented_effective_utc="2026-10-20T07:00:00Z",
                             dated_official_source_url="https://evil.example/support/articles/1"))
    def test_excluded_with_separately_verified_listing_event(self):
        validate_row(row(symbol="SCRTUSDT", current_catalogue="NO",
                         window_eligibility="EXCLUDED", listing_event_evidence="VERIFIED",
                         documented_event_type="DELISTED_FUTURES",
                         documented_effective_utc="2026-08-26T07:00:00Z",
                         dated_official_source_url="https://www.bitget.com/support/articles/12560603892891",
                         listing_event_source_url="https://www.bitget.com/support/articles/12560603818612",
                         listing_event_date_as_published="2024-11-21"))
    def test_false_listing_event_source_rejected(self):
        with self.assertRaises(ValueError):
            validate_row(row(listing_event_evidence="VERIFIED",
                             listing_event_source_url="https://wrong.example/support/articles/1",
                             listing_event_date_as_published="2025-11-04"))
    def test_wrong_window_rejected(self):
        with self.assertRaises(ValueError):
            validate_row(row(target_window_start_utc="2026-11-07T00:00:00Z"))
if __name__=="__main__": unittest.main()
