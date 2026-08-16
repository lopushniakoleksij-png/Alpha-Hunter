import unittest

from v710_early_execution_rr_shadow import (
    CLASS_CONFIRMATION_TOO_LATE,
    CLASS_EARLY_EXECUTABLE,
    CLASS_GOOD_RR_WRONG_DIRECTION,
    CLASS_INSUFFICIENT_EVIDENCE,
    CLASS_NO_EXECUTABLE_STRUCTURE,
    CLASS_RIGHT_DIRECTION_BAD_RR,
    CLASS_WRONG_DIRECTION_BAD_RR,
    MIN_HUGE_RR,
    PhaseEvidence,
    analyze_v78_rows,
    group_v78_rows,
    classify_episode,
    classify_v78_phase_rows,
    phase_evidence_from_v78_row,
    rr_lost,
)


def phase(
    name,
    *,
    available,
    consistent,
    structure,
    rr,
    quality=None,
):
    return PhaseEvidence(
        phase=name,
        direction_available=available,
        direction_consistent_with_confirmed=consistent,
        structure_valid=structure,
        rr_to_structure=rr,
        measurement_quality=quality,
    )


def v78_row(
    phase_name,
    *,
    observed_direction,
    consistent,
    structure,
    rr,
    quality="COMPLETE",
):
    return {
        "phase": phase_name,
        "phase_price": 100.0,
        "direction": "LONG",
        "direction_available_at_phase": (
            consistent is True
        ),
        "direction_consistent_with_confirmed": (
            consistent
        ),
        "confidence": 60.0,
        "move_consumed_pct": 1.0,
        "minutes_from_detection": 60.0,
        "structure_valid": structure,
        "rr_to_structure": rr,
        "measurement_quality": quality,
        "evidence": {
            "observed_direction_at_phase":
                observed_direction,
        },
    }


class TestV710RRMath(unittest.TestCase):
    def test_positive_rr_lost_means_deterioration(self):
        self.assertEqual(
            rr_lost(7.0, 2.0),
            5.0,
        )

    def test_negative_rr_lost_means_improvement(self):
        self.assertEqual(
            rr_lost(2.0, 4.0),
            -2.0,
        )

    def test_missing_rr_is_none(self):
        self.assertIsNone(
            rr_lost(None, 4.0)
        )


class TestV710Classification(unittest.TestCase):
    def test_early_executable_when_direction_and_rr_survive(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=True,
                structure=True,
                rr=6.0,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=5.2,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_EARLY_EXECUTABLE,
        )

        self.assertEqual(
            result.earliest_live_phase,
            "EMERGING",
        )

        self.assertFalse(
            result.trade_permission
        )

    def test_confirmation_too_late(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=True,
                structure=True,
                rr=7.5,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=1.8,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_CONFIRMATION_TOO_LATE,
        )

        self.assertAlmostEqual(
            result.rr_lost_emerging_to_confirmed,
            5.7,
        )

    def test_good_rr_wrong_direction(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=False,
                structure=True,
                rr=8.0,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=1.0,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_GOOD_RR_WRONG_DIRECTION,
        )

    def test_wrong_direction_and_bad_rr_is_not_mislabeled(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=False,
                structure=True,
                rr=2.0,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=1.0,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_WRONG_DIRECTION_BAD_RR,
        )

    def test_right_direction_but_bad_rr(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=True,
                structure=True,
                rr=2.4,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=0.8,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_RIGHT_DIRECTION_BAD_RR,
        )

    def test_no_structure(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=True,
                structure=False,
                rr=None,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=False,
                rr=None,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_NO_EXECUTABLE_STRUCTURE,
        )

    def test_unknown_consistency_is_not_promoted(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=None,
                structure=True,
                rr=8.0,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=2.0,
            ),
        )

        self.assertEqual(
            result.classification,
            CLASS_INSUFFICIENT_EVIDENCE,
        )

    def test_huge_rr_boundary_is_five(self):
        evidence = phase(
            "EMERGING",
            available=True,
            consistent=True,
            structure=True,
            rr=MIN_HUGE_RR,
        )

        self.assertTrue(
            evidence.huge_rr_available
        )


