from pathlib import Path

SQL = Path("ops/sql/preregister_cost_model_draft_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_cost_model_is_draft_only():
    assert "'cost-model-draft-r3-20260929'" in SQL
    assert "'draft'" in SQL
    assert "'cost_model_activation_permitted',false" in SQL
    assert "'no_realistic_net_r_claim_before_validation'" in SQL


def test_model_parameters_are_unset():
    assert "'cost-model-draft-r3-20260929',\n  'draft',\n  null,\n  null,\n  null,\n  null," in SQL
    assert "'fee_values_promoted_to_model',false" in SQL
    assert "'floor_is_validated_cost_model',false" in SQL


def test_requires_prospective_binding():
    assert "'explicit_prospective_decision_to_exact_fill_bindings'" in SQL
    assert "'verified_alpha_hunter_execution_attribution'" in SQL
    assert "'arrival_to_fill_slippage_sample'" in SQL


def test_no_trade_or_order_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission,true",
        "status='active'",
        "status = 'active'",
    ]:
        assert forbidden not in SQL
