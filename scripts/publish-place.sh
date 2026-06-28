#!/usr/bin/env bash
set -euo pipefail

: "${ROBLOX_API_KEY:?ROBLOX_API_KEY is required}"
: "${ROBLOX_UNIVERSE_ID:?ROBLOX_UNIVERSE_ID is required}"

PROJECT_FILE="racer.project.json"
OUTPUT_FILE="build/racer.rbxlx"
PLACE_ID="${ROBLOX_RACER_PLACE_ID:-${ROBLOX_PLACE_ID:-}}"
BUILD_INFO_FILE="src/shared/GeneratedBuildInfo.lua"
PLACE_IDS_FILE="src/shared/GeneratedPlaceIds.lua"

git_repo() {
  git -c safe.directory="${PWD}" "$@"
}

if [[ "${1:-}" != "" ]]; then
  echo "Racer Lab is the only publish target in this repository; run scripts/publish-place.sh without arguments." >&2
  exit 2
fi

: "${PLACE_ID:?ROBLOX_RACER_PLACE_ID or ROBLOX_PLACE_ID is required}"

if ! git_repo diff --quiet --ignore-submodules -- || ! git_repo diff --cached --quiet --ignore-submodules --; then
  echo "Refusing to publish from a dirty git tree. Commit or stash changes first." >&2
  exit 1
fi

GIT_COMMIT="$(git_repo rev-parse HEAD)"
GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 HEAD)"
PUBLISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ORIGINAL_BUILD_INFO="$(mktemp)"
ORIGINAL_PLACE_IDS="$(mktemp)"
cp "${BUILD_INFO_FILE}" "${ORIGINAL_BUILD_INFO}"
cp "${PLACE_IDS_FILE}" "${ORIGINAL_PLACE_IDS}"
restore_build_info() {
  cp "${ORIGINAL_BUILD_INFO}" "${BUILD_INFO_FILE}"
  cp "${ORIGINAL_PLACE_IDS}" "${PLACE_IDS_FILE}"
  rm -f "${ORIGINAL_BUILD_INFO}"
  rm -f "${ORIGINAL_PLACE_IDS}"
}
trap restore_build_info EXIT

mkdir -p build
cat > "${PLACE_IDS_FILE}" <<EOF
return {
	LobbyPlaceId = ${ROBLOX_LOBBY_PLACE_ID:-0},
	RacerPlaceId = ${PLACE_ID},
}
EOF
cat > "${BUILD_INFO_FILE}" <<EOF
return {
	GitCommit = "${GIT_COMMIT}",
	GitCommitShort = "${GIT_COMMIT_SHORT}",
	PublishedAt = "${PUBLISHED_AT}",
}
EOF

rojo build "${PROJECT_FILE}" --output "${OUTPUT_FILE}"

PUBLISH_RESPONSE="$(curl --fail-with-body \
  --request POST \
  --header "x-api-key: ${ROBLOX_API_KEY}" \
  --header "Content-Type: application/xml" \
  --data-binary @"${OUTPUT_FILE}" \
  "https://apis.roblox.com/universes/v1/${ROBLOX_UNIVERSE_ID}/places/${PLACE_ID}/versions?versionType=Published")"

PLACE_VERSION="$(printf '%s' "${PUBLISH_RESPONSE}" \
  | sed -nE 's/.*"(versionNumber|placeVersion|version)"[[:space:]]*:[[:space:]]*"?([0-9]+)"?.*/\2/p' \
  | head -n 1)"
if [[ "${PLACE_VERSION}" == "" ]]; then
  PLACE_VERSION="$(printf '%s' "${PUBLISH_RESPONSE}" | sed -nE 's/^[^0-9]*([0-9]+)[^0-9]*$/\1/p' | head -n 1)"
fi

if [[ "${PLACE_VERSION}" != "" ]]; then
  git_repo tag -f "racer-place-v${PLACE_VERSION}" "${GIT_COMMIT}" >/dev/null
  echo "Tagged racer-place-v${PLACE_VERSION} -> ${GIT_COMMIT_SHORT}"
else
  echo "Published response did not include a recognizable place version:" >&2
  echo "${PUBLISH_RESPONSE}" >&2
fi

echo "Published Racer Lab place ${PLACE_ID} in universe ${ROBLOX_UNIVERSE_ID}"
