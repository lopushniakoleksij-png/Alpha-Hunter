from pathlib import Path

SQL = Path("big_mover_supabase_runtime.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_live_scoring_is_bound_to_render_canonical_snapshot():
    required = [
        "alpha_hunter_signal_features sf",
        "join public.alpha_hunter_snapshots p",
        "p.run_id=sf.run_id",
        "validation_identity",
        "run_source",
        "in ('render_cron','render')",
    ]
    for marker in required:
        assert marker in LOWER


def test_stale_feature_source_fails_closed():
    assert "interval '90 minutes'" in LOWER
    assert "canonical render_cron feature run is stale" in LOWER
    assert "no canonical render_cron/legacy render feature run available" in LOWER


def test_scoring_reports_canonical_source_contract():
    assert "canonical_render_cron_signal_features" in LOWER
    assert "feature_source_max_age_minutes" in LOWER


def test_big_mover_runtime_remains_shadow_only():
    assert "'shadow_only',true" in LOWER
    assert "'trade_permission',false" in LOWER
    assert "place_order" not in LOWER
    assert "cancel_order" not in LOWER
    assert "modify_order" not in LOWER
    assert "set_leverage" not in LOWER
