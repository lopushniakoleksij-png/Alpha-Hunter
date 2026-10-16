"""P3 offline no-causal-attribution regression and SELECT-only SQL guard."""
from __future__ import annotations
import sys
from pathlib import Path

from pglast import parse_sql
from pglast.ast import SelectStmt

REVIEWS=Path(__file__).resolve().parents[1]/"ops"/"reviews"
sys.path.insert(0,str(REVIEWS))
from p3_historical_candidate_causality_guard_v01 import (
    classify_candidate,inspect_fixture
)

def fixture(i=0,*,action="PLACE_LIMIT",order_type="MARKET",status="UNIQUE_EVIDENCE_COMPLETE_MATCH"):
    return {
       "synthetic_test_only":True,"synthetic_event_id":f"synthetic-freeze-{i}",
       "synthetic_fill_id":f"synthetic-fill-{i}",
       "action":action,"order_type":order_type,"candidate_status":status,
       "decision_direction":"LONG","venue_trade_scope":"OPEN",
       "venue_order_state":"FILLED","trace_complete":True,
       "frozen_shadow_only":True,"trade_permission":False,
       "order_writer_present":False,"explicit_exact_fill_binding":False
    }

def test_limit_signal_and_market_execution_is_conflict_even_unique():
    res=classify_candidate(fixture())
    assert res["method_conflict"] is True
    assert res["verdict"]=="LIMIT_INTENT_MARKET_METHOD_CONFLICT_NOT_CAUSAL"
    assert res["verified_ah_execution"] is False

def test_execute_now_market_compatible_is_still_unverified():
    row=fixture(action="EXECUTE_NOW")
    res=classify_candidate(row)
    assert res["verdict"]=="UNIQUE_METHOD_COMPATIBLE_CAUSALITY_NOT_PROVED"
    assert res["realistic_cost_eligible"] is False

def test_execute_now_limit_does_not_gain_automatic_compatibility():
    row=fixture(action="EXECUTE_NOW",order_type="LIMIT")
    res=classify_candidate(row)
    assert res["verdict"]=="EXECUTE_NOW_LIMIT_METHOD_UNVERIFIED_NOT_CAUSAL"

def test_ambiguous_many_fills_or_events_never_auto_bind_even_method_compatible():
    rows=[
       fixture(0,status="AMBIGUOUS_EVIDENCE_COMPLETE_MATCH",action="EXECUTE_NOW"),
       fixture(1,status="AMBIGUOUS_EVIDENCE_COMPLETE_MATCH",action="EXECUTE_NOW"),
       fixture(2,status="AMBIGUOUS_EVIDENCE_COMPLETE_MATCH",action="EXECUTE_NOW"),
    ]
    rows[1]["synthetic_event_id"]=rows[0]["synthetic_event_id"]
    rows[2]["synthetic_fill_id"]=rows[0]["synthetic_fill_id"]
    result=inspect_fixture(rows)
    assert result["frozen_event_count"]==2
    assert result["venue_fill_row_count"]==2
    assert result["pair_status_counts"]["HEURISTIC_AMBIGUOUS_NOT_CAUSAL"]==3
    assert result["verified_ah_executions"]==0
    assert result["realistic_net_r"] is None

def test_duplicate_pair_never_counts_as_verified_second_trade():
    x=fixture()
    result=inspect_fixture([x,dict(x)])
    assert result["candidate_pairs"]==2
    assert result["duplicated_pairs"]==1
    assert result["pair_status_counts"]["DUPLICATE_HEURISTIC_PAIR_NOT_CAUSAL"]==1
    assert result["cost_claim_permitted"] is False

def test_source_writer_or_explicit_binding_cannot_be_assumed():
    for field,new in [
        ("trade_permission",True),
        ("order_writer_present",True),
        ("explicit_exact_fill_binding",True),
        ("trace_complete",False),
        ("frozen_shadow_only",False),
        ("synthetic_test_only",False),
        ("venue_order_state","NEW"),
        ("venue_trade_scope","CLOSE"),
    ]:
        r=fixture()
        r[field]=new
        assert classify_candidate(r)["verdict"]=="EVIDENCE_UNKNOWN_NOT_AUTHORIZED"

def test_any_heuristic_population_does_not_authorize_money_claim():
    rows=[fixture(i,status="UNIQUE_EVIDENCE_COMPLETE_MATCH",action="EXECUTE_NOW")
          for i in range(40)]
    result=inspect_fixture(rows)
    assert result["candidate_pairs"]==40
    assert result["verified_ah_executions"]==0
    assert result["exact_decision_order_fill_bindings_written"]==0
    assert result["cost_claim_permitted"] is False
    assert result["trade_permission"] is False
    assert result["scientific_pass_permitted"] is False
    assert result["production_promotion_permitted"] is False
    assert result["historical_r10_relabel_permitted"] is False
    assert result["new_trade_needed"] is False

def test_untrusted_or_non_synthetic_historical_data_fails_closed():
    assert classify_candidate({"action":"PLACE_LIMIT"})["verdict"]=="EVIDENCE_UNKNOWN_NOT_AUTHORIZED"
    assert inspect_fixture(None)["status"]=="UNKNOWN_FIXTURE"

def test_both_historical_audits_are_one_select_and_no_private_ids_in_output():
    paths=[
        REVIEWS/"p3_all_existing_candidate_base_crosscheck_readonly_20261016.sql",
        REVIEWS/"p3_unique_candidate_method_audit_readonly_20261016.sql"
    ]
    for path in paths:
        sql=path.read_text()
        statements=parse_sql(sql)
        assert len(statements)==1
        assert isinstance(statements[0].stmt,SelectStmt)
        body="\n".join(x for x in sql.splitlines()
                       if not x.lstrip().startswith("--")).lower()
        for forbidden in ("insert into","update public.","delete from","create table",
                          "alter table","drop table","grant ","revoke ","copy ",
                          "execute ","call ","pg_sleep("):
            assert forbidden not in body
        assert "false as " in body
    summary=paths[0].read_text().lower()
    detailed=paths[1].read_text().lower()
    assert "left join public.alpha_hunter_execution_decision_freezes_v01" in summary
    assert "left join public.alpha_hunter_fill_evidence" in summary
    assert "left join public.alpha_hunter_execution_order_evidence_v01" in summary
    assert "left join public.alpha_hunter_fill_traceability_runs" in summary
    assert "left join public.alpha_hunter_execution_fill_bindings_v01" in summary
    assert "distinct_venue_orders" in summary
    assert "permission_to_bind_or_restate_r10_execution" in detailed
    for private_selection in (
        "c.order_id,", "f.trade_id,", "c.fill_evidence_id,", "o.client_oid_sha256,"
    ):
        assert private_selection not in detailed
