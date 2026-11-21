#!/usr/bin/env python3
"""B2/B3 private QA identity census — read-only and fail-closed.

This is an *inventory*, not a restore, benchmark or schema-parity certificate.
The older Stage 7 physical TEMPLATE reference and the full-fingerprint
restoration target are different named databases and MUST NOT be conflated.
Run only in the existing authorised private Codespace, never in Actions.
No raw private SQL, credentials, paths or logs are printed.
"""
import os
import re
import subprocess
import sys

BRANCH = "fix/supabase-write-timeout-qa"
CONTAINER = "alpha-hunter-private-postgres17-qa"
IMAGE = "public.ecr.aws/supabase/postgres:17.6.1.156"
REFERENCE_DB = "ah_authentic_schema_20261110"
RESTORED_DB = "alpha_hunter_private_qa"


class Blocked(Exception):
    pass


def command(args, *, payload=None, timeout=20):
    try:
        done = subprocess.run(
            args, input=payload, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("authorised local QA tool unavailable") from None
    if done.returncode != 0:
        raise Blocked("local QA inspection failed; private details withheld")
    return done.stdout.strip()


def sql(db, query):
    if db not in ("postgres", REFERENCE_DB, RESTORED_DB):
        raise Blocked("unexpected QA database name")
    return command([
        "docker", "exec", "-i",
        "-e", "PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=10000",
        CONTAINER, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
        "-U", "postgres", "-h", "/var/run/postgresql", "-d", db,
    ], payload=query, timeout=15)


def classify_inventory(rows):
    """Interpret only two expected local database labels; no path or SQL output."""
    observed = set(rows.splitlines()) if rows else set()
    allowed = {REFERENCE_DB, RESTORED_DB}
    if not observed.issubset(allowed):
        raise Blocked("unexpected local PostgreSQL identity inventory")
    return REFERENCE_DB in observed, RESTORED_DB in observed


def verify_db_identity(db):
    output = sql(db, (
        "SELECT current_database() || '|' || current_user || '|' || "
        "current_setting('server_version_num');"
    ))
    if not re.fullmatch(re.escape(db) + r"\|postgres\|17\d{4}", output):
        raise Blocked("private PostgreSQL database identity mismatch")


def main():
    print("QA_IDENTITY_MODE=READ_ONLY")
    print("QA_DATABASE_CHANGES=NONE")
    print("QA_RESTART_AUTHORIZATION=NOT_GRANTED")
    print("PRODUCTION_RELEASE=NO_GO")
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        print("QA_IDENTITY_RESULT=BLOCKED_ENV")
        return 2
    try:
        if command(["git", "branch", "--show-current"]) != BRANCH:
            raise Blocked("wrong private repair branch")
        status = command([
            "docker", "inspect", "-f",
            "{{.Config.Image}}|{{.Path}}|{{.HostConfig.RestartPolicy.Name}}|"
            "{{.State.Running}}|{{.HostConfig.NetworkMode}}",
            CONTAINER
        ])
        if status != IMAGE + "|docker-entrypoint.sh|no|true|none":
            raise Blocked("stopped, replaced, or nonisolated private QA container")
        print("QA_CONTAINER_IDENTITY=PASS")
        inventory = sql("postgres", (
            "SELECT datname FROM pg_database WHERE datname IN "
            "('ah_authentic_schema_20261110','alpha_hunter_private_qa') "
            "ORDER BY datname;"
        ))
        reference_present, restored_present = classify_inventory(inventory)
        print("QA_STAGE7_REFERENCE_PRESENT=" + ("YES" if reference_present else "NO"))
        print("QA_FULL_PARITY_TARGET_PRESENT=" + ("YES" if restored_present else "NO"))
        for name, present in (
            (REFERENCE_DB, reference_present), (RESTORED_DB, restored_present)
        ):
            if present:
                verify_db_identity(name)
        if not restored_present:
            print("QA_IDENTITY_RESULT=BLOCKED_RESTORED_TARGET_MISSING")
            print("QA_SCHEMA_PARITY=NOT_VERIFIED")
            return 2
        print("QA_IDENTITY_RESULT=INVENTORY_COMPLETE")
        print("QA_SCHEMA_PARITY=NOT_VERIFIED")
        print("QA_INDEPENDENT_DBA_SIGNOFF=PENDING")
        return 0
    except Blocked:
        print("QA_IDENTITY_RESULT=BLOCKED_PRIVATE_REVIEW")
        print("QA_SCHEMA_PARITY=NOT_VERIFIED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
