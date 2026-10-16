"""P3 research-only offline cost input red-team; no actual trades or network."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "p3_cost_contract",
    ROOT/"ops/reviews/p3_offline_execution_cost_completeness_v01.py",
)
p3=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p3)

NOW="2026-10-15T17:00:00Z"


def one(i=0,*,role="TAKER",side="LONG"):
    ident=f"synthetic-{i}"
    def component(key):
        return {
            "amount":"-0.02" if key in p3.SIGNED_COMPONENTS else "0.00",
            "receipt_id":f"synthetic-receipt-{i}-{key}",
            "evidence_class":"SYNTHETIC_TEST_ONLY",
            "currency":"USDT",
        }
    return {
        "decision":{
            "decision_id":f"synthetic-decision-{ident}",
            "source_run_id":f"synthetic-run-{ident}",
            "spec_id":p3.FROZEN_SCIENTIFIC_SPEC,
            "symbol":"QUSDT", "direction":side,
            "frozen_at_utc":"2026-10-15T12:00:00Z",
            "intended_order_id":f"synthetic-order-{ident}",
            "arrival_quote_id":f"synthetic-arrival-{ident}",
            "entry_price":"1", "stop_price":("0.90" if side=="LONG" else "1.10"),
        },
        "entry_fill":{
            "decision_id":f"synthetic-decision-{ident}",
            "intended_order_id":f"synthetic-order-{ident}",
            "exchange_order_id":f"synthetic-exchange-{ident}",
            "venue_trade_id":f"synthetic-entry-trade-{ident}",
            "filled_at_utc":"2026-10-15T12:01:00Z",
            "symbol":"QUSDT", "direction":side, "liquidity_role":role,
            "filled_quantity":"1.5", "fill_price":"1.002",
        },
        "exit_fill":{
            "entry_venue_trade_id":f"synthetic-entry-trade-{ident}",
            "exit_venue_trade_id":f"synthetic-exit-trade-{ident}",
            "exit_at_utc":"2026-10-15T13:00:00Z",
            "exited_quantity":"1.5", "exit_price":"1.02",
            "exit_quote_id":f"synthetic-exit-quote-{ident}",
        },
        "components":{key:component(key) for key in p3.COMPONENTS},
    }


def check(rows, benchmarks=247):
    return p3.review_fixture(rows, now_utc=NOW, descriptive_benchmark_count=benchmarks)


def test_current_readiness_zero_exact_fills_not_rescued_by_247_benchmarks():
    o=check([])
    assert o["status"]=="OFFLINE_DATA_INSUFFICIENT_OR_INVALID"
    assert o["verified_real_execution_rows"]==0
    assert o["descriptive_benchmark_count_separate_not_verified_executions"]==247
    assert o["synthetic_segment_counts"]["total"]==0
    assert o["realistic_net_r"] is None


def test_30_perfect_synthetic_rows_never_grant_real_cost_model_or_permission():
    rows=[one(i,role=("TAKER" if i<20 else "MAKER"),
              side=("SHORT" if i<5 else "LONG")) for i in range(30)]
    result=check(rows)
    assert result["status"]=="OFFLINE_SYNTHETIC_STRUCTURAL_CANDIDATE_NOT_REAL_VALIDATION",result
    assert result["synthetic_segment_floors_met"] is True
    assert result["synthetic_segment_counts"]=={
        "total":30,"TAKER":20,"MAKER":10,"LONG":25,"SHORT":5
    }
    for key in ("validated_model","live_cost_validation_proven",
                "p2_live_receipt_custody_proven","scientific_pass_permitted",
                "trade_permission","exchange_authority","production_promotion_permitted"):
        assert result[key] is False
    assert result["realistic_net_r"] is None
    assert result["realistic_net_pnl"] is None
    assert result["verified_real_execution_rows"]==0


def test_missing_funding_receipt_is_not_treated_as_zero_cost():
    row=one()
    row["components"].pop("realized_funding_usdt")
    o=check([row])
    assert "REALISTIC_COST_COMPONENT_SET_INCOMPLETE" in o["blockers"]
    assert o["synthetic_structurally_complete_rows"]==0


def test_observed_zero_cost_requires_explicit_receipt_identity():
    row=one()
    row["components"]["realized_funding_usdt"]["receipt_id"]=""
    o=check([row])
    assert any("COMPONENT_SOURCE_OR_CURRENCY_UNVERIFIED" in x for x in o["blockers"])


def test_partial_fill_exit_cannot_masquerade_as_full_position_close():
    row=one()
    row["exit_fill"]["exited_quantity"]="0.7"
    assert "PARTIAL_OR_UNVERIFIED_FULL_EXIT_QUANTITY" in check([row])["blockers"]


def test_unlinked_exchange_fill_and_duplicate_decision_fail_closed():
    row=one()
    row["entry_fill"]["decision_id"]="synthetic-other"
    assert "DECISION_FILL_EXIT_IDENTITY_MISMATCH" in check([row])["blockers"]
    twice=[one(),one()]
    assert "DUPLICATE_DECISION_OR_FILL" in check(twice)["blockers"]


def test_venue_fill_prior_to_freeze_or_exit_before_entry_is_rejected():
    row=one()
    row["entry_fill"]["filled_at_utc"]="2026-10-15T11:59:59Z"
    assert "FROZEN_DECISION_FILL_EXIT_CLOCK_INVALID" in check([row])["blockers"]
    row=one()
    row["exit_fill"]["exit_at_utc"]="2026-10-15T12:00:01Z"
    assert "FROZEN_DECISION_FILL_EXIT_CLOCK_INVALID" in check([row])["blockers"]


def test_wrong_contract_side_and_invalid_stop_geometry_fail_closed():
    row=one(side="SHORT")
    row["entry_fill"]["direction"]="LONG"
    assert "DECISION_FILL_EXIT_IDENTITY_MISMATCH" in check([row])["blockers"]
    row=one(side="LONG")
    row["decision"]["stop_price"]="1.1"
    assert "UNVALIDATED_STRUCTURAL_RISK_GEOMETRY" in check([row])["blockers"]


def test_unobserved_quote_and_missing_exit_slippage_block():
    row=one()
    row["decision"]["arrival_quote_id"]=None
    assert "ARRIVAL_QUOTE_SOURCE_UNVERIFIED" in check([row])["blockers"]
    row=one()
    row["components"]["signed_exit_slippage_usdt"]["amount"]=None
    assert any("COMPONENT_NUMERIC_INVALID_OR_MISSING" in x for x in check([row])["blockers"])


def test_funding_and_markout_are_distinct_not_interchangeable():
    row=one()
    row["components"]["realized_funding_usdt"] = deepcopy(
        row["components"]["signed_post_fill_markout_usdt"]
    )
    assert any("COMPONENT_SOURCE_OR_CURRENCY_UNVERIFIED" in x for x in check([row])["blockers"])


def test_real_live_id_cannot_be_represented_as_synthetic_verified_sample():
    row=one()
    row["entry_fill"]["venue_trade_id"]="real-venue-id"
    row["exit_fill"]["entry_venue_trade_id"]="real-venue-id"
    assert "NON_SYNTHETIC_SOURCE_NOT_AUTHORIZED_FOR_OFFLINE_FIXTURE" in check([row])["blockers"]


def test_offline_review_has_no_service_side_effects():
    text=(ROOT/"ops/reviews/p3_offline_execution_cost_completeness_v01.py").read_text()
    assert "def review_fixture(" in text
    assert "requests." not in text and "psycopg." not in text
    assert "place_order(" not in text and "cancel_order(" not in text
    assert "realistic_net_r" in text and "FROZEN_SCIENTIFIC_SPEC" in text


def test_exit_venue_trade_id_cannot_be_reused_across_distinct_decisions():
    rows=[one(0),one(1)]
    rows[1]["exit_fill"]["exit_venue_trade_id"]=rows[0]["exit_fill"]["exit_venue_trade_id"]
    out=check(rows)
    assert "DUPLICATE_ENTRY_OR_EXIT_VENUE_TRADE_ACROSS_ROWS" in out["blockers"]
    assert out["synthetic_structurally_complete_rows"]==1
    assert out["production_promotion_permitted"] is False


def test_cross_sample_entry_and_exit_trade_identity_cannot_collide():
    rows=[one(0),one(1)]
    old=rows[0]["entry_fill"]["venue_trade_id"]
    rows[1]["exit_fill"]["exit_venue_trade_id"]=old
    out=check(rows)
    assert "DUPLICATE_ENTRY_OR_EXIT_VENUE_TRADE_ACROSS_ROWS" in out["blockers"]


def test_cross_sample_component_receipt_reuse_cannot_inflate_calibration_counts():
    rows=[one(i,role=("TAKER" if i<20 else "MAKER"),
              side=("SHORT" if i<5 else "LONG")) for i in range(30)]
    shared=rows[0]["components"]["realized_entry_fee_usdt"]["receipt_id"]
    rows[1]["components"]["realized_entry_fee_usdt"]["receipt_id"]=shared
    out=check(rows)
    assert "DUPLICATE_COMPONENT_RECEIPT_ACROSS_ROWS" in out["blockers"]
    assert out["synthetic_structurally_complete_rows"]==29
    assert out["synthetic_segment_floors_met"] is False
    assert out["validated_model"] is False
    assert out["realistic_net_r"] is None


def test_different_cost_components_across_rows_cannot_reuse_same_receipt():
    rows=[one(0),one(1)]
    rows[1]["components"]["realized_funding_usdt"]["receipt_id"]=(
        rows[0]["components"]["signed_exit_slippage_usdt"]["receipt_id"])
    out=check(rows)
    assert "DUPLICATE_COMPONENT_RECEIPT_ACROSS_ROWS" in out["blockers"]
