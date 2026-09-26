from pathlib import Path

ANALYSIS = Path("alpha_hunter/analysis.py").read_text(encoding="utf-8")
BRIDGE = Path("big_mover_money_entry_bridge.sql").read_text(encoding="utf-8")
STAGE = Path("money_entry_stage_single_writer.sql").read_text(encoding="utf-8")
MIGRATION = Path("money_entry_geometry_contract_binding_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = MIGRATION.lower()


def test_scanner_geometry_contract_is_explicit_and_versioned():
    assert (
        'EXECUTION_GEOMETRY_CONTRACT_ID = '
        '"SCANNER_CURRENT_PRICE_1H_40_EXTREMES_V1"'
    ) in ANALYSIS
    assert '"geometry_contract_id": EXECUTION_GEOMETRY_CONTRACT_ID' in ANALYSIS


def test_bridge_freezes_source_geometry_contract():
    assert (
        "source_payload#>>'{execution_setup,geometry_contract_id}'"
        " as geometry_contract_id"
    ) in BRIDGE
    assert "'geometry_contract_id',d.geometry_contract_id" in BRIDGE


def test_non_draft_threshold_requires_geometry_contract():
    assert "geometry_contract_id text" in STAGE
    assert "status='DRAFT' or (" in STAGE
    assert "geometry_contract_id is not null" in STAGE

    assert "ah_money_entry_threshold_geometry_required" in MIGRATION
    assert "status='DRAFT'" in MIGRATION


def test_stage_writer_selects_only_matching_active_threshold():
    required = [
        "v_source_geometry_contract_id",
        "v_threshold_geometry_contract_id",
        "SOURCE_GEOMETRY_CONTRACT_MISSING",
        "SOURCE_GEOMETRY_CONTRACT_MIXED",
        "NO_ACTIVE_VALIDATED_THRESHOLD_SET_FOR_GEOMETRY",
        "t.geometry_contract_id=v_source_geometry_contract_id",
    ]
    for marker in required:
        assert marker in STAGE


def test_exact_stage_requires_matching_geometry_contract():
    required = [
        "source_geometry_contract_id",
        "threshold_geometry_contract_id",
        "THRESHOLD_GEOMETRY_CONTRACT_MISMATCH",
        "geometry_contract_match",
        "ah_money_entry_exact_stage_geometry_match",
    ]
    for marker in required:
        assert marker in (STAGE + MIGRATION)

    assert (
        "threshold_geometry_contract_id=source_geometry_contract_id"
        in MIGRATION
    )


def test_existing_data_is_not_backfilled_or_reclassified():
    # Only inspect migration-time DDL before function definitions. The stage
    # writer function is expected to contain a future INSERT when it is called.
    ddl = LOWER.split(
        "create or replace function private.alpha_hunter_run_big_mover_money_entry_bridge()",
        1,
    )[0]

    for marker in (
        "update public.alpha_hunter_money_entry_threshold_sets",
        "update public.alpha_hunter_money_entry_stage_snapshots",
        "insert into public.alpha_hunter_money_entry_threshold_sets",
        "insert into public.alpha_hunter_money_entry_stage_snapshots",
    ):
        assert marker not in ddl


def test_no_threshold_numbers_or_execution_authority_are_introduced():
    forbidden = [
        "values ('",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "/api/v2/mix/order/place-order",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "'thresholds_invented',false" in STAGE
    assert "'trade_permission',false" in STAGE
