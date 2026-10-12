"""Regression for Oct 12 dashboard showing zero lists despite 630 parent evaluations.

Dashboard-only: incomplete child persistence is UNKNOWN, historical research
is segregated and NEVER enters action/paper/exchange decisions.
"""
from copy import deepcopy

import app as dashboard
from alpha_hunter.dashboard_observability import (
    format_historical_research,
    inspect_child_stage,
)

STAMP_LATEST = "2026-10-12T13:23:38+00:00"
STAMP_OLD = "2026-10-12T13:04:47+00:00"


def parent(run, at, symbols):
    return {
        "run_id":run,"collected_at_utc":at,"symbol_count":len(symbols),
        "payload":{
            "_storage_contract":"snapshot-parent-v0.2",
            "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"},
            "collected_at_utc":at,
            "multi_strategy_summary":{
                "configured_strategy_count":10,
                "total_evaluations":10*len(symbols),
                "shadow_candidate_count":1,
            },
            "symbols":[{"symbol":s} for s in symbols],
            "private_account":{"status":"CONNECTED","open_positions":[]},
            "universe":{"selected_count":len(symbols)},
        }
    }


def detail(symbol):
    return {
        "symbol":symbol,"last_price":1.1,"state":"WATCH_LONG",
        "market_phase":"IGNITION","opportunity_timing":"EARLY",
        "behaviour_score":7.0,"discovery_permission":True,
        "execution_setup":{"direction":"LONG","entry":1.1,"stop":1.0,
                           "target":2.2,"rr":11},
        "multi_strategy_engine":{"strategies":[{
            "strategy_id":"S3","status":"SHADOW_CANDIDATE",
            "direction":"LONG","action":"EXECUTE_NOW","signal_score":8.3,
            "entry":1.1,"stop":1.0,"target":2.2,"rr":11,
        }]}
    }


def test_missing_all_63_child_records_is_incomplete_not_zero_candidates():
    row=parent("run-630",STAMP_LATEST,[f"SYM{i}USDT" for i in range(63)])
    status=inspect_child_stage(row,row["payload"],[])
    assert status["status"]=="INCOMPLETE"
    assert status["expected"]==63 and status["persisted"]==0
    hydrated=dashboard._hydrate_dashboard_snapshot(row,row["payload"])
    # No mocked Supabase here; direct helper is canonical for this assertion.
    assert status["symbols"]==[]


def test_child_duplicates_and_symbol_identity_fail_even_with_matching_counts():
    row=parent("run-good",STAMP_OLD,["BTCUSDT","QUSDT"])
    variants=[
        [{"symbol":"BTCUSDT","payload":detail("BTCUSDT")},
         {"symbol":"BTCUSDT","payload":detail("BTCUSDT")}],
        [{"symbol":"BTCUSDT","payload":detail("BTCUSDT")},
         {"symbol":"QUSDT","payload":detail("BADUSDT")}],
        [{"symbol":"BTCUSDT","payload":detail("BTCUSDT")}],
    ]
    assert all(inspect_child_stage(row,row["payload"],x)["status"]=="INCOMPLETE" for x in variants)


def test_exact_unique_child_manifest_restores_full_rows_from_same_run():
    row=parent("run-good",STAMP_OLD,["BTCUSDT","QUSDT"])
    children=[{"symbol":"QUSDT","payload":detail("QUSDT")},
              {"symbol":"BTCUSDT","payload":detail("BTCUSDT")}]
    result=inspect_child_stage(row,row["payload"],children)
    assert result["status"]=="COMPLETE_SYMBOL_ROWS_NOT_MONITORING_PROOF"
    assert len(result["symbols"])==2


def test_read_only_history_strips_trade_setup_and_uses_timestamp_only():
    original=detail("QUSDT")
    before=deepcopy(original)
    historic={"run_id":"old","collected_at_utc":STAMP_OLD,
              "_detail_integrity":"COMPLETE_SYMBOL_ROWS_NOT_MONITORING_PROOF",
              "symbols":[original,detail("BTCUSDT")]}
    history=format_historical_research(historic)
    assert original==before
    assert history["status"]=="HISTORICAL_RESEARCH_ONLY_NOT_LIVE_NOT_EXECUTABLE"
    assert len(history["strategies"])==1
    assert history["strategies"][0]["status"]=="SHADOW_CANDIDATE"
    for key in ("entry","stop","target","action","reward_risk"):
        assert key not in history["strategies"][0]
    assert history["execution_authority"] is False
    assert history["scientific_pass_permitted"] is False


