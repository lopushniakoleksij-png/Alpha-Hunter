from pathlib import Path

SQL = Path("ops/sql/sealed_profitability_activation_guard_v02.sql").read_text(
    encoding="utf-8"
).lower()


def test_activation_enforces_preregistration_and_cadence_boundaries():
    assert "v_spec.preregistered_at_utc" in SQL
    assert "baseline_not_before_utc" in SQL
    assert "p.collected_at_utc>=v_not_before" in SQL
    assert "'preregistration_boundary_ok'" in SQL
    assert "'cadence_not_before_boundary_ok'" in SQL


def test_activation_enforces_frozen_scientific_fingerprint():
    assert "frozen_scientific_fingerprint_sha256" in SQL
    assert (
        "p.payload->'validation_identity'->>'scientific_fingerprint_sha256'"
        in SQL
    )
    assert "'scientific_fingerprint_ok'" in SQL
    assert "baseline_scientific_fingerprint_sha256" in SQL


def test_activation_preserves_original_completeness_gates():
    for marker in [
        "required_strategy_count",
        "total_evaluations",
        "previous_snapshot_context",
        "catalyst_summary",
        "multi_strategy_engine",
        "microstructure",
        "last_closed_candle",
        "v_strategy_rows<>v_valid_symbols",
        "v_micro_rows<>v_valid_symbols",
        "v_closed_rows<>v_valid_symbols",
    ]:
        assert marker in SQL


def test_activation_stays_shadow_only():
    for forbidden in [
        "trade_permission,true",
        "production_promotion_permitted,true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
    assert "'trade_permission',false" in SQL
    assert "'production_promotion_permitted',false" in SQL
    assert "'order_path','none'" in SQL


def test_activation_cron_uses_v02():
    assert "alpha-hunter-profitability-test-activation-v01-hourly" in SQL
    assert "alpha_hunter_try_activate_profitability_test_v02" in SQL
    assert "schedule := '8,38 * * * *'" in SQL
