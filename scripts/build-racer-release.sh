#!/bin/bash -p
set +x
set +a
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"

EXPECTED_ROJO_VERSION="Rojo 7.5.1"
ROJO_STORAGE_VERSION="7.5.1"
TOOLCHAIN_MANIFEST_RELATIVE="scripts/racer-release-toolchain.tsv"

fail() {
  echo "$1" >&2
  exit 1
}

detect_release_platform() {
  local kernel machine
  kernel="$(/usr/bin/uname -s)"
  machine="$(/usr/bin/uname -m)"
  case "${kernel}:${machine}" in
    Linux:x86_64|Linux:amd64)
      printf '%s\n' "linux-x86_64"
      ;;
    Darwin:arm64)
      printf '%s\n' "darwin-arm64"
      ;;
    Darwin:x86_64)
      printf '%s\n' "darwin-x86_64"
      ;;
    *)
      echo "Unsupported release-builder platform: ${kernel} ${machine}" >&2
      return 1
      ;;
  esac
}

sha256_file() {
  local digest output
  if [[ "${RELEASE_PLATFORM}" == darwin-* ]]; then
    output="$(
      /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/shasum -a 256 -- "$1"
    )" || return 1
  else
    output="$(
      /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C \
        /usr/bin/sha256sum -- "$1"
    )" || return 1
  fi
  digest="${output%%[[:space:]]*}"
  if [[ ! "${digest}" =~ ^[0-9a-f]{64}$ ]]; then
    echo "Unable to parse SHA-256 output for $1" >&2
    return 1
  fi
  printf '%s\n' "${digest}"
}

load_toolchain_manifest() {
  local manifest="$1"
  local archive_sha256 binary_sha256 expected_platform extra line record platform
  local line_number=0

  if [[ -L "${manifest}" || ! -f "${manifest}" ]]; then
    fail "Release snapshot toolchain manifest must be a regular non-symlink file."
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line_number=$((line_number + 1))
    if [[ -z "${line}" || "${line}" == *$'\r'* ]]; then
      fail "Release snapshot toolchain manifest contains a malformed line."
    fi
    case "${line_number}" in
      1)
        if [[ "${line}" != $'schema\tracer-release-toolchain-v1' ]]; then
          fail "Release snapshot toolchain manifest has an unsupported schema."
        fi
        ;;
      2)
        if [[ "${line}" != $'tool\trojo-rbx/rojo\t7.5.1' ]]; then
          fail "Release snapshot toolchain manifest has an unexpected Rojo identity."
        fi
        ;;
      3|4|5)
        extra=""
        IFS=$'\t' read -r record platform archive_sha256 binary_sha256 extra <<< "${line}"
        if [[ "${line}" != "${record}"$'\t'"${platform}"$'\t'"${archive_sha256}"$'\t'"${binary_sha256}" ]]; then
          fail "Release snapshot toolchain manifest platform row is malformed."
        fi
        case "${line_number}" in
          3) expected_platform="linux-x86_64" ;;
          4) expected_platform="darwin-arm64" ;;
          5) expected_platform="darwin-x86_64" ;;
        esac
        if [[ "${record}" != "platform" || "${platform}" != "${expected_platform}" ]]; then
          fail "Release snapshot toolchain manifest platforms are incomplete or out of order."
        fi
        if [[ ! "${archive_sha256}" =~ ^[0-9a-f]{64}$ || ! "${binary_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
          fail "Release snapshot toolchain manifest contains an invalid SHA-256."
        fi
        if [[ "${platform}" == "${RELEASE_PLATFORM}" ]]; then
          EXPECTED_ROJO_ARCHIVE_SHA256="${archive_sha256}"
          EXPECTED_ROJO_BINARY_SHA256="${binary_sha256}"
        fi
        ;;
      *)
        fail "Release snapshot toolchain manifest contains unexpected fields."
        ;;
    esac
  done < "${manifest}"

  if [[ "${line_number}" -ne 5 || -z "${EXPECTED_ROJO_ARCHIVE_SHA256:-}" || -z "${EXPECTED_ROJO_BINARY_SHA256:-}" ]]; then
    fail "Release snapshot toolchain manifest is incomplete."
  fi
}

require_private_rojo_hash() {
  local actual_sha256 phase="$1"
  actual_sha256="$(sha256_file "${PRIVATE_ROJO}")" \
    || fail "Unable to hash the private release Rojo copy."
  if [[ "${actual_sha256}" != "${EXPECTED_ROJO_BINARY_SHA256}" ]]; then
    fail "Private release Rojo changed ${phase}."
  fi
}

