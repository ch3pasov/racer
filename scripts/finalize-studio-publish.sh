#!/bin/bash -p
set +x
set +a
unset ROBLOX_API_KEY RACER_PUBLISH_API_KEY
set -euo pipefail

LOCK_CONTEXT_VALUE="racer-release-lock-v1"

if [[ "$#" -ne 1 ]]; then
  echo "Usage: scripts/finalize-studio-publish.sh <roblox-place-version>" >&2
  echo "Verify this PlaceVersion and the embedded commit in Studio before running." >&2
  exit 2
fi

PLACE_VERSION="$1"
if [[ ! "${PLACE_VERSION}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Roblox place version must be a positive decimal integer." >&2
  exit 2
fi

if [[ -z "${RACER_RELEASE_LOCK_CONTEXT+x}" && -z "${RACER_RELEASE_LOCK_FD+x}" ]]; then
  RELEASE_PHASE="initial"
elif [[ "${RACER_RELEASE_LOCK_CONTEXT-}" == "${LOCK_CONTEXT_VALUE}" \
  && "${RACER_RELEASE_LOCK_FD-}" == "8" ]]; then
  RELEASE_PHASE="locked"
else
  echo "Racer release lock context is missing, partial, or spoofed." >&2
  exit 1
fi
if [[ -n "${RACER_RELEASE_SECRET_CONTEXT+x}" \
  || -n "${RACER_RELEASE_SECRET_FD+x}" ]]; then
  echo "Racer publish finalizer received an unexpected secret context." >&2
  exit 1
fi
if { builtin true <&9; } 2>/dev/null; then
  exec 9<&-
  echo "Racer publish finalizer received an unexpected secret FD." >&2
  exit 1
fi

SCRIPT_SOURCE="${BASH_SOURCE[0]}"
case "${SCRIPT_SOURCE}" in
  /*) SCRIPT_CANDIDATE="${SCRIPT_SOURCE}" ;;
  */*) SCRIPT_CANDIDATE="${PWD}/${SCRIPT_SOURCE}" ;;
  *)
    echo "Finalizer must be invoked through an explicit path." >&2
    exit 1
    ;;
esac
SCRIPT_BASENAME="${SCRIPT_CANDIDATE##*/}"
SCRIPT_PARENT="$(/usr/bin/dirname -- "${SCRIPT_CANDIDATE}")"
builtin cd -P -- "${SCRIPT_PARENT}"
SCRIPT_DIR="${PWD}"
SCRIPT_PATH="${SCRIPT_DIR}/${SCRIPT_BASENAME}"
builtin cd -P -- "${SCRIPT_DIR}/.."
ROOT_DIR="${PWD}"
if [[ "${SCRIPT_PATH}" != "${ROOT_DIR}/scripts/finalize-studio-publish.sh" \
  || -L "${SCRIPT_PATH}" || ! -f "${SCRIPT_PATH}" ]]; then
  echo "Finalizer path is not the trusted repository script." >&2
  exit 1
fi

STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"
BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"
LOOKUP_SCRIPT="${SCRIPT_DIR}/lookup-place-version.sh"
PENDING_LABEL="build/racer-publish-pending.json"
PENDING_REF="refs/racer-publish/pending"
TEMP_ROOT=""

