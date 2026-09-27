from pathlib import Path

SQL_PATH = Path("ops/sql/answer_key_training_indexes_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_training_index_fix_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"


def test_indexes_cover_existing_training_predicates():
    required = [
        "alpha_hunter_signal_features(run_id,captured_at_utc desc)",
        "alpha_hunter_signal_features(captured_at_utc desc)",
        "symbol,mover_direction,audited_at_utc",
        "where mover_threshold_pct>=5",
        "where mover_threshold_pct>=10",
        "symbol,direction,observed_at_utc",
        "where threshold_pct>=5",
        "where threshold_pct>=10",
        "alpha_hunter_big_mover_answer_key(observed_at_utc desc)",
    ]
    compact = LOWER.replace("\n", "").replace("  ", "")
    for marker in required:
        assert marker.replace(" ", "") in compact.replace(" ", "")


def test_index_fix_does_not_modify_scientific_logic():
    forbidden = [
        "create or replace function",
        "drop function",
        "update public.alpha_hunter_",
        "delete from public.alpha_hunter_",
        "insert into public.alpha_hunter_",
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "threshold_pct =",
        "mover_threshold_pct =",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_index_fix_refreshes_planner_stats_only():
    assert "analyze public.alpha_hunter_signal_features" in LOWER
    assert "analyze public.alpha_hunter_missed_mover_audit" in LOWER
    assert "analyze public.alpha_hunter_big_mover_answer_key" in LOWER


def test_no_concurrent_index_in_transactional_migration():
    assert "concurrently" not in LOWER
