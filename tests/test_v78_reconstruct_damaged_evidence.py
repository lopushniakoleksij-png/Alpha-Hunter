import unittest

from datetime import datetime, timezone

import v78_reconstruct_damaged_evidence as repair


def row(
    snapshot_id,
    quality="INSUFFICIENT_CANDLE_HISTORY",
):
    return {
        "snapshot_id": snapshot_id,
        "episode_id": f"episode-{snapshot_id}",
        "symbol": "TESTUSDT",
        "phase": "EMERGING",
        "phase_at_utc": "2026-08-15T12:00:00+00:00",
        "measurement_quality": quality,
    }


class TestCandidateManifest(unittest.TestCase):
    def test_only_damaged_rows_enter_manifest(self):
        candidates = repair.candidate_rows([
            row("complete", "COMPLETE"),
            row("b"),
            row("a"),
        ])

        self.assertEqual(
            [item["snapshot_id"] for item in candidates],
            ["a", "b"],
        )

    def test_unexpected_quality_blocks_reconstruction(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "Unexpected non-COMPLETE",
        ):
            repair.candidate_rows([
                row("unknown", "PARTIAL"),
            ])

    def test_manifest_digest_is_order_independent(self):
        self.assertEqual(
            repair.manifest_digest([
                row("b"),
                row("a"),
            ]),
            repair.manifest_digest([
                row("a"),
                row("b"),
            ]),
        )

    def test_manifest_verification_detects_candidate_drift(self):
        manifest = repair.build_manifest(
            [row("a")],
            created_at=datetime(
                2026,
                8,
                22,
                tzinfo=timezone.utc,
            ),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "candidate set drifted",
        ):
            repair.verify_manifest(
                manifest,
                [row("a"), row("b")],
            )

    def test_verified_manifest_returns_frozen_digest(self):
        candidates = [row("b"), row("a")]
        manifest = repair.build_manifest(
            candidates,
            created_at=datetime(
                2026,
                8,
                22,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            repair.verify_manifest(
                manifest,
                list(reversed(candidates)),
            ),
            manifest["candidate_digest"],
        )


if __name__ == "__main__":
    unittest.main()
