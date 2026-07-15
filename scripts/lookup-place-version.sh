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
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

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
