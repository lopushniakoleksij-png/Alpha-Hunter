#!/usr/bin/env bash
# ALPHA HUNTER P0 / HARADA B2-B4 — PRIVATE CODESPACE ARCHIVE PREFLIGHT.
# Never exports private function source, secrets, row data, or SQL to Git.
# Read-only LOCAL schema archive inventory; no production connection or DDL.
set -Eeuo pipefail
set +x
umask 077

if [[ "$(printenv CODESPACES || true)" != "true" ]]; then
  echo "REFUSED: run only inside the existing authenticated GitHub Codespace."
  exit 2
fi
if [[ "$(git branch --show-current 2>/dev/null || true)" != "fix/supabase-write-timeout-qa" ]]; then
  echo "REFUSED: switch to the existing isolated draft repair branch."
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "BLOCKED: docker is not available in this Codespace."
  exit 3
fi
if ! docker image inspect postgres:17 >/dev/null 2>&1; then
  echo "BLOCKED: existing local postgres:17 image is not cached. No image pulled."
  exit 3
fi

base="$HOME/.alpha-hunter-private-dbqa"
if [[ ! -d "$base" || -L "$base" ]]; then
  echo "BLOCKED: private archive directory missing or unsafe."
  exit 3
fi
base_real="$(realpath -e "$base")"
if [[ "$(stat -c '%a' "$base_real")" != "700" ]]; then
  echo "REFUSED: private archive root permissions must be 700."
  exit 2
fi

selected=""
if (( $# == 1 )); then
  selected="$(realpath -e "$1" 2>/dev/null || true)"
  if [[ -z "$selected" || ! -f "$selected" ]]; then
    echo "BLOCKED: specified private archive does not exist."
    exit 3
  fi
else
  count=0
  while IFS= read -r -d '' item; do
    count=$((count+1))
    selected="$item"
  done < <(find "$base_real" -mindepth 2 -maxdepth 2 -type f -name production_schema.dump -print0)
  if (( count != 1 )); then
    echo "BLOCKED: provide the exact private archive path; available archive count=$count"
    echo "Never send the path or contents to a chat, public repo, or issue."
    exit 3
  fi
  selected="$(realpath -e "$selected")"
fi
case "$selected" in
  "$base_real"/*/production_schema.dump) ;;
  *) echo "REFUSED: archive must be inside private directory and named production_schema.dump."; exit 2 ;;
esac
parent="$(dirname "$selected")"
if [[ -L "$parent" || -L "$selected" ]]; then
  echo "REFUSED: symbolic-link archives are not allowed."
  exit 2
fi
if [[ "$(stat -c '%a' "$parent")" != "700" || "$(stat -c '%a' "$selected")" != "600" ]]; then
  echo "REFUSED: private export directory must be 700 and archive must be 600."
  exit 2
fi
if [[ ! -f "$parent/production_roles_no_passwords.sql" ]] ||
   [[ "$(stat -c '%a' "$parent/production_roles_no_passwords.sql")" != "600" ]]; then
  echo "BLOCKED: no-password private role inventory is missing or not mode 600."
  exit 3
fi

toc="$(mktemp "$parent/.archive-toc.XXXXXXXX")"
trap 'rm -f "$toc"' EXIT

# Air-gapped, READ-ONLY Docker process, never communicates with Supabase.
# Archive/function names and private SQL remain in owner-only local directory.
docker run --rm --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  -v "$parent:/qa:ro" postgres:17 \
  pg_restore --list /qa/production_schema.dump >"$toc"
if [[ ! -s "$toc" ]]; then
  echo "BLOCKED: offline pg_restore inventory is empty."
  exit 3
fi

failed=0
for name in \
 alpha_hunter_capture_strategy_observations_v01 \
 alpha_hunter_capture_shadow_decision_quote_v01 \
 alpha_hunter_auto_freeze_execution_decision_v02 \
 alpha_hunter_capture_payoff_geometry_health_v01 \
 alpha_hunter_create_calibrated_paper_order_v02 \
 alpha_hunter_enqueue_strategy_24h_outcome_v01
do
  if ! grep -Eq " FUNCTION private[[:space:]]+$name[[:space:]]*[(]" "$toc"; then
    echo "MISSING_KNOWN_PRIVATE_FUNCTION=$name"
    failed=1
  fi
done
for name in \
 trg_ah_capture_strategy_observations_v01 \
 trg_ah_capture_shadow_decision_quote_v01 \
 trg_ah_auto_freeze_execution_decision_v02 \
 trg_ah_payoff_geometry_health_v01 \
 trg_ah_calibrated_paper_order_v02 \
 trg_ah_enqueue_strategy_24h_outcome_v01
do
  if ! grep -Fq "$name" "$toc"; then
    echo "MISSING_KNOWN_TRIGGER=$name"
    failed=1
  fi
done
echo "ARCHIVE_FUNCTIONS=$(grep -c ' FUNCTION ' "$toc" || true)"
echo "ARCHIVE_TRIGGERS=$(grep -c ' TRIGGER ' "$toc" || true)"
echo "ARCHIVE_INDEXES=$(grep -c ' INDEX ' "$toc" || true)"
echo "ARCHIVE_CHECKSUM_SHA256=$(sha256sum "$selected" | cut -d ' ' -f1)"
echo "PRIVATE_EXPORT_READ_ONLY=YES"
echo "PRODUCTION_CREDENTIAL_ACCESS=NOT_ATTEMPTED"
if (( failed != 0 )); then
  echo "BLOCKED: required known graph objects absent. No restore attempted."
  exit 3
fi
echo "PASS: archive contains known graph object names; full transitive equivalence NOT YET VERIFIED."
echo "NEXT_GATE: private PG17 extension/role-compatible restore, then exact fingerprints."
