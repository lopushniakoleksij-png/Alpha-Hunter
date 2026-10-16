"""Research-only successor partial exit and residual-OCO lifecycle regressions.

All fills and acknowledgements are synthetic, never Bitget or sealed R9 fills.
"""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import pytest

from alpha_hunter.successor_residual_exit_contract import (
    Fill,Guard,Position,RejectedTransition,apply_synthetic_exit,
    initial_position,
)

D=Decimal


def guard(q="362", revision=0, when="2026-10-02T16:07:20Z", status="ARMED",
          sid=None,tid=None,stop_ack=None,target_ack=None,oco="ev-test"):
    return Guard(
        quantity=D(q),stop_price=D("0.6923"),target_price=D("0.7867"),
        stop_id=sid or f"stop-{revision}",
        target_id=tid or f"target-{revision}",
        oco_group=oco,stop_ack=stop_ack or f"stop-ack-{revision}",
        target_ack=target_ack or f"target-ack-{revision}",
        revision=revision,observed_at_utc=when,status=status,
    )


def position():
    return initial_position(
        position_id="fixture-EVAA-legacy-shape-NOT-A-TRADE",
        symbol="EVAAUSDT",direction="LONG",quantity="362",
        entry_price="0.6992",stop="0.6923",target="0.7867",
        entry_fee="0.25",initial_guard=guard(),
        opened_at_utc="2026-10-02T16:07:20Z",
    )


def fill(n=1,q="100",bid="0.8053",ask="0.8078",
         price="0.805",size="100",when=None,quote_id=None,fee="6"):
    if when is None:
        when=["2026-10-02T23:03:32Z","2026-10-02T23:23:04Z",
              "2026-10-02T23:42:58Z"][n-1]
    return Fill(
        event_id=f"synthetic-receipt-{n}",
        receipt_sha256=("%064x"%n),
        quote_id=quote_id or f"synthetic-quote-{n}",
        time_utc=when,quantity=D(q),exit_price=D(price),
        best_bid=D(bid),best_ask=D(ask),visible_exit_size=D(size),
        fee_bps=D(fee),trigger_type="TAKE_PROFIT",
        trigger_guard_id=f"target-{n-1}",
    )


def assert_no_authority(result):
    assert result.execution_price_verified is False
    assert result.source_authentication=="ISOLATED_SYNTHETIC_ONLY"
    assert result.counterfactual_only is True
    assert result.trade_permission is False
    assert result.production_promotion_permitted is False
    assert result.profitability_claim_permitted is False
    p=result.position
    assert p.paper_only is True
    assert p.trade_permission is False
    assert p.exchange_authority is False
    assert p.production_promotion_permitted is False
    assert p.profitability_claim_permitted is False


def test_three_atomic_synthetic_partial_exits_reprotect_then_close():
    origin=position()
    first=fill()
    r1=apply_synthetic_exit(origin,first,next_guard=guard("262",1,
         "2026-10-02T23:03:33Z"),expected_revision=0)
    assert r1.status=="SIMULATED_PARTIAL_PROTECTED"
    assert r1.position.remaining==D(262)
    assert r1.position.guard.quantity==r1.position.remaining
    assert r1.position.guard.status=="ARMED"
    assert origin.remaining==D(362) and not origin.fills
    assert_no_authority(r1)

    second=fill(2,q="200",bid="0.8327",ask="0.8353",
                price="0.832",size="276")
    r2=apply_synthetic_exit(r1.position,second,next_guard=guard("62",2,
         "2026-10-02T23:23:05Z"),expected_revision=1)
    assert r2.status=="SIMULATED_PARTIAL_PROTECTED"
    assert r2.position.remaining==D(62)
    assert r2.position.guard.quantity==D(62)
    assert_no_authority(r2)

    third=fill(3,q="62",bid="0.824",ask="0.8268",price="0.8234",size="62")
    r3=apply_synthetic_exit(r2.position,third,next_guard=guard("0",3,
         "2026-10-02T23:42:59Z",status="CANCELLED"),expected_revision=2)
    assert r3.status=="SIMULATED_CLOSED"
    assert r3.position.remaining==0
    assert r3.position.integrity_state=="CLOSED"
    assert r3.position.guard.status=="CANCELLED"
    assert r3.position.allocated_entry_fee==D(".25")
    assert len(r3.position.fills)==3
    assert r3.position.entry_quantity==sum(x.quantity for x in r3.position.fills)
    assert r3.gross_realized==sum((f.exit_price-D(".6992"))*f.quantity
                                   for f in (first,second,third))
    expected_exit_fee=sum(f.exit_price*f.quantity*D("6")/D("10000")
                          for f in (first,second,third))
    assert r3.position.realized_exit_fee==expected_exit_fee
    assert r3.net_realized_ex_funding==r3.gross_realized-D(".25")-expected_exit_fee
    assert r3.fees_deducted==D(".25")+expected_exit_fee
    assert r3.position.diagnostic_spread>0 and r3.position.diagnostic_slippage>0
    assert r3.net_realized_ex_funding!=(
        r3.gross_realized-D(".25")-expected_exit_fee-
        r3.position.diagnostic_spread-r3.position.diagnostic_slippage
    )  # No double-counting costs already embedded in the fill price
    assert_no_authority(r3)


