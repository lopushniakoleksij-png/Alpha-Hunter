"""P3 four historical candidates are a *forensic* audit only, not fill bindings.

No network, Bitget API, Supabase session, side effects or human-claim imputation.
"""
from pathlib import Path

from pglast import parse_sql
from pglast.ast import SelectStmt

ROOT=Path(__file__).resolve().parents[1]
SQL=(ROOT/"ops/reviews/p3_four_manual_order_provenance_readonly_20261015.sql").read_text()


def test_four_candidate_provenance_is_one_read_only_select():
    statements=parse_sql(SQL)
    assert len(statements)==1
    assert isinstance(statements[0].stmt,SelectStmt)
    body="\n".join(line for line in SQL.splitlines()
                   if not line.lstrip().startswith("--")).lower()
    for statement in ("insert into","update public.","delete from","create table",
                      "alter table","drop table","grant ","revoke ","execute ",
                      "copy ","call ","pg_sleep("):
        assert statement not in body


def test_all_four_frozen_identities_pinned_not_fuzzy_dynamic_historical_join():
    assert SQL.count("'UNIQUE_EVIDENCE_COMPLETE_MATCH'")==1
    for symbol,action in (
        ("ALGOUSDT","EXECUTE_NOW"),("MYXUSDT","PLACE_LIMIT"),
        ("SAFEUSDT","EXECUTE_NOW"),("WLDUSDT","PLACE_LIMIT")
    ):
        assert f"'{symbol}'" in SQL
        assert f"'{action}'" in SQL
    for timestamp in (
        "2026-10-08T09:43:27.104652+00",
        "2026-10-10T06:23:30.108448+00",
        "2026-10-12T09:43:36.071720+00",
        "2026-10-12T11:43:33.982301+00"
    ):
        assert timestamp in SQL
    assert "AND c.frozen_at_utc=r.frozen_at_utc" in SQL


def test_never_promotes_heuristic_match_to_execution_attribution():
    for pattern in (
        "this_exact_pair_explicitly_confirmed",
        "this_exact_pair_verified_execution",
        "o.fill_origin_class",
        "o.order_enter_point_source",
        "o.order_source",
        "o.client_oid_present",
        "o.raw_client_oid_persisted_here",
        "c.explicit_user_confirmation_required",
        "c.automatic_binding_permitted",
        "c.attribution_claim_permitted",
        "d.shadow_only",
        "f.evidence->>'order_write_path_present'",
        "false AS authorization_to_bind_or_restate_scientific_outcome",
        "LIMIT_INTENT_MARKET_EXECUTION_CONFLICT_NOT_VERIFIED",
        "EXECUTE_NOW_AND_MARKET_COMPATIBLE_CAUSALITY_NOT_VERIFIED"
    ):
        assert pattern in SQL


def test_review_does_not_print_exchange_ids_or_personal_authentication():
    # Exact venue IDs are used only internally as join keys by evidence views;
    # the rendered audit report deliberately omits their raw values.
    assert "c.order_id," not in SQL
    assert "f.trade_id," not in SQL
    assert "o.client_oid_sha256," not in SQL
    assert "raw_client_oid_persisted_here" in SQL
    assert "trade_permission FROM" not in SQL
