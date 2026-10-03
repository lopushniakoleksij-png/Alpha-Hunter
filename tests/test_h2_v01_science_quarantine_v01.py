from pathlib import Path

SQL = Path("h2_v01_science_quarantine_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_quarantine_is_explicit_and_append_only():
    assert "ah-h2-v01-trigger-source-quarantine-20261003" in LOWER
    assert "forming_15m_trigger_source_mismatch_issue_311" in LOWER
    assert "trg_ah_h2_science_quarantine_append_only_v01" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER


def test_existing_sealed_evidence_is_preserved_and_never_unsealed():
    assert "existing_evidence_preserved boolean not null default true" in LOWER
    assert "historical_results_exposed boolean not null default false" in LOWER
    assert "outcome_access_permitted boolean not null default false" in LOWER
    assert "confirmatory_analysis_permitted boolean not null default false" in LOWER
    assert "no sealed outcome value is selected or exposed" in LOWER


def test_quarantine_reads_only_operational_sealed_count_not_result_values():
    assert "alpha_hunter_h2_direction_sealed_collection_status_v01" in LOWER
    assert "sealed_outcome_set_count" in LOWER
    assert "from public.alpha_hunter_h2_direction_outcomes_sealed_v01" not in LOWER
    forbidden = [
        "h2_gross_r_pre_cost",
        "legacy_gross_r_pre_cost",
        "h2_path_class",
        "legacy_path_class",
        "h2_false_start",
        "legacy_false_start",
        "terminal_close",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_only_exact_known_v01_sealed_cron_is_unscheduled():
    assert "alpha-hunter-h2-direction-sealed-outcome-hourly" in LOWER
    assert "28 */6 * * *" in SQL
    assert "select private.alpha_hunter_run_h2_direction_sealed_v01();" in SQL
    assert "refuses unexpected sealed collector job contract" in LOWER
    assert "cron.unschedule(v_job.jobid)" in LOWER


def test_manual_v01_collector_fails_closed_without_outcome_access():
    assert "create or replace function private.alpha_hunter_run_h2_direction_sealed_v01()" in LOWER
    assert "quarantined_trigger_source_contract_invalid" in LOWER
    assert "'sealed_outcome_collection_permitted',false" in LOWER
    assert "'outcome_access_permitted',false" in LOWER
    assert "'confirmatory_analysis_permitted',false" in LOWER


def test_no_threshold_production_trade_or_order_authority():
    forbidden = [
        "trade_permission=true",
        "threshold_change_permitted=true",
        "production_promotion_permitted=true",
        "t0_authorized=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "'order_path','none'" in LOWER


def test_v01_cannot_transfer_maturity_into_v02():
    assert "v01_maturity_transfer_to_v02_permitted" in LOWER
    assert "ah-direction-architecture-h2-closed-capture-v02" in LOWER
    assert "collect_new_forward_h2_v02_only" in LOWER


def test_quarantine_never_deletes_or_updates_existing_science_rows():
    assert "delete from public.alpha_hunter_h2_direction" not in LOWER
    assert "update public.alpha_hunter_h2_direction" not in LOWER
