import json
from pathlib import Path

import v75_lifecycle_job
from alpha_hunter.lifecycle import LifecycleEpisode


def _episode(**overrides):
    values = {
        "episode_id": "episode-1",
        "symbol": "BTCUSDT",
        "path": "CONTINUATION",
        "first_detected_at_utc": "2026-09-20T00:00:00+00:00",
        "last_detected_at_utc": "2026-09-20T00:00:00+00:00",
        "first_detection_price": 100.0,
        "latest_price": 100.0,
    }
    values.update(overrides)
    return LifecycleEpisode(**values)


def test_lifecycle_episode_accepts_persisted_provisional_classification():
    episode = _episode(
        provisional_classification="ACTIVE",
        final_classification=None,
    )

    assert episode.provisional_classification == "ACTIVE"
    assert episode.final_classification is None
    assert episode.to_dict()["provisional_classification"] == "ACTIVE"


def test_load_state_is_backward_compatible_with_existing_provisional_field(
    tmp_path: Path,
    monkeypatch,
):
    state_path = tmp_path / "v75-lifecycle-episodes.json"
    state_path.write_text(
        json.dumps(
            [
                _episode(
                    provisional_classification="GOOD_DETECTION",
                    final_classification=None,
                ).to_dict()
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(v75_lifecycle_job, "STATE_PATH", state_path)

    episodes = v75_lifecycle_job.load_state()

    assert len(episodes) == 1
    assert episodes[0].provisional_classification == "GOOD_DETECTION"
    assert episodes[0].final_classification is None


def test_job_keeps_provisional_and_final_classifications_separate():
    source = Path("v75_lifecycle_job.py").read_text(encoding="utf-8")

    assert "episode.provisional_classification = (" in source
    assert "episode.final_classification = (\n            classify_episode(" not in source
    assert '"provisional_classification,"' in source


def test_finalizer_remains_owner_of_ground_truth_final_classification():
    source = Path("v75_episode_finalizer.py").read_text(encoding="utf-8")

    assert "episode.final_classification = (" in source
    assert "classify_ground_truth(" in source
