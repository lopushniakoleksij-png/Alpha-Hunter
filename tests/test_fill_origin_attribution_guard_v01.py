from pathlib import Path

SQL = Path("fill_origin_attribution_guard_v01.sql").read_text(encoding="utf-8")
TRACE = Path("alpha_hunter/traceability.py").read_text(encoding="utf-8")
JOB = Path("traceability_job.py").read_text(encoding="utf-8")


def test_manual_ui_sources_are_explicitly_external():
    for source in ("IOS", "ANDROID", "WEB", "APP", "MOBILE"):
        assert f"'{source}'" in SQL

    assert "HUMAN_UI_EXTERNAL" in SQL
    assert "API_ORIGIN_UNVERIFIED" in SQL
    assert "UNKNOWN_ORIGIN" in SQL
    assert "NON_API_EXTERNAL" in SQL


def test_api_origin_is_only_heuristic_eligible_not_verified():
    assert "heuristic_signal_attribution_eligible" in SQL
    assert "false as verified_alpha_hunter_execution" in SQL
    assert "false as alpha_hunter_execution_claim_permitted" in SQL
    assert "DETERMINISTIC_SYSTEM_ORDER_IDENTITY_NOT_YET_BOUND" in SQL

    assert "fill_origin_class" in TRACE
    assert "heuristic_fill_attribution_eligible" in TRACE
    assert 'return fill_origin_class(fill) == "API_ORIGIN_UNVERIFIED"' in TRACE


def test_traceability_excludes_non_api_before_heuristic_matching():
    attach = TRACE.split("def attach_fill_matches(", 1)[1].split(
        "def unlinked_open_like_fills(", 1
    )[0]

    origin_guard = attach.index(
        "if not heuristic_fill_attribution_eligible(fill):"
    )
    direction = attach.index("direction = _opening_fill_direction(fill)")
    assert origin_guard < direction
    assert "HEURISTIC_API_ORIGIN_FILL_MATCH" in attach


def test_unlinked_traceability_scope_is_api_origin_only():
    assert "API_ORIGIN_HEURISTIC_ELIGIBLE_ONLY" in TRACE
    assert "external_non_attributable_open_like_fill_count" in TRACE
    assert "HUMAN_UI_EXCLUDED_API_ORIGIN_HEURISTIC_ONLY" in TRACE
    assert "Unlinked API-origin open-like fills:" in JOB
    assert "External/non-attributable open-like fills:" in JOB


def test_origin_views_are_service_role_only_and_read_only():
    lower = SQL.lower()

    for marker in (
        "revoke all on public.alpha_hunter_fill_origin_attribution_v01",
        "revoke all on public.alpha_hunter_fill_origin_attribution_status_v01",
        "grant select on public.alpha_hunter_fill_origin_attribution_v01",
        "grant select on public.alpha_hunter_fill_origin_attribution_status_v01",
        "to service_role",
    ):
        assert marker in lower

    for forbidden in (
        "insert into",
        "update public.",
        "delete from",
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
    ):
        assert forbidden not in lower


def test_traceability_version_marks_new_attribution_semantics():
    assert 'TRACEABILITY_VERSION = "1.3"' in TRACE
