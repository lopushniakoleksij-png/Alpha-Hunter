"""Read-only regression for the approved GitHub hourly producer contract.

This checks source declarations in repository configuration only; it does NOT
authenticate runtime requests, tokens, deployment hosts or external publishers.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/alpha-hunter-realtime-profitability-test.yml"


class ApprovedProducerWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_source_claim_is_explicit_and_unique(self):
        declarations = re.findall(
            r"^\s*ALPHA_HUNTER_RUN_SOURCE:\s*([^\s#]+)", self.source, re.M
        )
        self.assertEqual(declarations, ["GITHUB_REALTIME_HOURLY"])

    def test_pinned_main_checkout_is_read_only(self):
        self.assertRegex(self.source, r"(?m)^\s*contents:\s*read\s*$")
        self.assertRegex(self.source, r"(?m)^\s*ref:\s*main\s*$")
        self.assertNotRegex(self.source, r"(?m)^\s*ref:\s*fix/supabase-write-timeout-qa\s*$")

    def test_scan_failure_not_masked_by_continue_on_error(self):
        self.assertIn("continue-on-error: true", self.source)
        self.assertIn("steps.live_scan.outcome == 'failure'", self.source)
        self.assertRegex(self.source, r"(?m)^\s*exit 1\s*$")

    def test_failure_guard_is_bound_to_live_scan_step(self):
        # A stray exit 1 elsewhere must not satisfy failure propagation.
        self.assertRegex(
            self.source,
            r"(?ms)^\s*- name: Run current main against real Bitget market data\n"
            r"(?:(?!^\s*- name:).)*?^\s*id: live_scan\s*$"
            r"(?:(?!^\s*- name:).)*?^\s*continue-on-error: true\s*$",
        )
        self.assertRegex(
            self.source,
            r"(?ms)^\s*- name: Preserve scanner failure status\n"
            r"(?:(?!^\s*- name:).)*?^\s*if: .*always\(\).*steps\.live_scan\.outcome == 'failure'.*$"
            r"(?:(?!^\s*- name:).)*?^\s*exit 1\s*$",
        )

    def test_paper_only_guard_present(self):
        for marker in ('"trade_permission": False', '"paper_only": True', '"order_path": "NONE"'):
            self.assertIn(marker, self.source)


if __name__ == "__main__":
    unittest.main()