git_repo() {
  /usr/bin/env -i \
    HOME=/ \
    XDG_CONFIG_HOME=/dev/null \
    PATH=/usr/bin:/bin \
    LC_ALL=C \
    LANG=C \
    TZ=UTC \
    GIT_ATTR_NOSYSTEM=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null \
    GIT_NO_REPLACE_OBJECTS=1 \
    /usr/bin/git \
    -c safe.directory="${ROOT_DIR}" \
    -c core.attributesFile=/dev/null \
    -C "${ROOT_DIR}" "$@"
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
    fail "Release index hidden-state inspection failed."
  fi
}

require_release_helpers_match_head() {
  local actual_blob expected_blob relative_path tree_entry
  for relative_path in "${RELEASE_HELPER_PATHS[@]}"; do
    if [[ -L "${ROOT_DIR}/${relative_path}" \
      || ! -f "${ROOT_DIR}/${relative_path}" \
      || ! -x "${ROOT_DIR}/${relative_path}" ]]; then
      fail "Release helper must be a regular executable file: ${relative_path}"
    fi
    expected_blob="$(git_repo rev-parse --verify "HEAD:${relative_path}")" \
      || fail "Release helper is missing from HEAD: ${relative_path}"
    tree_entry="$(git_repo ls-tree HEAD -- "${relative_path}")" \
      || fail "Release helper mode could not be inspected: ${relative_path}"
    if [[ "${tree_entry}" != "100755 blob ${expected_blob}"$'\t'"${relative_path}" ]]; then
      fail "Release helper must be a 100755 blob in HEAD: ${relative_path}"
    fi
    actual_blob="$(git_repo hash-object --no-filters -- "${ROOT_DIR}/${relative_path}")" \
      || fail "Release helper bytes could not be hashed: ${relative_path}"
    if [[ "${actual_blob}" != "${expected_blob}" ]]; then
      fail "Release helper bytes do not match HEAD: ${relative_path}"
    fi
  done
}

