"""Synthetic-only tests for P0 offline PostgreSQL 17 utility/network probe."""
from pathlib import Path
import runpy
import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_offline_runtime_network_probe_v01.py"),
    run_name="offline_probe_unit_test"
)
Blocked = S["Blocked"]


def test_no_server_and_no_mounts_in_ephemeral_utility_command():
    args = S["offline_command"]()
    assert args[:3] == ["docker", "run", "--rm"]
    assert "--pull=never" in args
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--user") + 1] == "65534:65534"
    assert "--entrypoint" in args
    assert args[-3] == "/bin/sh"
    assert args[-2] == "-c"
    assert "postgres --version" in args[-1]
    assert "basename" in args[-1]
    assert "pg_ctl" not in " ".join(args)
    for dangerous in ("--mount", "-v", "--volume", "--publish", "-p", "--privileged"):
        assert dangerous not in args


@pytest.mark.parametrize("output", [
    "postgres (PostgreSQL) 17.6\nQA_LOOPBACK_ONLY=YES\n",
    "postgres (PostgreSQL) 17.10\nQA_LOOPBACK_ONLY=YES\n",
    "postgres (PostgreSQL) 17\nQA_LOOPBACK_ONLY=YES\n",
])
def test_valid_offline_pg17_and_loopback_only_pass(output):
    assert S["parse_probe"](output)


@pytest.mark.parametrize("output", [
    "postgres (PostgreSQL) 16.10\nQA_LOOPBACK_ONLY=YES\n",
    "postgres (PostgreSQL) 18.0\nQA_LOOPBACK_ONLY=YES\n",
    "postgres (PostgreSQL) 17.6\n",
    "postgres (PostgreSQL) 17.6\nQA_LOOPBACK_ONLY=NO\n",
    "postgres (PostgreSQL) 17.6\nQA_LOOPBACK_ONLY=YES\nQA_LOOPBACK_ONLY=YES\n",
    "",
])
def test_version_or_loopback_failure_blocks(output):
    with pytest.raises(Blocked):
        S["parse_probe"](output)


def test_outside_original_codespace_refuses_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["verify_custody"]()
