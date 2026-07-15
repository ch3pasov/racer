#!/bin/bash -p
# Never allow an inherited `bash -x` to trace a credential expansion.
set +x
# Prevent `bash -a`/allexport from exporting the private shell copy below.
set +a
set -euo pipefail

LOCK_CONTEXT_VALUE="racer-release-lock-v1"
SECRET_CONTEXT_VALUE="racer-release-secret-v1"

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

# Identify the trusted initial invocation or the exact helper-created context
# using shell builtins only. Partial/spoofed contexts fail before any child.
if [[ -z "${RACER_RELEASE_LOCK_CONTEXT+x}" && -z "${RACER_RELEASE_LOCK_FD+x}" ]]; then
  RELEASE_PHASE="initial"
elif [[ "${RACER_RELEASE_LOCK_CONTEXT-}" == "${LOCK_CONTEXT_VALUE}" \
  && "${RACER_RELEASE_LOCK_FD-}" == "8" ]]; then
  RELEASE_PHASE="locked"
else
  unset ROBLOX_API_KEY RACER_PUBLISH_API_KEY
  echo "Racer release lock context is missing, partial, or spoofed." >&2
  exit 1
fi

# Keep the Open Cloud key in this shell only. Build-only never inspects it.
# The locked process must consume and close FD 9 before starting any child.
unset RACER_PUBLISH_API_KEY
if [[ "${RELEASE_PHASE}" == "locked" ]]; then
  unset ROBLOX_API_KEY
  if [[ "${BUILD_ONLY}" == "true" ]]; then
    if [[ -n "${RACER_RELEASE_SECRET_CONTEXT+x}" \
      || -n "${RACER_RELEASE_SECRET_FD+x}" ]]; then
      echo "Build-only release received an unexpected secret context." >&2
      exit 1
    fi
    if { builtin true <&9; } 2>/dev/null; then
      exec 9<&-
      echo "Build-only release received an unexpected secret FD." >&2
      exit 1
    fi
  else
    if [[ "${RACER_RELEASE_SECRET_CONTEXT-}" != "${SECRET_CONTEXT_VALUE}" \
      || "${RACER_RELEASE_SECRET_FD-}" != "9" ]]; then
      echo "Racer release secret context is missing, partial, or spoofed." >&2
      exit 1
    fi
    if ! IFS= builtin read -r -d '' RACER_PUBLISH_API_KEY <&9; then
      exec 9<&-
      unset RACER_PUBLISH_API_KEY RACER_RELEASE_SECRET_CONTEXT RACER_RELEASE_SECRET_FD
      echo "Racer release secret pipe was incomplete." >&2
      exit 1
    fi
    if IFS= builtin read -r -n 1 _RACER_SECRET_TRAILING <&9; then
      exec 9<&-
      unset RACER_PUBLISH_API_KEY RACER_RELEASE_SECRET_CONTEXT RACER_RELEASE_SECRET_FD
      echo "Racer release secret pipe contained trailing data." >&2
      exit 1
    fi
    exec 9<&-
    unset RACER_RELEASE_SECRET_CONTEXT RACER_RELEASE_SECRET_FD _RACER_SECRET_TRAILING
    if [[ -z "${RACER_PUBLISH_API_KEY}" \
      || "${RACER_PUBLISH_API_KEY}" == *$'\r'* \
      || "${RACER_PUBLISH_API_KEY}" == *$'\n'* ]]; then
      unset RACER_PUBLISH_API_KEY
      echo "Racer release secret pipe contained an invalid API key." >&2
      exit 2
    fi
    export -n RACER_PUBLISH_API_KEY
  fi
else
  if [[ -n "${RACER_RELEASE_SECRET_CONTEXT+x}" \
    || -n "${RACER_RELEASE_SECRET_FD+x}" ]]; then
    unset ROBLOX_API_KEY
    echo "Racer release acquisition received a preexisting secret context." >&2
    exit 1
  fi
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
    if [[ "${RACER_PUBLISH_API_KEY}" == *$'\r'* \
      || "${RACER_PUBLISH_API_KEY}" == *$'\n'* ]]; then
      unset RACER_PUBLISH_API_KEY
      echo "ROBLOX_API_KEY must not contain CR or LF." >&2
      exit 2
    fi
  fi
