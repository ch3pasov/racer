#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

OUTPUT_LABEL="build/racer.rbxlx"
OUTPUT_FILE="${ROOT_DIR}/${OUTPUT_LABEL}"
BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"

git_repo() {
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
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

BUILD_ONLY="false"
if [[ "$#" -eq 0 ]]; then
  :
elif [[ "$#" -eq 1 && "$1" == "--build-only" ]]; then
  BUILD_ONLY="true"
else
  echo "Usage: scripts/publish-place.sh [--build-only]" >&2
  exit 2
fi

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

require_clean_tree

GIT_COMMIT="$(git_repo rev-parse HEAD)"
GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 HEAD)"
PUBLISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/racer-publish.XXXXXX")"
PRIVATE_ARTIFACT="${TEMP_ROOT}/racer.rbxlx"
INSTALL_TEMP=""

cleanup() {
  if [[ -n "${INSTALL_TEMP}" ]]; then
    rm -f "${INSTALL_TEMP}"
  fi
  rm -rf "${TEMP_ROOT}"
}
trap cleanup EXIT

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

require_release_state
atomic_install_artifact

if [[ "${BUILD_ONLY}" == "true" ]]; then
  echo "Built ${OUTPUT_LABEL} for Racer place ${PLACE_ID}"
  echo "Commit: ${GIT_COMMIT}"
  echo "SHA-256: ${BUILD_SHA256}"
  exit 0
fi

: "${ROBLOX_API_KEY:?ROBLOX_API_KEY is required}"
: "${ROBLOX_UNIVERSE_ID:?ROBLOX_UNIVERSE_ID is required}"
if [[ ! "${ROBLOX_UNIVERSE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ROBLOX_UNIVERSE_ID must be a positive decimal integer." >&2
  exit 2
fi

PREFLIGHT_TAG="racer-publish-preflight-$$"
if git_repo rev-parse --verify --quiet "refs/tags/${PREFLIGHT_TAG}" >/dev/null; then
  echo "Temporary publish preflight tag unexpectedly exists: ${PREFLIGHT_TAG}." >&2
  exit 1
fi
git_repo update-ref "refs/tags/${PREFLIGHT_TAG}" "${GIT_COMMIT}" ""
git_repo update-ref -d "refs/tags/${PREFLIGHT_TAG}" "${GIT_COMMIT}"

require_release_state

PUBLISH_RESPONSE="$(env -u ROBLOX_API_KEY curl --fail-with-body \
  --request POST \
  --header @<(builtin printf 'x-api-key: %s\n' "${ROBLOX_API_KEY}") \
  --header "Content-Type: application/xml" \
  --data-binary @"${PRIVATE_ARTIFACT}" \
  "https://apis.roblox.com/universes/v1/${ROBLOX_UNIVERSE_ID}/places/${PLACE_ID}/versions?versionType=Published")"

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
  exit 1
fi

TAG="racer-place-v${PLACE_VERSION}"
if git_repo rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null; then
  echo "Refusing to move existing immutable publish tag ${TAG}." >&2
  exit 1
fi
git_repo tag "${TAG}" "${GIT_COMMIT}"

TAG_COMMIT="$(git_repo rev-parse "refs/tags/${TAG}^{commit}")"
if [[ "${TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
  echo "Publish tag ${TAG} did not resolve to the published commit ${GIT_COMMIT}." >&2
  exit 1
fi

LOOKUP_OUTPUT="$("${SCRIPT_DIR}/lookup-place-version.sh" "${PLACE_VERSION}")"
if [[ "${LOOKUP_OUTPUT}" != *"Commit: ${GIT_COMMIT}"* ]]; then
  echo "PlaceVersion lookup did not resolve ${PLACE_VERSION} to ${GIT_COMMIT}." >&2
  exit 1
fi
printf '%s\n' "${LOOKUP_OUTPUT}"
echo "Tagged ${TAG} -> ${GIT_COMMIT_SHORT}"

echo "Published Racer Lab place ${PLACE_ID} in universe ${ROBLOX_UNIVERSE_ID}"
