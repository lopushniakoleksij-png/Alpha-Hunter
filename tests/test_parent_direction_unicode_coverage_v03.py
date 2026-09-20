from pathlib import Path

SQL = Path("parent_direction_unicode_coverage_v03.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_unicode_safe_symbol_selection_keeps_usdt_suffix():
    assert "right(symbol,4)='USDT'" in SQL
    assert "^[A-Z0-9]+USDT$" not in SQL


def test_bitget_symbol_is_url_encoded():
    assert "extensions.urlencode(v_symbol.symbol::varchar)" in SQL
    assert "/api/v3/market/candles" in SQL


def test_full_coverage_contract_is_preserved():
    required = [
        "PRE_MOVER','IGNITION','EXPANSION",
        "ALL_SHADOW_QUEUE_PRE_MOVER_IGNITION_EXPANSION",
        "array['12H','1D']",
        "symbol_request_deduplication",
        "rate_limit_guard_ms",
    ]
    for marker in required:
        assert marker in SQL


def test_no_threshold_risk_or_trade_authority_change():
    forbidden = [
        "trade_permission=true",
        "production_execution_enabled=true",
        "set_leverage",
        "place-order",
        "cancel-order",
        "modify-order",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "'trade_permission',false" in SQL
    assert "shadow_only" in LOWER


def test_unicode_safe_model_version_is_explicit():
    assert "big-mover-parent-direction-shadow-v0.3-unicode-safe-full-money-entry-coverage" in SQL
