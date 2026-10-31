from pathlib import Path


SQL = Path("sealed_profitability_cadence_contract_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_hourly_cadence_is_frozen_and_append_only():
    required = [
        "expected_frequency_minutes integer not null default 60",
        "minimum_interval_minutes integer not null default 45",
        "maximum_interval_minutes integer not null default 90",
        "expected_schedule text not null default '0 * * * *'",
        "before update or delete on public.alpha_hunter_profitability_cadence_contract_v01",
    ]
    for marker in required:
        assert marker in LOWER


def test_cadence_monitor_detects_extra_scans_gaps_and_identity_drift():
    required = [
        "too_frequent_scan_intervals",
        "excessive_gap_intervals",
        "identity_mismatch_scan_count",
        "fail_extra_scan_frequency",
        "fail_scan_gap",
        "fail_build_or_config_identity",
    ]
    for marker in required:
        assert marker in LOWER


def test_cadence_contract_cannot_grant_trading_authority():
    required = [
        "true as audit_only",
        "true as paper_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER
