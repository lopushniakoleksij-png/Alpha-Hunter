"""Execute real unmodified R8/R9/R10 guard SQL in isolated PG16/17.

Only ephemeral schema and synthetic activation rows; no scanner or exchange.
"""
import json
import os
import pathlib
import subprocess
import psycopg

DSN="host=127.0.0.1 port=5432 dbname=postgres user=postgres password=isolated-only"
GUARDS=[
 ("R8","SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003",
  "alpha_hunter_paper_execution_integrity_activation_v08","PAPER_EXECUTION_R8"),
 ("R9","SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004",
  "alpha_hunter_paper_execution_activation_v09","PAPER_EXECUTION_R9"),
 ("R10","P0-SYNTHETIC-R10-TEST-ONLY",
  "alpha_hunter_paper_execution_activation_v10","P0-SYNTHETIC-R10-EXEC"),
]
T="2026-11-02 12:30:00+00"
DIFFERENT="2026-11-02 12:31:00+00"
FP="P0-SYNTHETIC-IDENTITY-NO-TRADES"
OTHER="P0-BAD-FINGERPRINT"
INSERT_ACTIVATION="""INSERT INTO public.alpha_hunter_profitability_test_activations_v01(
 spec_id,baseline_run_id,started_at_utc,
 baseline_config_sha256,baseline_git_commit,
 baseline_previous_snapshot_source,baseline_catalyst_version,
 baseline_symbol_rows,baseline_strategy_rows,baseline_microstructure_rows,
 baseline_closed_candle_rows,activation_checks,
 baseline_scientific_fingerprint_sha256
) VALUES (%s,'LOCAL-TEST-ONLY',%s,
 'synthetic','synthetic','synthetic','synthetic',
 0,0,0,0,'{"never_trade":true}'::jsonb,%s)"""
def assert_isolated():
    if os.getenv("AH_P0_ISOLATED_R8R9R10")!="1":
        raise RuntimeError("Explicit local gate not enabled")
    if any(os.getenv(x) for x in
           ["SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","BITGET_API_KEY",
            "BITGET_SECRET_KEY","RENDER_API_KEY"]):
        raise RuntimeError("Production credentials forbidden")
def run_sql(path):
    env={**os.environ,"PGHOST":"127.0.0.1","PGDATABASE":"postgres",
         "PGUSER":"postgres","PGPASSWORD":"isolated-only"}
    r=subprocess.run(["psql","-X","-v","ON_ERROR_STOP=1","-f",path],
                     env=env,text=True,capture_output=True,timeout=100)
    if r.returncode:raise RuntimeError("Fixture compilation: "+r.stderr[-1200:])
def count(conn,spec):
    return conn.execute(
        "SELECT count(*) FROM public.alpha_hunter_profitability_test_activations_v01 WHERE spec_id=%s",
        (spec,)).fetchone()[0]
def act(conn,spec,t,fp):
    return conn.execute(INSERT_ACTIVATION,(spec,t,fp)).rowcount
