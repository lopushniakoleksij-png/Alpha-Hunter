from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from big_mover_signature_job import load_rows, run_shadow_scan


FEATURES = (
    "volume_ratio",
    "open_interest_change_pct",
    "relative_strength_btc",
)


def _rows() -> list[dict]:
    rows: list[dict] = []

    for index in range(4):
        rows.append({
            "target_direction": "LONG",
            "is_mover": True,
            "volume_ratio": 3.0 + index * 0.1,
            "open_interest_change_pct": 12.0 + index,
            "relative_strength_btc": 5.0 + index * 0.2,
        })
        rows.append({
            "target_direction": "SHORT",
            "is_mover": True,
            "volume_ratio": 3.0 + index * 0.1,
            "open_interest_change_pct": 11.0 + index,
            "relative_strength_btc": -5.0 - index * 0.2,
        })

    for index in range(5):
        control = {
            "is_mover": False,
            "volume_ratio": 1.0 + index * 0.05,
            "open_interest_change_pct": 1.0 + index * 0.2,
            "relative_strength_btc": 0.1 + index * 0.05,
        }
        rows.append({**control, "target_direction": "LONG"})
        rows.append({**control, "target_direction": "SHORT"})

    return rows


class BigMoverSignatureJobTests(unittest.TestCase):
    def test_run_shadow_scan_ranks_candidates_without_trade_permission(self) -> None:
        report = run_shadow_scan(
            _rows(),
            [
                {
                    "symbol": "EARLYLONGUSDT",
                    "safety_eligible": True,
                    "volume_ratio": 3.0,
                    "open_interest_change_pct": 12.0,
                    "relative_strength_btc": 5.0,
                },
                {
                    "symbol": "EARLYSHORTUSDT",
                    "safety_eligible": True,
                    "volume_ratio": 3.0,
                    "open_interest_change_pct": 11.0,
                    "relative_strength_btc": -5.0,
                },
                {
                    "symbol": "UNVERIFIEDUSDT",
                    "safety_eligible": False,
                    "volume_ratio": 99.0,
                    "open_interest_change_pct": 99.0,
                    "relative_strength_btc": 99.0,
                },
            ],
            min_movers=4,
            min_controls=5,
            feature_names=FEATURES,
        )

        self.assertEqual(report["long_model_status"], "READY_FOR_SHADOW_SCORING")
        self.assertEqual(report["short_model_status"], "READY_FOR_SHADOW_SCORING")
        self.assertFalse(report["trade_permission"])

        by_symbol = {
            row["symbol"]: row
            for row in report["ranked_candidates"]
        }
        self.assertEqual(by_symbol["EARLYLONGUSDT"]["best_direction"], "LONG")
        self.assertEqual(by_symbol["EARLYSHORTUSDT"]["best_direction"], "SHORT")
        self.assertEqual(by_symbol["UNVERIFIEDUSDT"]["status"], "SAFETY_BLOCKED")
        self.assertFalse(
            any(row["trade_permission"] for row in report["ranked_candidates"])
        )

    def test_missing_safety_eligibility_fails_closed(self) -> None:
        report = run_shadow_scan(
            _rows(),
            [{
                "symbol": "MISSINGFLAGUSDT",
                "volume_ratio": 4.0,
                "open_interest_change_pct": 20.0,
                "relative_strength_btc": 8.0,
            }],
            min_movers=4,
            min_controls=5,
            feature_names=FEATURES,
        )

        result = report["ranked_candidates"][0]
        self.assertEqual(result["status"], "SAFETY_BLOCKED")
        self.assertIsNone(result["best_score"])

    def test_load_rows_supports_json_and_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            json_path = directory_path / "rows.json"
            jsonl_path = directory_path / "rows.jsonl"

            json_path.write_text(
                json.dumps({"rows": [{"symbol": "A"}, {"symbol": "B"}]}),
                encoding="utf-8",
            )
            jsonl_path.write_text(
                '{"symbol":"A"}\n{"symbol":"B"}\n',
                encoding="utf-8",
            )

            self.assertEqual(len(load_rows(json_path)), 2)
            self.assertEqual(len(load_rows(jsonl_path)), 2)


if __name__ == "__main__":
    unittest.main()
