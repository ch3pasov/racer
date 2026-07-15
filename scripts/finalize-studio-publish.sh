#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"
LOOKUP_SCRIPT="${SCRIPT_DIR}/lookup-place-version.sh"
PENDING_LABEL="build/racer-publish-pending.json"
RELEASE_LOCK_DIR="${ROOT_DIR}/build/.racer-publish-release.lock"
RELEASE_LOCK_HELD="false"

git_repo() {
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

require_clean_tree() {
  local tree_status
  tree_status="$(git_repo status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  if [[ -n "${tree_status}" ]]; then
    echo "Refusing to finalize a Racer publish from a dirty git tree." >&2
    exit 1
  fi
}

release_publish_lock() {
  if [[ "${RELEASE_LOCK_HELD}" == "true" ]]; then
    rmdir "${RELEASE_LOCK_DIR}"
    RELEASE_LOCK_HELD="false"
  fi
}

cleanup() {
  release_publish_lock
}
trap cleanup EXIT

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
if [[ ! -x "${LOOKUP_SCRIPT}" ]]; then
  echo "PlaceVersion lookup script is missing or not executable." >&2
  exit 1
fi

mkdir -p "$(dirname -- "${RELEASE_LOCK_DIR}")"
if ! mkdir "${RELEASE_LOCK_DIR}"; then
  echo "Another Racer release operation holds ${RELEASE_LOCK_DIR#"${ROOT_DIR}/"}." >&2
  echo "If no release process is running, inspect pending state before removing a stale lock." >&2
  exit 1
fi
RELEASE_LOCK_HELD="true"

MANIFEST_FIELDS=()
while IFS= read -r field; do
  MANIFEST_FIELDS+=("${field}")
done < <("${STATE_HELPER}" inspect)
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

VALIDATED_SHA256="$("${STATE_HELPER}" validate-artifact)"
if [[ "${VALIDATED_SHA256}" != "${ARTIFACT_SHA256}" ]]; then
  echo "Validated Racer artifact SHA-256 changed unexpectedly." >&2
  exit 1
fi

# Record a manually verified or recovered version before touching its git tag.
"${STATE_HELPER}" record-version "${PLACE_VERSION}" \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${ARTIFACT_SHA256}"

if [[ "$(git_repo rev-parse HEAD)" != "${STARTING_HEAD}" ]]; then
  echo "HEAD changed while validating the Racer publish." >&2
  exit 1
fi
require_clean_tree

TAG="racer-place-v${PLACE_VERSION}"
if EXISTING_TAG_COMMIT="$(git_repo rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)"; then
  if [[ "${EXISTING_TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
    echo "Immutable publish tag ${TAG} already points to another commit." >&2
    exit 1
  fi
else
  # An empty expected old value makes this an atomic create-only operation.
  if ! git_repo update-ref "refs/tags/${TAG}" "${GIT_COMMIT}" ""; then
    if ! EXISTING_TAG_COMMIT="$(git_repo rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)" \
      || [[ "${EXISTING_TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
      echo "Failed to create immutable publish tag ${TAG}." >&2
      exit 1
    fi
  fi
fi

TAG_COMMIT="$(git_repo rev-parse "refs/tags/${TAG}^{commit}")"
if [[ "${TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
  echo "Publish tag ${TAG} does not resolve to ${GIT_COMMIT}." >&2
  exit 1
fi

if ! LOOKUP_OUTPUT="$("${LOOKUP_SCRIPT}" "${PLACE_VERSION}")"; then
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
if [[ "$("${STATE_HELPER}" validate-artifact)" != "${ARTIFACT_SHA256}" ]]; then
  echo "Racer release artifact changed before pending state could be cleared." >&2
  exit 1
fi
if [[ "$(git_repo rev-parse "refs/tags/${TAG}^{commit}")" != "${GIT_COMMIT}" ]]; then
  echo "Publish tag changed before pending state could be cleared." >&2
  exit 1
fi

"${STATE_HELPER}" clear \
  --git-commit "${GIT_COMMIT}" \
  --artifact-sha256 "${ARTIFACT_SHA256}" \
  --place-version "${PLACE_VERSION}"

printf '%s\n' "${LOOKUP_OUTPUT}"
echo "Recorded Racer publish ${TAG} -> ${GIT_COMMIT_SHORT}"
echo "Artifact: ${ARTIFACT_LABEL} (${ARTIFACT_SIZE} bytes, ${ARTIFACT_SHA256})"
echo "Embedded PublishedAt: ${PUBLISHED_AT}"
