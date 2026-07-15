#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

BUILD_FILE="build/racer.rbxlx"

git_repo() {
  git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}" "$@"
}

if [[ "$#" -ne 1 ]]; then
  echo "Usage: scripts/finalize-studio-publish.sh <roblox-place-version>" >&2
  echo "Verify this published PlaceVersion in Studio before running." >&2
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

if [[ ! -s "${BUILD_FILE}" ]]; then
  echo "Missing Racer release artifact: ${BUILD_FILE}" >&2
  exit 1
fi

if [[ ! -x "${SCRIPT_DIR}/lookup-place-version.sh" ]]; then
  echo "PlaceVersion lookup script is missing or not executable." >&2
  exit 1
fi

require_clean_tree() {
  local tree_status
  tree_status="$(git_repo status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  if [[ -n "${tree_status}" ]]; then
    echo "Refusing to finalize a Studio publish from a dirty git tree." >&2
    exit 1
  fi
}

require_clean_tree

GIT_COMMIT="$(git_repo rev-parse HEAD)"
GIT_COMMIT_SHORT="$(git_repo rev-parse --short=12 HEAD)"
TAG="racer-place-v${PLACE_VERSION}"

if git_repo rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null; then
  echo "Refusing to move existing immutable publish tag ${TAG}." >&2
  exit 1
fi

BUILD_FILE="${BUILD_FILE}" \
EXPECTED_GIT_COMMIT="${GIT_COMMIT}" \
EXPECTED_GIT_COMMIT_SHORT="${GIT_COMMIT_SHORT}" \
EXPECTED_RACER_PLACE_ID="${PLACE_ID}" \
python3 - <<'PY'
import os
import re
import sys
import xml.etree.ElementTree as ET


def fail(message: str) -> None:
    print(f"Invalid Racer release build: {message}", file=sys.stderr)
    raise SystemExit(1)


try:
    root = ET.parse(os.environ["BUILD_FILE"]).getroot()
except (OSError, ET.ParseError) as error:
    fail(str(error))


def module_source(name: str) -> str:
    matches = []
    for item in root.iter("Item"):
        if item.get("class") != "ModuleScript":
            continue
        properties = item.find("Properties")
        if properties is None:
            continue
        values = {node.get("name"): node.text or "" for node in properties}
        if values.get("Name") == name:
            if "Source" not in values:
                fail(f"{name} has no Source property")
            matches.append(values["Source"])

    if len(matches) != 1:
        fail(f"expected exactly one {name} ModuleScript, found {len(matches)}")
    return matches[0]


def string_field(source: str, key: str) -> str:
    values = re.findall(
        rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"\r\n]*)"\s*,?\s*$',
        source,
    )
    if len(values) != 1:
        fail(f"expected exactly one string field {key}")
    return values[0]


def integer_field(source: str, key: str) -> str:
    values = re.findall(
        rf"(?m)^\s*{re.escape(key)}\s*=\s*([0-9]+)\s*,?\s*$",
        source,
    )
    if len(values) != 1:
        fail(f"expected exactly one integer field {key}")
    return values[0]


build_info = module_source("GeneratedBuildInfo")
place_ids = module_source("GeneratedPlaceIds")

checks = {
    "GitCommit": (
        string_field(build_info, "GitCommit"),
        os.environ["EXPECTED_GIT_COMMIT"],
    ),
    "GitCommitShort": (
        string_field(build_info, "GitCommitShort"),
        os.environ["EXPECTED_GIT_COMMIT_SHORT"],
    ),
    "RacerPlaceId": (
        integer_field(place_ids, "RacerPlaceId"),
        os.environ["EXPECTED_RACER_PLACE_ID"],
    ),
}

for key, (actual, expected) in checks.items():
    if actual != expected:
        fail(f"{key} mismatch: embedded {actual}, expected {expected}")

published_at = string_field(build_info, "PublishedAt")
if not re.fullmatch(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
    published_at,
):
    fail("PublishedAt is not a release timestamp")
PY

# Close the main time-of-check/time-of-use windows before creating the tag.
if [[ "$(git_repo rev-parse HEAD)" != "${GIT_COMMIT}" ]]; then
  echo "HEAD changed while validating the Studio publish." >&2
  exit 1
fi
require_clean_tree

if git_repo rev-parse --verify --quiet "refs/tags/${TAG}" >/dev/null; then
  echo "Refusing to move existing immutable publish tag ${TAG}." >&2
  exit 1
fi

# An empty expected old value makes this an atomic create-only operation.
if ! git_repo update-ref "refs/tags/${TAG}" "${GIT_COMMIT}" ""; then
  echo "Failed to create immutable publish tag ${TAG}; it may now exist." >&2
  exit 1
fi

TAG_COMMIT="$(git_repo rev-parse "refs/tags/${TAG}^{commit}")"
if [[ "${TAG_COMMIT}" != "${GIT_COMMIT}" ]]; then
  echo "Publish tag ${TAG} does not resolve to ${GIT_COMMIT}." >&2
  exit 1
fi

LOOKUP_OUTPUT="$("${SCRIPT_DIR}/lookup-place-version.sh" "${PLACE_VERSION}")"
if [[ "${LOOKUP_OUTPUT}" != *"Commit: ${GIT_COMMIT}"* ]]; then
  echo "PlaceVersion lookup did not resolve to ${GIT_COMMIT}." >&2
  exit 1
fi

printf '%s\n' "${LOOKUP_OUTPUT}"
echo "Recorded Studio publish ${TAG} -> ${GIT_COMMIT_SHORT}"
