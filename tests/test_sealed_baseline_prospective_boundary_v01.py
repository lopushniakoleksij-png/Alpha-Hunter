from pathlib import Path


SQL = Path("sealed_baseline_prospective_boundary_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_baseline_must_be_at_or_after_preregistration():
    assert "p.collected_at_utc>=v_spec.preregistered_at_utc" in SQL
    assert "prospective_boundary_ok" in SQL
    assert "baseline_after_preregistration" in SQL


def test_patch_does_not_change_trading_authority():
    required = [
        "'shadow_only',true",
        "'trade_permission',false",
        "'production_promotion_permitted',false",
        "'order_path','none'",
    ]
    for marker in required:
        assert marker in LOWER

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
