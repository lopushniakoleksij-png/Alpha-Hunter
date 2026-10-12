"""Static non-deployment guards for PR #337 read-only P1 review SQL.

These are NOT integration/production proof; exact SELECTs must also be tested
against live evidence via an independently authorized read-only connection.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ROOT / "ops/reviews/legacy_residual_coverage_readonly_20261012.sql",
    ROOT / "ops/reviews/legacy_ledger_balance_readonly_20261012.sql",
)

def sanitized(path):
    sql = path.read_text(encoding="utf-8")
    return "\n".join(line.split("--",1)[0] for line in sql.splitlines())

class LegacyResidualContractTests(unittest.TestCase):
    def test_select_only_no_writes_or_privilege_changes(self):
        for path in FILES:
            with self.subTest(path=path.name):
                sql = sanitized(path)
                self.assertRegex(sql.lstrip(), r"(?i)^with\b")
                self.assertNotRegex(sql, r"(?i)\b(insert|update|delete|merge|create|alter|drop|truncate|grant|revoke|call|execute|copy|vacuum|do)\b")
                self.assertRegex(sql, r"(?i)\bselect\b")

    def test_no_cohort_date_lifecycle_exclusion(self):
        for path in FILES:
            with self.subTest(path=path.name):
                sql = sanitized(path).lower()
                self.assertNotIn("paper_execution_r8",sql)
                self.assertNotIn("paper_execution_r9",sql)
                self.assertNotIn("paper_execution_r10",sql)
                self.assertNotIn("activation_id",sql)
                self.assertNotIn("submitted_at_utc >=",sql)
                self.assertNotIn("l.state in (",sql)

    def test_source_linkage_and_balance(self):
        sql = sanitized(FILES[1]).lower()
        for expected in ("alpha_hunter_paper_orders_v02","alpha_hunter_paper_fills_v02",
                         "alpha_hunter_paper_exit_fills_v04","full outer join",
                         "filled_greater_than_ordered","exit_greater_than_filled",
                         "orphan_fill_or_exit","positive_residual_requires_coverage_audit"):
            with self.subTest(expected=expected):
                self.assertIn(expected,sql)

    def test_protection_coverage_classifies_not_erases(self):
        sql = sanitized(FILES[0]).lower()
        for expected in ("alpha_hunter_paper_fills_v02","alpha_hunter_paper_exit_fills_v04",
                         "alpha_hunter_paper_protective_orders_v03",
                         "alpha_hunter_paper_protection_open_v04",
                         "unprotected_residual_review_required",
                         "quarantined_residual_preserve_evidence"):
            with self.subTest(expected=expected):
                self.assertIn(expected,sql)
        self.assertIn("residual_quantity",sql)
        self.assertIn(">0.000000000001",sql.replace(" ",""))

if __name__ == "__main__":
    unittest.main()