fi

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
case "${SCRIPT_SOURCE}" in
  /*) SCRIPT_CANDIDATE="${SCRIPT_SOURCE}" ;;
  */*) SCRIPT_CANDIDATE="${PWD}/${SCRIPT_SOURCE}" ;;
  *)
    unset RACER_PUBLISH_API_KEY
    echo "Publish script must be invoked through an explicit path." >&2
    exit 1
    ;;
esac
SCRIPT_BASENAME="${SCRIPT_CANDIDATE##*/}"
if ! SCRIPT_PARENT="$(/usr/bin/dirname -- "${SCRIPT_CANDIDATE}" 8>&-)"; then
  unset RACER_PUBLISH_API_KEY
  echo "Cannot resolve the publish script directory." >&2
  exit 1
fi
builtin cd -P -- "${SCRIPT_PARENT}"
SCRIPT_DIR="${PWD}"
SCRIPT_PATH="${SCRIPT_DIR}/${SCRIPT_BASENAME}"
builtin cd -P -- "${SCRIPT_DIR}/.."
ROOT_DIR="${PWD}"
if [[ "${SCRIPT_PATH}" != "${ROOT_DIR}/scripts/publish-place.sh" \
  || -L "${SCRIPT_PATH}" || ! -f "${SCRIPT_PATH}" ]]; then
  unset RACER_PUBLISH_API_KEY
  echo "Publish script path is not the trusted repository script." >&2
  exit 1
fi

OUTPUT_LABEL="build/racer.rbxlx"
OUTPUT_FILE="${ROOT_DIR}/${OUTPUT_LABEL}"
BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"
STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"
FINALIZER="${SCRIPT_DIR}/finalize-studio-publish.sh"
PENDING_LABEL="build/racer-publish-pending.json"
PENDING_REF="refs/racer-publish/pending"

