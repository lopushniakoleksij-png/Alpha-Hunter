import app as dashboard_app


def test_build_identity_prefers_render_runtime_metadata(monkeypatch):
    monkeypatch.setenv("ALPHA_HUNTER_VERSION", "7.2-test")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "1234567890abcdef")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")
    monkeypatch.setenv("RENDER_GIT_REPO_SLUG", "owner/repo")
    monkeypatch.setenv("RENDER_SERVICE_NAME", "alpha-hunter")
    monkeypatch.setenv("RENDER_INSTANCE_ID", "srv-instance")
    monkeypatch.setenv("ALPHA_HUNTER_DEPLOYED_AT_UTC", "2026-09-21T22:30:00+00:00")

    identity = dashboard_app.build_identity()

    assert identity["version"] == dashboard_app.APP_VERSION
    assert identity["git_commit"] == "1234567890abcdef"
    assert identity["git_commit_short"] == "1234567"
    assert identity["git_branch"] == "main"
    assert identity["git_repo"] == "owner/repo"
    assert identity["render_service"] == "alpha-hunter"
    assert identity["render_instance_id"] == "srv-instance"
    assert identity["deployed_at_utc"] == "2026-09-21T22:30:00+00:00"
    assert identity["deployed_at_source"] == "deployment_environment"


def test_build_identity_falls_back_to_process_start(monkeypatch):
    for key in (
        "RENDER_GIT_COMMIT",
        "GIT_COMMIT",
        "RENDER_GIT_BRANCH",
        "GIT_BRANCH",
        "RENDER_GIT_REPO_SLUG",
        "RENDER_SERVICE_NAME",
        "RENDER_INSTANCE_ID",
        "ALPHA_HUNTER_DEPLOYED_AT_UTC",
    ):
        monkeypatch.delenv(key, raising=False)

    identity = dashboard_app.build_identity()

    assert identity["git_commit"] == "unknown"
    assert identity["git_commit_short"] == "unknown"
    assert identity["deployed_at_utc"] == dashboard_app.SERVICE_STARTED_AT_UTC
    assert identity["deployed_at_source"] == "process_start_fallback"


def test_api_build_exposes_identity(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")
    monkeypatch.setenv("RENDER_GIT_BRANCH", "main")

    client = dashboard_app.app.test_client()
    response = client.get("/api/build")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["version"] == dashboard_app.APP_VERSION
    assert payload["git_commit"] == "abcdef1234567890"
    assert payload["git_commit_short"] == "abcdef1"
    assert payload["git_branch"] == "main"


def test_health_embeds_build_identity(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "fedcba9876543210")

    client = dashboard_app.app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["version"] == dashboard_app.APP_VERSION
    assert payload["build"]["git_commit"] == "fedcba9876543210"
