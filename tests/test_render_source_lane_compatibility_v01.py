from pathlib import Path


SQL = Path("render_source_lane_compatibility_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_big_mover_prefers_canonical_cron_and_keeps_legacy_fallback():
    assert "in ('render_cron','render')" in LOWER
    assert "when p.payload->'validation_identity'->>'run_source'='render_cron'" in LOWER
    assert "canonical_render_cron_signal_features" in LOWER


def test_ready_queue_accepts_cron_but_excludes_web_manual_scans():
    assert "in ('render_cron','render','github_fast_discovery')" in LOWER
    assert "'render_web'" not in LOWER


def test_source_lane_compatibility_never_grants_execution():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER

    assert "false as trade_permission" in LOWER
    assert "false as execution_authority" in LOWER
    assert "'none'::text as order_path" in LOWER
