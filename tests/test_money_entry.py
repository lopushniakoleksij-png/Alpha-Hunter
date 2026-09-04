import pytest

from alpha_hunter.money_entry import (
    build_money_entry_shadow,
    compare_entry_outcomes,
    confirmation_tax,
)


CFG = {
    "money_entry_shadow": {
        "max_t0_stop_distance_pct": 3.0,
        "min_t0_remaining_r": 3.0,
        "min_t1_remaining_r": 2.0,
        "min_t2_remaining_r": 1.5,
    }
}


def base_record():
    return {
        "direction": "LONG",
        "direction_12h": "LONG",
        "direction_1d": "LONG",
        "direction_1h": "LONG",
        "lifecycle_stage": "EARLY",
        "liquidity_ok": True,
        "participation_emerging": True,
        "participation_confirmed": False,
        "acceptance_confirmed": False,
        "trigger_confirmed": False,
        "expansion_confirmed": False,
        "structural_invalidation_valid": True,
        "stop_distance_pct": 1.5,
        "remaining_r": 5.0,
        "open_position_conflict": False,
    }


def test_t0_is_allowed_before_full_confirmation_but_never_grants_trade_permission():
    result = build_money_entry_shadow(base_record(), CFG)
    assert result["stage"] == "T0_CONTROLLED_ENTRY"
    assert result["eligible"] is True
    assert result["shadow_trade_permission"] is False


def test_t1_requires_acceptance_trigger_and_confirmed_participation():
    row = base_record()
    row.update({
        "participation_confirmed": True,
        "acceptance_confirmed": True,
        "trigger_confirmed": True,
        "remaining_r": 2.5,
    })
    result = build_money_entry_shadow(row, CFG)
    assert result["stage"] == "T1_ACCEPTANCE_CONFIRMED"


def test_t2_requires_expansion_and_remaining_r():
    row = base_record()
    row.update({
        "participation_confirmed": True,
        "acceptance_confirmed": True,
        "trigger_confirmed": True,
        "expansion_confirmed": True,
        "remaining_r": 2.0,
    })
    result = build_money_entry_shadow(row, CFG)
    assert result["stage"] == "T2_EXPANSION_CONFIRMED"


def test_wide_stop_blocks_t0():
    row = base_record()
    row["stop_distance_pct"] = 3.01
    result = build_money_entry_shadow(row, CFG)
    assert result["stage"] == "NO_T0"
    assert "T0_STOP_GEOMETRY_TOO_WIDE" in result["blockers"]


def test_parent_direction_conflict_blocks_t0():
    row = base_record()
    row["direction_1d"] = "SHORT"
    result = build_money_entry_shadow(row, CFG)
    assert result["stage"] == "NO_T0"
    assert "PARENT_1D_NOT_ALIGNED" in result["blockers"]


def test_open_position_conflict_is_hard_block():
    row = base_record()
    row["open_position_conflict"] = True
    result = build_money_entry_shadow(row, CFG)
    assert result["stage"] == "NO_T0"
    assert "OPEN_POSITION_CONFLICT" in result["blockers"]


def test_missing_thresholds_fail_closed_instead_of_inventing_values():
    result = build_money_entry_shadow(base_record(), {})
    assert result["stage"] == "DATA_INSUFFICIENT"
    assert result["eligible"] is False
    assert result["shadow_trade_permission"] is False


def test_confirmation_tax_positive_when_waiting_loses_rr():
    result = confirmation_tax(5.0, 2.0)
    assert result == {
        "status": "MEASURED",
        "early_rr": 5.0,
        "confirmed_rr": 2.0,
        "confirmation_tax_r": 3.0,
    }


def test_confirmation_tax_can_be_negative_when_waiting_improves_rr():
    result = confirmation_tax(2.0, 3.0)
    assert result["confirmation_tax_r"] == -1.0


def test_outcome_comparison_never_claims_expectancy():
    result = compare_entry_outcomes(1.4, 0.3)
    assert result["delta_net_r"] == pytest.approx(1.1)
    assert result["expectancy_claim_permitted"] is False


def test_outcome_comparison_reports_insufficient_data():
    result = compare_entry_outcomes(None, 0.3)
    assert result["status"] == "DATA_INSUFFICIENT"
    assert result["delta_net_r"] is None
