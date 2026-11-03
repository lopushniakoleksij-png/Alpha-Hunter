"""P0 real isolated PostgREST effective-role/real-table RLS checks.

All privileges / JWT credentials are ephemeral synthetic GitHub services only.
No existing Supabase configuration, no paid infrastructure, no business keys.
This mirrors the security property (deny public, allow dedicated writer), not
actual production BYPASSRLS or network/proxy gateway configuration.
"""
import base64
import hashlib
import hmac
import json
import os
import subprocess
import time
from pathlib import Path
import requests
import psycopg

DSN="host=127.0.0.1 port=5432 dbname=postgres user=postgres password=isolated-only"
BASE="http://127.0.0.1:3000"
SECRET="local-github-p0-fake-jwt-secret-exactly-64-characters-string"

def jwt(role):
    def b64(x):
        return base64.urlsafe_b64encode(json.dumps(x,separators=(",",":"),sort_keys=True).encode()).rstrip(b"=").decode()
    h=b64({"alg":"HS256","typ":"JWT"})
    p=b64({"role":role,"iat":1700000000,"exp":1900000000,"iss":"SYNTHETIC_P0"})
    sig=base64.urlsafe_b64encode(hmac.new(SECRET.encode(),(h+"."+p).encode(),hashlib.sha256).digest()).rstrip(b"=").decode()
    return h+"."+p+"."+sig

def request(method,table,role=None,**kw):
    h={"Accept":"application/json","Prefer":"return=minimal"}
    if role:
        h["Authorization"]="Bearer "+jwt(role)
    return requests.request(method,BASE+"/"+table,headers=h,timeout=(2,10),**kw)

def main():
    if os.getenv("AH_P0_ISOLATED_RLS_HTTP")!="1" or any(
        os.getenv(x) for x in ["SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","BITGET_API_KEY","RENDER_API_KEY"]
    ):raise RuntimeError("Refuse non-isolated role test or production credentials")
    with psycopg.connect(DSN,autocommit=True) as db:
        for role in ("ah_p0_anon","ah_p0_authenticated","ah_p0_writer"):
            db.execute("CREATE ROLE "+role+" NOLOGIN")
    env={**os.environ,"PGHOST":"127.0.0.1","PGDATABASE":"postgres",
         "PGUSER":"postgres","PGPASSWORD":"isolated-only"}
    for path in (
        "tests/fixtures/p0_production_catalog_trigger_chain_20261102.sql",
        "tests/fixtures/p0_catalog_parent_ledger_protection_addendum_20261102.sql",
    ):
        p=subprocess.run(["psql","-v","ON_ERROR_STOP=1","-f",path],
                          capture_output=True,text=True,timeout=90,env=env)
        if p.returncode:raise RuntimeError(p.stderr[-1900:])
    with psycopg.connect(DSN,autocommit=True) as db:
        db.execute("""
            GRANT USAGE ON SCHEMA public TO ah_p0_anon,ah_p0_authenticated,ah_p0_writer
        """)
        for tab in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots",
                    "alpha_hunter_account_state_snapshots","alpha_hunter_open_position_snapshots"):
            db.execute("ALTER TABLE public."+tab+" ENABLE ROW LEVEL SECURITY")
            db.execute("GRANT SELECT,INSERT ON public."+tab+
                       " TO ah_p0_anon,ah_p0_authenticated,ah_p0_writer")
        # Only the dedicated service writer has a policy; SQL GRANT alone is
        # intentionally insufficient for the anonymous and authenticated roles.
        for tab in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots",
                    "alpha_hunter_account_state_snapshots","alpha_hunter_open_position_snapshots"):
            db.execute("CREATE POLICY p0_writer_evidence ON public."+tab+
                       " FOR ALL TO ah_p0_writer USING (true) WITH CHECK (true)")
        db.execute("NOTIFY pgrst,'reload schema'")
    stable=0
    for _ in range(90):
        try:
            r=request("GET","alpha_hunter_snapshots",params={"select":"run_id","limit":1})
            if r.status_code==200:
                stable+=1
                if stable>=4:break
            else:stable=0
        except requests.RequestException:stable=0
        time.sleep(.3)
    else:raise RuntimeError("PostgREST synthetic anonymized schema not ready")
    bad={}
    for actor in (None,"ah_p0_authenticated"):
        name=actor or "ah_p0_anon"
        for table in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots"):
            r=request("GET",table,actor,params={"select":"run_id","limit":1})
            if r.status_code!=200 or r.json()!=[]:
                raise AssertionError(f"{name} RLS SELECT not denied: {table} {r.status_code} {r.text[:150]}")
            r=request("POST",table,actor,json={
                "run_id":"forgery","symbol":"FRAUDUSDT",
                "version":"forgery","collected_at_utc":"2026-11-02T11:30:00Z",
                "product_type":"usdt-futures","symbol_count":1,
                "payload":{}},)
            if r.status_code<400:
                raise AssertionError(f"{name} forged HTTP insert succeeded on {table}")
            bad[name+":"+table]=r.status_code
    body={"run_id":"isolated-role-writer","version":"safe-synthetic",
          "collected_at_utc":"2026-11-02T11:30:00Z",
          "product_type":"usdt-futures","symbol_count":0,
          "error_count":0,
          "payload":{"private_account":{"status":"NOT_CONFIGURED"},
                     "_canonical_publication_state":"PENDING"}}
    r=request("POST","alpha_hunter_snapshots","ah_p0_writer",json=body)
    if r.status_code not in (200,201,204):
        raise AssertionError(f"isolated dedicated writer rejected {r.status_code}: {r.text[:700]}")
    with psycopg.connect(DSN,autocommit=True) as db:
        n=db.execute("SELECT COUNT(*) FROM public.alpha_hunter_snapshots WHERE run_id='isolated-role-writer'").fetchone()[0]
        if n!=1:raise AssertionError("writer did not persist one parent")
        failed=db.execute("SELECT COUNT(*) FROM public.alpha_hunter_snapshots WHERE run_id='forgery'").fetchone()[0]
        if failed:raise AssertionError("privileged bypass or spoofed actor inserted data")
        ledger=db.execute("SELECT status FROM public.alpha_hunter_account_ledger_materialization_events WHERE run_id='isolated-role-writer'").fetchone()
        if not ledger or ledger[0]!="MATERIALIZED_DISCONNECTED":
            raise AssertionError("writer SECDEF parent/ledger effect unexpected "+str(ledger))
    out={"status":"ISOLATED_POSTGREST_ROLE_AUTHZ_PASS",
         "postgres_major":int(os.environ["AH_P0_PG_MAJOR"]),
         "forbidden_anonymous_authenticated_http":bad,
         "dedicated_writer_synthetic_parent":1,
         "public_forgery_committed":0,
         "account_materialization":"MATERIALIZED_DISCONNECTED",
         "real_production_roles_tested":False,
         "production_equivalence":False,"trade_permission":False,
         "DBA_SECURITY_SIGNOFF":False}
    Path("p0_rls_http_results").mkdir(exist_ok=True)
    Path("p0_rls_http_results/report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__":
    main()
