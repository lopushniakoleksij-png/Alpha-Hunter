"""Synthetic-only tests for owner-approved third recovered PG17 catalog census.

Does not call real Docker, PostgreSQL, SQL, production or private Codespace.
"""
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

S = runpy.run_path(
    str(Path(__file__).resolve().parents[1] /
        "ops/local/p0_qa_recovered_third_catalog_census_v01.py"),
    run_name="p0_catalog_test"
)
Blocked = S["Blocked"]


def sample_struct(counts=S["BASE_COUNTS"], hashes=S["BASE_HASHES"]):
    return ["|".join(counts + hashes)] + sorted(S["BASE_EXT"])


def test_historical_nov8_census_exactly_matches_expected_historical_baseline():
    x = S["interpret_struct"](sample_struct())
    assert x["counts_match"]
    assert x["hashes_match"]
    assert x["extensions_match"]
    assert x["table_count"] == "128"
    assert x["trigger_count"] == "131"
    assert x["indexes"] == "360"


@pytest.mark.parametrize("change", ["count", "digest", "ext"])
def test_historical_census_mismatch_is_not_certified(change):
    rows = sample_struct()
    if change == "count":
        fields = rows[0].split("|")
        fields[0] = "0"
        rows[0] = "|".join(fields)
    elif change == "digest":
        fields = rows[0].split("|")
        fields[11] = "a" * 32
        rows[0] = "|".join(fields)
    else:
        rows.pop()
    r = S["interpret_struct"](rows)
    assert not all((r["counts_match"], r["hashes_match"], r["extensions_match"]))


@pytest.mark.parametrize("broken", [
    [], ["not|enough"], ["|".join(("x",) + S["BASE_COUNTS"][1:] + S["BASE_HASHES"])],
])
def test_invalid_catalog_shape_refused(broken):
    with pytest.raises(Blocked):
        S["interpret_struct"](broken)


def test_private_function_custody_matching_baseline():
    got = sorted(S["BASE_FUNC"]) + ["0|0|"]
    assert S["interpret_private"](got) == (True, True)


@pytest.mark.parametrize("data", [
    ["private|0|0|0|bad", "public|0|0|0|bad", "0|0|"],
    list(S["BASE_FUNC"]) + ["1|1|different"],
])
def test_private_function_mismatch_detected(data):
    assert S["interpret_private"](data) != (True, True)


def test_safe_single_third_mount_without_host_network_or_ports(tmp_path):
    args = S["run_args"](tmp_path / "pgdata", "sha256:" + "a" * 64)
    assert args[:3] == ["docker", "run", "-d"]
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[args.index("--entrypoint") + 1] == "/bin/sh"
    assert "--pull=never" in args
    mounts = [args[n+1] for n, flag in enumerate(args) if flag == "--mount"]
    assert len(mounts) == 1
    assert str(tmp_path / "pgdata") in mounts[0]
    assert "type=bind" in mounts[0]
    assert " hba_file=/tmp/p0_catalog_hba.conf" in args[-1]
    assert "local all postgres trust" in args[-1]
    assert "default_transaction_read_only=on" in args[-1]
    for bad in ("--publish", "-p", "--privileged", "--network=host",
                "--volumes-from", "--env-file", "docker.sock"):
        assert bad not in args


def test_psql_read_only_transaction_and_identity(monkeypatch):
    calls = []
    def fake_call(args, timeout=35, inp=None, fail=True):
        calls.append((args, inp))
        return SimpleNamespace(returncode=0, stdout="1\n")
    monkeypatch.setitem(S["psql_sql"].__globals__, "call", fake_call)
    assert S["psql_sql"]("postgres", "SELECT 1;") == ["1"]
    args, inp = calls[0]
    assert "BEGIN READ ONLY" in inp
    assert args[args.index("-d")+1] == "postgres"
    assert "default_transaction_read_only=on" in " ".join(args)
    with pytest.raises(Blocked):
        S["psql_sql"]("production_database", "SELECT 1;")


def test_read_only_default_mode_refuses_to_launch_server(monkeypatch):
    calls = []
    monkeypatch.setitem(S["main"].__globals__, "preflight",
                        lambda: (Path("/third/copy"), ("original", "stopped", 2, "sha", "image")))
    monkeypatch.setitem(S["main"].__globals__, "load_allowed_sql",
                        lambda name: "WITH safe AS (SELECT 1) SELECT * FROM safe;")
    monkeypatch.setitem(S["main"].__globals__, "call",
                        lambda *args, **kwargs: calls.append(args))
    assert S["main"]([]) == 0
    assert not calls


@pytest.mark.parametrize("args", [
    ["--approve-original"],
    ["--approve-third-catalog-census", "--force"],
    ["--approve-third-copy-recovery"],
])
def test_unrecognised_approval_refused_before_private_inspection(args):
    assert S["main"](args) == 2


def test_non_codespace_refused_before_docker(monkeypatch):
    monkeypatch.delenv("CODESPACES", raising=False)
    with pytest.raises(Blocked, match="Codespace"):
        S["preflight"]()
