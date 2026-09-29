from pathlib import Path

SQL = Path("ops/sql/big_mover_answer_key_decouple_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_answer_key_no_longer_runs_heavy_scoring_inline():
    answer_key = SQL.split(
        "create or replace function public.alpha_hunter_collect_big_mover_answer_key()",
        1,
    )[1].split(
        "revoke execute on function public.alpha_hunter_collect_big_mover_answer_key()",
        1,
    )[0]
    assert "alpha_hunter_run_big_mover_shadow()" not in answer_key
    assert "'heavy_scoring_inline',false" in answer_key


def test_answer_key_preserves_bitget_capture_and_safety():
    for marker in [
        "api/v2/mix/market/tickers?producttype=usdt-futures",
        "alpha_hunter_big_mover_answer_key",
        "'shadow_only',true",
        "'trade_permission',false",
        "on conflict(event_id) do nothing",
    ]:
        assert marker in SQL


def test_parent_direction_refuses_stale_shadow():
    assert "alpha_hunter_collect_big_mover_parent_direction_core_v03" in SQL
    assert "clock_timestamp()-v_shadow_at>interval '90 minutes'" in SQL
    assert "big-mover shadow is stale" in SQL


def test_heavy_shadow_scoring_is_isolated_after_core_chain():
    assert "alpha-hunter-big-mover-shadow-model-research-v01" in SQL
    assert "'11 * * * *'" in SQL
    assert "set statement_timeout='240s'" in SQL
    assert "select public.alpha_hunter_run_big_mover_shadow();" in SQL


def test_no_trade_authority_added():
    for forbidden in [
        "trade_permission,true",
        "production_promotion_permitted,true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL


def test_public_security_definer_is_not_api_exposed():
    assert (
        "revoke execute on function public.alpha_hunter_collect_big_mover_answer_key()"
        in SQL
    )
    assert "from public,anon,authenticated" in SQL
