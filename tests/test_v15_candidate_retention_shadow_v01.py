from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


SQL_PATH = Path("ops/sql/v15_candidate_retention_shadow_v01.sql")
SCRIPT_PATH = Path("ops/collect_candidate_retention_shadow.py")
PERFORMANCE_PATH = Path("performance_job.py")

SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")
PERFORMANCE = PERFORMANCE_PATH.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location(
    "candidate_retention_shadow",
    SCRIPT_PATH,
)
assert spec is not None and spec.loader is not None
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


def test_retention_schema_is_ops_only_and_v14_excluded():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "v15_parallel_shadow" in LOWER
    assert "false as counted_in_v14" in LOWER
    assert "counted_in_v14 boolean not null default false" in LOWER
    assert "audit_only boolean not null default true" in LOWER
    assert "false as trade_permission" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_targets_come_only_from_sealed_candidate_episodes():
    assert "alpha_hunter_strategy_observations_v01" in LOWER
    assert "alpha_hunter_strategy_episodes_v01" in LOWER
    assert "o.status='shadow_candidate'" in LOWER
    assert "o.action in ('execute_now','place_limit')" in LOWER
    assert "e.episode_id=c.episode_id" in LOWER
    assert "sealed_candidate_episodes_only" in LOWER
    assert "universe_discovery_permitted" in LOWER


def test_episode_identity_is_strategy_instance_identity():
    assert "o.strategy_instance_id as episode_id" in LOWER
    assert "e.episode_id=c.episode_id" in LOWER


def test_retention_rows_are_append_only_and_service_role_only():
    assert LOWER.count("enable row level security") >= 2
    assert LOWER.count("alpha_hunter_block_append_only_mutation") >= 2
    assert (
        "grant select,insert on table "
        "public.alpha_hunter_candidate_retention_shadow_candles_v01"
    ) in LOWER
    assert (
        "grant select,insert on table "
        "public.alpha_hunter_candidate_retention_shadow_runs_v01"
    ) in LOWER


def test_retention_window_matches_sealed_24h_episode_clock():
    assert "e.first_observed_at_utc+interval '24 hours'" in LOWER
    assert (
        "date_trunc('hour',c.first_candidate_at_utc)+interval '1 hour'"
        in LOWER
    )
    assert "candle_open_utc+interval '1 hour'<=retention_horizon_end_utc" in LOWER


def test_public_get_only_and_no_private_or_order_path():
    assert 'PRODUCT_TYPE = "USDT-FUTURES"' in SCRIPT
    assert 'GRANULARITY = "1H"' in SCRIPT
    assert "client.candles(" in SCRIPT
    assert "private_credentials_required" in SCRIPT
    assert '"private_credentials_required": False' in SCRIPT
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
        assert forbidden not in SCRIPT


def test_recent_candle_fetch_supports_backfill():
    assert "CANDLE_LIMIT = 30" in SCRIPT
    assert "candle_known <= checked_at" in SCRIPT
    assert "if candle_open < retention_start" in SCRIPT
    assert "if candle_known > horizon_end" in SCRIPT


def test_build_rows_uses_only_fully_closed_future_candles():
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
        ["1758992400000", "10", "11", "9", "10.5", "100", "1000"],
        ["1758996000000", "10.5", "12", "10", "11", "110", "1200"],
        ["1758999600000", "11", "13", "10.5", "12", "120", "1400"],
    ]

    rows, considered = retention._build_rows_for_symbol(
        "TESTUSDT",
        targets,
        raw,
        checked_at,
    )

    assert considered >= 1
    assert all(row["fully_closed"] is True for row in rows)
    assert all(row["counted_in_v14"] is False for row in rows)
    assert all(row["trade_permission"] is False for row in rows)
    assert all(row["episode_id"] == "episode-1" for row in rows)
    assert all(
        retention._parse_utc(row["candle_known_at_utc"]) <= checked_at
        for row in rows
    )


def test_performance_job_runs_shadow_collector_nonfatally():
    assert "collect_candidate_retention_shadow.py" in PERFORMANCE
    assert "V15 CANDIDATE RETENTION SHADOW DEGRADED" in PERFORMANCE
    assert "V15 CANDIDATE RETENTION SHADOW: PASS" in PERFORMANCE
    assert "check=False" in PERFORMANCE


def test_no_v14_scientific_files_changed_by_schema_location():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert SCRIPT_PATH.parent.as_posix() == "ops"
    assert PERFORMANCE_PATH.name == "performance_job.py"