def main():
    assert_isolated()
    root=pathlib.Path(__file__).resolve().parents[2]
    run_sql(str(root/"tests/fixtures/p0_production_catalog_trigger_chain_20261102.sql"))
    run_sql(str(root/"tests/fixtures/p0_r8_r9_r10_sealed_guard_isolated_20261102.sql"))
    result={}
    with psycopg.connect(DSN,autocommit=True) as db:
        major=int(db.execute("SHOW server_version_num").fetchone()[0])//10000
        if major not in (16,17):raise AssertionError("Only PG16 or PG17")
        db.execute("""
            INSERT INTO public.alpha_hunter_profitability_test_specs_v01(
             spec_id,frozen_git_commit,scientific_role)
            VALUES(%s,'TEST-ONLY','SUCCESSOR_EXECUTED_PAPER_24H_R10')
        """,(GUARDS[2][1],))
        for name,spec,table,id in GUARDS:
            if act(db,spec,T,FP)!=0 or count(db,spec)!=0:
                raise AssertionError(name+" missing execution proof was admitted")
            if name=="R10":
                db.execute("INSERT INTO public."+table+
                           "(activation_id,spec_id,activated_at_utc,scientific_fingerprint_sha256) VALUES(%s,%s,%s,%s)",
                           (id,spec,T,FP))
            else:
                db.execute("INSERT INTO public."+table+
                           "(activation_id,activated_at_utc,scientific_fingerprint_sha256) VALUES(%s,%s,%s)",
                           (id,T,FP))
            for wrong_t,wrong_fp,expected in [
                (DIFFERENT,FP,"timestamp"),
                (T,OTHER,"fingerprint")]:
                failed=False
                try:
                    with db.transaction():
                        act(db,spec,wrong_t,wrong_fp)
                except psycopg.errors.RaiseException:
                    failed=True
                if not failed or count(db,spec):
                    raise AssertionError(name+" did not reject mismatched "+expected)
            if act(db,spec,T,FP)!=1 or count(db,spec)!=1:
                raise AssertionError(name+" cannot record aligned synthetic activation")
            row=db.execute("""
                SELECT shadow_only,trade_permission,production_promotion_permitted,order_path
                FROM public.alpha_hunter_profitability_test_activations_v01 WHERE spec_id=%s
            """,(spec,)).fetchone()
            if row!=(True,False,False,"NONE"):
                raise AssertionError(name+" changed paper-only authority "+str(row))
            result[name]={"missing_counterpart":"DENIED",
                         "mismatch_timestamp":"REJECTED",
                         "mismatch_fingerprint":"REJECTED",
                         "exact_counterpart":"SYNTHETIC_RECORD_ONLY",
                         "trade_permission":False}
        # Without the explicitly preregistered successor R10 role, the R10
        # guard should NOT recognize an unrelated scientific role as R10.
        # This is role segregation, not permission to promote another cohort.
        db.execute("""
            INSERT INTO public.alpha_hunter_profitability_test_specs_v01(
              spec_id,frozen_git_commit,scientific_role)
            VALUES('P0-UNRELATED-SYNTHETIC-ROLE','TEST-ONLY','RESEARCH_UNRELATED')
        """)
        db.execute("""
            INSERT INTO public.alpha_hunter_paper_execution_activation_v10(
              activation_id,spec_id,activated_at_utc,scientific_fingerprint_sha256)
            VALUES('UNRELATED-P0','P0-UNRELATED-SYNTHETIC-ROLE',%s,%s)
        """,(T,FP))
        if act(db,"P0-UNRELATED-SYNTHETIC-ROLE",T,FP)!=1:
            raise AssertionError("Unrelated role behavior changed unexpectedly")
        if db.execute("""
            SELECT count(*) FROM public.alpha_hunter_profitability_test_activations_v01
            WHERE trade_permission=true OR production_promotion_permitted=true
               OR shadow_only=false OR order_path<>'NONE'
        """).fetchone()[0]:
            raise AssertionError("Any synthetic activation granted order authority")
        n=db.execute("SELECT count(*) FROM public.alpha_hunter_profitability_test_activations_v01").fetchone()[0]
        if n!=4:raise AssertionError(f"Unexpected synthetic activation count {n}")
        # Actual rollback: entirely separate transaction, ensures blocked
        # evidence cannot create orphan side effects when upstream aborts.
        with db.transaction():
            db.execute("SAVEPOINT p0_activation_rollback")
            db.execute("""
              INSERT INTO public.alpha_hunter_profitability_test_specs_v01(
                  spec_id,frozen_git_commit,scientific_role)
              VALUES('P0-ROLLBACK-ONLY','TEST-ONLY','RESEARCH_UNRELATED')
            """)
            act(db,"P0-ROLLBACK-ONLY",T,FP)
            db.execute("ROLLBACK TO SAVEPOINT p0_activation_rollback")
        if count(db,"P0-ROLLBACK-ONLY"):
            raise AssertionError("Rollback left an activation")
    report={
      "status":"P0_R8R9R10_GUARD_CONTRACT_ISOLATED_PASS",
      "postgres_major":major,
      "scope":"REAL_GUARD_FUNCTION_BODIES_MINIMAL_COUNTERPART_ROWTYPES",
      "guards":result,"transaction_rollback":"PASS",
      "synthetic_activation_rows_only":True,
      "real_R8_R9_R10_untouched":True,
      "production_runtime_execution":False,
      "profitability_promoted":False,
      "trade_permission":False,
      "independent_signoff":False
    }
    out=pathlib.Path("p0_activation_guard_evidence")
    out.mkdir(exist_ok=True)
    (out/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":
    main()
