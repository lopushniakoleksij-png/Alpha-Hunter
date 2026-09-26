from pathlib import Path

SQL = Path("ops/sql/profitability_activation_cadence_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_activation_cadence_checks_every_ten_minutes():
    assert "alpha-hunter-profitability-test-activation-v01-hourly" in SQL
    assert "7,17,27,37,47,57 * * * *" in SQL
    assert "cron.alter_job" in LOWER


def test_activation_cadence_fails_closed_if_job_is_missing_or_ambiguous():
    assert "into strict v_jobid" in LOWER


def test_activation_cadence_does_not_change_scientific_or_trade_logic():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "minimum_test_days",
        "minimum_completed_paper_trades",
        "required_minimum_rr",
        "frozen_scientific_fingerprint_sha256",
    ]
    for marker in forbidden:
        assert marker not in LOWER
