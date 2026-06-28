#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "" || "${2:-}" != "" ]]; then
  echo "Usage: scripts/lookup-place-version.sh <roblox-place-version>" >&2
  exit 2
fi

PLACE_VERSION="$1"
TAG="racer-place-v${PLACE_VERSION}"

if ! git rev-parse --verify --quiet "${TAG}^{commit}" >/dev/null; then
  echo "No git tag found for Roblox place version ${PLACE_VERSION} (${TAG})." >&2
  exit 1
fi

COMMIT="$(git rev-parse "${TAG}^{commit}")"
SUBJECT="$(git show -s --format=%s "${COMMIT}")"
DATE="$(git show -s --format=%cI "${COMMIT}")"

echo "Roblox place version ${PLACE_VERSION}"
echo "Tag: ${TAG}"
echo "Commit: ${COMMIT}"
echo "Date: ${DATE}"
echo "Subject: ${SUBJECT}"
