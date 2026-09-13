from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from alpha_hunter.big_mover_signature import (
    classify_detection,
    classify_lifecycle,
    fit_signature,
    rank_candidates,
    reconstruct_lead_snapshots,
    score_candidate,
)


FEATURES = (
    "volume_ratio",
    "open_interest_change_pct",
    "relative_strength_btc",
)


def _training_rows() -> list[dict]:
    rows: list[dict] = []

    for index in range(5):
        rows.append({
            "target_direction": "LONG",
            "is_mover": True,
            "volume_ratio": 3.0 + index * 0.1,
            "open_interest_change_pct": 12.0 + index,
            "relative_strength_btc": 5.0 + index * 0.2,
        })

    for index in range(7):
        rows.append({
            "target_direction": "LONG",
            "is_mover": False,
            "volume_ratio": 1.0 + index * 0.05,
            "open_interest_change_pct": 1.0 + index * 0.2,
            "relative_strength_btc": 0.1 + index * 0.05,
        })

    for index in range(5):
        rows.append({
            "target_direction": "SHORT",
            "is_mover": True,
            "volume_ratio": 3.0 + index * 0.1,
            "open_interest_change_pct": 10.0 + index,
            "relative_strength_btc": -6.0 - index * 0.2,
        })

    for index in range(7):
        rows.append({
            "target_direction": "SHORT",
            "is_mover": False,
            "volume_ratio": 1.0 + index * 0.05,
            "open_interest_change_pct": 1.0 + index * 0.2,
            "relative_strength_btc": 0.1 + index * 0.05,
        })

    return rows


