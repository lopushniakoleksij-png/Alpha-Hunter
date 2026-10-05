from pathlib import Path

from alpha_hunter.paper_execution import build_initial_paper_execution


def _decision():
    return {
        "decision_id": "r10-runtime-decision",
        "run_id": "canonical-run-r10",
        "observed_at_utc": "2026-10-05T08:20:00+00:00",
        "symbol": "TESTUSDT",
        "strategy_id": "S2",
        "direction": "LONG",
        "action_status": "PLACE_LIMIT_PAPER",
        "entry_price": 10.0,
        "stop_price": 9.0,
        "target_price": 15.0,
        "best_bid": 9.99,
        "best_ask": 10.01,
        "best_bid_size": 1000.0,
        "best_ask_size": 1000.0,
        "public_maker_fee_bps": 2.0,
        "public_taker_fee_bps": 6.0,
        "paper_authority": True,
        "evidence": {
            "instrument_constraints": {
                "size_multiplier": "0.1",
                "minimum_trade_number": "0.1",
                "minimum_trade_usdt": "5",
            },
        },
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def _identity(**overrides):
    row = {
        "activation_id": "PAPER_EXECUTION_R10",
        "spec_id": "SEALED-R10-TEST",
        "scientific_fingerprint_sha256": "d" * 64,
    }
    row.update(overrides)
    return row


def test_required_successor_identity_fails_closed_when_absent():
    orders, fills, events = build_initial_paper_execution(
        [_decision()],
        execution_gate_open=True,
        successor_identity_required=True,
    )
    assert orders == []
    assert fills == []
    assert [event["state"] for event in events] == ["CANCELLED"]
    assert "PAPER_SUCCESSOR_IDENTITY_INVALID" in events[0]["payload"]["blockers"]


def test_required_successor_identity_rejects_wrong_activation_or_fingerprint():
    for identity in (
        _identity(activation_id="PAPER_EXECUTION_R9"),
        _identity(scientific_fingerprint_sha256="not-a-fingerprint"),
    ):
        orders, fills, events = build_initial_paper_execution(
            [_decision()],
            execution_gate_open=True,
            successor_identity=identity,
            successor_identity_required=True,
        )
        assert orders == []
        assert fills == []
        assert "PAPER_SUCCESSOR_IDENTITY_INVALID" in events[0]["payload"]["blockers"]


def test_valid_r10_identity_is_stamped_at_original_order_admission():
    orders, fills, events = build_initial_paper_execution(
        [_decision()],
        execution_gate_open=True,
        successor_identity=_identity(),
        successor_identity_required=True,
    )
    assert len(orders) == 1
    order = orders[0]
    assert order["successor_activation_id"] == "PAPER_EXECUTION_R10"
    assert order["successor_spec_id"] == "SEALED-R10-TEST"
    assert order["successor_scientific_fingerprint_sha256"] == "d" * 64
    assert order["successor_source_run_id"] == "canonical-run-r10"
    assert order["submitted_at_utc"] == _decision()["observed_at_utc"]
    assert order["paper_only"] is True
    assert order["exchange_authority"] is False
    assert order["trade_permission"] is False
    assert order["order_path"] == "NONE"
    assert fills == []
    assert [event["state"] for event in events] == ["SUBMITTED"]


def test_runtime_source_uses_only_r10_open_admission_and_requires_identity():
    source = Path("alpha_hunter/storage.py").read_text(encoding="utf-8")
    assert '"alpha_hunter_paper_admission_open_v10"' in source
    assert '"activation_id": "eq.PAPER_EXECUTION_R10"' in source
    assert 'successor_identity_required=True' in source
    assert 'execution_gate_blocker="PAPER_SUCCESSOR_ADMISSION_NOT_ACTIVATED"' in source
    assert '"alpha_hunter_paper_admission_open_v09"' not in source