def test_362_position_with_bid_size_100_cannot_falsely_close_362():
    p=position()
    with pytest.raises(RejectedTransition,match="FILL_EXCEEDS_SINGLE_OBSERVED_LEVEL"):
        apply_synthetic_exit(p,replace(fill(),quantity=D("362")),
            next_guard=guard("0",1,"2026-10-02T23:03:33Z",status="CANCELLED"),
            expected_revision=0)
    assert p.remaining==D(362)


def test_missing_residual_stop_or_target_ack_halts_instead_of_claiming_safe_position():
    p=position()
    r=apply_synthetic_exit(p,fill(),next_guard=None,expected_revision=0)
    assert r.status=="HALTED_UNRESOLVED"
    assert r.position.integrity_state=="HALTED_UNRESOLVED"
    assert r.position.incident=="RESIDUAL_GUARD_ACK_MISSING"
    assert r.position.remaining==D(362) and len(r.position.fills)==0
    assert_no_authority(r)
    with pytest.raises(RejectedTransition,match="INTEGRITY_HALT_STAYS_HALTED"):
        apply_synthetic_exit(r.position,fill(2,q="30"),next_guard=guard("332",1,
             "2026-10-02T23:23:05Z"),expected_revision=0)


@pytest.mark.parametrize("bad_guard",[
    guard("263",1,"2026-10-02T23:03:33Z"),  # residual under/overprotected
    guard("261",1,"2026-10-02T23:03:33Z"),
    guard("262",1,"2026-10-02T23:03:33Z",stop_ack="same",target_ack="same"),
    guard("262",1,"2026-10-02T23:03:31Z"),  # before synthetic fill
    guard("262",1,"2026-10-02T23:03:33Z",oco="new-oco"),
    guard("262",1,"2026-10-02T23:03:33Z",status="CANCELLED"),
    guard("262",2,"2026-10-02T23:03:33Z"),
])
def test_fails_closed_on_insufficient_residual_protection(bad_guard):
    p=position()
    r=apply_synthetic_exit(p,fill(),next_guard=bad_guard,expected_revision=0)
    assert r.status=="HALTED_UNRESOLVED"
    assert r.position.integrity_state=="HALTED_UNRESOLVED"
    assert len(r.position.fills)==0
    assert_no_authority(r)


def test_deduplicated_event_is_noop_even_with_old_expected_revision():
    r=apply_synthetic_exit(position(),fill(),next_guard=guard("262",1,
           "2026-10-02T23:03:33Z"),expected_revision=0)
    again=apply_synthetic_exit(r.position,fill(),next_guard=None,expected_revision=0)
    assert again.status=="DUPLICATE_NOOP"
    assert again.position==r.position and again.position.revision==1
    assert_no_authority(again)



def test_terminal_closed_position_replays_last_fill_idempotently():
    p=position()
    f=fill(q="362",size="362")
    final=apply_synthetic_exit(p,f,next_guard=guard("0",1,
        "2026-10-02T23:03:33Z",status="CANCELLED"),expected_revision=0)
    assert final.status=="SIMULATED_CLOSED"
    duplicate=apply_synthetic_exit(final.position,f,next_guard=None,expected_revision=0)
    assert duplicate.status=="DUPLICATE_NOOP"
    assert duplicate.position==final.position
    assert duplicate.position.integrity_state=="CLOSED"
    assert duplicate.net_realized_ex_funding==final.net_realized_ex_funding
    assert_no_authority(duplicate)
    with pytest.raises(RejectedTransition,match="INTEGRITY_HALT_STAYS_HALTED"):
        apply_synthetic_exit(final.position,fill(2,q="1"),
            next_guard=None,expected_revision=1)



def test_same_event_id_with_new_content_halts_custody():
    r=apply_synthetic_exit(position(),fill(),next_guard=guard("262",1,
           "2026-10-02T23:03:33Z"),expected_revision=0)
    conflicting=apply_synthetic_exit(r.position,replace(fill(),exit_price=D(".8049")),
        next_guard=None,expected_revision=0)
    assert conflicting.status=="HALTED_UNRESOLVED"
    assert conflicting.position.incident=="CONFLICTING_EVENT_ID"
    assert conflicting.position.remaining==D(262)
    assert_no_authority(conflicting)