if [[ -z "${HOME:-}" || "${HOME}" != /* ]]; then
  echo "Racer releases require an absolute HOME." >&2
  exit 1
fi
RELEASE_TMPDIR="${TMPDIR:-/tmp}"
if [[ "${RELEASE_TMPDIR}" != /* ]]; then
  echo "Racer releases require an absolute TMPDIR." >&2
  exit 1
fi

if [[ "${RELEASE_PHASE}" == "initial" ]]; then
  if ! EARLY_TREE_STATUS="$(
    /usr/bin/env -i \
      HOME=/ XDG_CONFIG_HOME=/dev/null PATH=/usr/bin:/bin LC_ALL=C LANG=C TZ=UTC \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
      /usr/bin/git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" \
      status --porcelain=v1 --untracked-files=all --ignore-submodules=none
  )"; then
    echo "Cannot verify the Racer release tree before lock handoff." >&2
    exit 1
  fi
  if [[ -n "${EARLY_TREE_STATUS}" ]]; then
    echo "Refusing to finalize a Racer publish from a dirty git tree." >&2
    exit 1
  fi
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
  exec /usr/bin/env -i "${REEXEC_ENV[@]}" \
    /usr/bin/python3 -I "${STATE_HELPER}" with-release-lock -- \
    /bin/bash -p "${SCRIPT_PATH}" "${PLACE_VERSION}"
  echo "Cannot exec the Racer release-lock helper." >&2
  exit 1
fi

if ! /usr/bin/env -i \
  HOME="${HOME}" TMPDIR="${RELEASE_TMPDIR}" PATH=/usr/bin:/bin \
  LC_ALL=C LANG=C TZ=UTC \
  RACER_RELEASE_LOCK_CONTEXT="${LOCK_CONTEXT_VALUE}" RACER_RELEASE_LOCK_FD=8 \
  /usr/bin/python3 -I "${STATE_HELPER}" assert-release-lock; then
  exit 1
fi

state_helper() {
  /usr/bin/env -i \
    HOME="${HOME}" TMPDIR="${RELEASE_TMPDIR}" PATH=/usr/bin:/bin \
    LC_ALL=C LANG=C TZ=UTC \
    /usr/bin/python3 -I "${STATE_HELPER}" "$@"
}

git_repo() {
  /usr/bin/env -i \
    HOME=/ XDG_CONFIG_HOME=/dev/null PATH=/usr/bin:/bin LC_ALL=C LANG=C TZ=UTC \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    /usr/bin/git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

PENDING_REF_COMMIT=""
PENDING_REF_EXPECTED_PRESENT="false"

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

require_final_tag_direct_ref() {
  local status
  local symbolic_target

  if symbolic_target="$(git_repo symbolic-ref -q "refs/tags/${TAG}" 2>/dev/null)"; then
    echo "Immutable publish tag ${TAG} must not be symbolic (${symbolic_target})." >&2
    return 1
  else
    status=$?
  fi
  if [[ "${status}" -ne 1 ]]; then
    echo "Immutable publish tag ${TAG} symbolic state could not be inspected." >&2
    return 1
  fi
  return 0
}

final_tag_points_to_commit() {
  local tag_commit

  if ! require_final_tag_direct_ref; then
    return 1
  fi

  if ! tag_commit="$(git_repo rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)"; then
    return 1
  fi
  [[ "${tag_commit}" == "${GIT_COMMIT}" ]]
}

require_pending_ref_state() {
  local status

  if inspect_pending_ref; then
    if [[ "${PENDING_REF_EXPECTED_PRESENT}" != "true" ]]; then
      echo "Racer pending recovery ref unexpectedly reappeared after deletion." >&2
      exit 1
    fi
    if [[ "${PENDING_REF_COMMIT}" != "${GIT_COMMIT}" ]]; then
      echo "Racer pending recovery ref does not match the manifest commit." >&2
      exit 1
    fi
    return
  else
    status=$?
  fi
  if [[ "${status}" -ne 1 ]]; then
    exit 1
  fi
  if [[ "${PENDING_REF_EXPECTED_PRESENT}" == "true" ]]; then
    echo "Racer pending recovery ref disappeared before finalization completed." >&2
    exit 1
  fi
  if [[ "${RECORDED_PLACE_VERSION}" != "${PLACE_VERSION}" ]] \
    || ! final_tag_points_to_commit; then
    echo "Missing recovery ref is valid only after the exact publish tag exists." >&2
    exit 1
  fi
}

delete_pending_ref() {
  local status

  if [[ "${PENDING_REF_EXPECTED_PRESENT}" == "true" ]]; then
    if ! git_repo update-ref --no-deref -d "${PENDING_REF}" "${GIT_COMMIT}"; then
      if inspect_pending_ref; then
        echo "Failed to delete the Racer pending recovery ref with its commit guard." >&2
        exit 1
      else
        status=$?
      fi
      if [[ "${status}" -ne 1 ]] || ! final_tag_points_to_commit; then
        echo "Racer pending recovery ref deletion could not be verified." >&2
        exit 1
      fi
    fi
    PENDING_REF_EXPECTED_PRESENT="false"
  fi
  require_pending_ref_state
}

require_clean_tree() {
  local tree_status
  tree_status="$(git_repo status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  if [[ -n "${tree_status}" ]]; then
    echo "Refusing to finalize a Racer publish from a dirty git tree." >&2
    exit 1
  fi
}

sha256_file() {
  /usr/bin/env -i TARGET_FILE="$1" PATH=/usr/bin:/bin LC_ALL=C LANG=C \
    /usr/bin/python3 -I -c 'import hashlib
import os
from pathlib import Path

print(hashlib.sha256(Path(os.environ["TARGET_FILE"]).read_bytes()).hexdigest())'
}

file_size() {
  /usr/bin/env -i TARGET_FILE="$1" PATH=/usr/bin:/bin LC_ALL=C LANG=C \
    /usr/bin/python3 -I -c 'import os

print(os.stat(os.environ["TARGET_FILE"], follow_symlinks=False).st_size)'
}

cleanup() {
  if [[ -n "${TEMP_ROOT}" ]]; then
    /bin/rm -rf "${TEMP_ROOT}"
  fi
}
trap cleanup EXIT

: "${ROBLOX_RACER_PLACE_ID:?ROBLOX_RACER_PLACE_ID is required}"
PLACE_ID="${ROBLOX_RACER_PLACE_ID}"
if [[ ! "${PLACE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ROBLOX_RACER_PLACE_ID must be a positive decimal integer." >&2
  exit 2
fi
if [[ -n "${ROBLOX_LOBBY_PLACE_ID:-}" && ! "${ROBLOX_LOBBY_PLACE_ID}" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "ROBLOX_LOBBY_PLACE_ID must be zero or a positive decimal integer." >&2
  exit 2
fi
if [[ -n "${ROBLOX_UNIVERSE_ID:-}" && ! "${ROBLOX_UNIVERSE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ROBLOX_UNIVERSE_ID must be a positive decimal integer." >&2
  exit 2
fi

if [[ ! -x "${STATE_HELPER}" ]]; then
  echo "Pending publish state helper is missing or not executable." >&2
  exit 1
fi
if [[ ! -x "${BUILD_HELPER}" ]]; then
  echo "Release snapshot builder is missing or not executable." >&2
  exit 1
fi
if [[ ! -x "${LOOKUP_SCRIPT}" ]]; then
  echo "PlaceVersion lookup script is missing or not executable." >&2
  exit 1
fi

MANIFEST_FIELDS=()
while IFS= read -r field; do
  MANIFEST_FIELDS+=("${field}")
done < <(state_helper inspect)
if [[ "${#MANIFEST_FIELDS[@]}" -ne 12 ]]; then
  echo "Pending publish state did not return its complete validated identity." >&2
  exit 1
fi

PUBLISH_MODE="${MANIFEST_FIELDS[0]}"
GIT_COMMIT="${MANIFEST_FIELDS[2]}"
GIT_COMMIT_SHORT="${MANIFEST_FIELDS[3]}"
PUBLISHED_AT="${MANIFEST_FIELDS[4]}"
ARTIFACT_LABEL="${MANIFEST_FIELDS[5]}"
ARTIFACT_SHA256="${MANIFEST_FIELDS[6]}"
ARTIFACT_SIZE="${MANIFEST_FIELDS[7]}"
UNIVERSE_ID="${MANIFEST_FIELDS[8]}"
MANIFEST_PLACE_ID="${MANIFEST_FIELDS[9]}"
LOBBY_PLACE_ID="${MANIFEST_FIELDS[10]}"
RECORDED_PLACE_VERSION="${MANIFEST_FIELDS[11]}"
TAG="racer-place-v${PLACE_VERSION}"

if [[ "${PLACE_ID}" != "${MANIFEST_PLACE_ID}" ]]; then
  echo "ROBLOX_RACER_PLACE_ID does not match the pending Racer place." >&2
  exit 1
fi
if [[ -n "${ROBLOX_LOBBY_PLACE_ID:-}" && "${ROBLOX_LOBBY_PLACE_ID}" != "${LOBBY_PLACE_ID}" ]]; then
  echo "ROBLOX_LOBBY_PLACE_ID does not match the pending lobby place." >&2
  exit 1
fi
if [[ "${PUBLISH_MODE}" == "open-cloud" && -n "${ROBLOX_UNIVERSE_ID:-}" && "${ROBLOX_UNIVERSE_ID}" != "${UNIVERSE_ID}" ]]; then
  echo "ROBLOX_UNIVERSE_ID does not match the pending Open Cloud universe." >&2
  exit 1
fi
if [[ "${RECORDED_PLACE_VERSION}" != "-" && "${RECORDED_PLACE_VERSION}" != "${PLACE_VERSION}" ]]; then
  echo "Pending publish records PlaceVersion ${RECORDED_PLACE_VERSION}, not ${PLACE_VERSION}." >&2
  exit 1
fi

PENDING_REF_STATUS=0
if inspect_pending_ref; then
  PENDING_REF_EXPECTED_PRESENT="true"
  if [[ "${PENDING_REF_COMMIT}" != "${GIT_COMMIT}" ]]; then
    echo "Racer pending recovery ref does not match the manifest commit." >&2
    exit 1
  fi
else
  PENDING_REF_STATUS=$?
  if [[ "${PENDING_REF_STATUS}" -ne 1 ]]; then
    exit 1
  fi
  PENDING_REF_EXPECTED_PRESENT="false"
  if [[ "${RECORDED_PLACE_VERSION}" != "${PLACE_VERSION}" ]] \
    || ! final_tag_points_to_commit; then
    echo "Pending recovery ref is missing before its exact publish tag was finalized." >&2
    exit 1
  fi
fi

require_clean_tree
STARTING_HEAD="$(git_repo rev-parse HEAD)"
if ! RESOLVED_COMMIT="$(git_repo rev-parse --verify "${GIT_COMMIT}^{commit}")"; then
  echo "Pending publish commit is not available in this repository: ${GIT_COMMIT}" >&2
  exit 1
fi
if [[ "${RESOLVED_COMMIT}" != "${GIT_COMMIT}" ]]; then
  echo "Pending publish commit did not resolve to its exact object id." >&2
  exit 1
fi

VALIDATED_SHA256="$(state_helper validate-artifact)"
if [[ "${VALIDATED_SHA256}" != "${ARTIFACT_SHA256}" ]]; then
  echo "Validated Racer artifact SHA-256 changed unexpectedly." >&2
  exit 1
fi

ARTIFACT_FILE="${ROOT_DIR}/${ARTIFACT_LABEL}"
if [[ ! -f "${ARTIFACT_FILE}" || -L "${ARTIFACT_FILE}" ]]; then
  echo "Validated Racer release artifact is missing or is not a regular file." >&2
  exit 1
fi
ORIGINAL_ARTIFACT_SHA256="$(sha256_file "${ARTIFACT_FILE}")"
ORIGINAL_ARTIFACT_SIZE="$(file_size "${ARTIFACT_FILE}")"
if [[ "${ORIGINAL_ARTIFACT_SHA256}" != "${ARTIFACT_SHA256}" ]]; then
  echo "Original Racer artifact SHA-256 does not match its validated manifest." >&2
  exit 1
fi
if [[ "${ORIGINAL_ARTIFACT_SIZE}" != "${ARTIFACT_SIZE}" ]]; then
  echo "Original Racer artifact size does not match its validated manifest." >&2
  exit 1
fi

TEMP_ROOT="$(/usr/bin/mktemp -d "${RELEASE_TMPDIR}/racer-finalize.XXXXXX")"
REBUILT_ARTIFACT="${TEMP_ROOT}/racer-rebuilt.rbxlx"
/bin/bash -p "${BUILD_HELPER}" \
  "${GIT_COMMIT}" \
  "${PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${MANIFEST_PLACE_ID}" \
  "${REBUILT_ARTIFACT}"

REBUILT_ARTIFACT_SHA256="$(sha256_file "${REBUILT_ARTIFACT}")"
REBUILT_ARTIFACT_SIZE="$(file_size "${REBUILT_ARTIFACT}")"
if [[ "${REBUILT_ARTIFACT_SHA256}" != "${ARTIFACT_SHA256}" ]]; then
  echo "Rebuilt Racer artifact SHA-256 does not match the pending manifest." >&2
  exit 1
fi
if [[ "${REBUILT_ARTIFACT_SIZE}" != "${ARTIFACT_SIZE}" ]]; then
  echo "Rebuilt Racer artifact size does not match the pending manifest." >&2
  exit 1
fi
if ! /usr/bin/cmp -s "${ARTIFACT_FILE}" "${REBUILT_ARTIFACT}"; then
  echo "Racer release artifact is not the exact reproducible build of its pending commit." >&2
  exit 1
fi

require_original_artifact_state() {
  if [[ "$(git_repo rev-parse HEAD)" != "${STARTING_HEAD}" ]]; then
    echo "HEAD changed while validating the Racer publish." >&2
    exit 1
  fi
  require_clean_tree
  if [[ ! -f "${ARTIFACT_FILE}" || -L "${ARTIFACT_FILE}" ]]; then
    echo "Original Racer release artifact is missing or is not a regular file." >&2
    exit 1
  fi
  if [[ "$(file_size "${ARTIFACT_FILE}")" != "${ORIGINAL_ARTIFACT_SIZE}" ]]; then
    echo "Original Racer release artifact size changed during finalization." >&2
    exit 1
  fi
  if [[ "$(sha256_file "${ARTIFACT_FILE}")" != "${ORIGINAL_ARTIFACT_SHA256}" ]]; then
    echo "Original Racer release artifact changed during finalization." >&2
    exit 1
  fi
}

require_original_artifact_state
require_pending_ref_state

# Record a manually verified or recovered version before touching its git tag.
state_helper record-version "${PLACE_VERSION}" \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${ARTIFACT_SHA256}"
RECORDED_PLACE_VERSION="${PLACE_VERSION}"

require_original_artifact_state
require_pending_ref_state

if ! require_final_tag_direct_ref; then
  exit 1
fi
if EXISTING_TAG_COMMIT="$(git_repo rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)"; then
  if [[ "${EXISTING_TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
    echo "Immutable publish tag ${TAG} already points to another commit." >&2
    exit 1
  fi
else
  # An empty expected old value makes this an atomic create-only operation.
  if ! git_repo update-ref --no-deref "refs/tags/${TAG}" "${GIT_COMMIT}" ""; then
    if ! final_tag_points_to_commit; then
      echo "Failed to create immutable publish tag ${TAG}." >&2
      exit 1
    fi
  fi
fi

if ! final_tag_points_to_commit; then
  echo "Publish tag ${TAG} does not resolve to ${GIT_COMMIT}." >&2
  exit 1
fi

if ! LOOKUP_OUTPUT="$(/bin/bash -p "${LOOKUP_SCRIPT}" "${PLACE_VERSION}")"; then
  echo "PlaceVersion lookup failed; ${PENDING_LABEL} was retained." >&2
  exit 1
fi
LOOKUP_COMMIT_FOUND="false"
while IFS= read -r lookup_line; do
  if [[ "${lookup_line}" == "Commit: ${GIT_COMMIT}" ]]; then
    LOOKUP_COMMIT_FOUND="true"
  fi
done <<< "${LOOKUP_OUTPUT}"
if [[ "${LOOKUP_COMMIT_FOUND}" != "true" ]]; then
  echo "PlaceVersion lookup did not resolve exactly to ${GIT_COMMIT}." >&2
  exit 1
fi

# Recheck every mutable local input before deleting the only recovery record.
if [[ "$(git_repo rev-parse HEAD)" != "${STARTING_HEAD}" ]]; then
  echo "HEAD changed before pending publish state could be cleared." >&2
  exit 1
fi
require_clean_tree
if [[ "$(state_helper validate-artifact)" != "${ARTIFACT_SHA256}" ]]; then
  echo "Racer release artifact changed before pending state could be cleared." >&2
  exit 1
fi
if [[ "$(git_repo rev-parse "refs/tags/${TAG}^{commit}")" != "${GIT_COMMIT}" ]]; then
  echo "Publish tag changed before pending state could be cleared." >&2
  exit 1
fi
require_pending_ref_state

# The immutable tag now keeps the commit reachable. Delete only the exact
# recovery ref, then clear its manifest. A retry can resume between these steps.
delete_pending_ref

state_helper clear \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${ARTIFACT_SHA256}" \
  --place-version "${PLACE_VERSION}"

printf '%s\n' "${LOOKUP_OUTPUT}"
echo "Recorded Racer publish ${TAG} -> ${GIT_COMMIT_SHORT}"
echo "Artifact: ${ARTIFACT_LABEL} (${ARTIFACT_SIZE} bytes, ${ARTIFACT_SHA256})"
echo "Embedded PublishedAt: ${PUBLISHED_AT}"
