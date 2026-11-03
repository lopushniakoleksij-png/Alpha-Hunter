"""P0.3 independent reviewer-only Supabase API role test — strictly GET only.

Runs against exact project hostname; keys are supplied only in REVIEWER'S
local environment, never in GitHub, logs or ChatGPT. No PATCH/POST/DELETE, SQL,
RPC, orders, auth login, role mutation or production data output.

A successful run is bounded API evidence, NEVER production release approval.
"""
from __future__ import annotations
import argparse
import json
import os
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PROJECT="https://yjgtjzymfurqzqqxcrnp.supabase.co"
ROUTES=(
    ("parent", "/rest/v1/alpha_hunter_snapshots?select=run_id&limit=1"),
    ("child", "/rest/v1/alpha_hunter_symbol_snapshots?select=run_id&limit=1"),
    ("exit", "/rest/v1/alpha_hunter_paper_exit_attempts_v04?select=source_run_id&limit=1"),
)
ALLOWED_ROLES=("no-key","anon","authenticated","service_role")
CREDENTIAL_ENV={
    "anon":"AH_P03_PUBLISHABLE_KEY",
    "authenticated":"AH_P03_PUBLISHABLE_KEY",
    "service_role":"AH_P03_PRIVILEGED_REVIEW_KEY",
}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("External redirect refused")

def real_get(path:str,headers:dict[str,str])->tuple[int,bytes]:
    if not path.startswith("/") or "://" in path or urlsplit(PROJECT+path).netloc!="yjgtjzymfurqzqqxcrnp.supabase.co":
        raise RuntimeError("Unexpected external hostname")
    request=urllib.request.Request(PROJECT+path,headers=headers,method="GET")
    opener=urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), NoRedirect()
    )
    try:
        with opener.open(request,timeout=18) as resp:
            return int(resp.status),resp.read(8192)
    except urllib.error.HTTPError as err:
        return int(err.code),err.read(8192)

def _safe_key(val:str,role:str)->str:
    if not val or val.strip()!=val or "\n" in val or "\r" in val:
        raise RuntimeError("Missing/invalid privately held key")
    if role in ("anon","authenticated"):
        if not (val.startswith("sb_publishable_") or val.startswith("eyJ")):
            raise RuntimeError("Only publishable / legacy anon client keys allowed")
    if role=="service_role":
        if not (val.startswith("sb_secret_") or val.startswith("eyJ")):
            raise RuntimeError("Only reviewer-held secret or legacy service key allowed")
    return val

def _evaluate(role,route,status,body)->tuple[bool,str]:
    if role=="no-key":
        return status in (401,403),"api_key_required" if status in (401,403) else "gateway_not_denied"
    if role in ("anon","authenticated"):
        if route in ("parent","child"):
            if status!=200:return False,"rls_read_not_verified"
            try:
                # Real table has zero RLS policies; successful SELECT MUST return no rows.
                data=json.loads(body)
                return data==[],"rls_zero_rows" if data==[] else "unexpected_public_rows"
            except (ValueError,TypeError):
                return False,"unexpected_response_type"
        return status in (401,403),"sensitive_table_denied" if status in (401,403) else "sensitive_table_access_unexpected"
    if role=="service_role":
        if status!=200:return False,"privileged_read_failed"
        try:
            records=json.loads(body)
            return isinstance(records,list),"privileged_read_http_ok" if isinstance(records,list) else "unexpected_response_type"
        except (ValueError,TypeError):
            return False,"unexpected_response_type"
    return False,"unknown_role"

def run(role:str,env:dict[str,str]|None=None,get=real_get)->dict:
    if role not in ALLOWED_ROLES:raise RuntimeError("Invalid review role")
    env=dict(os.environ if env is None else env)
    if role!="no-key" and env.get("AH_P03_EXPLICIT_API_REVIEW")!="1":
        raise RuntimeError("Reviewer opt-in required, no HTTP requests performed")
    if role=="service_role" and env.get("AH_P03_PRIVILEGED_READ_AUTHORIZED")!="1":
        raise RuntimeError("Independent reviewer privileged read authorization required")
    headers={"Accept":"application/json","User-Agent":"AH-P03-Independent-ReadOnly-Reviewer/1.0"}
    if role!="no-key":
        key=_safe_key(env.get(CREDENTIAL_ENV[role],""),role)
        headers["apikey"]=key
        if role=="authenticated":
            token=env.get("AH_P03_AUTH_USER_ACCESS_TOKEN","")
            if not token or token.strip()!=token or "\r" in token or "\n" in token:
                raise RuntimeError("Existing signed-in user's JWT required (no login performed)")
            headers["Authorization"]="Bearer "+token
        if role=="service_role" and key.startswith("eyJ"):
            headers["Authorization"]="Bearer "+key
    checks={}
    if role=="authenticated":
        code,_=get("/auth/v1/user",headers)
        checks["signed_in_token"]={"http":code,"pass":code==200,
                                   "detail":"jwt_authenticated" if code==200 else "jwt_unverified"}
        if code!=200:
            return {"status":"BLOCKED_INVALID_AUTHENTICATED_TOKEN",
                    "role":role,"checks":checks,"release_authorized":False,
                    "independent_human_signoff":False,"production_write_performed":False}
    for label,route in ROUTES:
        code,body=get(route,headers)
        okay,reason=_evaluate(role,label,code,body)
        # The raw response is NEVER persisted or displayed.
        checks[label]={"http":code,"pass":okay,"detail":reason}
    all_pass=all(x["pass"] for x in checks.values())
    status=("NO_KEY_GATE_PASS_NOT_ROLE_PROOF" if role=="no-key"
            else "BOUNDED_API_ROLE_CHECK_PASS_AWAIT_HUMAN_SIGNOFF") if all_pass else "BLOCKED_ROLE_API_MISMATCH"
    return {"status":status,"role":role,"checks":checks,
            "all_checks_passed":all_pass,"live_api_hostname":"yjgtjzymfurqzqqxcrnp.supabase.co",
            "production_write_performed":False,"independent_human_signoff":False,
            "reviewer_has_signed":False,"production_release_authorized":False,
            "trade_permission":False}

def main():
    parser=argparse.ArgumentParser(description="Read-only reviewer Supabase role-check; never authorizes release")
    parser.add_argument("--role",required=True,choices=ALLOWED_ROLES)
    args=parser.parse_args()
    outcome=run(args.role)
    print(json.dumps(outcome,sort_keys=True,indent=2))
    if not outcome.get("all_checks_passed",False):
        raise SystemExit(2)

if __name__=="__main__":
    main()