def test_overfill_stale_revision_and_duplicated_quote_ids_rejected():
    r=apply_synthetic_exit(position(),fill(),next_guard=guard("262",1,
           "2026-10-02T23:03:33Z"),expected_revision=0)
    p=r.position
    with pytest.raises(RejectedTransition,match="STALE_EXPECTED_REVISION"):
        apply_synthetic_exit(p,fill(2),next_guard=None,expected_revision=0)
    with pytest.raises(RejectedTransition,match="OVERFILL"):
        apply_synthetic_exit(p,fill(2,q="263",bid="0.8327",ask="0.8353",
             price="0.832",size="300"),next_guard=None,expected_revision=1)
    with pytest.raises(RejectedTransition,match="REUSED_MARKET_OBSERVATION"):
        apply_synthetic_exit(p,fill(2,q="10",bid="0.8327",ask="0.8353",
             price="0.832",size="300",quote_id="synthetic-quote-1"),
             next_guard=None,expected_revision=1)
    assert p.remaining==D(262) and p.revision==1


@pytest.mark.parametrize("change,reason",[
    (dict(exit_price=D(".79")),"UNAPPROVED_SLIPPAGE"),
    (dict(exit_price=D(".81")),"UNAPPROVED_SLIPPAGE"),
    (dict(fee_bps=D("25")),"UNAPPROVED_FEE"),
    (dict(fee_bps=D("-1")),"UNAPPROVED_FEE"),
    (dict(quantity=D("0")),"OVERFILL"),
    (dict(quantity=D("-1")),"OVERFILL"),
    (dict(evidence_kind="QUOTE_ONLY"),"PROVIDER_FILL_EVIDENCE"),
    (dict(receipt_status="UNKNOWN"),"PROVIDER_FILL_EVIDENCE"),
    (dict(receipt_sha256="UNVERIFIED"),"SYNTHETIC_RECEIPT_IDENTITY"),
    (dict(visible_exit_size=D("99")),"FILL_EXCEEDS_SINGLE"),
    (dict(best_ask=D(".70")),"INVALID_QUOTE"),
])
def test_bad_costs_market_size_and_claimed_receipts_rejected(change,reason):
    with pytest.raises(RejectedTransition,match=reason):
        apply_synthetic_exit(position(),replace(fill(),**change),
             next_guard=None,expected_revision=0)


def test_terminal_fill_requires_acknowledged_cancel_of_both_protections():
    p=position()
    f=fill(q="100",size="100")
    r=apply_synthetic_exit(p,f,next_guard=guard("262",1,
           "2026-10-02T23:03:33Z"),expected_revision=0)
    f2=fill(2,q="262",bid="0.8327",ask="0.8353",
         price=".832",size="276")
    wrong=guard("0",2,"2026-10-02T23:23:05Z",status="ARMED")
    halt=apply_synthetic_exit(r.position,f2,next_guard=wrong,expected_revision=1)
    assert halt.status=="HALTED_UNRESOLVED"
    assert halt.position.integrity_state=="HALTED_UNRESOLVED"
    assert halt.position.remaining==D("262")
    assert_no_authority(halt)


def test_short_side_prices_buy_at_ask_and_profit_formula():
    q=D("20")
    g=Guard(q,D("1.1"),D(".8"),"s0","t0","oco","sa0","ta0",0,
            "2026-10-02T01:00:00Z")
    p=initial_position(position_id="short-fixture",symbol="TESTUSDT",
        direction="SHORT",quantity=q,entry_price="1",stop="1.1",
        target=".8",entry_fee=".02",initial_guard=g,
        opened_at_utc="2026-10-02T01:00:00Z")
    f=Fill("f1","a"*64,"q1","2026-10-02T01:01:00Z",q,
           D(".7995"),D(".798"),D(".799"),D("30"),D("6"),
           "TAKE_PROFIT","t0")
    end=Guard(D(0),D("1.1"),D(".8"),"s1","t1","oco",
             "sa1","ta1",1,"2026-10-02T01:01:01Z","CANCELLED")
    out=apply_synthetic_exit(p,f,next_guard=end,expected_revision=0)
    assert out.status=="SIMULATED_CLOSED"
    assert out.gross_realized==(D("1")-D(".7995"))*q
    assert out.net_realized_ex_funding==out.gross_realized-D(".02")-D(".7995")*q*D(6)/D(10000)
    assert_no_authority(out)



