from pathlib import Path

SQL = Path("forward_missed_mover_audit_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_audit_unit_is_first_5pct_episode_not_every_threshold_row():
    required = [
        "where a.threshold_pct=5",
        "lag(a.observed_at_utc)",
        "interval '24 hours'",
        "episode_starts",
        "previous_5pct_at",
    ]
    for marker in required:
        assert marker in SQL


def test_root_cause_uses_only_pre5_evidence():
    required = [
        "sf.captured_at_utc<p.observed_at_utc",
        "u.observed_at_utc<p.observed_at_utc",
        "abs((sf.source_payload->>'change_24h_pct')::double precision)<5.0",
        "abs(change_24h_pct)<5.0",
        "root_cause_uses_only_pre5_evidence",
        "post_event_magnitude_used_for_classification",
        "future_outcome_used_for_classification",
    ]
    for marker in required:
        assert marker in SQL


def test_mover_direction_maps_to_trade_direction_deterministically():
    assert "case when p.direction='UP' then 'LONG' else 'SHORT' end" in SQL


def test_found_and_missed_classes_are_explicit():
    required = [
        "NOT_AUDITABLE",
        "FOUND_EXECUTABLE_SHADOW",
        "FOUND_DIRECTION_PREMOVE",
        "WRONG_DIRECTION_PREMOVE",
        "FOUND_UNCONFIRMED_PREMOVE",
        "DEEP_SCAN_EVIDENCE_GAP",
        "PREFILTERED_NOT_DEEP_SCANNED",
        "SEEN_NOT_PREFILTERED",
    ]
    for marker in required:
        assert marker in SQL


def test_root_cause_classes_cover_money_pipeline():
    required = [
        "'DATA'",
        "'DISCOVERY'",
        "'RANKING'",
        "'DIRECTION'",
        "'CONFIRMATION_TAX'",
        "'EXECUTION_RR'",
        "'EXECUTION'",
        "'EXECUTION_HANDOFF'",
    ]
    for marker in required:
        assert marker in SQL


def test_legacy_alignment_block_maps_to_confirmation_tax():
    assert "Direction is not fully aligned" in SQL
    assert "then 'CONFIRMATION_TAX'" in SQL


def test_rr_block_maps_to_execution_rr():
    assert "rr_minimum_met" in SQL
    assert "then 'EXECUTION_RR'" in SQL


def test_no_second_market_scan_or_exchange_http_call():
    assert "second_market_scan_used" in SQL
    assert "false as second_market_scan_used" in SQL
    for marker in (
        "http_get",
        "api.bitget.com",
        "market/tickers",
        "market/candles",
    ):
        assert marker not in LOWER


def test_audit_is_append_only_service_role_read_only():
    assert (
        "alter table public.alpha_hunter_forward_missed_mover_audit_v01"
        in LOWER
    )
    assert "enable row level security" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert (
        "grant select on table public.alpha_hunter_forward_missed_mover_audit_v01"
        in LOWER
    )


def test_no_execution_or_production_authority():
    required = [
        "shadow_only boolean not null default true",
        "trade_permission boolean not null default false",
        "t0_authorized boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "order_path text not null default 'NONE'",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_hourly_job_reuses_database_evidence_only():
    assert "alpha-hunter-forward-missed-mover-audit-hourly" in SQL
    assert "'19 * * * *'" in SQL
    assert "alpha_hunter_big_mover_answer_key" in SQL
    assert "alpha_hunter_universe_hourly" in SQL
    assert "alpha_hunter_signal_features" in SQL