class BigMoverSignatureTests(unittest.TestCase):
    def _models(self) -> tuple[dict, dict]:
        rows = _training_rows()
        long_model = fit_signature(
            rows,
            direction="LONG",
            feature_names=FEATURES,
            min_movers=4,
            min_controls=5,
        )
        short_model = fit_signature(
            rows,
            direction="SHORT",
            feature_names=FEATURES,
            min_movers=4,
            min_controls=5,
        )
        return long_model, short_model

    def test_fit_uses_empirical_separation_and_stays_shadow_only(self) -> None:
        long_model, short_model = self._models()

        self.assertEqual(long_model["status"], "READY_FOR_SHADOW_SCORING")
        self.assertEqual(short_model["status"], "READY_FOR_SHADOW_SCORING")
        self.assertFalse(long_model["trade_permission"])
        self.assertFalse(short_model["trade_permission"])
        self.assertGreater(
            long_model["features"]["relative_strength_btc"]["effect"],
            0,
        )
        self.assertLess(
            short_model["features"]["relative_strength_btc"]["effect"],
            0,
        )

        long_weight_sum = sum(
            feature["weight"] for feature in long_model["features"].values()
        )
        self.assertAlmostEqual(long_weight_sum, 1.0, places=8)

    def test_candidate_matching_mover_signature_scores_above_control_like_candidate(self) -> None:
        long_model, _ = self._models()

        mover_like = {
            "symbol": "EARLYLONGUSDT",
            "volume_ratio": 3.0,
            "open_interest_change_pct": 12.0,
            "relative_strength_btc": 5.0,
        }
        control_like = {
            "symbol": "CONTROLUSDT",
            "volume_ratio": 1.2,
            "open_interest_change_pct": 1.8,
            "relative_strength_btc": 0.2,
        }

        high = score_candidate(mover_like, long_model, safety_eligible=True)
        low = score_candidate(control_like, long_model, safety_eligible=True)

        self.assertEqual(high["status"], "SCORED")
        self.assertGreater(high["score"], low["score"])
        self.assertGreater(high["score"], 80)
        self.assertLess(low["score"], 20)
        self.assertFalse(high["trade_permission"])

    def test_hard_safety_gate_cannot_be_bypassed(self) -> None:
        long_model, _ = self._models()
        candidate = {
            "symbol": "BLOCKEDUSDT",
            "volume_ratio": 99,
            "open_interest_change_pct": 99,
            "relative_strength_btc": 99,
        }

        result = score_candidate(
            candidate,
            long_model,
            safety_eligible=False,
        )

        self.assertEqual(result["status"], "SAFETY_BLOCKED")
        self.assertIsNone(result["score"])
        self.assertFalse(result["trade_permission"])

    def test_insufficient_evidence_fails_closed(self) -> None:
        model = fit_signature(
            _training_rows()[:2],
            direction="LONG",
            feature_names=FEATURES,
            min_movers=4,
            min_controls=5,
        )

        self.assertEqual(model["status"], "INSUFFICIENT_EVIDENCE")
        result = score_candidate(
            {"symbol": "X", "volume_ratio": 10},
            model,
            safety_eligible=True,
        )
        self.assertEqual(result["status"], "MODEL_NOT_READY")
        self.assertIsNone(result["score"])

    def test_ranking_keeps_long_and_short_models_separate(self) -> None:
        long_model, short_model = self._models()
        ranked = rank_candidates(
            [
                {
                    "symbol": "LONGUSDT",
                    "safety_eligible": True,
                    "volume_ratio": 3.1,
                    "open_interest_change_pct": 13.0,
                    "relative_strength_btc": 5.4,
                },
                {
                    "symbol": "SHORTUSDT",
                    "safety_eligible": True,
                    "volume_ratio": 3.1,
                    "open_interest_change_pct": 12.0,
                    "relative_strength_btc": -6.3,
                },
                {
                    "symbol": "RISKFAILUSDT",
                    "safety_eligible": False,
                    "volume_ratio": 10.0,
                    "open_interest_change_pct": 50.0,
                    "relative_strength_btc": 20.0,
                },
            ],
            long_model=long_model,
            short_model=short_model,
        )

        by_symbol = {row["symbol"]: row for row in ranked}
        self.assertEqual(by_symbol["LONGUSDT"]["best_direction"], "LONG")
        self.assertEqual(by_symbol["SHORTUSDT"]["best_direction"], "SHORT")
        self.assertEqual(by_symbol["RISKFAILUSDT"]["status"], "SAFETY_BLOCKED")
        self.assertFalse(any(row["trade_permission"] for row in ranked))

    def test_lifecycle_thresholds_are_caller_owned(self) -> None:
        self.assertEqual(
            classify_lifecycle(
                1.5,
                direction="LONG",
                ignition_abs_pct=2,
                expansion_abs_pct=8,
                extended_abs_pct=20,
            ),
            "PRE_MOVER",
        )
        self.assertEqual(
            classify_lifecycle(
                -5,
                direction="SHORT",
                ignition_abs_pct=2,
                expansion_abs_pct=8,
                extended_abs_pct=20,
            ),
            "IGNITION",
        )
        self.assertEqual(
            classify_lifecycle(
                25,
                direction="LONG",
                ignition_abs_pct=2,
                expansion_abs_pct=8,
                extended_abs_pct=20,
            ),
            "EXTENDED",
        )

    def test_detection_classification_covers_required_audit_states(self) -> None:
        ignition = "2026-09-13T08:00:00+00:00"

        self.assertEqual(
            classify_detection(
                first_found_at="2026-09-13T07:00:00+00:00",
                ignition_at=ignition,
                traded=True,
                auditable=True,
            ),
            "FOUND_AND_TRADED",
        )
        self.assertEqual(
            classify_detection(
                first_found_at="2026-09-13T07:00:00+00:00",
                ignition_at=ignition,
                traded=False,
                auditable=True,
            ),
            "FOUND_BUT_MISSED",
        )
        self.assertEqual(
            classify_detection(
                first_found_at="2026-09-13T09:00:00+00:00",
                ignition_at=ignition,
                traded=False,
                auditable=True,
            ),
            "LATE_DETECTED",
        )
        self.assertEqual(
            classify_detection(
                first_found_at=None,
                ignition_at=ignition,
                traded=False,
                auditable=True,
            ),
            "NOT_FOUND",
        )
        self.assertEqual(
            classify_detection(
                first_found_at=None,
                ignition_at=None,
                traded=False,
                auditable=False,
            ),
            "NOT_AUDITABLE",
        )

    def test_reconstruction_selects_last_observation_at_or_before_each_lead(self) -> None:
        ignition = datetime(2026, 9, 13, 12, tzinfo=timezone.utc)
        history = []
        for hours_before in (30, 24, 13, 12, 7, 6, 3, 1, 0):
            history.append({
                "symbol": "MOVEUSDT",
                "captured_at_utc": (
                    ignition - timedelta(hours=hours_before)
                ).isoformat(),
                "hours_before": hours_before,
            })

        snapshots = reconstruct_lead_snapshots(history, ignition_at=ignition)

        self.assertEqual(snapshots["T-24h"]["hours_before"], 24)
        self.assertEqual(snapshots["T-12h"]["hours_before"], 12)
        self.assertEqual(snapshots["T-6h"]["hours_before"], 6)
        self.assertEqual(snapshots["T-3h"]["hours_before"], 3)
        self.assertEqual(snapshots["T-1h"]["hours_before"], 1)
        self.assertEqual(snapshots["IGNITION"]["hours_before"], 0)


if __name__ == "__main__":
    unittest.main()
