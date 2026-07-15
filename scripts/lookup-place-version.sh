#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ "${1:-}" == "" || "${2:-}" != "" ]]; then
  echo "Usage: scripts/lookup-place-version.sh <roblox-place-version>" >&2
  exit 2
fi

PLACE_VERSION="$1"
TAG="racer-place-v${PLACE_VERSION}"

if [[ ! "${PLACE_VERSION}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Roblox place version must be a positive decimal integer." >&2
  exit 2
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

fail() {
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

require_no_hidden_index_entries
require_release_helpers_match_head
require_release_git_metadata

if SYMBOLIC_TARGET="$(git_repo symbolic-ref -q "refs/tags/${TAG}" 2>/dev/null)"; then
  echo "Publish tag ${TAG} must not be symbolic (${SYMBOLIC_TARGET})." >&2
  exit 1
else
  SYMBOLIC_STATUS=$?
fi
if [[ "${SYMBOLIC_STATUS}" -ne 1 ]]; then
  echo "Publish tag ${TAG} symbolic state could not be inspected." >&2
  exit 1
fi

if ! git_repo rev-parse --verify --quiet "refs/tags/${TAG}^{commit}" >/dev/null; then
  echo "No git tag found for Roblox place version ${PLACE_VERSION} (${TAG})." >&2
  exit 1
fi

COMMIT="$(git_repo rev-parse "refs/tags/${TAG}^{commit}")"
SUBJECT="$(git_repo show -s --format=%s "${COMMIT}")"
DATE="$(git_repo show -s --format=%cI "${COMMIT}")"

echo "Roblox place version ${PLACE_VERSION}"
echo "Tag: ${TAG}"
echo "Commit: ${COMMIT}"
echo "Date: ${DATE}"
echo "Subject: ${SUBJECT}"
