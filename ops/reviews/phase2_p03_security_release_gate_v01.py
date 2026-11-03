"""P0.3 deterministic reviewer-gate assessment, NO release mechanism.

Input is a read-only production CATALOG SNAPSHOT, not credentials, not an
external identity proof. Every code path remains NO-GO or REVIEW_REQUIRED:
a self-authored tool cannot sign independent DBA/security decisions.
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_APPROVALS = (
    "independent_dba_signed",
    "independent_security_signed",
    "independent_science_risk_signed",
    "independent_operations_signed",
    "immutable_sha_reviewed_and_signed",
    "production_authorization",
)


def assess(snapshot: dict) -> dict:
    issues=[]
    fatal=[]
    roles=snapshot.get("roles") or {}
    relations=snapshot.get("relations") or {}
    funcs=snapshot.get("functions") or {}
    src=snapshot.get("source_custody") or {}
    release=snapshot.get("release_surface") or {}
    pos=snapshot.get("immutable_positions") or {}
    for role in ("anon","authenticated","service_role"):
        if role not in roles or not isinstance(roles[role].get("bypassrls"),bool):
            fatal.append("ROLE_METADATA_MISSING:"+role)
    if roles.get("anon",{}).get("bypassrls") is not False:
        fatal.append("UNSAFE_ANONYMOUS_RLS_BYPASS")
    if roles.get("authenticated",{}).get("bypassrls") is not False:
        fatal.append("UNSAFE_AUTHENTICATED_RLS_BYPASS")
    if roles.get("service_role",{}).get("bypassrls") is True:
        issues.append("PRIVILEGED_SERVICE_ROLE_REQUIRES_INDEPENDENT_API_AUTHZ")
    else:
        fatal.append("SERVICE_ROLE_BYPASSRLs_METADATA_UNEXPECTED")
    for table in ("alpha_hunter_snapshots","alpha_hunter_symbol_snapshots",
                  "alpha_hunter_paper_exit_attempts_v04",
                  "alpha_hunter_profitability_test_activations_v01"):
        item=relations.get(table) or {}
        if item.get("rls_enabled") is not True:
            fatal.append("RLS_NOT_VERIFIED:"+table)
        if not isinstance(item.get("policies"),int):
            fatal.append("RLS_POLICY_COUNT_UNKNOWN:"+table)
        if item.get("anon_insert_grant") or item.get("authenticated_insert_grant"):
            issues.append("OVERBROAD_SQL_PUBLIC_WRITE_GRANT:"+table)
    if funcs.get("public_security_definer_anon_executable") != 0:
        fatal.append("PUBLIC_EXECUTABLE_SECURITY_DEFINER")
    if funcs.get("private_security_definer_anon_executable") != 0:
        fatal.append("PRIVATE_SECURITY_DEFINER_EXPOSED_ANON")
    if funcs.get("private_security_definer_authenticated_executable") != 0:
        fatal.append("PRIVATE_SECURITY_DEFINER_EXPOSED_AUTH")
    if funcs.get("private_schema_anon_usage") is not False or funcs.get("private_schema_authenticated_usage") is not False:
        fatal.append("PRIVATE_SCHEMA_PUBLIC_USAGE")
    if src.get("receipts_since_2026_11_01") is None or src.get("verified_parent_receipts") is None:
        fatal.append("SOURCE_CUSTODY_COUNTS_MISSING")
    elif src.get("verified_parent_receipts") < src.get("receipts_since_2026_11_01"):
        issues.append("LEGACY_MONITORING_RECEIPTS_NOT_VERIFIED")
    if src.get("provider_signature_receipts") != src.get("receipts_since_2026_11_01"):
        issues.append("UNSIGNED_OR_UNATTESTED_PROVIDER_QUOTE_CUSTODY")
    if src.get("confirmed_alert_delivery_acks") is None:
        issues.append("DURABLE_ALERT_RECIPIENT_CONFIRMATION_UNPROVEN")
    if pos.get("historical_first_entry_ordering_status") != "RESOLVED_INDEPENDENTLY":
        issues.append("FIRST_ENTRY_ORDERING_STILL_UNRESOLVED")
    if release.get("protected_cron",{}).get("branch") != "main":
        fatal.append("PROTECTED_CRON_BRANCH_UNEXPECTED")
    if release.get("protected_cron",{}).get("auto_deploy") is True:
        issues.append("PROTECTED_MAIN_AUTO_DEPLOY_ENABLED")
    if release.get("github_main_branch_protected") is not True:
        issues.append("MAIN_BRANCH_NOT_ENFORCEABLY_PROTECTED")
    target=release.get("approved_isolated_successor_service")
    if not isinstance(target,dict) or not target.get("isolated"):
        issues.append("NO_APPROVED_ISOLATED_SUCCESSOR_TARGET")
    else:
        if target.get("service_id") == release.get("protected_cron",{}).get("service_id"):
            fatal.append("RELEASE_TARGET_IS_PROTECTED_CRON")
        if target.get("source_branch") == "main" or target.get("auto_deploy") is not False:
            fatal.append("RELEASE_TARGET_CAN_TRIGGER_MAIN_OR_UNATTENDED_DEPLOY")
    for key in REQUIRED_APPROVALS:
        if release.get(key) is not True:
            issues.append("HUMAN_RELEASE_APPROVAL_MISSING:"+key)
    if pos.get("real_order_permission") is not False or pos.get("paper_only") is not True:
        fatal.append("REAL_ORDER_AUTHORITY_NOT_DENIED")
    if pos.get("no_production_write_permitted") is not True:
        fatal.append("PRODUCTION_WRITE_GATE_NOT_FROZEN")
    if snapshot.get("evidence_method","").lower().find("read-only")<0:
        fatal.append("SOURCE_AUDIT_NOT_READ_ONLY")
    issues=sorted(set(issues))
    fatal=sorted(set(fatal))
    return {
        "status":"PRODUCTION_NO_GO",
        "validation":"CATALOG_SNAPSHOT_CLASSIFIER_NOT_LIVE_REQUEST_PROOF",
        "not_an_independent_security_approval":True,
        "blockers":issues,
        "critical_invariants":fatal,
        "release_action_permitted":False,
        "branch_merge_permitted":False,
        "cron_change_permitted":False,
        "production_sql_permitted":False,
        "real_trade_permission":False,
        "verified_guard_scope":"NO_LIVE_SERVICE_ROLE_JWT_OR_EXCHANGE_FILLS"
    }


def main():
    root=Path(__file__).resolve().parents[2]
    source=root/"ops/reviews/p03_live_prod_security_baseline_20261102.json"
    report=assess(json.loads(source.read_text()))
    print(json.dumps(report,sort_keys=True,indent=2))
    out=Path("p03_readonly_security_evidence")
    out.mkdir(exist_ok=True)
    (out/"no_go_assessment.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    if report["critical_invariants"]:
        raise SystemExit("Frozen metadata violates critical invariant: "+str(report["critical_invariants"]))
    if report["release_action_permitted"]:
        raise SystemExit("No-Go classifier incorrectly permitted release")


if __name__=="__main__":
    main()
