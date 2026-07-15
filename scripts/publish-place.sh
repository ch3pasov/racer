#!/usr/bin/env bash
# Never allow an inherited `bash -x` to trace a credential expansion.
set +x
# Prevent `bash -a`/allexport from exporting the private shell copy below.
set +a
set -euo pipefail

BUILD_ONLY="false"
if [[ "$#" -eq 0 ]]; then
  :
elif [[ "$#" -eq 1 && "$1" == "--build-only" ]]; then
  BUILD_ONLY="true"
else
  unset ROBLOX_API_KEY RACER_PUBLISH_API_KEY
  echo "Usage: scripts/publish-place.sh [--build-only]" >&2
  exit 2
fi

# Keep the Open Cloud key in this shell only. Build-only must neither inspect
# nor export it, while normal publishing validates it before any child process.
unset RACER_PUBLISH_API_KEY
if [[ "${BUILD_ONLY}" == "true" ]]; then
  unset ROBLOX_API_KEY
else
  if [[ -z "${ROBLOX_API_KEY:-}" ]]; then
    unset ROBLOX_API_KEY
    echo "ROBLOX_API_KEY is required." >&2
    exit 2
  fi
  RACER_PUBLISH_API_KEY="${ROBLOX_API_KEY}"
  export -n RACER_PUBLISH_API_KEY
  unset ROBLOX_API_KEY
  if [[ "${RACER_PUBLISH_API_KEY}" == *$'\r'* ]] \
    || [[ "${RACER_PUBLISH_API_KEY}" == *$'\n'* ]]; then
    unset RACER_PUBLISH_API_KEY
    echo "ROBLOX_API_KEY must not contain CR or LF." >&2
    exit 2
  fi
  readonly RACER_PUBLISH_API_KEY
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

OUTPUT_LABEL="build/racer.rbxlx"
OUTPUT_FILE="${ROOT_DIR}/${OUTPUT_LABEL}"
BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"
STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"
FINALIZER="${SCRIPT_DIR}/finalize-studio-publish.sh"
PENDING_LABEL="build/racer-publish-pending.json"
PENDING_REF="refs/racer-publish/pending"
RELEASE_LOCK_DIR="${ROOT_DIR}/build/.racer-publish-release.lock"

