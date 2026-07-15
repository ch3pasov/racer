#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

EXPECTED_ROJO_VERSION="Rojo 7.5.1"

git_repo() {
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

if [[ "$#" -ne 5 ]]; then
  echo "Usage: scripts/build-racer-release.sh <git-commit> <published-at> <lobby-place-id> <racer-place-id> <absolute-output>" >&2
  exit 2
fi

GIT_COMMIT="$1"
PUBLISHED_AT="$2"
LOBBY_PLACE_ID="$3"
RACER_PLACE_ID="$4"
OUTPUT_FILE="$5"

if ! RESOLVED_COMMIT="$(git_repo rev-parse --verify "${GIT_COMMIT}^{commit}")"; then
  echo "Release commit does not resolve to a git commit: ${GIT_COMMIT}" >&2
  exit 2
fi
if [[ "${RESOLVED_COMMIT}" != "${GIT_COMMIT}" ]]; then
  echo "Release commit must be the full immutable git object id." >&2
  exit 2
fi
if [[ ! "${PUBLISHED_AT}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]; then
  echo "PublishedAt must be a UTC timestamp in YYYY-MM-DDTHH:MM:SSZ form." >&2
  exit 2
fi
if [[ ! "${LOBBY_PLACE_ID}" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "Lobby place id must be zero or a positive decimal integer." >&2
  exit 2
fi
if [[ ! "${RACER_PLACE_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Racer place id must be a positive decimal integer." >&2
  exit 2
fi
if [[ "${OUTPUT_FILE}" != /* ]]; then
  echo "Release output path must be absolute." >&2
  exit 2
fi

if ! ACTUAL_ROJO_VERSION="$(LC_ALL=C rojo --version)"; then
  echo "Unable to run the pinned Rojo release builder." >&2
  exit 1
fi
if [[ "${ACTUAL_ROJO_VERSION}" != "${EXPECTED_ROJO_VERSION}" ]]; then
  echo "Release builds require ${EXPECTED_ROJO_VERSION}; found ${ACTUAL_ROJO_VERSION}." >&2
  exit 1
fi

GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 "${GIT_COMMIT}^{commit}")"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/racer-release-build.XXXXXX")"
SNAPSHOT_DIR="${TEMP_ROOT}/snapshot"
ARCHIVE_FILE="${TEMP_ROOT}/source.tar"
SNAPSHOT_OUTPUT="${TEMP_ROOT}/racer.rbxlx"
OUTPUT_TEMP=""

cleanup() {
  if [[ -n "${OUTPUT_TEMP}" ]]; then
    rm -f "${OUTPUT_TEMP}"
  fi
  rm -rf "${TEMP_ROOT}"
}
trap cleanup EXIT

mkdir -p "${SNAPSHOT_DIR}"
git_repo archive --format=tar --output="${ARCHIVE_FILE}" "${GIT_COMMIT}"
tar -xf "${ARCHIVE_FILE}" -C "${SNAPSHOT_DIR}"

BUILD_INFO_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedBuildInfo.lua"
PLACE_IDS_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedPlaceIds.lua"
if [[ ! -f "${BUILD_INFO_FILE}" || ! -f "${PLACE_IDS_FILE}" ]]; then
  echo "Release snapshot is missing the tracked generated metadata modules." >&2
  exit 1
fi

cat > "${PLACE_IDS_FILE}" <<EOF
return {
	LobbyPlaceId = ${LOBBY_PLACE_ID},
	RacerPlaceId = ${RACER_PLACE_ID},
}
EOF
cat > "${BUILD_INFO_FILE}" <<EOF
return {
	GitCommit = "${GIT_COMMIT}",
	GitCommitShort = "${GIT_COMMIT_SHORT}",
	PublishedAt = "${PUBLISHED_AT}",
}
EOF

(
  cd "${SNAPSHOT_DIR}"
  LC_ALL=C rojo build "racer.project.json" --output "${SNAPSHOT_OUTPUT}"
)

OUTPUT_DIR="$(dirname -- "${OUTPUT_FILE}")"
mkdir -p "${OUTPUT_DIR}"
OUTPUT_TEMP="$(mktemp "${OUTPUT_DIR}/.racer-release.XXXXXX")"
cp "${SNAPSHOT_OUTPUT}" "${OUTPUT_TEMP}"
chmod 0644 "${OUTPUT_TEMP}"
mv -f "${OUTPUT_TEMP}" "${OUTPUT_FILE}"
OUTPUT_TEMP=""
