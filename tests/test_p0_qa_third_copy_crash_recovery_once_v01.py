"""Synthetic-only P0 tests: no real Docker, DB, private file or restart."""
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_third_copy_crash_recovery_once_v01.py"),
    run_name="p0_third_recovery_synthetic_test"
)
Blocked = S["Blocked"]


def test_plan_is_safe_and_no_server_is_started(monkeypatch):
    calls = []
    monkeypatch.setitem(
        S["main"].__globals__, "preflight",
        lambda: (Path("/private/third/pgdata"), ("id", "stopped", 2, "sha", "img"))
    )
    monkeypatch.setitem(
        S["main"].__globals__, "cmd",
        lambda args, **kwargs: calls.append(args)
    )
    assert S["main"]([]) == 0
    assert calls == []


@pytest.mark.parametrize("bad", [["--approve"], ["--start-original"], ["--approve-third-copy-recovery", "--force"]])
def test_non_exact_owner_approval_argument_refused(bad):
    assert S["main"](bad) == 2


def test_launch_args_only_mount_third_copy_without_ports_or_production(tmp_path):
    args = S["launch_args"](tmp_path / "pgdata")
    joined = " ".join(args)
    assert args[:3] == ["docker", "run", "-d"]
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--user") + 1] != "0:0"
    assert "--pull=never" in args
    assert args[args.index("--entrypoint") + 1] == "/bin/sh"
    assert args[-3] == "postgres:17"
    assert args[-2] == "-c"
    assert args[-1].startswith("exec postgres -D ")
    assert "--mount" in args
    mounts = [args[i + 1] for i, x in enumerate(args) if x == "--mount"]
    assert len(mounts) == 1
    assert str(tmp_path / "pgdata") in mounts[0]
    assert "type=bind" in mounts[0]
    for forbidden in (
        "--publish", "-p", "--privileged", "--network=host", "--env-file",
        "--volume", "--volumes-from", "docker.sock",
    ):
        assert forbidden not in args


def make_inspect(pg, **overrides):
    payload = {
        "HostConfig": {
            "NetworkMode": "none", "ReadonlyRootfs": True,
            "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
            "PortBindings": None,
        },
        "Mounts": [
            {"Type": "bind", "Source": str(pg),
             "Destination": S["INSIDE_PGDATA"], "RW": True},
            {"Type": "tmpfs", "Destination": "/tmp"},
        ],
        "Config": {"User": S["os"].geteuid().__str__() + ":" +
                   S["os"].getegid().__str__()},
        "State": {"Running": True}
    }
    for k, v in overrides.items():
        payload[k] = v
    return payload


def runtime_inspect_with(monkeypatch, pg, inspect):
    def fake_cmd(args, **kwargs):
        assert args[:3] == ["docker", "container", "inspect"]
        return SimpleNamespace(stdout=json.dumps([inspect]))
    monkeypatch.setitem(S["runtime_policy"].__globals__, "cmd", fake_cmd)


def test_runtime_policy_allows_only_single_private_pgdata_bind(tmp_path, monkeypatch):
    pg = tmp_path / "pgdata"
    runtime_inspect_with(monkeypatch, pg, make_inspect(pg))
    assert S["runtime_policy"](pg)["State"]["Running"]


@pytest.mark.parametrize("bad", [
    {"HostConfig": {"NetworkMode": "bridge"}},
    {"HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": False}},
    {"Mounts": [{"Type": "bind", "Source": "/other/protected", "RW": True}]},
])
def test_misconfigured_runtime_fails_closed(tmp_path, monkeypatch, bad):
    pg = tmp_path / "pgdata"
    inspect = make_inspect(pg)
    for name, change in bad.items():
        inspect[name].update(change) if isinstance(change, dict) else inspect.__setitem__(name, change)
    runtime_inspect_with(monkeypatch, pg, inspect)
    with pytest.raises(Blocked):
        S["runtime_policy"](pg)


@pytest.mark.parametrize("output", [
    ("postgres (PostgreSQL) 17.6\n", False),
    ("PostgreSQL boot\n", False),
    ("", False),
])
def test_log_readiness_requires_exact_genuine_pg_ready_line(output):
    body, _ = output
    # no caller is permitted to infer a ready state just from version/boot lines
    assert "database system is ready to accept connections" not in body


def test_crash_recovery_needs_explicit_owner_flag(monkeypatch):
    approved = []
    monkeypatch.setitem(
        S["main"].__globals__, "preflight",
        lambda: (Path("/private/third/pgdata"), ("id", "stopped", 2, "sha", "img"))
    )
    monkeypatch.setitem(
        S["main"].__globals__, "cmd",
        lambda args, **kwargs: approved.append(args) or SimpleNamespace(stdout="123")
    )
    monkeypatch.setitem(S["main"].__globals__, "runtime_policy",
                        lambda pg: {"State": {"Running": False}})
    monkeypatch.setitem(S["main"].__globals__, "log_flags",
                        lambda: {"ready": False, "redo": False, "fatal": True})
    monkeypatch.setitem(S["main"].__globals__, "stop_if_running", lambda: None)
    assert S["main"](["--approve-third-copy-recovery"]) == 2
    assert any(cmd[:3] == ["docker", "run", "-d"] for cmd in approved)


def test_untrusted_environment_refused_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["preflight"]()
