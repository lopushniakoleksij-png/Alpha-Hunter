#!/usr/bin/env bash
# Alpha Hunter: private, schema-only export for isolated PostgreSQL acceptance.
# This script is safe for the public repo: NO connection strings or passwords.
# It makes READ-ONLY connections to production; it NEVER changes production data.
# Required: Docker postgres:17 image, existing Codespace, Supabase DB password.
# Run from repository root via: bash ops/local/export_private_pg_schema.sh
set -Eeuo pipefail
set +x
umask 077
# Explicitly confine private credential-handling export to its existing Codespace.
# Never request credentials on GitHub Actions, another workstation, or main.
if [[ "$(printenv CODESPACES || true)" != "true" ]] ||
   [[ "$(printenv GITHUB_ACTIONS || true)" == "true" ]] ||
   [[ "$(git branch --show-current 2>/dev/null || true)" != "fix/supabase-write-timeout-qa" ]]; then
  echo "REFUSED: private export requires the existing authorised Codespace on isolated draft branch."
  exit 2
fi

PROJECT_REF="yjgtjzymfurqzqqxcrnp"
BASE="$HOME/.alpha-hunter-private-dbqa"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BASE/$STAMP"
mkdir -p "$DEST"
chmod 700 "$BASE" "$DEST"
trap 'unset DB_PASSWORD' EXIT

if ! docker image inspect postgres:17 >/dev/null 2>&1; then
  echo "ERROR: postgres:17 client image is not present. Stop to review storage costs."
  exit 1
fi

echo "ALPHA HUNTER — PRIVATE SCHEMA-ONLY EXPORT"
echo "Schema definitions only, no table data or production writes."
echo "Function source may embed sensitive constants; never publish the archive."
echo "Files stay outside Git under: $DEST"
echo "For Supabase > Connect choose Session pooler (IPv4), port 5432."
echo "Do not paste your database password into ChatGPT, GitHub, or this repo."
read -r -p "Paste only the Session pooler HOST (no URL/password): " DB_HOST
if [[ ! "$DB_HOST" =~ ^[a-zA-Z0-9.-]+\.pooler\.supabase\.com$ ]]; then
  echo "ERROR: expected official Supabase session pooler hostname; aborting."
  exit 1
fi

CERT_MOUNT=()
SSL_ROOT="system"
read -r -p "Optional Supabase CA certificate absolute path in Codespace (Enter = system trust): " CERT_PATH
if [[ -n "$CERT_PATH" ]]; then
  if [[ "$CERT_PATH" != /* || ! -f "$CERT_PATH" ]]; then
    echo "ERROR: CA certificate file not found; aborting."
    exit 1
  fi
  CERT_MOUNT=( -v "$CERT_PATH:/qa-ca/server.crt:ro" )
  SSL_ROOT="/qa-ca/server.crt"
fi

read -r -s -p "Supabase database password (input hidden): " DB_PASSWORD
printf '\n'
if [[ -z "$DB_PASSWORD" ]]; then
  echo "ERROR: empty password."
  exit 1
fi

# Password travels only through a Docker stdin pipe (not command-line args,
# Docker env config, a persistent credentials file or GitHub).
# The QA PostgreSQL server container remains offline.
run_private_pg() {
  printf '%s\n' "$DB_PASSWORD" | docker run --rm -i --network bridge \
    --user "$(id -u):$(id -g)" \
    -e "PGHOST=$DB_HOST" \
    -e "PGUSER=postgres.$PROJECT_REF" \
    -e PGPORT=5432 \
    -e PGDATABASE=postgres \
    -e PGSSLMODE=verify-full \
    -e "PGSSLROOTCERT=$SSL_ROOT" \
    -e "PGOPTIONS=-c default_transaction_read_only=on -c lock_timeout=5000 -c statement_timeout=60000" \
    -e HOME=/tmp \
    -v "$DEST:/qa:rw" \
    "${CERT_MOUNT[@]}" \
    postgres:17 bash -ceu 'IFS= read -r PGPASSWORD; export PGPASSWORD; exec "$@"' \
    bash "$@"
}

echo "Step 1/3: verify TLS and READ-ONLY session..."
run_private_pg psql -X -qAt -c "select 'TLS_AND_READONLY_OK' where current_setting('transaction_read_only')='on';" |
  grep -Fx 'TLS_AND_READONLY_OK' >/dev/null

echo "Step 2/3: export production schema definitions only (no table rows)..."
run_private_pg pg_dump \
  --schema-only --format=custom \
  --lock-wait-timeout=5s \
  --file=/qa/production_schema.partial.dump \
  --no-tablespaces
mv "$DEST/production_schema.partial.dump" "$DEST/production_schema.dump"
chmod 600 "$DEST/production_schema.dump"

echo "Step 3/3: export role definitions with all passwords omitted..."
run_private_pg pg_dumpall \
  --roles-only --no-role-passwords \
  --file=/qa/production_roles_no_passwords.sql
chmod 600 "$DEST/production_roles_no_passwords.sql"

( cd "$DEST" && sha256sum production_schema.dump production_roles_no_passwords.sql > sha256-local.txt )
# Offline archive inspection only; do not print SQL function bodies or object names.
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$DEST:/qa:ro" postgres:17 \
  pg_restore --list /qa/production_schema.dump |
  awk '/ FUNCTION / {f++} / TRIGGER / {t++} / INDEX / {i++} / ACL / {a++}
       END {printf "Archive inventory: functions=%d triggers=%d indexes=%d ACL entries=%d\n", f,t,i,a}'
printf 'SUCCESS: private schema archive and no-password role file saved.\n'
printf 'Private folder: %s\n' "$DEST"
printf 'Archive size: %s bytes\n' "$(wc -c < "$DEST/production_schema.dump")"
printf 'IMPORTANT: not a restored or validated production-equivalent clone yet.\n'
printf 'Do NOT move these files into Git, attach them to chats or publish them.\n'
