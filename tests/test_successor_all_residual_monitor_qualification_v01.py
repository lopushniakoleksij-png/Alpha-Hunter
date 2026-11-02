"""Research-only P2 proof: quote identity, 35m continuity, and quarantines."""
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def load(path,key):
    s=spec_from_file_location(key,ROOT/path)
    m=module_from_spec(s);s.loader.exec_module(m);return m
mod=load("ops/reviews/successor_all_residual_monitor_qualification_v01.py","p2monitor")
prev=load("tests/test_successor_forward_asof_inventory_v01.py","p2sourcefixtures")
RUN="synthetic-p2-qual"
SOURCE="BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE"

def fixture():
    inv=prev.build()
    scan={"run_id":RUN,"collected_at_utc":"2026-10-12T12:00:00Z",
     "validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
       "scientific_fingerprint_sha256":"a"*64}}
    states=[{"entry_order_id":o,"state":"MANAGED_PROTECTED","protection_count":2}
            for o in ("nmr-old-partial","q-new")]
    attempts=[{"entry_order_id":oid,"source_run_id":RUN,"symbol":symbol,
      "direction":"LONG","attempt_id":"attempt-"+oid,"outcome":"NO_TRIGGER",
      "observed_at_utc":"2026-10-12T12:00:04Z","best_bid":"1",
      "best_ask":"1.01","best_bid_size":"10","best_ask_size":"8",
      "blockers":[],"evidence":{"quote_source":SOURCE}}
      for oid,symbol in (("nmr-old-partial","NMRUSDT"),("q-new","QUSDT"))]
    prior=[{"entry_order_id":"nmr-old-partial","symbol":"NMRUSDT",
      "direction":"LONG","observed_at_utc":"2026-10-12T11:45:00Z",
      "previous_sealed_run_id":"synthetic-previous-run","seal_verified":True}]
    return [inv,scan,states,attempts,prior]

def score(data):
    return mod.score_monitoring_coverage(*data,
      approved_quote_sources=frozenset({SOURCE}),quote_window_seconds=30)

def blockers(result):
    return {b for p in result["positions"] for b in p["blockers"]}

def test_full_supplied_proof_remains_research_only():
    a=score(fixture())
    assert a["managed_locally_qualified"]==2
    assert not a["scientific_pass_permitted"] and not a["exchange_authority"]
    assert not a["independently_authenticated_source"]

def test_missing_old_residual_attempt_refused():
    a=fixture();a[3]=a[3][1:]
    result=score(a)
    assert result["expected_residuals"]==2
    assert "POSITION_MONITOR_ATTEMPT_COUNT_NOT_ONE" in blockers(result)

def test_source_label_missing_or_quote_too_late_refused():
    a=fixture();a[3][0]["evidence"]={}
    assert "QUOTE_SOURCE_UNLABELED" in blockers(score(a))
    a=fixture();a[3][0]["observed_at_utc"]="2026-10-12T12:00:40Z"
    assert "QUOTE_OUTSIDE_POLICY_WINDOW" in blockers(score(a))

def test_frozen_35min_exact_boundary_and_violation():
    a=fixture();a[4][0]["observed_at_utc"]="2026-10-12T11:25:04Z"
    assert score(a)["managed_locally_qualified"]==2
    a[4][0]["observed_at_utc"]="2026-10-12T11:25:03Z"
    assert "FROZEN_35M_POSITION_CONTINUITY_BREACH" in blockers(score(a))

def test_historic_fill_without_prior_observation_cannot_substitute():
    a=fixture();a[4]=[]
    assert "FROZEN_35M_POSITION_CONTINUITY_BREACH" in blockers(score(a))

def test_quarantined_and_unprotected_residuals_block_scientific_claim():
    a=fixture();a[2][0]={"entry_order_id":"nmr-old-partial","state":"UNPROTECTED_INCIDENT"}
    r=score(a)
    assert "UNPROTECTED_FILLED_RESIDUAL_INCIDENT" in blockers(r)
    assert r["quarantined_or_unprotected"]==1
    a=fixture();a[2][0]={"entry_order_id":"nmr-old-partial",
        "state":"QUARANTINED_UNVERIFIED","quarantine_case_id":"synthetic-case"}
    assert "QUARANTINED_RESIDUAL_UNMONITORED" in blockers(score(a))

def test_duplicate_attempt_or_missing_disposition_cannot_pass():
    a=fixture();a[3].append(dict(a[3][0]))
    assert "POSITION_MONITOR_ATTEMPT_COUNT_NOT_ONE" in blockers(score(a))
    a=fixture();a[2]=a[2][:1]
    assert "RESIDUAL_DISPOSITION_COVERAGE_MISMATCH" in score(a)["run_blockers"]

def test_fabricated_source_completeness_not_accepted_as_real_proof():
    a=fixture();a[0]["status"]="SOURCE_EVIDENCE_UNKNOWN_OR_INVALID"
    assert score(a)["status"]=="SOURCE_INCOMPLETE"


def test_tampered_source_residual_manifest_refused_even_when_attempts_match():
    a=fixture()
    a[0]["positions"][0]["residual_qty"]="999"
    result=score(a)
    assert result["status"]=="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    assert "SOURCE_RESIDUAL_MANIFEST_DIGEST_MISMATCH" in result["run_blockers"]

