"""P0 regression: configured Supabase persistence failures must fail the cron job.

Pure offline tests: no network, database, scanner execution, real orders or
production mutations. Isolates the helper via AST to avoid importing collectors.
"""
import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "alpha_hunter" / "collector.py"


def code_fn():
    tree = ast.parse(COLLECTOR.read_text(encoding="utf-8"), filename=str(COLLECTOR))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "cloud_persistence_exit_code"
    )
    isolated = ast.fix_missing_locations(ast.Module(body=[helper], type_ignores=[]))
    scope = {}
    exec(compile(isolated, str(COLLECTOR), "exec"), scope)
    return scope["cloud_persistence_exit_code"]


@pytest.mark.parametrize(
    ("enabled", "status", "expected"),
    [
        (False, "DISABLED", 0),
        (False, "FAILED: synthetic timeout", 0),
        (True, "SAVED", 0),
        (True, "NOT_CONFIGURED", 2),
        (True, "DISABLED", 2),
        (True, "FAILED: HTTP 500 57014 synthetic statement timeout", 2),
        (True, "FAILED: synthetic 15s client read timeout", 2),
        (True, "UNVERIFIED", 2),
    ],
)
def test_persistence_exit_contract(enabled, status, expected):
    assert code_fn()(enabled=enabled, status=status) == expected


def test_collector_main_propagates_cloud_result_and_does_not_return_zero():
    tree = ast.parse(COLLECTOR.read_text(encoding="utf-8"), filename=str(COLLECTOR))
    main = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    final = main.body[-1]
    assert isinstance(final, ast.Return)
    assert isinstance(final.value, ast.Call)
    assert isinstance(final.value.func, ast.Name)
    assert final.value.func.id == "cloud_persistence_exit_code"
    keyword_names = {kw.arg for kw in final.value.keywords}
    assert keyword_names == {"enabled", "status"}

    # The collector must log its failure but allow the nonzero result to
    # propagate back to run.py / hourly.py and therefore the Render cron job.
    source = ast.get_source_segment(COLLECTOR.read_text(encoding="utf-8"), main)
    assert 'cloud_status = (' in source
    assert 'f"FAILED: {exc}"' in source
    assert 'cloud_status = "SAVED"' in source
