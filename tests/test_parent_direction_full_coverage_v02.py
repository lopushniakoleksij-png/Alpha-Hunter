from pathlib import Path

SQL = Path('parent_direction_full_coverage_v02.sql').read_text()


def test_parent_direction_matches_money_entry_candidate_contract():
    assert "research_status='SHADOW_QUEUE'" in SQL
    assert "lifecycle in('PRE_MOVER','IGNITION','EXPANSION')" in SQL
    assert "rn<=5" not in SQL
    assert "coverage_contract','ALL_SHADOW_QUEUE_PRE_MOVER_IGNITION_EXPANSION'" in SQL


def test_symbol_requests_are_deduplicated_before_direction_fanout():
    assert "select symbol,max(captured_at_utc) as captured_at_utc" in SQL
    assert "group by symbol" in SQL
    assert "for v_hypothesis in" in SQL
    assert "symbol_request_deduplication',true" in SQL
    assert "http_requests" in SQL
    assert "hypotheses_covered" in SQL


def test_public_candle_rate_limit_is_guarded():
    assert "api/v3/market/candles" in SQL
    assert "array['12H','1D']" in SQL
    assert "pg_catalog.pg_sleep(0.06)" in SQL
    assert "rate_limit_guard_ms',60" in SQL


def test_existing_logical_snapshot_identity_is_preserved():
    assert "md5('big-mover-parent-direction-shadow-v0.1|'" in SQL
    assert "big-mover-parent-direction-shadow-v0.2-full-money-entry-coverage" in SQL
    assert "on conflict(snapshot_id) do update" in SQL


def test_safety_boundary_is_unchanged():
    required = [
        "shadow_only',true",
        "trade_permission',false",
        "revoke all on function private.alpha_hunter_collect_big_mover_parent_direction() from public,anon,authenticated",
        "grant execute on function private.alpha_hunter_collect_big_mover_parent_direction() to service_role",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
        "status='ACTIVE'",
    ]
    for marker in forbidden:
        assert marker not in SQL
