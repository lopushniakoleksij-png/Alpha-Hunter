from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "ops/sql/sealed_profitability_r7_paper_geometry_baseline_v01.sql"


def test_r7_preregistration_sql_parses_and_is_append_only():
    sql = SQL_PATH.read_text(encoding="utf-8")
    lower = sql.lower()

    assert parse_sql(sql)
    assert "insert into public.alpha_hunter_profitability_test_specs_v01" in lower
    assert "insert into public.alpha_hunter_profitability_cadence_contract_v01" in lower
    assert "update public.alpha_hunter_profitability" not in lower
    assert "delete from public.alpha_hunter_profitability" not in lower
    assert "truncate" not in lower


def test_r7_freezes_hardened_runtime_and_scientific_fingerprint():
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "SEALED-ARCH-V14R7-FP-20M-20261003" in sql
    assert "e15a6d984bfed05021308b9180bebc1385079b5b" in sql
    assert "a69cfb66c070640238d2ff480988c02c7da7f6955b43d4f1a12f10c4fc6095db" in sql
    assert "'RENDER_CRON'" in sql


def test_r7_preserves_sealed_economic_and_cadence_gates():
    sql = SQL_PATH.read_text(encoding="utf-8")

    required = [
        "  10,",
        "  5.0,",
        "  24,",
        "  30,",
        "  100,",
        "  1.96,",
        "'RENDER_CRON_ALIGNED_00_20_40'",
        "  20,",
        "  15,",
        "  35,",
    ]
    for marker in required:
        assert marker in sql

    assert "'NONE'" in sql
    assert "SEALED_PROFITABILITY_PREREGISTRATION" in sql
    assert "SEALED_SCAN_CADENCE_CONTRACT" in sql


def test_r7_has_no_live_trade_authority():
    lower = SQL_PATH.read_text(encoding="utf-8").lower()

    assert "place_order(" not in lower
    assert "cancel_order(" not in lower
    assert "modify_order(" not in lower
    assert "set_leverage(" not in lower
    assert "trade_permission" in lower
    assert "production_promotion_permitted" in lower
    assert "order_path" in lower