def test_latest_incomplete_fallback_historical_never_replaces_current(monkeypatch):
    current=parent("latest-failed",STAMP_LATEST,["QUSDT","SOLUSDT"])
    older=parent("older-full",STAMP_OLD,["QUSDT","BTCUSDT"])
    called=[]
    def rows(table,params):
        called.append((table,dict(params)))
        if table == dashboard.SNAPSHOT_TABLE:
            if params.get("limit")=="1":
                return [current]
            return [current,older]
        if params["run_id"]=="eq.latest-failed":
            return []
        if params["run_id"]=="eq.older-full":
            return [{"symbol":s,"payload":detail(s)} for s in ["QUSDT","BTCUSDT"]]
        raise AssertionError("Unexpected source")
    monkeypatch.setattr(dashboard,"supabase_get_rows",rows)
    monkeypatch.setattr(dashboard,"latest_test_engine_status",lambda:{})
    monkeypatch.setattr(dashboard,"latest_paper_lifecycle_status",lambda:{})
    result=dashboard.dashboard_view_data()
    assert result["updated"]==STAMP_LATEST
    assert result["detail_integrity"]=="INCOMPLETE"
    assert result["detail_expected"]==2 and result["detail_persisted"]==0
    assert result["historical_research"]["collected_at_utc"]==STAMP_OLD
    assert result["historical_research"]["strategies"][0]["symbol"]=="QUSDT"
    assert result["best_action"] is None
    assert result["actionable"]==[]
    assert result["blocked_actions"]==[]
    assert result["research"]==[]
    assert result["strategy_shadow"]==[]
    assert result["strategy_summary"]["total_evaluations"]==20
    assert result["historical_research"]["trade_permission"] is False
    assert any(z[0]=="alpha_hunter_symbol_snapshots" for z in called)


def test_dashboard_html_and_api_do_not_misstate_empty_lists(monkeypatch):
    current=parent("latest-failed",STAMP_LATEST,["QUSDT","SOLUSDT"])
    older=parent("older-full",STAMP_OLD,["QUSDT","BTCUSDT"])
    def rows(table,params):
        if table == dashboard.SNAPSHOT_TABLE:
            return [current] if params.get("limit")=="1" else [current,older]
        return [] if params["run_id"]=="eq.latest-failed" else [
            {"symbol":s,"payload":detail(s)} for s in ["QUSDT","BTCUSDT"]
        ]
    monkeypatch.setattr(dashboard,"supabase_get_rows",rows)
    monkeypatch.setattr(dashboard,"latest_test_engine_status",lambda:{})
    monkeypatch.setattr(dashboard,"latest_paper_lifecycle_status",lambda:{})
    client=dashboard.app.test_client()
    response=client.get("/")
    assert response.status_code==200
    html=response.get_data(as_text=True)
    assert "SCAN INCOMPLETE" in html
    assert "2</b> of <b>2</b>" not in html
    assert "Previous complete scan" in html
    assert "Previous S1" in html
    assert "NOT EXECUTABLE" in html
    assert "PAPER ACTION QUEUE UNAVAILABLE" in html
    assert "SAFETY BLOCKS UNKNOWN" in html
    assert "runScanButton" in html and 'disabled title="Database persistence incomplete' in html
    payload=client.get("/api/latest").get_json()
    assert payload["detail_integrity"]=="INCOMPLETE"
    assert payload["historical_research"]["status"]=="HISTORICAL_RESEARCH_ONLY_NOT_LIVE_NOT_EXECUTABLE"
    assert payload["actionable"]==[] and payload["trade_ready"]==[]


def test_no_verified_prior_scan_gives_explicit_unavailable_not_false_empty(monkeypatch):
    current=parent("latest-failed",STAMP_LATEST,["QUSDT"])
    monkeypatch.setattr(dashboard,"supabase_get_rows",
        lambda table,params:[current] if table==dashboard.SNAPSHOT_TABLE else [])
    monkeypatch.setattr(dashboard,"latest_test_engine_status",lambda:{})
    monkeypatch.setattr(dashboard,"latest_paper_lifecycle_status",lambda:{})
    page=dashboard.app.test_client().get("/").get_data(as_text=True)
    assert "No previously complete canonical scan" in page
    assert "PAPER ACTION QUEUE UNAVAILABLE" in page
    assert "NO SAFE PAPER TRADE in the current canonical snapshot." not in page


def test_render_web_source_cannot_be_selected_as_trusted_history(monkeypatch):
    newest=parent("latest-failed",STAMP_LATEST,["QUSDT"])
    web=parent("web-quick",STAMP_OLD,["QUSDT"])
    web["payload"]["validation_identity"]["run_source"]="RENDER_WEB"
    old=parent("proper-previous",STAMP_OLD,["BTCUSDT"])
    calls=[]
    def rows(table,params):
        calls.append((table,params))
        if table==dashboard.SNAPSHOT_TABLE:
            return [newest,web,old]
        assert params["run_id"]=="eq.proper-previous"
        return [{"symbol":"BTCUSDT","payload":detail("BTCUSDT")}]
    monkeypatch.setattr(dashboard,"supabase_get_rows",rows)
    got=dashboard.latest_historical_research_snapshot("latest-failed")
    assert got["run_id"]=="proper-previous"
    assert all(z[1].get("run_id")!="eq.web-quick" for z in calls if z[0]!="alpha_hunter_snapshots")
