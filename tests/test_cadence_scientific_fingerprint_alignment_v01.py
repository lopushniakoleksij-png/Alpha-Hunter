from pathlib import Path

SQL = Path(
    "ops/sql/cadence_scientific_fingerprint_alignment_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_cadence_uses_frozen_scientific_fingerprint_when_present():
    assert "frozen_scientific_fingerprint_sha256" in LOWER
    assert "scientific_fingerprint_sha256" in LOWER
    assert (
        "when s.frozen_scientific_fingerprint_sha256 is not null then"
        in LOWER
    )
    assert (
        "coalesce(s.scientific_fingerprint_sha256,'')"
        in LOWER
    )


def test_cadence_preserves_legacy_git_config_fallback():
    assert "else" in LOWER
    assert "s.git_commit=s.baseline_git_commit" in LOWER
    assert "s.config_sha256=s.baseline_config_sha256" in LOWER


def test_cadence_thresholds_are_not_changed():
    assert "c.minimum_interval_minutes" in LOWER
    assert "c.maximum_interval_minutes" in LOWER
    assert "fail_extra_scan_frequency" in LOWER
    assert "fail_scan_gap" in LOWER
    assert "fail_scan_stale" in LOWER


def test_cadence_patch_preserves_no_trade_authority():
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]:
        assert forbidden not in LOWER


def test_cadence_patch_stays_outside_scientific_fingerprint():
    path = Path("ops/sql/cadence_scientific_fingerprint_alignment_v01.sql")
    assert path.parent.as_posix() == "ops/sql"
    assert path.name not in [p.name for p in Path(".").glob("*.sql")]
