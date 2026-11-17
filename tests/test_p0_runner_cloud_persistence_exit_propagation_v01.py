"""P0 regression: cloud-write failures must halt the canonical launcher.

Loads the actual alpha_hunter.collector.cloud_persistence_exit_code helper
and run.py run() AST into an offline namespace. No real scanner is invoked,
no network calls occur, and no credentials or production state are read.
"""
import ast
from contextlib import contextmanager
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "alpha_hunter" / "collector.py"
RUNNER = ROOT / "run.py"


def extract_fn(path, name, namespace):
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(path))
    fn = next(
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    isolated = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(isolated, str(path), "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize(
    ("persist_enabled", "cloud_status", "expected_exit"),
    [
        (True, "FAILED: HTTP 500 SQLSTATE 57014 synthetic statement timeout", 2),
        (True, "FAILED: synthetic 15-second client read timeout", 2),
        (True, "NOT_CONFIGURED", 2),
        (True, "UNVERIFIED", 2),
        (False, "FAILED: offline storage disabled", 0),
    ],
)
def test_failed_configured_scan_never_reaches_secondary_persistence(
    persist_enabled, cloud_status, expected_exit
):
    cloud_exit = extract_fn(
        COLLECTOR, "cloud_persistence_exit_code", {}
    )
    exit_code = cloud_exit(enabled=persist_enabled, status=cloud_status)
    assert exit_code == expected_exit

    if exit_code == 0:
        # A successful/disabled status permits the normal path: not part of
        # this test's fail-closed short-circuit assertion.
        return

    calls = []

    @contextmanager
    def capture():
        calls.append("capture_scanner_calls")
        yield {}

    def collector_main():
        calls.append("collector_main")
        return exit_code

    def forbidden(*_args, **_kwargs):
        calls.append("FORBIDDEN_DOWNSTREAM_PERSISTENCE")
        raise AssertionError("cloud write failed; no downstream data write allowed")

    namespace = {
        "capture_existing_universe_calls": capture,
        "main": collector_main,
        "load_config": forbidden,
        "SupabaseConfig": type("Guard", (), {"from_environment": forbidden}),
        "build_rows_from_existing_scan": forbidden,
        "persist_rows": forbidden,
        "persist_account_ledger": forbidden,
        "persist_fill_traceability": forbidden,
    }
    actual_run = extract_fn(RUNNER, "run", namespace)
    assert actual_run() == exit_code
    assert calls == ["capture_scanner_calls", "collector_main"]


def test_entrypoint_exits_with_run_status():
    source = RUNNER.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(RUNNER))
    last = module.body[-1]
    assert isinstance(last, ast.If)
    call = last.body[0]
    assert isinstance(call, ast.Raise)
    assert isinstance(call.exc, ast.Call)
    assert isinstance(call.exc.func, ast.Name)
    assert call.exc.func.id == "SystemExit"
    assert isinstance(call.exc.args[0], ast.Call)
    assert isinstance(call.exc.args[0].func, ast.Name)
    assert call.exc.args[0].func.id == "run"