git_repo() {
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

PENDING_REF_COMMIT=""

pending_ref_storage_exists() {
  local loose_path
  local packed_path
  local object_id
  local ref_name
  local remainder

  if ! loose_path="$(git_repo rev-parse --git-path "${PENDING_REF}")"; then
    return 2
  fi
  if [[ -e "${loose_path}" || -L "${loose_path}" ]]; then
    return 0
  fi
  if ! packed_path="$(git_repo rev-parse --git-path packed-refs)"; then
    return 2
  fi
  if [[ -f "${packed_path}" ]]; then
    while read -r object_id ref_name remainder; do
      if [[ "${ref_name:-}" == "${PENDING_REF}" ]]; then
        return 0
      fi
    done < "${packed_path}"
  fi
  return 1
}

inspect_pending_ref() {
  local object_id
  local status
  local resolved_commit
  local symbolic_target

  if symbolic_target="$(git_repo symbolic-ref -q "${PENDING_REF}" 2>/dev/null)"; then
    echo "Racer pending recovery ref must not be symbolic (${symbolic_target})." >&2
    return 2
  else
    status=$?
  fi
  if [[ "${status}" -ne 1 ]]; then
    echo "Racer pending recovery ref symbolic state could not be inspected." >&2
    return 2
  fi

  if object_id="$(git_repo show-ref --verify --hash "${PENDING_REF}" 2>/dev/null)"; then
    if [[ ! "${object_id}" =~ ^[0-9a-f]{40}$ ]]; then
      echo "Racer pending recovery ref has an invalid object id." >&2
      return 2
    fi
    if ! resolved_commit="$(git_repo rev-parse --verify "${PENDING_REF}^{commit}" 2>/dev/null)"; then
      echo "Racer pending recovery ref does not point directly to a commit." >&2
      return 2
    fi
    if [[ "${resolved_commit}" != "${object_id}" ]]; then
      echo "Racer pending recovery ref must point directly to its release commit." >&2
      return 2
    fi
    PENDING_REF_COMMIT="${object_id}"
    return 0
  else
    status=$?
  fi

  PENDING_REF_COMMIT=""
  if pending_ref_storage_exists; then
    echo "Racer pending recovery ref is unreadable or invalid." >&2
    return 2
  else
    status=$?
  fi
  if [[ "${status}" -ne 1 ]]; then
    echo "Racer pending recovery ref storage could not be inspected." >&2
    return 2
  fi
  return 1
}

require_pending_ref_absent() {
  local status

  if inspect_pending_ref; then
    echo "A Racer publish recovery ref already exists at ${PENDING_REF}." >&2
    echo "Finalize its pending publish before building or publishing again." >&2
    exit 1
  else
    status=$?
  fi
  if [[ "${status}" -ne 1 ]]; then
    exit 1
  fi
}

create_pending_ref() {
  local status

  if ! git_repo update-ref --no-deref "${PENDING_REF}" "${GIT_COMMIT}" ""; then
    echo "Failed to create the Racer pending recovery ref atomically." >&2
    exit 1
  fi
  if inspect_pending_ref; then
    if [[ "${PENDING_REF_COMMIT}" != "${GIT_COMMIT}" ]]; then
      echo "Racer pending recovery ref does not match the release commit." >&2
      exit 1
    fi
    return
  else
    status=$?
  fi
  echo "Racer pending recovery ref could not be verified after creation." >&2
  exit "${status}"
}

sha256_file() {
  TARGET_FILE="$1" python3 -c 'import hashlib
import os
from pathlib import Path

print(hashlib.sha256(Path(os.environ["TARGET_FILE"]).read_bytes()).hexdigest())'
}

require_clean_tree() {
  local tree_status
  tree_status="$(git_repo status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  if [[ -n "${tree_status}" ]]; then
    echo "Refusing to build or publish from a dirty git tree. Commit or stash changes first." >&2
    exit 1
  fi
}

TEMP_ROOT=""
INSTALL_TEMP=""
RELEASE_LOCK_HELD="false"

release_publish_lock() {
  if [[ "${RELEASE_LOCK_HELD}" == "true" ]]; then
    rmdir "${RELEASE_LOCK_DIR}"
    RELEASE_LOCK_HELD="false"
  fi
}

cleanup() {
  if [[ -n "${INSTALL_TEMP}" ]]; then
    rm -f "${INSTALL_TEMP}"
  fi
  if [[ -n "${TEMP_ROOT}" ]]; then
    rm -rf "${TEMP_ROOT}"
  fi
  release_publish_lock
}
trap cleanup EXIT

: "${ROBLOX_RACER_PLACE_ID:?ROBLOX_RACER_PLACE_ID is required}"
PLACE_ID="${ROBLOX_RACER_PLACE_ID}"
LOBBY_PLACE_ID="${ROBLOX_LOBBY_PLACE_ID:-0}"

if [[ ! "${PLACE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ROBLOX_RACER_PLACE_ID must be a positive decimal integer." >&2
  exit 2
fi

if [[ ! "${LOBBY_PLACE_ID}" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "ROBLOX_LOBBY_PLACE_ID must be zero or a positive decimal integer." >&2
  exit 2
fi

if [[ ! -x "${BUILD_HELPER}" ]]; then
  echo "Release snapshot builder is missing or not executable: ${BUILD_HELPER}" >&2
  exit 1
fi
if [[ ! -x "${STATE_HELPER}" ]]; then
  echo "Pending publish state helper is missing or not executable: ${STATE_HELPER}" >&2
  exit 1
fi
if [[ ! -x "${FINALIZER}" ]]; then
  echo "Publish finalizer is missing or not executable: ${FINALIZER}" >&2
  exit 1
fi

mkdir -p "$(dirname -- "${RELEASE_LOCK_DIR}")"
if ! mkdir "${RELEASE_LOCK_DIR}"; then
  echo "Another Racer release operation holds ${RELEASE_LOCK_DIR#"${ROOT_DIR}/"}." >&2
  echo "If no release process is running, inspect pending state before removing a stale lock." >&2
  exit 1
fi
RELEASE_LOCK_HELD="true"

# A manifest and its private git recovery ref must both be absent before a new build.
require_pending_ref_absent
# Any state file, including a corrupt one, blocks before the artifact can be rebuilt.
"${STATE_HELPER}" assert-absent

require_clean_tree

GIT_COMMIT="$(git_repo rev-parse HEAD)"
GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 HEAD)"
PUBLISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/racer-publish.XXXXXX")"
PRIVATE_ARTIFACT="${TEMP_ROOT}/racer.rbxlx"

"${BUILD_HELPER}" \
  "${GIT_COMMIT}" \
  "${PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${PLACE_ID}" \
  "${PRIVATE_ARTIFACT}"

BUILD_SHA256="$(sha256_file "${PRIVATE_ARTIFACT}")"

require_release_state() {
  if [[ "$(git_repo rev-parse HEAD)" != "${GIT_COMMIT}" ]]; then
    echo "HEAD changed while preparing the Racer release artifact." >&2
    exit 1
  fi
  require_clean_tree
  if [[ "$(sha256_file "${PRIVATE_ARTIFACT}")" != "${BUILD_SHA256}" ]]; then
    echo "Private Racer release artifact changed after it was built." >&2
    exit 1
  fi
}

atomic_install_artifact() {
  mkdir -p "$(dirname -- "${OUTPUT_FILE}")"
  INSTALL_TEMP="$(mktemp "$(dirname -- "${OUTPUT_FILE}")/.racer.rbxlx.XXXXXX")"
  cp "${PRIVATE_ARTIFACT}" "${INSTALL_TEMP}"
  chmod 0644 "${INSTALL_TEMP}"
  mv -f "${INSTALL_TEMP}" "${OUTPUT_FILE}"
  INSTALL_TEMP=""
  if [[ "$(sha256_file "${OUTPUT_FILE}")" != "${BUILD_SHA256}" ]]; then
    echo "Installed Racer release artifact does not match the private build." >&2
    exit 1
  fi
}

require_installed_artifact() {
  if [[ ! -f "${OUTPUT_FILE}" || -L "${OUTPUT_FILE}" ]]; then
    echo "Installed Racer release artifact is missing or is not a regular file." >&2
    exit 1
  fi
  if [[ "$(sha256_file "${OUTPUT_FILE}")" != "${BUILD_SHA256}" ]]; then
    echo "Installed Racer release artifact changed after it was built." >&2
    exit 1
  fi
}

create_pending_state() {
  local mode="$1"
  local manifest_sha
  local -a arguments
  arguments=(
    create
    --mode "${mode}"
    --git-commit "${GIT_COMMIT}"
    --git-commit-short "${GIT_COMMIT_SHORT}"
    --published-at "${PUBLISHED_AT}"
    --racer-place-id "${PLACE_ID}"
    --lobby-place-id "${LOBBY_PLACE_ID}"
  )
  if [[ "${mode}" == "open-cloud" ]]; then
    arguments+=(--universe-id "${ROBLOX_UNIVERSE_ID}")
  fi
  manifest_sha="$("${STATE_HELPER}" "${arguments[@]}")"
  if [[ "${manifest_sha}" != "${BUILD_SHA256}" ]]; then
    echo "Pending publish state recorded an unexpected artifact SHA-256." >&2
    exit 1
  fi
}

require_release_state
atomic_install_artifact
require_installed_artifact

if [[ "${BUILD_ONLY}" == "true" ]]; then
  create_pending_ref
  create_pending_state "studio"
  echo "Built ${OUTPUT_LABEL} for Racer place ${PLACE_ID}"
  echo "Commit: ${GIT_COMMIT}"
  echo "SHA-256: ${BUILD_SHA256}"
  echo "Pending Studio publish: ${PENDING_LABEL}"
  exit 0
fi

: "${ROBLOX_UNIVERSE_ID:?ROBLOX_UNIVERSE_ID is required}"
if [[ ! "${ROBLOX_UNIVERSE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ROBLOX_UNIVERSE_ID must be a positive decimal integer." >&2
  exit 2
fi

require_release_state
require_installed_artifact
create_pending_ref
create_pending_state "open-cloud"

# The POST must still match both the private snapshot and the durable manifest.
require_release_state
require_installed_artifact
if [[ "$("${STATE_HELPER}" validate-artifact)" != "${BUILD_SHA256}" ]]; then
  echo "Pending publish state no longer matches the Racer release artifact." >&2
  exit 1
fi

if ! PUBLISH_RESPONSE="$(env -u ROBLOX_API_KEY curl --disable --fail-with-body \
    --request POST \
    --header @<(builtin printf 'x-api-key: %s\n' "${RACER_PUBLISH_API_KEY}") \
    --header "Content-Type: application/xml" \
    --data-binary @"${PRIVATE_ARTIFACT}" \
    "https://apis.roblox.com/universes/v1/${ROBLOX_UNIVERSE_ID}/places/${PLACE_ID}/versions?versionType=Published")"; then
  echo "Roblox publish request failed; ${PENDING_LABEL} was retained for recovery." >&2
  exit 1
fi

if ! PLACE_VERSION="$(PUBLISH_RESPONSE="${PUBLISH_RESPONSE}" python3 -c 'import json
import os
import sys

try:
    payload = json.loads(os.environ["PUBLISH_RESPONSE"])
except (KeyError, json.JSONDecodeError) as error:
    print(f"invalid Roblox publish JSON: {error}", file=sys.stderr)
    raise SystemExit(1)

version = payload.get("versionNumber")
if not isinstance(version, int) or isinstance(version, bool) or version <= 0:
    print("Roblox publish response must contain a positive integer versionNumber", file=sys.stderr)
    raise SystemExit(1)
print(version)')"; then
  echo "Published response did not include a valid place version." >&2
  echo "${PENDING_LABEL} was retained; do not retry the publish request." >&2
  exit 1
fi

# Persist the accepted PlaceVersion before any tag or other finalization work.
"${STATE_HELPER}" record-version "${PLACE_VERSION}" \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${BUILD_SHA256}"

# The finalizer takes the same release lock and is the single tag/lookup/clear path.
release_publish_lock
if ! env -u ROBLOX_API_KEY "${FINALIZER}" "${PLACE_VERSION}"; then
  echo "PlaceVersion ${PLACE_VERSION} was published but ${PENDING_LABEL} remains pending." >&2
  exit 1
fi

echo "Published Racer Lab place ${PLACE_ID} in universe ${ROBLOX_UNIVERSE_ID}"
