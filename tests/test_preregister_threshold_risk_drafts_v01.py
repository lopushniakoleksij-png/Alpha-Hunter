from pathlib import Path

SQL = Path("ops/sql/preregister_threshold_risk_drafts_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_threshold_contract_is_draft_only():
    assert "'me-thresh-draft-r3-20260929'" in SQL
    assert "'draft'" in SQL
    assert "'numeric_threshold_promotion_permitted',false" in SQL
    assert "'no_threshold_inference_from_pilot_means_alone'" in SQL


def test_risk_contract_is_draft_only():
    assert "'risk-policy-draft-r3-20260929'" in SQL
    assert "'risk_policy_activation_permitted',false" in SQL
    assert "'veto_only_position_and_portfolio_risk'" in SQL


def test_no_validation_or_activation_timestamp_is_set():
    assert "validated_at_utc" in SQL
    assert "activated_at_utc" in SQL
    assert "null,\n  null,\n  'money-entry-threshold-draft-r3-v0.1'" in SQL
    assert "null,\n  null,\n  'portfolio-risk-policy-draft-r3-v0.1'" in SQL


def test_no_trade_or_order_authority():
    assert "trade_permission" in SQL
    assert "true,\n  false" in SQL
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


def test_numeric_policy_values_remain_unset():
    assert "'me-thresh-draft-r3-20260929',\n  'draft',\n  null,\n  null,\n  null,\n  null," in SQL
    assert "'risk-policy-draft-r3-20260929',\n  'draft',\n  null,\n  null,\n  null,\n  null,\n  null,\n  null," in SQL
