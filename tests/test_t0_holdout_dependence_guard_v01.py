from pathlib import Path

SQL = Path("ops/sql/t0_holdout_dependence_guard_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_dependence_contract_is_preregistered_before_outcomes():
    assert "registered_before_holdout_outcomes_matured',true" in SQL
    assert "me-t0-long-dependence-guard-v01" in SQL
    assert "me-t0-long-holdout-v01" in SQL


def test_symbol_and_day_cluster_checks_are_both_required():
    assert "symbol_equal_weight_cluster_mean" in SQL
    assert "utc_day_equal_weight_cluster_mean" in SQL
    assert "symbol_mean_lower95" in SQL
    assert "day_mean_lower95" in SQL


def test_original_holdout_must_also_pass():
    assert "require_original_gross_holdout_pass" in SQL
    assert "o.gross_holdout_pass is not true" in SQL


def test_minimum_effect_is_applied_to_cluster_means():
    assert "ss.symbol_mean_r<c.minimum_cluster_mean_r" in SQL
    assert "ds.day_mean_r<c.minimum_cluster_mean_r" in SQL


def test_no_threshold_activation_or_production_authority():
    assert "threshold_activation_permitted boolean not null default false" in SQL
    assert "production_promotion_permitted boolean not null default false" in SQL
    for forbidden in [
        "update private.alpha_hunter_t0_threshold_holdout",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "threshold_activation_permitted=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_view_uses_security_invoker():
    assert "with (security_invoker=true,security_barrier=true)" in SQL