def test_empty_supplied_inventory_cannot_claim_absence_of_live_positions():
    a=fixture()
    a[0]["positions"]=[]
    a[0]["manifest_sha256"]=mod.sha256(
      mod.dumps([],sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()
    a[2]=[]
    a[3]=[]
    a[4]=[]
    result=score(a)
    assert result["status"]=="EMPTY_SOURCE_INVENTORY_UNAUTHENTICATED_NO_LIVE_POSITION_CLAIM"
    assert not result["independently_authenticated_source"]
    assert not result["scientific_pass_permitted"]


def test_missing_or_self_referential_prior_seal_fails_closed():
    data = fixture()
    data[4][0].pop("observed_at_utc")
    result = score(data)
    assert "PRIOR_SEALED_POSITION_TIME_MISSING" in blockers(result)
    assert result["status"] == "FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    assert result["scientific_pass_permitted"] is False

    data = fixture()
    data[4][0]["observed_at_utc"] = "invalid-clock"
    assert "PRIOR_SEALED_POSITION_TIME_MISSING" in blockers(score(data))

    data = fixture()
    data[4][0]["previous_sealed_run_id"] = RUN
    result = score(data)
    assert "PRIOR_SEALED_POSITION_SELF_REFERENCE" in blockers(result)
    assert not result["independently_authenticated_source"]


def test_oct23_all_cohort_25_residual_rehearsal_never_promotes_science():
    """Synthetic shape mirrors the independent 25/3/21/1 live ledger census.

    No live rows, credentials, position IDs, or production writes are used.
    The 3 managed positions have locally consistent *supplied* observations,
    but the 21 quarantines and 1 unprotected residual remain fail-visible.
    """
    from copy import deepcopy

    case=fixture()
    base=deepcopy(case[0]["positions"][1])
    third=deepcopy(base)
    third["entry_order_id"]="synthetic-managed-third"
    third["symbol"]="SYNTH03USDT"
    case[0]["positions"].append(third)
    case[2].append({"entry_order_id":third["entry_order_id"],
                    "state":"MANAGED_PROTECTED","protection_count":2})
    attempt=deepcopy(case[3][1])
    attempt["entry_order_id"]=third["entry_order_id"]
    attempt["symbol"]=third["symbol"]
    attempt["attempt_id"]="synthetic-managed-third-attempt"
    case[3].append(attempt)

    for k in range(21):
        row=deepcopy(base)
        row["entry_order_id"]=f"synthetic-quarantined-{k:02d}"
        row["symbol"]=f"SYNTHQ{k:02d}USDT"
        case[0]["positions"].append(row)
        case[2].append({"entry_order_id":row["entry_order_id"],
                        "state":"QUARANTINED_UNVERIFIED",
                        "quarantine_case_id":f"synthetic-case-{k:02d}"})

    incident=deepcopy(case[0]["positions"][0])
    incident["entry_order_id"]="synthetic-unprotected-partial"
    case[0]["positions"].append(incident)
    case[2].append({"entry_order_id":incident["entry_order_id"],
                    "state":"UNPROTECTED_INCIDENT"})

    case[0]["manifest_sha256"]=mod.sha256(
        mod.dumps(case[0]["positions"],sort_keys=True,
                  separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()

    result=score(case)
    assert result["expected_residuals"]==25
    assert result["managed_locally_qualified"]==3
    assert result["quarantined_or_unprotected"]==22
    assert result["status"]=="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    assert "QUARANTINED_RESIDUAL_UNMONITORED" in blockers(result)
    assert "UNPROTECTED_FILLED_RESIDUAL_INCIDENT" in blockers(result)
    assert not result["scientific_pass_permitted"]
    assert not result["production_promotion_permitted"]
    assert not result["independently_authenticated_source"]
    assert result["order_path"]=="NONE"
    assert result["exchange_authority"] is False

    # A missing case/disposition must fail closed even if remaining attempts
    # and their self-labeled quotes look internally consistent.
    case[2].pop()
    result=score(case)
    assert "RESIDUAL_DISPOSITION_COVERAGE_MISMATCH" in result["run_blockers"]
    assert result["scientific_pass_permitted"] is False


def test_oct23_live_sql_is_select_only_and_denies_independent_source_claim():
    """Static safety invariant for the reviewed read-only source diagnostic."""
    import re
    sql=(ROOT/"ops/reviews/successor_p0_live_residual_quote_coverage_20261023.sql").read_text()
    active="\n".join(
        line for line in sql.splitlines()
        if not line.lstrip().startswith("--")
    )
    assert re.match(r"\s*WITH\s+latest\s+AS\s*\(",active,re.I)
    assert active.count(";")==1
    forbidden=r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|TRUNCATE|CREATE|GRANT|REVOKE|CALL|COPY|EXECUTE)\b"
    assert not re.search(forbidden,active,re.I)
    for contract in (
        "alpha_hunter_paper_fills_v02",
        "alpha_hunter_paper_exit_fills_v04",
        "alpha_hunter_paper_protection_horizon_open_v09",
        "alpha_hunter_paper_exit_attempts_v04",
        "raw_response_sha256",
        "quote_receipt_digest",
        "request_id",
        "gap_seconds>2100",
        "independent_quote_bytes_authenticated",
        "immutable_asof_position_inventory_proven",
        "scientific_profitability_or_admission_authorized",
        "FAIL_CLOSED_UNVERIFIED_LEDGER_OR_MONITORING",
    ):
        assert contract in sql,contract
    assert "2100 AS frozen_max_monitoring_gap_seconds" in active
    assert "false AS scientific_profitability_or_admission_authorized" in active
