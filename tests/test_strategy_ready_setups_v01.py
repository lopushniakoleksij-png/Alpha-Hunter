from pathlib import Path

SQL = Path("strategy_ready_setups_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_ready_queue_accepts_only_shadow_candidates_with_five_r():
    required = [
        "o.status='shadow_candidate'",
        "o.action in ('execute_now','place_limit')",
        "o.reward_risk>=5.0",
        "coalesce(o.geometry_valid,false)",
    ]
    for marker in required:
        assert marker in LOWER


def test_ready_queue_is_source_scoped_and_fresh():
    assert "in ('render_cron','render','github_fast_discovery')" in LOWER
    assert "'render_web'" not in LOWER
    assert "interval '90 minutes'" in LOWER
    assert "source_latest" in LOWER


def test_ready_queue_rechecks_directional_geometry():
    assert "o.stop_price<o.entry_price" in LOWER
    assert "o.entry_price<o.target_price" in LOWER
    assert "o.target_price<o.entry_price" in LOWER
    assert "o.entry_price<o.stop_price" in LOWER


def test_ready_queue_never_grants_order_authority():
    required = [
        "true as decision_support_only",
        "true as shadow_only",
        "false as live_money_claim_permitted",
        "false as execution_authority",
        "false as trade_permission",
        "false as production_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER


def test_watch_or_sub_five_r_cannot_enter_contract():
    assert "ready_setup_now" in LOWER
    assert "ready_limit_setup" in LOWER
    assert "s1_s10_shadow_candidate_5r" in LOWER
