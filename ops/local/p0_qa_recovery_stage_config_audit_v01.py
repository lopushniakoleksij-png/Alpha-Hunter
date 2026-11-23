#!/usr/bin/env python3
"""P0 A3: read-only security audit of an owner-private staged PG17 copy.

No PostgreSQL server startup, Docker run, SQL, production connection,
PID deletion or private content disclosure. Reads only configuration metadata,
never prints values/paths/credentials. Live original QA stays STOPPED.

The parser is deliberately conservative; this is a safety inventory, NOT an
approval to run PostgreSQL. Recovery requires a separate owner-approved,
networkless, no-cron plan using a THIRD disposable copy.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / ".alpha-hunter-private-dbqa"
ORIGINAL = "alpha-hunter-private-postgres17-qa"
BRANCH = "fix/supabase-write-timeout-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
MAX_CONFIG = 2 * 1024 * 1024

# Key names are non-secret. Never print config values or file contents.
RISK_KEYS = frozenset((
    "shared_preload_libraries", "archive_mode", "archive_command",
    "archive_library", "restore_command", "recovery_end_command",
    "primary_conninfo", "primary_slot_name", "synchronous_standby_names",
    "listen_addresses", "port", "unix_socket_directories",
    "ssl", "ssl_cert_file", "ssl_key_file", "data_directory",
    "config_file", "hba_file", "ident_file",
    "external_pid_file", "logging_collector", "log_directory",
    "cron.database_name", "cron.launch_active_jobs", "cron.host",
    "cron.use_background_workers", "wal_level",
    "include", "include_if_exists", "include_dir",
))
INCLUDE_KEYS = frozenset(("include", "include_if_exists", "include_dir"))
SENSITIVE_KEYS = frozenset((
    "primary_conninfo", "primary_slot_name", "archive_command",
    "restore_command", "recovery_end_command",
    "ssl_key_file",
))


class Blocked(Exception):
    pass


def invoke(args):
    try:
        return subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, check=True, timeout=12,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise Blocked("protected local metadata lookup failed") from None


def guard():
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        raise Blocked("existing authorised Codespace required")
    if invoke(["git", "branch", "--show-current"]).strip() != BRANCH:
        raise Blocked("original isolated repair branch required")
    if ROOT.is_symlink() or not ROOT.is_dir() or ROOT.stat().st_mode & 0o777 != 0o700:
        raise Blocked("private recovery root unsafe")
    info = json.loads(invoke(["docker", "inspect", ORIGINAL]))[0]
    if (info.get("Config", {}).get("Image") != IMAGE
            or info.get("Path") != "docker-entrypoint.sh"
            or info.get("HostConfig", {}).get("NetworkMode") != "none"
            or info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name") not in ("no", "")
            or info.get("State", {}).get("Status") != "exited"
            or info.get("State", {}).get("Running")):
        raise Blocked("original container identity or offline status changed")
    return info


def staged_directory():
    roots = sorted(ROOT.glob("p0_recovery_stage_*"))
    if len(roots) != 1:
        raise Blocked("expected one original staged recovery copy")
    folder = roots[0]
    pgdata = folder / "pgdata"
    for d in (folder, pgdata):
        if d.is_symlink() or not d.is_dir() or d.stat().st_mode & 0o777 != 0o700:
            raise Blocked("staged directory missing or permissions unsafe")
    if (pgdata / "PG_VERSION").read_bytes().strip() != b"17":
        raise Blocked("staged cluster major version mismatch")
    if not (pgdata / "global" / "pg_control").is_file():
        raise Blocked("staged control file missing")
    return pgdata


def parse_settings(text):
    """Find noncommented configuration keys. Never return values.

    PostgreSQL supports quoted keys and include directives; suspicious
    entries are retained for manual review. This is not a PostgreSQL parser.
    """
    keys = set()
    ambiguous = 0
    for line in text.splitlines():
        t = line.lstrip()
        if not t or t.startswith("#"):
            continue
        # No need to parse values, which may contain secrets.
        m = re.match(r'^"?([A-Za-z_][A-Za-z_0-9.]*)"?\s*=', t)
        if m:
            keys.add(m.group(1).lower())
        else:
            ambiguous += 1
    return keys, ambiguous


def audit(pgdata, original):
    configs = ("postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf")
    present = []
    keys = set()
    ambiguous = 0
    for name in configs:
        file = pgdata / name
        if file.is_symlink():
            raise Blocked("staged configuration symlink is not safe")
        if file.exists():
            if not file.is_file() or file.stat().st_size > MAX_CONFIG:
                raise Blocked("staged configuration type or size unexpected")
            present.append(name)
            if name.startswith("postgresql"):
                scanned, unparsed = parse_settings(file.read_text(encoding="utf-8"))
                keys |= scanned
                ambiguous += unparsed

    tbl = pgdata / "pg_tblspc"
    if tbl.is_symlink():
        raise Blocked("tablespace directory is a symlink")
    tablespace_count = len(list(tbl.iterdir())) if tbl.is_dir() else -1
    if tablespace_count != 0:
        raise Blocked("external tablespace references require separate custody review")
    pid = pgdata / "postmaster.pid"
    if not pid.is_file() or pid.is_symlink():
        raise Blocked("expected inherited stale postmaster PID is missing or unsafe")
    if pid.stat().st_size < 1 or pid.stat().st_size > 8192:
        raise Blocked("unexpected inherited PID-file size")
    cmd = original.get("Config", {}).get("Cmd") or []
    if not isinstance(cmd, list):
        raise Blocked("original command line metadata invalid")
    return {
        "config_count": len(present),
        "risk_keys": sorted(keys & RISK_KEYS),
        "includes": sorted(keys & INCLUDE_KEYS),
        "sensitive": sorted(keys & SENSITIVE_KEYS),
        "ambiguous": ambiguous,
        "tablespace_count": tablespace_count,
        "pid_present": True,
        "original_cmd_override": any("config_file" in str(a) or "data_directory" in str(a)
                                     for a in cmd),
        "auto_config_present": "postgresql.auto.conf" in present,
    }


def main():
    print("QA_CONFIG_AUDIT=OFFLINE_READ_ONLY_STAGED_COPY")
    print("QA_PRODUCTION_DB_CONNECTION=NONE")
    print("QA_POSTGRES_SERVER_START=NO")
    print("QA_ORIGINAL_CONTAINER_RESTART=NO")
    try:
        before = guard()
        pgdata = staged_directory()
        result = audit(pgdata, before)
        after = guard()
        if before.get("Id") != after.get("Id") or (
            before.get("State", {}).get("FinishedAt") !=
            after.get("State", {}).get("FinishedAt")
        ):
            raise Blocked("original container stopped identity changed during check")
        print("QA_STAGED_CONFIG_FILES_PRESENT=" + str(result["config_count"]))
        print("QA_STAGED_AUTO_CONF_PRESENT=" + ("YES" if result["auto_config_present"] else "NO"))
        print("QA_STAGED_SETTINGS_RISK_KEY_COUNT=" + str(len(result["risk_keys"])))
        print("QA_STAGED_SETTINGS_RISK_KEYS=" + ",".join(result["risk_keys"]))
        print("QA_STAGED_INCLUDE_DIRECTIVES=" + (
            ",".join(result["includes"]) if result["includes"] else "NONE_SEEN"))
        print("QA_STAGED_SENSITIVE_SETTING_KEYS=" + (
            ",".join(result["sensitive"]) if result["sensitive"] else "NONE_SEEN"))
        print("QA_STAGED_CONFIG_UNPARSED_LINES=" + str(result["ambiguous"]))
        print("QA_TABLESPACE_ENTRIES=" + str(result["tablespace_count"]))
        print("QA_STALE_POSTMASTER_PID=PRESENT_UNCHANGED")
        print("QA_ORIGINAL_COMMAND_CONFIG_OVERRIDE=" + (
            "PRESENT_REVIEW" if result["original_cmd_override"] else "NOT_IN_CMD"))
        print("QA_CONFIG_VALUES_OR_SECRETS_PRINTED=NO")
        print("QA_ISOLATED_POSTGRES_RUNTIME_START=NOT_AUTHORISED")
        print("QA_NEXT_GATE=REVIEW_NO_NETWORK_NO_CRON_THIRD_COPY_CRASH_RECOVERY_PLAN")
        return 0
    except (Blocked, UnicodeError, ValueError, KeyError, TypeError, OSError) as e:
        print("QA_CONFIG_AUDIT_RESULT=BLOCKED_" + (
            str(e).upper().replace(" ", "_")[:90] if isinstance(e, Blocked)
            else "PRIVATE_CONFIG_INSPECTION_ERROR"))
        print("QA_ORIGINAL_CONTAINER_RESTART=NO")
        return 2


if __name__ == "__main__":
    sys.exit(main())
