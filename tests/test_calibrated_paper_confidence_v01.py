from pathlib import Path

SQL = Path("ops/sql/calibrated_paper_confidence_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_calibration_is_backed_by_train_and_holdout():
    assert "58,39,12,8" in SQL
    assert "67.1428571428571" in SQL
    assert "55.5007161169824" in SQL
    assert "77.0012881732822" in SQL
    assert "'production_claim_permitted',false" in SQL


def test_stable_cohort_definition_is_frozen():
    for marker in [
        "'watch_short'",
        "'bearish'",
        "'neutral'",
        "'btc_neutral'",
        "'good'",
        "'volume_expansion',false",
    ]:
        assert marker in SQL


def test_execution_gate_keeps_rr5_and_short_geometry():
    assert "new.reward_risk<p.minimum_reward_risk" in SQL
    assert "new.target_price<new.planned_entry_price" in SQL
    assert "new.planned_entry_price<new.stop_price" in SQL
    assert "new.direction<>'short'" in SQL


def test_forward_only_uses_new_frozen_decisions():
    assert "after insert on public.alpha_hunter_execution_decision_freezes_v01" in SQL
    assert "no historical freeze is backfilled" in SQL


def test_old_raw_confidence_gate_is_paused():
    assert "paper-prod-65-70-rr5-v01" in SQL
    assert "set status='paused'" in SQL


def test_no_live_exchange_authority():
    for marker in [
        "paper_only boolean not null default true",
        "live_order_authority boolean not null default false",
        "live_exchange_order_sent boolean not null default false",
        "trade_permission boolean not null default false",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "live_exchange_order_sent=true",
        "trade_permission=true",
    ]:
        assert forbidden not in SQL
