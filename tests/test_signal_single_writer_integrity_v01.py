from pathlib import Path

SQL_PATH = Path("ops/sql/signal_single_writer_integrity_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_single_writer_integrity_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_signal_single_writer_integrity_v01" in LOWER


def test_integrity_binds_to_latest_auxiliary_source_run():
    assert "alpha_hunter_execution_quality_collector_runs_v01" in LOWER
    assert "a.source_run_id=s.run_id" in LOWER.replace(" ", "")
    assert "auxiliary_source_run_id" in LOWER


def test_integrity_checks_signal_storage_contract():
    assert "signal-source-v0.2" in LOWER
    assert "compact_signal_rows" in LOWER
    assert "noncompact_signal_rows" in LOWER
    assert "signal_single_writer_regression" in LOWER


def test_single_writer_contract_is_explicit_and_fail_closed():
    assert "canonical_scanner_only" in LOWER
    assert "false as auxiliary_signal_write_permitted" in LOWER
    assert "no_auxiliary_run" in LOWER
    assert "no_signal_rows" in LOWER


def test_view_is_read_only_and_trade_disabled():
    assert "security_invoker=true" in LOWER
    assert "security_barrier=true" in LOWER
    assert "false as mutation_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_no_signal_write_or_evidence_mutation_is_added():
    for forbidden in [
        "insert into public.alpha_hunter_signals",
        "update public.alpha_hunter_signals",
        "delete from public.alpha_hunter_signals",
        "truncate ",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
