#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/racer-snapshot-test.XXXXXX")"

cleanup() {
  rm -rf "${TEMP_ROOT}"
}
trap cleanup EXIT

TEST_REPO="${TEMP_ROOT}/repo"
git -c safe.directory="${ROOT_DIR}" clone --quiet --no-hardlinks "${ROOT_DIR}" "${TEST_REPO}"

# Exercise the current worktree scripts even when this test runs before its commit.
for relative_path in \
  scripts/build-racer-release.sh \
  scripts/finalize-studio-publish.sh \
  scripts/publish-place.sh \
  scripts/racer-publish-state.py; do
  cp "${ROOT_DIR}/${relative_path}" "${TEST_REPO}/${relative_path}"
done
git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" config user.name "Racer Release Test"
git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" config user.email "racer-release-test@example.invalid"
git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" add scripts
git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" commit --quiet --allow-empty -m "pending publish test fixture"

HELPER="${TEST_REPO}/scripts/build-racer-release.sh"
PUBLISHER="${TEST_REPO}/scripts/publish-place.sh"
GIT_COMMIT="$(git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" rev-parse HEAD)"
FIXED_PUBLISHED_AT="2000-01-02T03:04:05Z"
LOBBY_PLACE_ID="93743736131610"
RACER_PLACE_ID="123630607312596"
FIRST_BUILD="${TEMP_ROOT}/first.rbxlx"
SECOND_BUILD="${TEMP_ROOT}/second.rbxlx"
DIRTY_BUILD="${TEMP_ROOT}/dirty.rbxlx"
FOREIGN_CWD_BUILD="${TEMP_ROOT}/foreign-cwd.rbxlx"
FOREIGN_CALLER_DIR="${TEMP_ROOT}/foreign-caller"

"${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${FIRST_BUILD}" >/dev/null
"${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${SECOND_BUILD}" >/dev/null

if ! cmp -s "${FIRST_BUILD}" "${SECOND_BUILD}"; then
  echo "Fixed-metadata release builds were not byte-for-byte deterministic." >&2
  exit 1
fi
mkdir -p "${FOREIGN_CALLER_DIR}"
(
  cd "${FOREIGN_CALLER_DIR}"
  "${HELPER}" \
    "${GIT_COMMIT}" \
    "${FIXED_PUBLISHED_AT}" \
    "${LOBBY_PLACE_ID}" \
    "${RACER_PLACE_ID}" \
    "${FOREIGN_CWD_BUILD}" >/dev/null
)
if ! cmp -s "${FIRST_BUILD}" "${FOREIGN_CWD_BUILD}"; then
  echo "Release helper produced a different build from a caller directory without aftman.toml." >&2
  exit 1
fi
if ! grep -q "PublishedAt = &quot;${FIXED_PUBLISHED_AT}&quot;" "${FIRST_BUILD}" \
  && ! grep -q "PublishedAt = \"${FIXED_PUBLISHED_AT}\"" "${FIRST_BUILD}"; then
  echo "Deterministic test build did not embed the fixed release timestamp." >&2
  exit 1
fi

printf '\n-- Uncommitted integration-test mutation.\n' >> "${TEST_REPO}/src/racer/shared/RacerConfig.lua"
"${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${DIRTY_BUILD}" >/dev/null
if ! cmp -s "${FIRST_BUILD}" "${DIRTY_BUILD}"; then
  echo "Release helper consumed a dirty live source instead of the captured commit." >&2
  exit 1
fi

set +e
DIRTY_PUBLISH_OUTPUT="$(ROBLOX_RACER_PLACE_ID="${RACER_PLACE_ID}" \
  ROBLOX_LOBBY_PLACE_ID="${LOBBY_PLACE_ID}" \
  "${PUBLISHER}" --build-only 2>&1)"
DIRTY_PUBLISH_STATUS="$?"
set -e
if [[ "${DIRTY_PUBLISH_STATUS}" -eq 0 ]]; then
  echo "Top-level publisher accepted a dirty live tree." >&2
  exit 1
fi
if [[ "${DIRTY_PUBLISH_OUTPUT}" != *"dirty git tree"* ]]; then
  echo "Top-level publisher did not report its dirty-tree refusal." >&2
  exit 1
fi

git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" restore src/racer/shared/RacerConfig.lua
BUILD_INFO_BEFORE="$(git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" hash-object src/shared/GeneratedBuildInfo.lua)"
PLACE_IDS_BEFORE="$(git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" hash-object src/shared/GeneratedPlaceIds.lua)"
ROBLOX_RACER_PLACE_ID="${RACER_PLACE_ID}" \
ROBLOX_LOBBY_PLACE_ID="${LOBBY_PLACE_ID}" \
  "${PUBLISHER}" --build-only >/dev/null
BUILD_INFO_AFTER="$(git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" hash-object src/shared/GeneratedBuildInfo.lua)"
PLACE_IDS_AFTER="$(git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" hash-object src/shared/GeneratedPlaceIds.lua)"
if [[ "${BUILD_INFO_BEFORE}" != "${BUILD_INFO_AFTER}" || "${PLACE_IDS_BEFORE}" != "${PLACE_IDS_AFTER}" ]]; then
  echo "Top-level snapshot build changed tracked generated metadata." >&2
  exit 1
fi
if [[ ! -s "${TEST_REPO}/build/racer.rbxlx" ]]; then
  echo "Top-level build-only mode did not atomically install the release artifact." >&2
  exit 1
fi
if [[ ! -s "${TEST_REPO}/build/racer-publish-pending.json" ]]; then
  echo "Top-level build-only mode did not record its pending Studio publish." >&2
  exit 1
fi

FAKE_BIN="${TEMP_ROOT}/fake-bin"
mkdir -p "${FAKE_BIN}"
cat > "${FAKE_BIN}/rojo" <<'EOF'
#!/usr/bin/env bash
echo "Rojo 0.0.0"
EOF
chmod +x "${FAKE_BIN}/rojo"

set +e
WRONG_ROJO_OUTPUT="$(PATH="${FAKE_BIN}:${PATH}" \
  "${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${TEMP_ROOT}/wrong-rojo.rbxlx" 2>&1)"
WRONG_ROJO_STATUS="$?"
set -e
if [[ "${WRONG_ROJO_STATUS}" -eq 0 ]]; then
  echo "Release helper accepted an unpinned Rojo version." >&2
  exit 1
fi
if [[ "${WRONG_ROJO_OUTPUT}" != *"require Rojo 7.5.1"* ]]; then
  echo "Release helper did not explain the pinned Rojo requirement." >&2
  exit 1
fi

BUILD_SHA256="$(TARGET_FILE="${FIRST_BUILD}" python3 -c 'import hashlib
import os
from pathlib import Path

print(hashlib.sha256(Path(os.environ["TARGET_FILE"]).read_bytes()).hexdigest())')"
echo "Release snapshot integration test passed (${BUILD_SHA256})"