class TestV710V78Adapter(unittest.TestCase):
    def test_wrong_live_direction_is_preserved(self):
        row = v78_row(
            "EMERGING",
            observed_direction="SHORT",
            consistent=False,
            structure=True,
            rr=8.0,
        )

        evidence = (
            phase_evidence_from_v78_row(
                row,
                "EMERGING",
            )
        )

        self.assertTrue(
            evidence.direction_available
        )

        self.assertEqual(
            evidence.observed_direction,
            "SHORT",
        )

        self.assertFalse(
            evidence
            .direction_consistent_with_confirmed
        )

    def test_real_v78_rows_can_classify_confirmation_too_late(self):
        result = classify_v78_phase_rows(
            [
                v78_row(
                    "EMERGING",
                    observed_direction="LONG",
                    consistent=True,
                    structure=True,
                    rr=7.0,
                ),
                v78_row(
                    "CONFIRMED",
                    observed_direction="LONG",
                    consistent=True,
                    structure=True,
                    rr=1.5,
                ),
            ]
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.classification,
            CLASS_CONFIRMATION_TOO_LATE,
        )

    def test_incomplete_measurement_is_not_called_bad_structure(self):
        result = classify_v78_phase_rows(
            [
                v78_row(
                    "EMERGING",
                    observed_direction="LONG",
                    consistent=True,
                    structure=False,
                    rr=None,
                    quality=(
                        "INSUFFICIENT_CANDLE_HISTORY"
                    ),
                ),
                v78_row(
                    "CONFIRMED",
                    observed_direction="LONG",
                    consistent=True,
                    structure=True,
                    rr=2.0,
                ),
            ]
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.classification,
            CLASS_INSUFFICIENT_EVIDENCE,
        )

    def test_missing_emerging_phase_is_not_invented(self):
        result = classify_v78_phase_rows(
            [
                v78_row(
                    "CONFIRMED",
                    observed_direction="LONG",
                    consistent=True,
                    structure=True,
                    rr=5.0,
                )
            ]
        )

        self.assertIsNone(result)


class TestV710Safety(unittest.TestCase):
    def test_v710_never_grants_trade_permission(self):
        result = classify_episode(
            phase(
                "EMERGING",
                available=True,
                consistent=True,
                structure=True,
                rr=10.0,
            ),
            phase(
                "CONFIRMED",
                available=True,
                consistent=True,
                structure=True,
                rr=10.0,
            ),
        )

        self.assertFalse(
            result.trade_permission
        )


class TestV710DatasetAnalysis(unittest.TestCase):
    def _episode_rows(
        self,
        episode_id,
        symbol,
        emerging_rr,
        confirmed_rr,
        consistent=True,
    ):
        emerging = v78_row(
            "EMERGING",
            observed_direction=(
                "LONG"
                if consistent
                else "SHORT"
            ),
            consistent=consistent,
            structure=True,
            rr=emerging_rr,
        )

        confirmed = v78_row(
            "CONFIRMED",
            observed_direction="LONG",
            consistent=True,
            structure=True,
            rr=confirmed_rr,
        )

        for row in (
            emerging,
            confirmed,
        ):
            row["episode_id"] = (
                episode_id
            )
            row["symbol"] = symbol
            row["path"] = "REVERSAL"
            row["phase_at_utc"] = (
                "2026-08-16T00:00:00+00:00"
            )

        return [
            emerging,
            confirmed,
        ]

    def test_group_v78_rows_separates_episodes(self):
        rows = (
            self._episode_rows(
                "ep1",
                "AAAUSDT",
                6.0,
                2.0,
            )
            +
            self._episode_rows(
                "ep2",
                "BBBUSDT",
                2.0,
                1.0,
            )
        )

        grouped = group_v78_rows(
            rows
        )

        self.assertEqual(
            set(grouped),
            {
                "ep1",
                "ep2",
            },
        )

    def test_dataset_finds_confirmation_too_late(self):
        report = analyze_v78_rows(
            self._episode_rows(
                "ep1",
                "AAAUSDT",
                7.0,
                1.5,
                True,
            )
        )

        self.assertEqual(
            report[
                "classification_counts"
            ][
                CLASS_CONFIRMATION_TOO_LATE
            ],
            1,
        )

    def test_dataset_preserves_wrong_early_direction(self):
        report = analyze_v78_rows(
            self._episode_rows(
                "ep1",
                "AAAUSDT",
                8.0,
                1.0,
                False,
            )
        )

        self.assertEqual(
            report[
                "classification_counts"
            ][
                CLASS_GOOD_RR_WRONG_DIRECTION
            ],
            1,
        )

    def test_dataset_never_generates_trade_permission(self):
        report = analyze_v78_rows(
            self._episode_rows(
                "ep1",
                "AAAUSDT",
                7.0,
                6.0,
                True,
            )
        )

        self.assertFalse(
            report["trade_permission"]
        )

        self.assertTrue(
            all(
                row["trade_permission"]
                is False
                for row
                in report[
                    "classifications"
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
