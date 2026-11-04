"""Read-only iPhone dashboard: historical storage summary without stale signal promotion."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from alpha_hunter.web_history_summary import (
    ArchiveEvidenceUnavailable, CHILD_TABLE, FEATURE_TABLE, PARENT_TABLE,
    archived_storage_summary,
)
import app as web

AT = datetime(2026, 11, 4, 20, 57, tzinfo=timezone.utc)
LATEST_RUN = "e" * 32
GOOD_RUN = "a" * 32
SYMBOLS = ("BTCUSDT", "ETHUSDT")
STORED_AT = (AT - timedelta(minutes=34)).isoformat()


def parent(run_id: str, collected_at: str):
    return {
        "run_id": run_id,
        "collected_at_utc": collected_at,
        "symbol_count": len(SYMBOLS),
        "error_count": 0,
        "payload": {
            "run_id": run_id,
            "_storage_contract": "snapshot-parent-v0.2",
            "validation_identity": {
                "run_source": "RENDER_CRON",
                "runtime_role": "RENDER_CRON",
            },
            "symbols": [{"symbol": s} for s in SYMBOLS],
        },
    }


def fixture(*, latest_has_children=False, older_features=True):
    latest = parent(LATEST_RUN, (AT - timedelta(minutes=14)).isoformat())
    good = parent(GOOD_RUN, STORED_AT)
    children = [
        {"run_id": GOOD_RUN, "symbol": s, "state": state,
         "error": None, "trade_permission": False}
        for s, state in zip(SYMBOLS, ("WATCH_LONG", "NEUTRAL"))
    ]
    features = [
        {"run_id": GOOD_RUN, "symbol": s, "captured_at_utc": STORED_AT}
        for s in SYMBOLS
    ]
    calls = []
    def get(table, query):
        calls.append((table, dict(query)))
        if table == PARENT_TABLE:
            return copy.deepcopy([latest, good] if query.get("limit") != "1" else [
                {"run_id": LATEST_RUN, "collected_at_utc": latest["collected_at_utc"]}
            ])
        if table == CHILD_TABLE:
            if query["run_id"] == f"eq.{LATEST_RUN}":
                return copy.deepcopy(children) if latest_has_children else []
            return copy.deepcopy(children)
        if table == FEATURE_TABLE:
            if query["run_id"] == f"eq.{LATEST_RUN}":
                return copy.deepcopy(features) if latest_has_children else []
            return copy.deepcopy(features) if older_features else []
        pytest.fail("unexpected table or query")
    return latest, good, children, features, calls, get


def test_latest_incomplete_revealed_and_older_complete_labeled_historical():
    latest, good, children, features, calls, get = fixture()
    result = archived_storage_summary(get, now_utc=AT)
    history = result["historical_completed_scan"]
    assert result["latest_reported_scan_at_utc"] == latest["collected_at_utc"]
    assert result["latest_reported_declared_symbols"] == 2
    assert history["collected_at_utc"] == good["collected_at_utc"]
    assert history["declared_symbols"] == history["persisted_symbols"] == history["persisted_features"] == 2
    assert history["age_minutes"] == 34.0
    assert history["aggregate_states"] == {"NEUTRAL": 1, "WATCH_LONG": 1}
    assert result["mode"] == "HISTORICAL_STORAGE_STATUS_ONLY"
    assert result["historical_only"] is True
    assert result["trade_permission"] is False
    assert result["verified_live_trade_signal"] is False
    assert result["exchange_authority"] is False
    assert result["source_run_not_substituted"] is True
    assert "symbols" not in result and "entry" not in str(result).lower()
    assert calls[0][1]["payload->validation_identity->>run_source"] == "eq.RENDER_CRON"
    assert calls[1][1]["run_id"] == f"eq.{LATEST_RUN}"
    assert calls[2][1]["run_id"] == f"eq.{GOOD_RUN}"
    assert calls[3][1]["run_id"] == f"eq.{GOOD_RUN}"
    assert calls[-1][1]["limit"] == "1"


def test_if_historical_feature_set_missing_never_mark_as_complete():
    _, _, _, _, _, get = fixture(older_features=False)
    result = archived_storage_summary(get, now_utc=AT)
    assert result["historical_completed_scan"] is None
    assert not result["verified_live_trade_signal"]


@pytest.mark.parametrize("mutation", [
    lambda kids: kids[0].update(run_id="not-the-same-run"),
    lambda kids: kids[1].update(symbol="BTCUSDT"),
    lambda kids: kids[0].update(trade_permission=True),
    lambda kids: kids[0].update(error="bad"),
])
def test_corrupt_child_evidence_never_marked_complete(mutation):
    latest, good, children, features, _, _ = fixture()
    mutation(children)
    def get(table, query):
        if table == PARENT_TABLE:
            return [latest, good] if query.get("limit") != "1" else [
                {"run_id": latest["run_id"], "collected_at_utc": latest["collected_at_utc"]}
            ]
        if table == CHILD_TABLE:
            return [] if query["run_id"] == f"eq.{LATEST_RUN}" else children
        if table == FEATURE_TABLE:
            return features
        pytest.fail("unexpected table")
    assert archived_storage_summary(get, now_utc=AT)["historical_completed_scan"] is None


def test_missing_feature_timestamp_or_symbol_blocks_archived_claim():
    latest, good, children, features, _, _ = fixture()
    features[0]["captured_at_utc"] = AT.isoformat()
    def get(table, query):
        if table == PARENT_TABLE:
            return [latest, good] if query.get("limit") != "1" else [
                {"run_id": latest["run_id"], "collected_at_utc": latest["collected_at_utc"]}
            ]
        if table == CHILD_TABLE:
            return [] if query["run_id"] == f"eq.{LATEST_RUN}" else children
        if table == FEATURE_TABLE:
            return features
        pytest.fail("unexpected table")
    assert archived_storage_summary(get, now_utc=AT)["historical_completed_scan"] is None


def test_recheck_newer_run_refuses_to_claim_a_fresh_historical_report():
    latest, good, _, _, _, get = fixture()
    def changed(table, query):
        if table == PARENT_TABLE and query.get("limit") == "1":
            return [{"run_id": "f" * 32, "collected_at_utc": AT.isoformat()}]
        return get(table, query)
    with pytest.raises(ArchiveEvidenceUnavailable, match="advanced"):
        archived_storage_summary(changed, now_utc=AT)


def test_no_parent_source_fails_closed():
    with pytest.raises(ArchiveEvidenceUnavailable, match="missing"):
        archived_storage_summary(lambda *_args: [], now_utc=AT)


def test_never_substitute_latest_as_complete_when_children_are_mixed():
    latest, good, children, features, _, _ = fixture()
    def get(table, query):
        if table == PARENT_TABLE:
            return [latest, good] if query.get("limit") != "1" else [
                {"run_id": latest["run_id"], "collected_at_utc": latest["collected_at_utc"]}
            ]
        if table == CHILD_TABLE:
            if query["run_id"] == f"eq.{LATEST_RUN}":
                return [{**c, "run_id": LATEST_RUN} for c in children]
            return children
        if table == FEATURE_TABLE:
            if query["run_id"] == f"eq.{LATEST_RUN}":
                return features  # wrong run ID
            return features
        pytest.fail("unexpected table")
    result = archived_storage_summary(get, now_utc=AT)
    assert result["historical_completed_scan"]["collected_at_utc"] == STORED_AT
    assert result["latest_reported_scan_at_utc"] != STORED_AT


def test_malformed_parent_does_not_look_like_verified_data():
    latest, good, kids, features, _, _ = fixture()
    good["payload"]["symbols"] = [{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}]
    def get(table, query):
        if table == PARENT_TABLE:
            return [latest, good] if query.get("limit") != "1" else [
                {"run_id": latest["run_id"], "collected_at_utc": latest["collected_at_utc"]}
            ]
        if table == CHILD_TABLE:
            return []
        pytest.fail("source should not need feature read")
    assert archived_storage_summary(get, now_utc=AT)["historical_completed_scan"] is None


def test_incomplete_html_includes_archive_panel_but_live_api_remains_503(monkeypatch):
    monkeypatch.setenv("RENDER_SERVICE_ID", "web-history-isolated")
    monkeypatch.setattr(web, "_DASHBOARD_READ_UNAVAILABLE_UNTIL", 0)
    monkeypatch.setattr(web, "latest_snapshot", lambda: (_ for _ in ()).throw(
        web.CanonicalSnapshotIncomplete("synthetic latest failed scan")
    ))
    client = web.app.test_client()
    html = client.get("/")
    assert html.status_code == 200
    assert html.headers["X-Alpha-Hunter-Evidence-State"] == "INCOMPLETE"
    text = html.get_data(as_text=True)
    assert "Last stored complete scan" in text
    assert "/api/historical-status" in text
    assert "HISTORICAL ONLY" in text
    assert "Bitget public market prices" in text
    api = client.get("/api/latest")
    assert api.status_code == 503
    assert api.get_json()["error"] == "canonical_scan_incomplete"


def test_archive_api_returns_aggregates_only_and_no_store(monkeypatch):
    monkeypatch.setattr(web, "cached_historical_status", lambda: archived_storage_summary(
        fixture()[-1], now_utc=AT,
    ))
    result = web.app.test_client().get("/api/historical-status")
    assert result.status_code == 200
    assert result.headers["X-Alpha-Hunter-Evidence-State"] == "HISTORICAL_ONLY"
    assert result.headers["Cache-Control"] == "no-store"
    p = result.get_json()
    assert p["trade_permission"] is False
    assert p["historical_only"] is True
    assert "ranked_research_only" not in p
    assert "symbols" not in str(p)


def test_archive_api_fails_safely_without_data(monkeypatch):
    monkeypatch.setattr(web, "cached_historical_status", lambda: (_ for _ in ()).throw(
        ArchiveEvidenceUnavailable("test DB unavailable")
    ))
    result = web.app.test_client().get("/api/historical-status")
    assert result.status_code == 503
    assert result.get_json()["verified_live_trade_signal"] is False
    assert result.get_json()["trade_permission"] is False
    assert result.headers["Cache-Control"] == "no-store"


def test_cache_budgets_archive_db_reads(monkeypatch):
    from alpha_hunter import web_history_summary
    now = [1000.0]
    calls = [0]
    def fake_scan(_reader, *, now_utc):
        calls[0] += 1
        return {"mode": "HISTORICAL_STORAGE_STATUS_ONLY", "historical_only": True}
    monkeypatch.setattr(web, "_HISTORICAL_STATUS_CACHE", None)
    monkeypatch.setattr(web, "_HISTORICAL_STATUS_UNTIL", 0.0)
    monkeypatch.setattr(web.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(web, "archived_storage_summary", fake_scan)
    a = web.cached_historical_status()
    b = web.cached_historical_status()
    assert a == b and calls == [1]
    now[0] += 61.0
    c = web.cached_historical_status()
    assert calls == [2]