if [[ -z "${HOME:-}" || "${HOME}" != /* ]]; then
  unset RACER_PUBLISH_API_KEY
  echo "Racer releases require an absolute HOME." >&2
  exit 1
fi
RELEASE_TMPDIR="${TMPDIR:-/tmp}"
if [[ "${RELEASE_TMPDIR}" != /* ]]; then
  unset RACER_PUBLISH_API_KEY
  echo "Racer releases require an absolute TMPDIR." >&2
  exit 1
fi

git_repo() {
  /usr/bin/env -i \
    HOME=/ XDG_CONFIG_HOME=/dev/null PATH=/usr/bin:/bin LC_ALL=C LANG=C TZ=UTC \
    GIT_ATTR_NOSYSTEM=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_NO_REPLACE_OBJECTS=1 \
    /usr/bin/git \
    -c safe.directory="${ROOT_DIR}" \
    -c core.attributesFile=/dev/null \
    -C "${ROOT_DIR}" "$@"
}

release_fail() {
  unset RACER_PUBLISH_API_KEY
  echo "$1" >&2
  exit 1
}

RELEASE_HELPER_PATHS=(
  scripts/publish-place.sh
  scripts/build-racer-release.sh
  scripts/racer-publish-state.py
  scripts/finalize-studio-publish.sh
  scripts/lookup-place-version.sh
)

require_no_hidden_index_entries() {
  if ! git_repo ls-files -v -z | while IFS= read -r -d '' entry; do
    case "${entry:0:1}" in
      S|[a-z])
        echo "Release index contains a hidden entry: ${entry:2}" >&2
        exit 42
        ;;
    esac
  done; then
    release_fail "Release index hidden-state inspection failed."
  fi
}

require_release_helpers_match_head() {
  local actual_blob expected_blob relative_path tree_entry
  for relative_path in "${RELEASE_HELPER_PATHS[@]}"; do
    if [[ -L "${ROOT_DIR}/${relative_path}" \
      || ! -f "${ROOT_DIR}/${relative_path}" \
      || ! -x "${ROOT_DIR}/${relative_path}" ]]; then
      release_fail "Release helper must be a regular executable file: ${relative_path}"
    fi
    expected_blob="$(git_repo rev-parse --verify "HEAD:${relative_path}")" \
      || release_fail "Release helper is missing from HEAD: ${relative_path}"
    tree_entry="$(git_repo ls-tree HEAD -- "${relative_path}")" \
      || release_fail "Release helper mode could not be inspected: ${relative_path}"
    if [[ "${tree_entry}" != "100755 blob ${expected_blob}"$'\t'"${relative_path}" ]]; then
      release_fail "Release helper must be a 100755 blob in HEAD: ${relative_path}"
    fi
    actual_blob="$(git_repo hash-object --no-filters -- "${ROOT_DIR}/${relative_path}")" \
      || release_fail "Release helper bytes could not be hashed: ${relative_path}"
    if [[ "${actual_blob}" != "${expected_blob}" ]]; then
      release_fail "Release helper bytes do not match HEAD: ${relative_path}"
    fi
  done
}

require_release_git_metadata() {
  local attributes_path replace_refs
  replace_refs="$(git_repo for-each-ref --format='%(refname)' refs/replace)" \
    || release_fail "Release replacement refs could not be inspected."
  if [[ -n "${replace_refs}" ]]; then
    release_fail "Release repository must not contain Git replacement refs."
  fi
  attributes_path="$(git_repo rev-parse --git-path info/attributes)" \
    || release_fail "Release repository attributes path could not be resolved."
  if [[ "${attributes_path}" != /* ]]; then
    attributes_path="${ROOT_DIR}/${attributes_path}"
  fi
  if [[ -e "${attributes_path}" || -L "${attributes_path}" ]]; then
    release_fail "Release repository must not contain info/attributes."
  fi
}

require_clean_tree() {
  local tree_status
  require_no_hidden_index_entries
  require_release_helpers_match_head
  require_release_git_metadata
  tree_status="$(git_repo status --porcelain=v1 --untracked-files=all --ignore-submodules=none)" \
    || release_fail "Cannot verify the Racer release tree."
  if [[ -n "${tree_status}" ]]; then
    release_fail "Refusing to build or publish from a dirty git tree. Commit or stash changes first."
  fi
}

if [[ "${RELEASE_PHASE}" == "initial" ]]; then
  require_clean_tree

  REEXEC_ENV=(
    "HOME=${HOME}"
    "TMPDIR=${RELEASE_TMPDIR}"
    "PATH=/usr/bin:/bin"
    "LC_ALL=C"
    "LANG=C"
    "TZ=UTC"
  )
  for RELEASE_NAME in ROBLOX_LOBBY_PLACE_ID ROBLOX_RACER_PLACE_ID ROBLOX_UNIVERSE_ID; do
    if [[ -n "${!RELEASE_NAME+x}" ]]; then
      REEXEC_ENV+=("${RELEASE_NAME}=${!RELEASE_NAME}")
    fi
  done
  LOCK_ARGUMENTS=(with-release-lock)
  if [[ "${BUILD_ONLY}" == "true" ]]; then
    LOCK_ARGUMENTS+=(-- /bin/bash -p "${SCRIPT_PATH}" --build-only)
  else
    exec 9< <(builtin printf '%s\0' "${RACER_PUBLISH_API_KEY}")
    unset RACER_PUBLISH_API_KEY
    LOCK_ARGUMENTS+=(--secret-fd 9 -- /bin/bash -p "${SCRIPT_PATH}")
  fi
  exec /usr/bin/env -i "${REEXEC_ENV[@]}" \
    /usr/bin/python3 -I "${STATE_HELPER}" "${LOCK_ARGUMENTS[@]}"
  echo "Cannot exec the Racer release-lock helper." >&2
  exit 1
fi

# This is intentionally the first child after the locked process consumed FD 9.
if ! /usr/bin/env -i \
  HOME="${HOME}" TMPDIR="${RELEASE_TMPDIR}" PATH=/usr/bin:/bin \
  LC_ALL=C LANG=C TZ=UTC \
  RACER_RELEASE_LOCK_CONTEXT="${LOCK_CONTEXT_VALUE}" RACER_RELEASE_LOCK_FD=8 \
  /usr/bin/python3 -I "${STATE_HELPER}" assert-release-lock; then
  unset RACER_PUBLISH_API_KEY
  exit 1
fi

require_clean_tree

state_helper() {
  /usr/bin/env -i \
    HOME="${HOME}" TMPDIR="${RELEASE_TMPDIR}" PATH=/usr/bin:/bin \
    LC_ALL=C LANG=C TZ=UTC \
    /usr/bin/python3 -I "${STATE_HELPER}" "$@"
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
  /usr/bin/env -i TARGET_FILE="$1" PATH=/usr/bin:/bin LC_ALL=C LANG=C \
    /usr/bin/python3 -I -c 'import hashlib
import os
from pathlib import Path

print(hashlib.sha256(Path(os.environ["TARGET_FILE"]).read_bytes()).hexdigest())'
}

TEMP_ROOT=""
INSTALL_TEMP=""

cleanup() {
  if [[ -n "${INSTALL_TEMP}" ]]; then
    /bin/rm -f "${INSTALL_TEMP}"
  fi
  if [[ -n "${TEMP_ROOT}" ]]; then
    /bin/rm -rf "${TEMP_ROOT}"
  fi
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

# A manifest and its private git recovery ref must both be absent before a new build.
require_pending_ref_absent
# Any state file, including a corrupt one, blocks before the artifact can be rebuilt.
state_helper assert-absent

require_clean_tree

GIT_COMMIT="$(git_repo rev-parse HEAD)"
GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 HEAD)"
PUBLISHED_AT="$(/usr/bin/env -i PATH=/usr/bin:/bin TZ=UTC \
  /bin/date -u +"%Y-%m-%dT%H:%M:%SZ")"
TEMP_ROOT="$(/usr/bin/mktemp -d "${RELEASE_TMPDIR}/racer-publish.XXXXXX")"
PRIVATE_ARTIFACT="${TEMP_ROOT}/racer.rbxlx"

/bin/bash -p "${BUILD_HELPER}" \
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
  local output_directory
  output_directory="$(/usr/bin/dirname -- "${OUTPUT_FILE}")"
  /bin/mkdir -p "${output_directory}"
  INSTALL_TEMP="$(/usr/bin/mktemp "${output_directory}/.racer.rbxlx.XXXXXX")"
  /bin/cp "${PRIVATE_ARTIFACT}" "${INSTALL_TEMP}"
  /bin/chmod 0644 "${INSTALL_TEMP}"
  /bin/mv -f "${INSTALL_TEMP}" "${OUTPUT_FILE}"
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
  manifest_sha="$(state_helper "${arguments[@]}")"
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
if [[ "$(state_helper validate-artifact)" != "${BUILD_SHA256}" ]]; then
  echo "Pending publish state no longer matches the Racer release artifact." >&2
  exit 1
fi

if ! PUBLISH_RESPONSE="$(/usr/bin/env -i \
    HOME="${HOME}" TMPDIR="${RELEASE_TMPDIR}" PATH=/usr/bin:/bin \
    LC_ALL=C LANG=C TZ=UTC \
    /usr/bin/curl --disable --fail-with-body \
    --request POST \
    --header @<(builtin printf 'x-api-key: %s\n' "${RACER_PUBLISH_API_KEY}") \
    --header "Content-Type: application/xml" \
    --data-binary @"${PRIVATE_ARTIFACT}" \
    "https://apis.roblox.com/universes/v1/${ROBLOX_UNIVERSE_ID}/places/${PLACE_ID}/versions?versionType=Published" \
    )"; then
  echo "Roblox publish request failed; ${PENDING_LABEL} was retained for recovery." >&2
  exit 1
fi

if ! PLACE_VERSION="$(/usr/bin/env -i PUBLISH_RESPONSE="${PUBLISH_RESPONSE}" \
  PATH=/usr/bin:/bin LC_ALL=C LANG=C /usr/bin/python3 -I -c 'import json
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
state_helper record-version "${PLACE_VERSION}" \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${BUILD_SHA256}"

# Preserve the exact open-file-description across an exec handoff. There is no
# unlock/reacquire window, and the finalizer returns its exact status or signal.
unset RACER_PUBLISH_API_KEY PUBLISH_RESPONSE
if [[ -n "${INSTALL_TEMP}" ]]; then
  /bin/rm -f "${INSTALL_TEMP}"
  INSTALL_TEMP=""
fi
if [[ -n "${TEMP_ROOT}" ]]; then
  /bin/rm -rf "${TEMP_ROOT}"
  TEMP_ROOT=""
fi
trap - EXIT
exec /bin/bash -p "${FINALIZER}" "${PLACE_VERSION}"
echo "Cannot exec the Racer publish finalizer." >&2
exit 1
