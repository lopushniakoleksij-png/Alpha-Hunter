from alpha_hunter.scientific_validation import evaluate_hypothesis


def spec(**overrides):
    row = {
        "hypothesis_id": "H_NET_R_6H_001",
        "metric": "net_r_6h",
        "expected_direction": "GREATER",
        "minimum_effect": 0.5,
        "min_samples_per_group": 10,
        "alpha": 0.05,
        "family_size": 1,
        "preregistered": True,
        "falsification_rule": "Reject if holdout TEST does not beat CONTROL by at least 0.5R.",
        "require_holdout": True,
    }
    row.update(overrides)
    return row


def observation(observation_id, group, value, **overrides):
    row = {
        "observation_id": observation_id,
        "group": group,
        "value": value,
        "holdout": True,
        "data_quality_ok": True,
        "shadow_only": True,
        "trade_permission": False,
    }
    row.update(overrides)
    return row


def strong_positive_sample():
    rows = []
    for idx in range(20):
        rows.append(observation(f"t{idx}", "TEST", 2.0 + idx * 0.01))
        rows.append(observation(f"c{idx}", "CONTROL", 0.2 + idx * 0.01))
    return rows


def test_supported_shadow_evidence_never_grants_production_permission():
    result = evaluate_hypothesis(
        spec(),
        strong_positive_sample(),
        bootstrap_iterations=500,
        permutation_iterations=500,
        seed=1,
    )
    assert result["status"] == "SUPPORTED_SHADOW"
    assert result["scientific_support"] is True
    assert result["decision"] == "RETAIN_FOR_REPLICATION"
    assert result["shadow_only"] is True
    assert result["trade_permission"] is False
    assert result["production_promotion_permitted"] is False
    assert result["replication_required"] is True


def test_hypothesis_must_be_preregistered():
    result = evaluate_hypothesis(spec(preregistered=False), strong_positive_sample())
    assert result["status"] == "INVALID_HYPOTHESIS"
    assert result["reason"] == "HYPOTHESIS_NOT_PREREGISTERED"
    assert result["trade_permission"] is False


def test_non_holdout_rows_cannot_satisfy_forward_evidence_requirement():
    rows = [
        observation(f"t{idx}", "TEST", 3.0, holdout=False)
        for idx in range(12)
    ] + [
        observation(f"c{idx}", "CONTROL", 0.0, holdout=False)
        for idx in range(12)
    ]
    result = evaluate_hypothesis(spec(), rows)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["excluded_non_holdout"] == 24
    assert result["scientific_support"] is False


def test_any_observation_outside_shadow_boundary_fails_closed():
    rows = strong_positive_sample()
    rows[0]["trade_permission"] = True
    result = evaluate_hypothesis(spec(), rows)
    assert result["status"] == "SAFETY_BOUNDARY_VIOLATION"
    assert result["production_promotion_permitted"] is False


def test_duplicate_observation_id_is_data_integrity_failure():
    rows = strong_positive_sample()
    rows[1]["observation_id"] = rows[0]["observation_id"]
    result = evaluate_hypothesis(spec(), rows)
    assert result["status"] == "DATA_INTEGRITY_FAILURE"
    assert result["scientific_support"] if "scientific_support" in result else True
    assert result["production_promotion_permitted"] is False


def test_multiple_testing_uses_bonferroni_adjustment():
    result = evaluate_hypothesis(
        spec(family_size=5),
        strong_positive_sample(),
        bootstrap_iterations=500,
        permutation_iterations=500,
        seed=2,
    )
    assert result["multiple_testing_method"] == "BONFERRONI"
    assert result["adjusted_alpha"] == 0.01
    assert result["production_promotion_permitted"] is False


def test_opposite_effect_can_falsify_preregistered_hypothesis():
    rows = []
    for idx in range(15):
        rows.append(observation(f"t{idx}", "TEST", -1.5 + idx * 0.01))
        rows.append(observation(f"c{idx}", "CONTROL", 0.5 + idx * 0.01))
    result = evaluate_hypothesis(
        spec(),
        rows,
        bootstrap_iterations=400,
        permutation_iterations=400,
        seed=3,
    )
    assert result["status"] == "FALSIFIED"
    assert result["decision"] == "REJECT_HYPOTHESIS"
    assert result["scientific_support"] is False


def test_low_resampling_configuration_is_rejected():
    result = evaluate_hypothesis(
        spec(),
        strong_positive_sample(),
        bootstrap_iterations=50,
        permutation_iterations=50,
    )
    assert result["status"] == "INVALID_ANALYSIS_CONFIG"
    assert result["scientific_support"] is False
