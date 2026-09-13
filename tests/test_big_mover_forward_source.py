from __future__ import annotations

from datetime import datetime, timezone

import alpha_hunter.big_mover_forward_source as module
from alpha_hunter.big_mover_evidence import EvidenceWindow


class FakeReader:
    def __init__(self, coverage, features=None, answers=None):
        self.coverage = coverage
        self.features = features or []
        self.answers = answers or []

    def get_rows(self, table, params, page_size=1000):
        if table == "alpha_hunter_big_mover_answer_key":
            select = params.get("select", "")
            if select == "observed_at_utc":
                return list(self.coverage)
            return list(self.answers)
        if table == "alpha_hunter_signal_features":
            return list(self.features)
        raise AssertionError(table)


def old_result():
    window = EvidenceWindow(
        training_start_utc="2026-08-18T00:00:00+00:00",
        training_end_utc="2026-09-08T00:00:00+00:00",
        latest_audit_utc="2026-09-09T00:00:00+00:00",
        horizon_hours=24,
        mover_threshold_pct=10.0,
        control_ceiling_pct=5.0,
        pre_expansion_abs_move_pct=5.0,
        audit_staleness_hours=96.0,
    )
    evidence = [
        {
            "symbol": "OLDUSDT",
            "captured_at_utc": "2026-09-08T00:00:00+00:00",
            "label": "MOVER",
            "direction": "LONG",
            "features": {"volume_ratio": 2.0},
        },
        {
            "symbol": "OVERLAPUSDT",
            "captured_at_utc": "2026-09-10T01:00:00+00:00",
            "label": "CONTROL",
            "direction": "LONG",
            "features": {"volume_ratio": 1.0},
        },
    ]
    return evidence, [{"symbol": "LIVEUSDT"}], window, {"latest_feature_run_id": "R1"}


def test_first_horizon_does_not_invent_controls(monkeypatch):
    monkeypatch.setattr(module, "load_shadow_inputs", lambda *args, **kwargs: old_result())
    reader = FakeReader(
        coverage=[
            {"observed_at_utc": "2026-09-13T08:00:00+00:00"},
            {"observed_at_utc": "2026-09-13T09:00:00+00:00"},
        ]
    )

    evidence, _, _, context = module.load_shadow_inputs_forward(
        reader,
        now=datetime(2026, 9, 13, 9, 5, tzinfo=timezone.utc),
    )

    assert evidence == old_result()[0]
    assert context["answer_key_status"] == "COLLECTING_FIRST_HORIZON"
    assert context["forward_answer_key_evidence_rows"] == 0


def test_mature_answer_key_replaces_overlapping_bootstrap(monkeypatch):
    monkeypatch.setattr(module, "load_shadow_inputs", lambda *args, **kwargs: old_result())
    feature = {
        "symbol": "NEWUSDT",
        "captured_at_utc": "2026-09-10T00:00:00+00:00",
        "direction": None,
        "state": "WATCH",
        "volume_ratio": 3.0,
        "relative_strength_btc": 2.0,
        "source_payload": {"change_24h_pct": 1.0},
    }
    answers = [
        {
            "symbol": "NEWUSDT",
            "observed_at_utc": "2026-09-10T12:00:00+00:00",
            "direction": "UP",
            "threshold_pct": 10.0,
            "current_24h_move_pct": 11.0,
        }
    ]
    reader = FakeReader(
        coverage=[
            {"observed_at_utc": "2026-09-10T00:00:00+00:00"},
            {"observed_at_utc": "2026-09-11T01:00:00+00:00"},
        ],
        features=[feature],
        answers=answers,
    )

    evidence, _, _, context = module.load_shadow_inputs_forward(
        reader,
        now=datetime(2026, 9, 11, 1, 5, tzinfo=timezone.utc),
    )

    assert context["answer_key_status"] == "MATURE_FORWARD_LABELS_AVAILABLE"
    assert context["forward_answer_key_evidence_rows"] == 2
    assert any(
        row["symbol"] == "NEWUSDT"
        and row["direction"] == "LONG"
        and row["label"] == "MOVER"
        for row in evidence
    )
    assert any(
        row["symbol"] == "NEWUSDT"
        and row["direction"] == "SHORT"
        and row["label"] == "CONTROL"
        for row in evidence
    )
    assert not any(row["symbol"] == "OVERLAPUSDT" for row in evidence)
    assert any(row["symbol"] == "OLDUSDT" for row in evidence)
