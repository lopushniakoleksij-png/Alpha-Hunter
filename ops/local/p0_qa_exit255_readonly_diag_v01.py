#!/usr/bin/env python3
"""Read-only QA container exit-255 investigation. No SQL, secrets, or restart."""
from datetime import datetime, timedelta, timezone
import collections
import json
import os
import re
import subprocess
import sys

N = "alpha-hunter-private-postgres17-qa"
BRANCH = "fix/supabase-write-timeout-qa"
IDENT = "public.ecr.aws/supabase/postgres:17.6.1.156|docker-entrypoint.sh|none|no"
SIGNALS = {
    "FATAL": r"\bfatal:",
    "PANIC": r"\bpanic:",
    "PERMISSION_DENIED": r"permission denied",
    "SHUTDOWN_REQUEST": r"shutdown request",
    "NORMAL_SHUTDOWN": r"database system is shut down",
    "DISK_FULL": r"no space left",
    "OUT_OF_MEMORY": r"out of memory",
    "SEGFAULT": r"segmentation fault",
}
ACTIONS = ("create", "start", "stop", "kill", "die", "destroy", "oom", "restart")


class Denied(Exception):
    pass


def command(args, *, timeout=30, include_stderr=False):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise Denied("read-only Docker inspection failed; stderr withheld")
    return p.stdout + p.stderr if include_stderr else p.stdout


def classify_logs(text):
    lowered = text.lower()
    return {k: len(re.findall(p, lowered)) for k, p in SIGNALS.items()}


def classify_events(text):
    found = collections.Counter()
    for line in text.splitlines():
        try:
            event = json.loads(line)
            key = str(event.get("Action", event.get("status", ""))).lower()
            if key in ACTIONS:
                found[key] += 1
        except (ValueError, TypeError):
            pass
    return found


def main():
    print("QA_A1_MODE=READ_ONLY")
    print("QA_RESTART_AUTHORIZATION=NOT_GRANTED")
    print("PRODUCTION_RELEASE=NO_GO")
    if os.environ.get("CODESPACES") != "true" or os.environ.get("GITHUB_ACTIONS") == "true":
        print("QA_A1_RESULT=BLOCKED_ENV")
        return 2
    try:
        if command(["git", "branch", "--show-current"]).strip() != BRANCH:
            raise Denied("wrong repair branch")
        ident = command([
            "docker", "inspect", "-f",
            "{{.Config.Image}}|{{.Path}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.RestartPolicy.Name}}", N
        ]).strip()
        if ident != IDENT:
            raise Denied("QA container identity mismatch")
        print("QA_IDENTITY=PASS")
        state = json.loads(command(["docker", "inspect", "-f", "{{json .State}}", N]))
        print("QA_RUNNING=" + ("YES" if state.get("Running") else "NO"))
        print("QA_EXIT_CODE=" + str(state.get("ExitCode", "UNKNOWN")))
        print("QA_OOM_FLAG=" + ("YES" if state.get("OOMKilled") else "NO"))
        print("QA_STATE_ERROR=" + ("PRESENT" if state.get("Error") else "NONE"))
        if state.get("Running"):
            print("QA_A1_RESULT=RUNNING_VERIFY_REFERENCE")
            return 0
        if state.get("Status") != "exited":
            raise Denied("unexpected QA state")
        started = datetime.fromisoformat(state["StartedAt"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(state["FinishedAt"].replace("Z", "+00:00"))
        if finished < started or finished.year < 2026:
            raise Denied("invalid stop timing")
        print("QA_STARTED_UTC=" + started.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print("QA_FINISHED_UTC=" + finished.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        mounts = json.loads(command(["docker", "inspect", "-f", "{{json .Mounts}}", N]))
        print("QA_MOUNT_COUNT=" + str(len(mounts)))
        print("QA_MOUNT_TYPES=" + ",".join(sorted({str(m.get("Type", "")).upper() for m in mounts})))
        # Never print mount paths, names, raw logs, SQL or environment variables.
        begin = (finished - timedelta(minutes=3)).isoformat()
        end = (finished + timedelta(seconds=1)).isoformat()
        try:
            logs = command([
                "docker", "logs", "--timestamps", "--tail", "500",
                "--since", begin, "--until", end, N
            ], include_stderr=True)
            for label, count in classify_logs(logs).items():
                print("QA_FINAL_" + label + "=" + str(count))
            print("QA_FINAL_LOG_CHECK=PASS")
        except (Denied, subprocess.TimeoutExpired):
            print("QA_FINAL_LOG_CHECK=UNAVAILABLE")
        try:
            events = command([
                "docker", "events", "--since",
                (finished - timedelta(minutes=10)).isoformat(), "--until",
                (finished + timedelta(minutes=2)).isoformat(),
                "--filter", "container=" + N, "--format", "{{json .}}"
            ], timeout=25)
            counts = classify_events(events)
            for action in ACTIONS:
                print("QA_EVENT_" + action.upper() + "=" + str(counts[action]))
            print("QA_EVENT_HISTORY=BEST_EFFORT")
        except (Denied, subprocess.TimeoutExpired):
            print("QA_EVENT_HISTORY=UNAVAILABLE")
        print("QA_EXIT255_CAUSE=NOT_YET_CERTIFIED")
        print("QA_BACKUP_INTEGRITY=NOT_YET_VERIFIED")
        print("QA_RESTART_ALLOWED=NO")
        print("QA_A1_RESULT=READ_ONLY_COMPLETE")
        return 0
    except (Denied, ValueError, TypeError, KeyError, OSError, subprocess.TimeoutExpired):
        print("QA_A1_RESULT=BLOCKED_NEEDS_PRIVATE_REVIEW")
        return 2


if __name__ == "__main__":
    sys.exit(main())
