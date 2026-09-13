from pathlib import Path

SQL = Path('money_scorecard_stage_flag_hotfix.sql').read_text()


def test_missing_exact_stage_flags_fail_closed_to_false():
    assert "coalesce(s.exact_stage_status='T0_CONTROLLED_ENTRY',false)" in SQL
    assert "coalesce(s.exact_stage_status='T1_ACCEPTANCE_CONFIRMED',false)" in SQL
    assert "coalesce(s.exact_stage_status='T2_EXPANSION_CONFIRMED',false)" in SQL
    assert "coalesce(s.exact_stage_status in ('T0_CONTROLLED_ENTRY','T1_ACCEPTANCE_CONFIRMED','T2_EXPANSION_CONFIRMED'),false)" in SQL


def test_hotfix_preserves_shadow_boundary():
    lowered = SQL.lower()
    assert "'big-mover-money-scorecard-v0.2-stage-linked',true,false" in SQL
    assert 'place-order' not in lowered
    assert '/api/v2/mix/order' not in lowered
    assert '/api/v3/trade/' not in lowered
    assert 'trade_permission=true' not in lowered.replace(' ', '')


def test_security_definer_search_path_is_pinned():
    assert "security definer\nset search_path = ''" in SQL
    assert 'revoke all on function private.alpha_hunter_seed_big_mover_money_scorecard() from public, anon, authenticated;' in SQL
