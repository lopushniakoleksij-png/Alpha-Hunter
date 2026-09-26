from pathlib import Path


SQL = Path("profitability_sample_integrity_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_sample_integrity_is_post_baseline_only():
    required = [
        "post_baseline_episode_count",
        "post_baseline_candidate_episode_count",
        "post_baseline_24h_outcome_rows",
        "post_baseline_24h_economic_eligible_rows",
        "post_baseline_episodes_only",
    ]
    for marker in required:
        assert marker in LOWER


def test_left_censored_candidates_are_excluded_from_economic_sample():
    assert "left_censored_candidate_observation_count" in LOWER
    assert "left_censored_24h_outcome_rows" in LOWER
    assert "left_censored_candidates_are_diagnostic_only" in LOWER
    assert "coalesce(o.first_seen_at_utc,o.observed_at_utc)>=s.started_at_utc" in LOWER


def test_sample_integrity_rejects_prebaseline_contamination_and_duplicates():
    required = [
        "contaminated_pre_baseline_economics_rows",
        "duplicate_economics_episode_rows",
        "duplicate_24h_outcome_rows",
        "fail_pre_baseline_contamination",
        "fail_duplicate_sample_rows",
        "sealed_sample_integrity_ok",
    ]
    for marker in required:
        assert marker in LOWER


def test_audit_cannot_change_profitability_or_trading_authority():
    required = [
        "true as audit_only",
        "true as paper_only",
        "false as profitability_rule_change_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
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
