from pathlib import Path


SQL = Path("evidence_acl_quarantine_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_immutable_evidence_tables_are_select_only_for_service_role():
    expected = {
        "alpha_hunter_early_mover_cohort",
        "alpha_hunter_money_entry_candidate_episodes",
        "alpha_hunter_money_entry_stage_progressions",
        "alpha_hunter_money_entry_progression_anomalies",
    }
    for table in expected:
        assert f"'{table}'" in SQL
    assert "revoke all on table public.%I from service_role" in SQL
    assert "grant select on table public.%I to service_role" in SQL
    assert "grant insert" not in LOWER
    assert "grant update" not in LOWER
    assert "grant delete" not in LOWER
    assert "grant truncate" not in LOWER


def test_unsafe_draft_progression_entry_points_are_quarantined():
    assert "alpha_hunter_record_money_entry_progression(text)" in SQL
    assert "alpha_hunter_backfill_money_entry_progressions()" in SQL
    assert "revoke all on function" in LOWER
    assert "disable trigger trg_ah_after_portfolio_risk_capture_progression" in LOWER
    assert "drop table" not in LOWER
    assert "delete from" not in LOWER
    assert "truncate table" not in LOWER


def test_quarantine_is_safe_when_draft_pr19_objects_are_absent():
    assert "pg_catalog.to_regclass" in SQL
    assert SQL.count("pg_catalog.to_regprocedure") == 2
    assert "if exists (" in LOWER


def test_quarantine_does_not_touch_operational_scorecard_writers():
    assert "alpha_hunter_big_mover_money_scorecard_candidates" not in SQL
    assert "alpha_hunter_big_mover_money_scorecard_outcomes" not in SQL
    assert "cron." not in LOWER
