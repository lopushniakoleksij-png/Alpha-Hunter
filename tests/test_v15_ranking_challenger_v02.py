from pathlib import Path

SQL_PATH = Path("ops/sql/v15_ranking_challenger_v02.sql")
SCRIPT_PATH = Path("ops/collect_v15_ranking_challenger.py")
PERFORMANCE_PATH = Path("performance_job.py")

SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")
SCRIPT_LOWER = SCRIPT.lower()
PERFORMANCE = PERFORMANCE_PATH.read_text(encoding="utf-8")


def test_selector_uses_only_contemporaneous_universe_evidence():
    assert "alpha_hunter_universe_hourly" in LOWER
    for forbidden in [
        "alpha_hunter_big_mover_answer_key",
        "alpha_hunter_forward_missed_mover_audit",
        "signal_outcomes",
        "strategy_forward_outcomes",
        "realized_pnl",
    ]:
        assert forbidden not in LOWER


def test_selector_is_early_unselected_and_cadence_normalized():
    required = [
        "prefilter_eligible is true",
        "deep_scan_selected is false",
        "abs(u.change_24h_pct)<5.0",
        "interval '5 minutes'",
        "interval '30 minutes'",
        "between 300 and 1800",
        "ln(p.quote_volume_24h/p.previous_quote_volume_24h)",
        "*3600.0/nullif(p.previous_gap_seconds,0)",
        "hourly_normalized_volume_log_growth>0",
        "challenger_rank<=5",
    ]
    for marker in required:
        assert marker in LOWER


def test_selector_never_mutates_production_or_trade_authority():
    required = [
        "false as production_selector_changed",
        "false as outcome_evidence_used",
        "false as counted_in_v14",
        "false as t0_authorized",
        "false as threshold_change_permitted",
        "false as production_promotion_permitted",
        "true as shadow_only",
        "false as trade_permission",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER

    for forbidden in [
        "update public.alpha_hunter_universe_hourly",
        "insert into public.alpha_hunter_universe_hourly",
        "delete from public.alpha_hunter_universe_hourly",
    ]:
        assert forbidden not in LOWER


def test_sidecar_tables_are_rls_append_only_and_service_role_only():
    assert LOWER.count("enable row level security") >= 2
    assert LOWER.count("alpha_hunter_block_append_only_mutation") >= 2
    assert "alpha_hunter_v15_ranking_challenger_observations_v01" in LOWER
    assert "alpha_hunter_v15_ranking_challenger_runs_v01" in LOWER
    assert "to service_role" in LOWER


def test_collector_has_no_private_exchange_or_order_write_path():
    assert "MAX_TARGETS = 5" in SCRIPT
    assert "collect_symbol(" in SCRIPT
    assert "apply_candidate_quality(" in SCRIPT
    assert "apply_multi_strategy_engine(" in SCRIPT
    for forbidden in [
        "BITGET_API_KEY",
        "BITGET_SECRET_KEY",
        "BITGET_API_PASSPHRASE",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
    ]:
        assert forbidden.lower() not in SCRIPT_LOWER


def test_persisted_authority_is_always_false():
    assert '"counted_in_v14": False' in SCRIPT
    assert '"production_selector_changed": False' in SCRIPT
    assert '"threshold_change_permitted": False' in SCRIPT
    assert '"production_promotion_permitted": False' in SCRIPT
    assert '"trade_permission": False' in SCRIPT
    assert '"order_path": "NONE"' in SCRIPT


def test_performance_job_runs_challenger_nonfatally():
    assert "collect_v15_ranking_challenger.py" in PERFORMANCE
    assert "V15 RANKING CHALLENGER SHADOW: PASS" in PERFORMANCE
    assert "V15 RANKING CHALLENGER SHADOW DEGRADED" in PERFORMANCE
    assert "check=False" in PERFORMANCE


def test_v15_files_stay_outside_v14_scientific_paths():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SCRIPT_PATH.parent.as_posix() == "ops"
    assert PERFORMANCE_PATH.name == "performance_job.py"
