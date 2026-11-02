"""Isolated P0 parent snapshot/account/protection trigger materialization acceptance.
No production service credentials, no actual exchange authority and no orders.
"""
import json
import os
from pathlib import Path
import subprocess
import time

import psycopg
import requests

ROOT=Path(__file__).resolve().parents[2]
DSN="host=127.0.0.1 port=5432 dbname=postgres user=postgres password=isolated-only"
BASE="http://127.0.0.1:3000"

def assert_local():
    if os.getenv("AH_P0_PARENT_LEDGER_LOCAL")!="1":
        raise RuntimeError("Explicit disposable-fixture flag required")
    if any(os.getenv(x) for x in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","BITGET_API_KEY","RENDER_API_KEY")):
        raise RuntimeError("Any production credential forbids test")

def psql(path):
    result=subprocess.run(["psql","-v","ON_ERROR_STOP=1","-f",str(path)],
        env={**os.environ,"PGHOST":"127.0.0.1","PGDATABASE":"postgres",
             "PGUSER":"postgres","PGPASSWORD":"isolated-only"},
        text=True,capture_output=True,timeout=120)
    if result.returncode:raise RuntimeError("Local schema failed: "+result.stderr[-1500:])

def ready():
    count=0
    for _ in range(90):
        try:
            statuses=[requests.get(BASE+"/"+tbl,params={"limit":"1"},timeout=2).status_code
                      for tbl in ("alpha_hunter_snapshots","alpha_hunter_account_state_snapshots")]
            if statuses==[200,200]:
                count+=1
                if count>=4:return
            else:count=0
        except requests.RequestException: count=0
        time.sleep(.25)
    raise RuntimeError("Isolated PostgREST never ready")

def parent(run, account):
    resp=requests.post(BASE+"/alpha_hunter_snapshots",json={
        "run_id":run,"collected_at_utc":"2026-11-02T11:30:00Z",
        "version":"synthetic-local-v0","product_type":"usdt-futures",
        "symbol_count":62,"error_count":0,
        "payload":{"_canonical_publication_state":"PENDING",
                   "validation_identity":{"run_source":"RENDER_CRON",
                                          "scientific_fingerprint_sha256":"SYNTHETIC-NO-TRADE"},
                   "private_account":account}},
        headers={"Prefer":"return=minimal"},timeout=(3,12))
    if resp.status_code not in (200,201,204):
        raise RuntimeError(f"Isolated parent insert HTTP {resp.status_code} {resp.text[:500]}")


def test_synthetic_payoff_and_calibration_interlocks(db):
    """Exact production trigger bodies, but local EMPTY cost-floor view only.

    Never claim real cost model or release: no authenticated quote, orders or
    R8/R9/R10 activation is created.
    """
    db.execute("""
      CREATE VIEW public.alpha_hunter_execution_cost_floor_status_v01
      AS SELECT 'ALL'::text AS cost_scope,
                NULL::double precision AS observable_taker_round_trip_floor_median_bps
      WHERE false
    """)
    db.execute("""
      CREATE TRIGGER trg_ah_payoff_geometry_health_v01 AFTER INSERT
      ON public.alpha_hunter_execution_decision_freezes_v01
      FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_capture_payoff_geometry_health_v01()
    """)
    db.execute("""
      CREATE TRIGGER trg_ah_calibrated_paper_order_v02 AFTER INSERT
      ON public.alpha_hunter_execution_decision_freezes_v01
      FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_create_calibrated_paper_order_v02()
    """)
    db.execute("""
      INSERT INTO private.alpha_hunter_payoff_geometry_health_specs_v01(
         spec_id,status,registered_at_utc,minimum_history_n,
         cost_fragile_threshold_r,stop_reference,target_reference,
         minimum_forward_observations,minimum_forward_symbols,minimum_forward_days)
      VALUES ('PAYOFF-GEOMETRY-HEALTH-V01','COLLECTING',
              '2026-10-01 00:00+00',30,0.25,'STRUCTURAL','STRUCTURAL',100,1,1)
    """)
    db.execute("""
      INSERT INTO public.alpha_hunter_execution_decision_freezes_v01(
        execution_event_id,spec_id,decision_observation_id,strategy_instance_id,
        decision_run_id,symbol,strategy_id,direction,action,
        decision_observed_at_utc,decision_captured_at_utc,frozen_at_utc,
        reference_price,planned_entry_price,stop_price,target_price,reward_risk,
        best_bid,best_ask,midpoint,entry_cross_price,quote_complete,prospective_capture)
      VALUES('synthetic-geometry-1','SYNTHETIC-RESEARCH-NO-PROFIT',
             'synthetic-observation-1','synthetic-instance-1',
             'parent-synthetic-connected','TESTUSDT','S2','SHORT','EXECUTE_NOW',
             '2026-11-02 11:30+00','2026-11-02 11:31+00','2026-11-02 11:31+00',
             100,100,103,85,5,99.9,100.1,100,99.9,true,true)
    """)
    proof=db.execute("""
      SELECT geometry_health,history_n,trade_permission,
             production_promotion_permitted,order_path
      FROM private.alpha_hunter_payoff_geometry_health_observations_v01
      WHERE execution_event_id='synthetic-geometry-1'
    """).fetchone()
    if proof!=("INSUFFICIENT_HISTORY",0,False,False,"NONE"):
        raise AssertionError("Synthetic payoff trigger did not fail closed "+str(proof))
    orders=db.execute("SELECT count(*) FROM private.alpha_hunter_calibrated_paper_orders_v01").fetchone()[0]
    if orders!=0:
        raise AssertionError("Calibrated paper order created without activated policy")
    with db.transaction():
        db.execute("SAVEPOINT payoff_trial")
        db.execute("""
          INSERT INTO public.alpha_hunter_execution_decision_freezes_v01(
            execution_event_id,spec_id,decision_observation_id,strategy_instance_id,
            decision_run_id,symbol,strategy_id,direction,action,
            decision_observed_at_utc,decision_captured_at_utc,frozen_at_utc,
            planned_entry_price,stop_price,target_price,reward_risk,
            best_bid,best_ask,midpoint,entry_cross_price,quote_complete,prospective_capture)
          VALUES('synthetic-geometry-rollback','SYNTHETIC-RESEARCH-NO-PROFIT',
                 'obs-rollback','instance-rollback','parent-synthetic-connected',
                 'TESTUSDT','S2','SHORT','EXECUTE_NOW','2026-11-02 11:30+00',
                 '2026-11-02 11:31+00','2026-11-02 11:31+00',
                 100,103,85,5,99.9,100.1,100,99.9,true,true)
        """)
        db.execute("ROLLBACK TO SAVEPOINT payoff_trial")
    after=db.execute("""
      SELECT count(*) FROM private.alpha_hunter_payoff_geometry_health_observations_v01
      WHERE execution_event_id='synthetic-geometry-rollback'
    """).fetchone()[0]
    if after:
        raise AssertionError("Rolled back payoff created orphan")
    return {"geometry_status":proof[0],"history_n":proof[1],
            "calibrated_paper_orders_created":orders,"rollback":"PASS",
            "cost_floor_view":"SYNTHETIC_EMPTY_STUB_NOT_PRODUCTION_EXACT",
            "trade_permission":False}

def main():
    assert_local()
    psql(ROOT/"tests/fixtures/p0_production_catalog_trigger_chain_20261102.sql")
    psql(ROOT/"tests/fixtures/p0_catalog_parent_ledger_protection_addendum_20261102.sql")
    with psycopg.connect(DSN,autocommit=True) as db:
        db.execute("NOTIFY pgrst,'reload schema'")
    ready()
    parent("parent-no-private",{"status":"NOT_CONFIGURED"})
    parent("parent-unknown",{"status":"CONNECTED","accounts":[],"open_positions":[],
                             "open_position_count":0})
    synthetic={
        "status":"CONNECTED",
        "accounts":[{"margin_coin":"USDT","account_equity":"1000","available":"950",
                     "unrealized_pl":"-10","locked":"50"}],
        "open_position_count":1,
        "open_positions":[{
            "symbol":"TESTUSDT","hold_side":"short","total":"2",
            "open_price_avg":"100","mark_price":"101","unrealized_pl":"-2",
            "take_profit":None,"stop_loss":None,
            "protection_observation_status":"DATA_INSUFFICIENT",
            "protection_orders":[],
            "margin_mode":"isolated","leverage":"1"}],
        "protection_observation_status":"DATA_INSUFFICIENT",
        "api_permission_probe_status":"NOT_TESTED"}
    parent("parent-synthetic-connected",synthetic)
    with psycopg.connect(DSN,autocommit=True) as db:
        rows=db.execute("""
            SELECT s.run_id,m.status,a.connection_status,a.schema_validated,
                   a.complete, a.trade_permission,
                   (SELECT count(*) FROM private.alpha_hunter_snapshot_slim_v01 sl
                    WHERE sl.run_id=s.run_id) slim_count,
                   (SELECT count(*) FROM public.alpha_hunter_open_position_snapshots ps
                    WHERE ps.account_snapshot_id=a.account_snapshot_id) open_positions
            FROM public.alpha_hunter_snapshots s
            JOIN public.alpha_hunter_account_ledger_materialization_events m
              ON m.run_id=s.run_id
            JOIN public.alpha_hunter_account_state_snapshots a
              ON a.account_snapshot_id=m.account_snapshot_id
            ORDER BY s.run_id
        """).fetchall()
        if len(rows)!=3: raise AssertionError(f"Expected exactly 3 parent materializations, got {rows}")
        states={x[0]:x for x in rows}
        if states["parent-no-private"][1]!="MATERIALIZED_DISCONNECTED":
            raise AssertionError(f"Disconnected parent mismatch {states}")
        if states["parent-unknown"][1]!="MATERIALIZED_INSUFFICIENT":
            raise AssertionError(f"Invalid USDT account must fail closed: {states}")
        x=states["parent-synthetic-connected"]
        if (x[1],x[2],x[3],x[4],x[5],x[6],x[7])!=(
            "MATERIALIZED_CONNECTED","CONNECTED_READ_ONLY",True,True,False,1,1):
            raise AssertionError(f"Parent ledger/position materialization failed: {x}")
        protection=db.execute("""
            SELECT count(*),count(*) FILTER(WHERE trade_permission=false)
            FROM public.alpha_hunter_protection_reconciliation_events_v01
        """).fetchone()
        if protection[0]<1 or protection[0]!=protection[1]:
            raise AssertionError(f"Missing or unsafe protection reconciliation: {protection}")
        ledger=db.execute("""
            SELECT count(*) FROM public.alpha_hunter_open_position_snapshots
            WHERE trade_permission=true
        """).fetchone()[0]
        if ledger: raise AssertionError("Synthetic protected ledger granted order authority")
        # Drop graph in a savepoint-less isolated *transaction*, not the real database.
        # A rollback must leave the DB with original synthetic evidence.
        before=db.execute("SELECT count(*) FROM public.alpha_hunter_account_state_snapshots").fetchone()[0]
        with db.transaction():
            db.execute("SAVEPOINT synthetic_rollback")
            db.execute("INSERT INTO public.alpha_hunter_snapshots(run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload) VALUES('temporary-rollback',now(),'test','usdt-futures',0,0,%s)",(psycopg.types.json.Jsonb({"private_account":{"status":"NOT_CONFIGURED"}}),))
            db.execute("ROLLBACK TO SAVEPOINT synthetic_rollback")
        after=db.execute("SELECT count(*) FROM public.alpha_hunter_account_state_snapshots").fetchone()[0]
        if before!=after:raise AssertionError("Synthetic rollback changed account ledger count")
        geometry=test_synthetic_payoff_and_calibration_interlocks(db)
        report={"status":"ISOLATED_PARENT_LEDGER_AND_PROTECTION_PASS",
                "postgres_major":int(db.execute("SHOW server_version_num").fetchone()[0])//10000,
                "materialized":len(rows),"open_positions":1,
                "protection_events":protection[0],
                "account_rollback_passed":True,
                "payoff_and_calibration":geometry,
                "paper_only":True,"trade_permission":False,
                "full_production_equivalence":False,
                "release_authorization":False,
                "r9_r10_untouched":True}
    Path("parent_ledger_evidence").mkdir(exist_ok=True)
    Path("parent_ledger_evidence/report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,sort_keys=True))

if __name__=="__main__":
    main()