require_release_git_metadata() {
  local attributes_path replace_refs
  replace_refs="$(git_repo for-each-ref --format='%(refname)' refs/replace)" \
    || fail "Release replacement refs could not be inspected."
  if [[ -n "${replace_refs}" ]]; then
    fail "Release repository must not contain Git replacement refs."
  fi
  attributes_path="$(git_repo rev-parse --git-path info/attributes)" \
    || fail "Release repository attributes path could not be resolved."
  if [[ "${attributes_path}" != /* ]]; then
    attributes_path="${ROOT_DIR}/${attributes_path}"
  fi
  if [[ -e "${attributes_path}" || -L "${attributes_path}" ]]; then
    fail "Release repository must not contain info/attributes."
  fi
}

require_release_repository_integrity() {
  require_no_hidden_index_entries
  require_release_helpers_match_head
  require_release_git_metadata
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

RELEASE_PLATFORM="$(detect_release_platform)" || exit 1

require_release_repository_integrity

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

GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 "${GIT_COMMIT}^{commit}")"
umask 077
TEMP_ROOT="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/racer-release-build.XXXXXX")"
SNAPSHOT_DIR="${TEMP_ROOT}/snapshot"
ARCHIVE_FILE="${TEMP_ROOT}/source.tar"
SNAPSHOT_OUTPUT="${TEMP_ROOT}/racer.rbxlx"
PRIVATE_TOOL_DIR="${TEMP_ROOT}/toolchain"
PRIVATE_ROJO="${PRIVATE_TOOL_DIR}/rojo"
PRIVATE_HOME="${TEMP_ROOT}/home"
PRIVATE_TMPDIR="${TEMP_ROOT}/tmp"
OUTPUT_TEMP=""

cleanup() {
  if [[ -n "${OUTPUT_TEMP}" ]]; then
    /bin/rm -f "${OUTPUT_TEMP}"
  fi
  /bin/rm -rf "${TEMP_ROOT}"
}
trap cleanup EXIT

/bin/mkdir -p "${SNAPSHOT_DIR}" "${PRIVATE_TOOL_DIR}" "${PRIVATE_HOME}" "${PRIVATE_TMPDIR}"
git_repo archive --format=tar --output="${ARCHIVE_FILE}" "${GIT_COMMIT}"
/usr/bin/env -i \
  PATH=/usr/bin:/bin \
  LC_ALL=C \
  LANG=C \
  TZ=UTC \
  /usr/bin/tar -xf "${ARCHIVE_FILE}" -C "${SNAPSHOT_DIR}"

TOOLCHAIN_MANIFEST="${SNAPSHOT_DIR}/${TOOLCHAIN_MANIFEST_RELATIVE}"
load_toolchain_manifest "${TOOLCHAIN_MANIFEST}"

if [[ -z "${HOME:-}" || "${HOME}" != /* ]]; then
  fail "Release builds require an absolute HOME for Aftman tool storage."
fi
ROJO_SOURCE="${HOME}/.aftman/tool-storage/rojo-rbx/rojo/${ROJO_STORAGE_VERSION}/rojo"
if [[ -L "${ROJO_SOURCE}" || ! -f "${ROJO_SOURCE}" ]]; then
  fail "Release Rojo must be a regular non-symlink file in canonical Aftman storage."
fi
if [[ ! -x "${ROJO_SOURCE}" ]]; then
  fail "Release Rojo in canonical Aftman storage is not executable."
fi
ACTUAL_ROJO_BINARY_SHA256="$(sha256_file "${ROJO_SOURCE}")" \
  || fail "Unable to hash release Rojo in canonical Aftman storage."
if [[ "${ACTUAL_ROJO_BINARY_SHA256}" != "${EXPECTED_ROJO_BINARY_SHA256}" ]]; then
  fail "Release Rojo SHA-256 does not match the authenticated platform manifest."
fi

/bin/cp "${ROJO_SOURCE}" "${PRIVATE_ROJO}"
/bin/chmod 0500 "${PRIVATE_ROJO}"
if [[ -L "${PRIVATE_ROJO}" || ! -f "${PRIVATE_ROJO}" ]]; then
  fail "Private release Rojo copy is not a regular non-symlink file."
fi
require_private_rojo_hash "while it was copied"

BUILD_INFO_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedBuildInfo.lua"
PLACE_IDS_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedPlaceIds.lua"
if [[ ! -f "${BUILD_INFO_FILE}" || ! -f "${PLACE_IDS_FILE}" ]]; then
  echo "Release snapshot is missing the tracked generated metadata modules." >&2
  exit 1
fi

/bin/cat > "${PLACE_IDS_FILE}" <<EOF
return {
	LobbyPlaceId = ${LOBBY_PLACE_ID},
	RacerPlaceId = ${RACER_PLACE_ID},
}
EOF
/bin/cat > "${BUILD_INFO_FILE}" <<EOF
return {
	GitCommit = "${GIT_COMMIT}",
	GitCommitShort = "${GIT_COMMIT_SHORT}",
	PublishedAt = "${PUBLISHED_AT}",
}
EOF

(
  cd "${SNAPSHOT_DIR}"
  require_private_rojo_hash "before its version check"
  if ! ACTUAL_ROJO_VERSION="$(
    /usr/bin/env -i \
      HOME="${PRIVATE_HOME}" \
      TMPDIR="${PRIVATE_TMPDIR}" \
      PATH="/usr/bin:/bin" \
      LC_ALL=C \
      LANG=C \
      TZ=UTC \
      "${PRIVATE_ROJO}" --version
  )"; then
    echo "Unable to run the pinned Rojo release builder." >&2
    exit 1
  fi
  if [[ "${ACTUAL_ROJO_VERSION}" != "${EXPECTED_ROJO_VERSION}" ]]; then
    echo "Release builds require ${EXPECTED_ROJO_VERSION}; found ${ACTUAL_ROJO_VERSION}." >&2
    exit 1
  fi
  require_private_rojo_hash "after its version check"
  /usr/bin/env -i \
    HOME="${PRIVATE_HOME}" \
    TMPDIR="${PRIVATE_TMPDIR}" \
    PATH="/usr/bin:/bin" \
    LC_ALL=C \
    LANG=C \
    TZ=UTC \
    "${PRIVATE_ROJO}" build "racer.project.json" --output "${SNAPSHOT_OUTPUT}"
  require_private_rojo_hash "during the release build"
)

OUTPUT_DIR="$(/usr/bin/dirname -- "${OUTPUT_FILE}")"
/bin/mkdir -p "${OUTPUT_DIR}"
OUTPUT_TEMP="$(/usr/bin/mktemp "${OUTPUT_DIR}/.racer-release.XXXXXX")"
/bin/cp "${SNAPSHOT_OUTPUT}" "${OUTPUT_TEMP}"
/bin/chmod 0644 "${OUTPUT_TEMP}"
/bin/mv -f "${OUTPUT_TEMP}" "${OUTPUT_FILE}"
OUTPUT_TEMP=""
