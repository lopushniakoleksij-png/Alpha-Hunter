from pathlib import Path

SQL = Path("money_entry_stage_position_conflict_binding_v01.sql").read_text(encoding="utf-8")


def test_position_conflict_requires_exact_canonical_verified_account_evidence():
    required = [
        "a.source='CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE'",
        "a.connection_status='CONNECTED_READ_ONLY'",
        "a.schema_validated=true",
        "a.complete=true",
        "a.shadow_only=true",
        "a.trade_permission=false",
        "a.evidence->>'canonical_run_id'=p_source_run_id",
        "a.evidence->>'cached_payload_only'='true'",
        "a.evidence->>'no_extra_bitget_request'='true'",
        "a.captured_at_utc<=p_source_captured_at_utc",
        "a.captured_at_utc>=date_trunc('hour',p_source_captured_at_utc)",
    ]
    for text in required:
        assert text in SQL


def test_position_count_must_match_persisted_child_rows():
    assert "persisted_open_position_count" in SQL
    assert "select count(*)::integer" in SQL
    assert "public.alpha_hunter_open_position_snapshots" in SQL


def test_writer_uses_canonical_conflict_not_scanner_payload_fallback():
    assert "pc.position_conflict canonical_position_conflict" in SQL
    assert "s.canonical_position_conflict open_position_conflict" in SQL
    assert "source_payload#>>'{execution_setup,checks,open_position_conflict}'" not in SQL
    assert "source_payload->>'open_position_conflict'" not in SQL


def test_missing_account_evidence_stays_fail_closed():
    assert "OPEN_POSITION_CONFLICT_NOT_CAPTURED" in SQL
    assert "case when n.open_position_conflict is null" in SQL
    assert "when n.open_position_conflict is true then 'OPEN_POSITION_CONFLICT'" in SQL


def test_existing_liquidity_and_threshold_gates_are_preserved():
    assert "private.alpha_hunter_stage_universe_liquidity" in SQL
    assert "s.universe_liquidity_pass liquidity_ok" in SQL
    assert "LIQUIDITY_PASS_NOT_CAPTURED" in SQL
    assert "NO_ACTIVE_VALIDATED_THRESHOLD_SET" in SQL
    assert "exact_stage_claim_requires_active_validated_thresholds',true" in SQL


def test_no_exchange_or_live_execution_path_is_added():
    lowered = SQL.lower()
    assert "api.bitget.com" not in lowered
    assert "http_post" not in lowered
    assert "place_order" not in lowered
    assert "submit_order" not in lowered
    assert "trade_permission',false" in SQL
    assert "'shadow_only',true" in SQL
    assert "money-entry-stage-single-writer-v0.3-position-conflict-bound" in SQL
