#!/usr/bin/env bash
# Alpha Hunter Harada B1-B3: zero-write local preflight INSIDE the EXISTING
# PRIVATE GitHub Codespace. No database credentials, exports or secrets printed.
# No Supabase connection, paid project, container start, deploy or migration.
set -Eeuo pipefail
set +x
umask 077

if [[ "$(printenv CODESPACES || true)" != "true" ]]; then
  echo "REFUSED: run inside existing GitHub Codespace, not production or CI."
  exit 2
fi
branch="$(git branch --show-current 2>/dev/null || true)"
if [[ "$branch" != "fix/supabase-write-timeout-qa" ]]; then
  echo "REFUSED: checkout the isolated draft repair branch before inspection."
  exit 2
fi
echo "ALPHA HUNTER B1/B2 PRIVATE DATABASE CLONE PREFLIGHT (NO WRITES)"
echo "RUN_MODE=READ_ONLY_LOCAL_METADATA"
echo "SOURCE_BRANCH=ISOLATED_DRAFT"
echo "PRODUCTION_DB_CONNECTION=NOT_ATTEMPTED"

if ! command -v docker >/dev/null 2>&1; then
 echo "DOCKER_CLIENT=UNAVAILABLE"
else
 echo "DOCKER_CLIENT=AVAILABLE"
 if docker image inspect postgres:17 >/dev/null 2>&1; then
   echo "POSTGRES17_CLIENT_IMAGE=CACHED"
 else
   echo "POSTGRES17_CLIENT_IMAGE=NOT_CACHED"
 fi
 if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
   echo "LOCAL_DOCKER_DAEMON=REACHABLE"
   echo "RUNNING_LOCAL_PG17_CONTAINERS=$(docker ps --filter 'ancestor=postgres:17' --format '{{.ID}}' | wc -l | tr -d ' ')"
 else
   echo "LOCAL_DOCKER_DAEMON=UNAVAILABLE"
 fi
fi

base="$HOME/.alpha-hunter-private-dbqa"
if [[ ! -d "$base" ]]; then
  echo "PRIVATE_SCHEMA_FOLDER=NOT_PRESENT"
  echo "AUTHENTIC_SCHEMA_DUMP=NOT_FOUND"
  echo "NEXT_GATE=AUTHORISED_PRIVATE_SCHEMA_EXPORT"
  exit 0
fi
if [[ -L "$base" ]]; then
 echo "REFUSED: private schema folder must not be a symbolic link"
 exit 2
fi
folder_mode="$(stat -c '%a' "$base")"
if [[ "$folder_mode" != "700" ]]; then
 echo "PRIVATE_SCHEMA_FOLDER_PERMISSIONS=REVIEW_REQUIRED"
 echo "REFUSED: expected mode 700; do not disclose or upload SQL"
 exit 2
fi

count=0
for archive in "$base"/*/production_schema.dump; do
  if [[ ! -f "$archive" ]]; then continue; fi
  mode="$(stat -c '%a' "$archive")"
  if [[ "$mode" != "600" ]]; then
    echo "REFUSED: archive permissions must be 600"
    exit 2
  fi
  count=$((count+1))
done
echo "PRIVATE_SCHEMA_ARCHIVE_COUNT=$count"
if (( count == 0 )); then
  echo "AUTHENTIC_SCHEMA_DUMP=NOT_FOUND"
  echo "NEXT_GATE=AUTHORISED_PRIVATE_SCHEMA_EXPORT"
  exit 0
fi
echo "AUTHENTIC_SCHEMA_DUMP=FOUND_PRIVATE_ARCHIVE_PERMISSIONS_OK"
echo "NEXT_GATE=OFFLINE_ARCHIVE_VALIDATION_AND_SUPABASE_EXTENSION_COMPATIBILITY"
echo "NOTE=Archive existence is not proof of restored private graph or benchmark"
