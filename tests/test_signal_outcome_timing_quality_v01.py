from pathlib import Path

SQL = Path("ops/sql/signal_outcome_timing_quality_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_quality_uses_exact_due_timestamp():
    assert "s.detected_at_utc+make_interval(hours=>o.horizon_hours)" in SQL


def test_30_minute_bounded_evidence_rule():
    assert "bounded_within_30m" in SQL
    assert "interval '30 minutes'" in SQL
    assert "bounded_endpoint_evidence_permitted" in SQL


def test_exact_horizon_claim_is_never_granted():
    assert "false as exact_horizon_claim_permitted" in SQL


def test_legacy_rows_are_preserved():
    assert "no legacy outcome row is updated or deleted" in SQL
    assert "delete from public.alpha_hunter_signal_outcomes" not in SQL
    assert "update public.alpha_hunter_signal_outcomes" not in SQL


def test_private_security_invoker_views():
    assert "security_invoker=true" in SQL
    assert "revoke all on private.alpha_hunter_signal_outcome_timing_quality_v01" in SQL
    assert "grant select on private.alpha_hunter_signal_outcome_timing_quality_v01" in SQL


def test_no_trade_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL
