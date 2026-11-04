"""Synthetic offline tests: P0 hourly scorer cannot bypass canonical persistence."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from alpha_hunter.big_mover_signature import build_directional_signature
from alpha_hunter.hourly_shadow_score import (
    HourlyScoringBlocked,
    make_profile_bundle,
    score_verified_hourly,
)

AT = datetime(2026, 11, 4, 19, 47, tzinfo=timezone.utc)
SOURCE = datetime(2026, 11, 4, 19, 43, tzinfo=timezone.utc)
RUN = "synthetic-render-cron-only"
FINGERPRINT = "a" * 64
CONFIG = {
    "early_ignition_min_abs_change_pct": 0.8,
    "early_ignition_max_abs_change_pct": 3.0,
    "maximum_24h_extension_pct": 25.0,
    "quiet_24h_abs_change_max_pct": 2.0,
}


def _training(direction):
    return [
        {"direction": direction, "label": "MOVER", "is_pre_expansion": True,
         "features": {"volume_ratio": 11.0, "funding_rate": -0.004}},
        {"direction": direction, "label": "MOVER", "is_pre_expansion": True,
         "features": {"volume_ratio": 10.0, "funding_rate": -0.003}},
        {"direction": direction, "label": "CONTROL", "is_pre_expansion": True,
         "features": {"volume_ratio": 2.0, "funding_rate": 0.0001}},
        {"direction": direction, "label": "CONTROL", "is_pre_expansion": True,
         "features": {"volume_ratio": 1.0, "funding_rate": 0.0002}},
    ]


def inputs():
    signs = [
        build_directional_signature(_training(direction), direction)
        for direction in ("LONG", "SHORT")
    ]
    profile_bundle = make_profile_bundle(
        signs, trained_at_utc="2026-11-04T17:00:00+00:00",
        training_end_utc="2026-11-03T16:00:00+00:00",
        scientific_fingerprint_sha256=FINGERPRINT,
    )
    return dict(
        parent={
            "run_id": RUN, "symbol_count": 2, "error_count": 0,
            "collected_at_utc": SOURCE.isoformat(),
            "payload": {
                "_storage_contract": "snapshot-parent-v0.2", "run_id": RUN,
                "validation_identity": {
                    "run_source": "RENDER_CRON", "runtime_role": "RENDER_CRON",
                    "scientific_fingerprint_sha256": FINGERPRINT,
                },
                "symbols": [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
            },
        },
        children=[
            {"run_id": RUN, "symbol": s, "payload": {"symbol": s}, "error": None}
            for s in ("BTCUSDT", "ETHUSDT")
        ],
        feature_rows=[
            {
                "run_id": RUN, "symbol": s, "captured_at_utc": SOURCE.isoformat(),
                "features": {"volume_ratio": 8.0, "funding_rate": -0.002},
                "source_payload": {"change_24h_pct": 0.5},
            }
            for s in ("BTCUSDT", "ETHUSDT")
        ],
        profile_bundle=profile_bundle,
        universe_scan_config=CONFIG,
        expected_scientific_fingerprint=FINGERPRINT,
        now_utc=AT,
    )


def test_complete_exact_source_scores_both_directions_without_trades():
    result = score_verified_hourly(**inputs())
    assert result["expected_symbols"] == 2
    assert result["persisted_child_count"] == 2
    assert result["persisted_feature_count"] == 2
    assert len(result["ranked_research_only"]) == 4
    assert {s["direction"] for s in result["ranked_research_only"]} == {"LONG", "SHORT"}
    assert result["mode"] == "P0_HOURLY_SCORING_ONLY_ISOLATED_RESEARCH"
    assert result["model_parity_with_deployed_sql_v02"] == "NOT_VERIFIED"
    assert result["shadow_only"] is True
    assert result["trade_permission"] is False
    assert result["exchange_authority"] is False
    assert result["production_promotion_permitted"] is False
    assert result["order_path"] == "NONE"
    assert all(s["trade_permission"] is False for s in result["ranked_research_only"])


def test_deterministic_when_input_rows_reordered():
    a = inputs()
    b = copy.deepcopy(a)
    b["children"].reverse()
    b["feature_rows"].reverse()
    assert score_verified_hourly(**a) == score_verified_hourly(**b)


@pytest.mark.parametrize("broken, reason", [
    (lambda a: a["children"].clear(), "incomplete canonical child"),
    (lambda a: a["children"].pop(), "incomplete canonical child"),
    (lambda a: a["children"][1].update(symbol="BTCUSDT"), "invalid or duplicated"),
    (lambda a: a["children"][0].update(run_id="another-run"), "child run identity"),
    (lambda a: a["children"][0]["payload"].update(symbol="FAKEUSDT"), "invalid or duplicated"),
    (lambda a: a["feature_rows"].clear(), "incomplete exact-run"),
    (lambda a: a["feature_rows"].pop(), "incomplete exact-run"),
    (lambda a: a["feature_rows"][1].update(symbol="BTCUSDT"), "feature symbol"),
    (lambda a: a["feature_rows"][0].update(run_id="another-run"), "feature run identity"),
    (lambda a: a["feature_rows"][0].update(captured_at_utc="2026-11-04T19:40:00+00:00"), "feature timestamp"),
    (lambda a: a["feature_rows"][0].update(source_payload={}), "missing observed"),
    (lambda a: a["parent"]["payload"].update(run_id="someone-else"), "parent and payload"),
    (lambda a: a["parent"]["payload"]["symbols"][1].update(symbol="BTCUSDT"), "duplicate or invalid parent"),
    (lambda a: a["parent"].update(error_count=1), "scanner reported"),
    (lambda a: a["parent"]["payload"]["validation_identity"].update(run_source="GITHUB_REALTIME_HOURLY"), "not canonical"),
    (lambda a: a["parent"]["payload"]["validation_identity"].update(scientific_fingerprint_sha256="b" * 64), "fingerprint mismatch"),
])
def test_incomplete_mismatched_or_damaged_persistence_blocks_all_scores(broken, reason):
    a = inputs()
    broken(a)
    with pytest.raises(HourlyScoringBlocked, match=reason):
        score_verified_hourly(**a)


def test_real_incident_shape_61_parent_zero_children_blocks_before_scoring():
    a = inputs()
    a["parent"]["symbol_count"] = 61
    a["parent"]["payload"]["symbols"] = [
        {"symbol": f"TEST{i:02d}USDT"} for i in range(61)
    ]
    a["children"] = []
    a["feature_rows"] = []
    with pytest.raises(HourlyScoringBlocked, match="incomplete canonical child"):
        score_verified_hourly(**a)


def test_profile_digest_detects_tampering():
    a = inputs()
    a["profile_bundle"]["signatures"][0]["feature_profiles"][0]["weight"] += 1
    with pytest.raises(HourlyScoringBlocked, match="digest mismatch"):
        score_verified_hourly(**a)


@pytest.mark.parametrize("broken, reason", [
    (lambda a: a["profile_bundle"].update(scientific_fingerprint_sha256="b" * 64), "digest mismatch"),
    (lambda a: a["profile_bundle"].update(trade_permission=True), "trade authority"),
    (lambda a: a["profile_bundle"].update(signatures=[]), "digest mismatch"),
    (lambda a: a["profile_bundle"].update(contract="other"), "profile contract"),
])
def test_bad_profile_artifact_cannot_be_used(broken, reason):
    a = inputs()
    broken(a)
    with pytest.raises(HourlyScoringBlocked, match=reason):
        score_verified_hourly(**a)


def test_stale_feature_run_blocks_even_if_children_are_complete():
    a = inputs()
    a["now_utc"] = SOURCE + timedelta(minutes=91)
    with pytest.raises(HourlyScoringBlocked, match="stale"):
        score_verified_hourly(**a)


def test_freshness_exact_90_minute_boundary_does_not_disable_safety():
    a = inputs()
    a["now_utc"] = SOURCE + timedelta(minutes=90)
    a["profile_bundle"] = make_profile_bundle(
        [build_directional_signature(_training(direction), direction)
         for direction in ("LONG", "SHORT")],
        trained_at_utc="2026-11-04T17:00:00+00:00",
        training_end_utc="2026-11-03T16:00:00+00:00",
        scientific_fingerprint_sha256=FINGERPRINT,
    )
    assert score_verified_hourly(**a)["source_age_seconds"] == 5400.0


def test_future_source_timestamp_is_not_faked_into_freshness():
    a = inputs()
    a["now_utc"] = SOURCE - timedelta(seconds=6)
    with pytest.raises(HourlyScoringBlocked, match="from future"):
        score_verified_hourly(**a)


def test_mature_training_window_and_profile_age_gate():
    a = inputs()
    a["now_utc"] = SOURCE + timedelta(minutes=1)
    a["profile_bundle"]["trained_at_utc"] = "2026-11-03T00:00:00+00:00"
    a["profile_bundle"]["training_end_utc"] = "2026-11-01T16:00:00+00:00"
    from alpha_hunter.hourly_shadow_score import _hash_payload
    a["profile_bundle"]["digest_sha256"] = _hash_payload({
        k: v for k, v in a["profile_bundle"].items() if k != "digest_sha256"
    })
    with pytest.raises(HourlyScoringBlocked, match="profile stale"):
        score_verified_hourly(**a)


def test_producer_does_not_call_network(monkeypatch):
    import requests
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: pytest.fail("network used"))
    monkeypatch.setattr(requests, "post", lambda *_a, **_k: pytest.fail("network used"))
    assert len(score_verified_hourly(**inputs())["ranked_research_only"]) == 4


def test_offline_cli_writes_research_results_only_after_complete_evidence(tmp_path, monkeypatch):
    import json
    import sys
    from ops.reviews import p0_hourly_shadow_score_cli_v01 as cli

    fixture = tmp_path / "offline.json"
    good = inputs()
    good["now_utc"] = None
    fixture.write_text(json.dumps({
        "parent": good["parent"],
        "children": good["children"],
        "feature_rows": good["feature_rows"],
        "profile_bundle": good["profile_bundle"],
        "universe_scan_config": good["universe_scan_config"],
        "expected_scientific_fingerprint": good["expected_scientific_fingerprint"],
    }), encoding="utf-8")
    output = tmp_path / "research.json"
    monkeypatch.setattr(sys, "argv", [
        "offline-scorer", "--input", str(fixture), "--output", str(output),
        "--as-of-utc", AT.isoformat(),
    ])
    assert cli.main() == 0
    doc = json.loads(output.read_text(encoding="utf-8"))
    assert doc["trade_permission"] is False
    assert doc["production_promotion_permitted"] is False
    assert len(doc["ranked_research_only"]) == 4

    output.unlink()
    broken = json.loads(fixture.read_text(encoding="utf-8"))
    broken["children"] = []
    fixture.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(HourlyScoringBlocked, match="incomplete canonical child"):
        cli.main()
    assert not output.exists()
