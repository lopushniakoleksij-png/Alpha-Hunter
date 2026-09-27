from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


SQL_PATH = Path("ops/sql/v15_candidate_retention_target_ledger_v02.sql")
SCRIPT_PATH = Path("ops/collect_candidate_retention_shadow.py")
WORKFLOW_PATH = Path(
    ".github/workflows/production-deployment-target-sync-v01.yml"
)

SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location(
    "candidate_retention_shadow_v02",
    SCRIPT_PATH,
)
assert spec is not None and spec.loader is not None
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def test_target_ledger_is_append_only_and_v14_excluded():
    assert "alpha_hunter_candidate_retention_shadow_targets_v02" in LOWER
    assert "enable row level security" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert "false" in LOWER
    assert "counted_in_v14 boolean not null default false" in LOWER
    assert "trade_permission boolean not null default false" in LOWER
    assert "order_path text not null default 'none'" in LOWER


def test_existing_targets_are_seeded_before_they_age_out():
    assert (
        "from public.alpha_hunter_candidate_retention_targets_v01 t"
        in LOWER
    )
    assert "on conflict (episode_id) do nothing" in LOWER


def test_collection_targets_are_separate_from_historical_audit_targets():
    assert "alpha_hunter_candidate_retention_collection_targets_v02" in LOWER
    assert (
        "retention_horizon_end_utc>clock_timestamp()-interval '2 hours'"
        in LOWER
    )
    coverage_segment = LOWER.split(
        "create or replace view "
        "public.alpha_hunter_candidate_retention_shadow_coverage_v01",
        1,
    )[1]
    assert (
        "from public.alpha_hunter_candidate_retention_shadow_targets_v02"
        in coverage_segment
    )


def test_collector_persists_discovered_targets_then_reads_collection_ledger():
    assert 'DISCOVERY_VIEW = "alpha_hunter_candidate_retention_targets_v01"' in SCRIPT
    assert (
        'TARGET_TABLE = "alpha_hunter_candidate_retention_shadow_targets_v02"'
        in SCRIPT
    )
    assert (
        'COLLECTION_VIEW = '
        '"alpha_hunter_candidate_retention_collection_targets_v02"'
        in SCRIPT
    )
    assert "_persist_targets(settings, discovered_targets, checked_at)" in SCRIPT
    assert "_load_targets(settings, COLLECTION_VIEW)" in SCRIPT


def test_existing_candle_is_not_generated_again():
    checked_at = datetime(2026, 9, 27, 19, 30, tzinfo=timezone.utc)
    targets = [
        {
            "episode_id": "episode-1",
            "first_candidate_observation_id": "obs-1",
            "symbol": "TESTUSDT",
            "strategy_id": "S6",
            "direction": "SHORT",
            "first_observed_at_utc": "2026-09-27T16:43:18+00:00",
            "first_candidate_at_utc": "2026-09-27T16:43:18+00:00",
            "first_candidate_action": "EXECUTE_NOW",
            "retention_start_utc": "2026-09-27T17:00:00+00:00",
            "retention_horizon_end_utc": "2026-09-28T16:43:18+00:00",
        }
    ]
    raw = [
        ["1790528400000", "10", "11", "9", "10.5", "100", "1000"],
        ["1790532000000", "10.5", "12", "10", "11", "110", "1200"],
    ]

    first_rows, _ = retention._build_rows_for_symbol(
        "TESTUSDT",
        targets,
        raw,
        checked_at,
    )
    assert len(first_rows) == 2

    existing = {
        (
            "episode-1",
            str(first_rows[0]["candle_open_utc"]),
        )
    }
    second_rows, _ = retention._build_rows_for_symbol(
        "TESTUSDT",
        targets,
        raw,
        checked_at,
        existing,
    )
    assert len(second_rows) == 1
    assert second_rows[0]["candle_open_utc"] != first_rows[0]["candle_open_utc"]


def test_existing_key_query_is_recent_and_bounded():
    assert "timedelta(hours=30)" in SCRIPT
    assert '"limit": "10000"' in SCRIPT
    assert '"select": "episode_id,candle_open_utc"' in SCRIPT


def test_retention_collector_is_classified_as_runtime_deploy_change():
    assert '- "ops/collect_candidate_retention_shadow.py"' in WORKFLOW


def test_no_v14_scientific_or_trade_path_change():
    for forbidden in [
        "insert into public.alpha_hunter_strategy_forward_outcomes_v01",
        "update public.alpha_hunter_strategy_forward_outcomes_v01",
        "delete from public.alpha_hunter_strategy_forward_outcomes_v01",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
        assert forbidden not in SCRIPT.lower()
