"""Operator-truth contract for the read-only S1-S10 matrix.

This change is presentation-only: never modify paper admission, strategy
scores, directional conflicts, or the immutable R10 experiment.
"""
import inspect

import app


def test_matrix_does_not_label_local_comparison_as_canonical():
    assert "Previous comparison source (not proof of current canonical authority):" in app.PAGE
    assert "Previous canonical context:" not in app.PAGE


def test_strategy_scores_and_rr_are_described_truthfully():
    assert "Scores are uncalibrated 0-10 rule checklists" in app.PAGE
    assert "10.00 is not confidence or a profitability estimate" in app.PAGE
    assert "R:R is planned price geometry, not realized return" in app.PAGE
    assert "<th>Rule score /10</th>" in app.PAGE
    assert "<th>Planned R:R</th>" in app.PAGE


def test_shadow_strategy_intent_does_not_claim_paper_admission_authority():
    assert "These rows describe strategy intent, not R10 paper-admission permission" in app.PAGE
    assert "<th>Strategy gate (shadow)</th>" in app.PAGE
    assert "They cannot grant exchange/order authority." in app.PAGE


def test_existing_fail_closed_conflict_and_watch_gates_remain_intact():
    source = inspect.getsource(app.dashboard_payload)
    assert 'item["_display_gate_action"] = "BLOCKED_CONFLICT"' in source
    assert 'item["_display_setup_intent"] = "NO_ACTION"' in source
    assert 'item["_display_setup_intent"] = "WATCH_ONLY"' in source
    assert "canonicalize_action_queue(" in source
