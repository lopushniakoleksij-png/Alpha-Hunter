from pathlib import Path

WORKFLOW = Path(
    ".github/workflows/alpha-hunter-realtime-profitability-test.yml"
).read_text(encoding="utf-8")


def test_profitability_evaluator_is_attempted_after_scanner_failure():
    required = [
        "id: evidence_credentials",
        "id: live_scan",
        "continue-on-error: true",
        "always() && steps.evidence_credentials.outcome == 'success'",
        "run: python test_engine_job.py",
        "Preserve scanner failure status",
        "steps.live_scan.outcome == 'failure'",
    ]
    for marker in required:
        assert marker in WORKFLOW


def test_profitability_workflow_keeps_scanner_failure_visible():
    preserve = WORKFLOW.split("- name: Preserve scanner failure status", 1)[1]
    assert "exit 1" in preserve
    assert "evaluator was still attempted" in preserve


def test_profitability_workflow_remains_read_only_and_paper_only():
    assert "Order execution: disabled" in WORKFLOW
    assert '\"trade_permission\": False' in WORKFLOW
    assert '\"paper_only\": True' in WORKFLOW
    assert '\"order_path\": \"NONE\"' in WORKFLOW