def test_reused_synthetic_receipt_digest_under_new_event_id_halts():
    r=apply_synthetic_exit(position(),fill(),next_guard=guard("262",1,
        "2026-10-02T23:03:33Z"),expected_revision=0)
    second=fill(2,q="30",bid="0.8327",ask="0.8353",price=".832",
                size="300")
    duplicated=replace(second,receipt_sha256=fill().receipt_sha256)
    halted=apply_synthetic_exit(r.position,duplicated,next_guard=None,
                                expected_revision=1)
    assert halted.status=="HALTED_UNRESOLVED"
    assert halted.position.incident=="REUSED_FILL_RECEIPT_DIGEST"
    assert halted.position.remaining==D(262)
    assert halted.position.integrity_state=="HALTED_UNRESOLVED"
    assert_no_authority(halted)


@pytest.mark.parametrize("old_ack",["stop","target"])
def test_each_residual_oco_leg_requires_fresh_acknowledgement(old_ack):
    original=position()
    g=guard("262",1,"2026-10-02T23:03:33Z",
            stop_ack="stop-ack-0" if old_ack=="stop" else "stop-ack-1",
            target_ack="target-ack-0" if old_ack=="target" else "target-ack-1")
    failed=apply_synthetic_exit(original,fill(),next_guard=g,expected_revision=0)
    assert failed.status=="HALTED_UNRESOLVED"
    assert failed.position.incident=="BOTH_PROTECTIVE_LEGS_NOT_REACKNOWLEDGED"
    assert failed.position.remaining==D(362)
    assert_no_authority(failed)


def test_terminal_cancellation_ack_must_be_new_for_each_oco_leg():
    original=position()
    stopped=guard("0",1,"2026-10-02T23:03:33Z",status="CANCELLED",
                  target_ack="target-ack-0")
    f=fill(q="362",size="362")
    halted=apply_synthetic_exit(original,f,next_guard=stopped,expected_revision=0)
    assert halted.status=="HALTED_UNRESOLVED"
    assert halted.position.incident=="BOTH_PROTECTIVE_LEGS_NOT_REACKNOWLEDGED"
    assert_no_authority(halted)



def test_trigger_must_be_linked_to_current_active_protection():
    with pytest.raises(RejectedTransition,match="TRIGGER_NOT_LINKED"):
        apply_synthetic_exit(position(),
          replace(fill(),trigger_guard_id="target-archived"),
          next_guard=None,expected_revision=0)


def test_take_profit_cannot_fill_before_exit_side_quote_reaches_target():
    p=position()
    with pytest.raises(RejectedTransition,match="PROTECTIVE_TRIGGER_NOT_OBSERVED"):
        apply_synthetic_exit(p,fill(bid=".780",ask=".782",
                                   price=".7797",size="100"),
                             next_guard=None,expected_revision=0)
    assert p.remaining==D(362)


def test_stop_cannot_derive_from_target_price_quote():
    p=position()
    with pytest.raises(RejectedTransition,match="PROTECTIVE_TRIGGER_NOT_OBSERVED"):
        apply_synthetic_exit(p,replace(fill(),trigger_type="STOP_LOSS",
                                trigger_guard_id="stop-0"),
            next_guard=None,expected_revision=0)


def test_trigger_type_must_be_current_known_protective_leg():
    with pytest.raises(RejectedTransition,match="PROTECTIVE_TRIGGER_TYPE_NOT_SUPPORTED"):
        apply_synthetic_exit(position(),replace(fill(),trigger_type="HORIZON_24H"),
            next_guard=None,expected_revision=0)


def test_stop_side_synthetic_fill_still_requires_residual_guard():
    p=position()
    f=fill(bid=".6878",ask=".6887",price=".6877",size="107")
    f=replace(f,trigger_type="STOP_LOSS",trigger_guard_id="stop-0")
    r=apply_synthetic_exit(p,f,next_guard=guard("262",1,
        "2026-10-02T23:03:33Z"),expected_revision=0)
    assert r.status=="SIMULATED_PARTIAL_PROTECTED"
    assert r.position.remaining==D("262")
    assert r.net_realized_ex_funding<0
    assert_no_authority(r)



def test_research_contract_has_no_authorsity_and_has_explicit_risk_signoff_gap():
    src=Path("alpha_hunter/successor_residual_exit_contract.py").read_text()
    for bad in ("import requests","urllib","psycopg","sqlalchemy","supabase",
                "place_order(","cancel_order(","execute_sql", "apply_migration",
                "trade_permission = True"):
        assert bad not in src
    assert "ISOLATED_SYNTHETIC_RECEIPT" in src
    assert "HALTED_UNRESOLVED" in src
    assert "production_promotion_permitted: bool = False" in src
    doc=Path("ops/research/SUCCESSOR_EXIT_RESIDUAL_RISK_APPROVAL_V01.md").read_text()
    assert "RISK_APPROVAL: NOT_GRANTED" in doc
    assert "DBA_APPROVAL: NOT_GRANTED" in doc
    assert "SCIENTIFIC_APPROVAL: NOT_GRANTED" in doc
    assert "LIVE_TRADING_AUTHORITY: DISABLED" in doc
