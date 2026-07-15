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
  scripts/racer-release-toolchain.tsv \
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
printf 'unexpected\tmanifest\trow\n' >> "${TEST_REPO}/scripts/racer-release-toolchain.tsv"
"${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${DIRTY_BUILD}" >/dev/null
if ! cmp -s "${FIRST_BUILD}" "${DIRTY_BUILD}"; then
  echo "Release helper consumed dirty live source or toolchain data instead of the captured commit." >&2
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

git -c safe.directory="${TEST_REPO}" -C "${TEST_REPO}" restore \
  scripts/racer-release-toolchain.tsv \
  src/racer/shared/RacerConfig.lua
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
PATH_IMPOSTOR_MARKER="${TEMP_ROOT}/path-rojo-ran"
PATH_BASH_IMPOSTOR_MARKER="${TEMP_ROOT}/path-bash-ran"
PATH_CAT_IMPOSTOR_MARKER="${TEMP_ROOT}/path-cat-ran"
PATH_GIT_IMPOSTOR_MARKER="${TEMP_ROOT}/path-git-ran"
PATH_TAR_IMPOSTOR_MARKER="${TEMP_ROOT}/path-tar-ran"
BASH_ENV_MARKER="${TEMP_ROOT}/bash-env-ran"
BASH_ENV_POISON="${TEMP_ROOT}/bash-env-poison.sh"
PATH_BUILD="${TEMP_ROOT}/path-impostor.rbxlx"
mkdir -p "${FAKE_BIN}"
cat > "${FAKE_BIN}/rojo" <<'EOF'
#!/usr/bin/env bash
/usr/bin/printf 'invoked\n' > "${PATH_IMPOSTOR_MARKER}"
exit 98
EOF
chmod +x "${FAKE_BIN}/rojo"
cat > "${FAKE_BIN}/bash" <<'EOF'
#!/bin/sh
/usr/bin/printf 'invoked\n' > "${PATH_BASH_IMPOSTOR_MARKER}"
exit 95
EOF
cat > "${FAKE_BIN}/git" <<'EOF'
#!/bin/sh
/usr/bin/printf 'invoked\n' > "${PATH_GIT_IMPOSTOR_MARKER}"
exit 94
EOF
cat > "${FAKE_BIN}/cat" <<'EOF'
#!/bin/sh
/usr/bin/printf 'invoked\n' > "${PATH_CAT_IMPOSTOR_MARKER}"
exit 91
EOF
cat > "${FAKE_BIN}/tar" <<'EOF'
#!/bin/sh
/usr/bin/printf 'invoked\n' > "${PATH_TAR_IMPOSTOR_MARKER}"
exit 93
EOF
chmod +x "${FAKE_BIN}/bash" "${FAKE_BIN}/cat" "${FAKE_BIN}/git" "${FAKE_BIN}/tar"
cat > "${BASH_ENV_POISON}" <<'EOF'
/usr/bin/printf 'invoked\n' > "${BASH_ENV_MARKER}"
exit 92
EOF

PATH_IMPOSTOR_MARKER="${PATH_IMPOSTOR_MARKER}" \
PATH_BASH_IMPOSTOR_MARKER="${PATH_BASH_IMPOSTOR_MARKER}" \
PATH_CAT_IMPOSTOR_MARKER="${PATH_CAT_IMPOSTOR_MARKER}" \
PATH_GIT_IMPOSTOR_MARKER="${PATH_GIT_IMPOSTOR_MARKER}" \
PATH_TAR_IMPOSTOR_MARKER="${PATH_TAR_IMPOSTOR_MARKER}" \
BASH_ENV_MARKER="${BASH_ENV_MARKER}" \
BASH_ENV="${BASH_ENV_POISON}" \
TAR_OPTIONS="--racer-toolchain-poison" \
PATH="${FAKE_BIN}:${PATH}" \
  "${HELPER}" \
  "${GIT_COMMIT}" \
  "${FIXED_PUBLISHED_AT}" \
  "${LOBBY_PLACE_ID}" \
  "${RACER_PLACE_ID}" \
  "${PATH_BUILD}" >/dev/null
if [[ -e "${PATH_IMPOSTOR_MARKER}" ]]; then
  echo "Release helper executed a PATH Rojo impostor." >&2
  exit 1
fi
if [[ -e "${PATH_BASH_IMPOSTOR_MARKER}" ]]; then
  echo "Release helper executed a PATH Bash impostor." >&2
  exit 1
fi
if [[ -e "${PATH_CAT_IMPOSTOR_MARKER}" ]]; then
  echo "Release helper executed a PATH cat impostor." >&2
  exit 1
fi
if [[ -e "${PATH_GIT_IMPOSTOR_MARKER}" ]]; then
  echo "Release helper executed a PATH Git impostor." >&2
  exit 1
fi
if [[ -e "${PATH_TAR_IMPOSTOR_MARKER}" ]]; then
  echo "Release helper executed a PATH tar impostor." >&2
  exit 1
fi
if [[ -e "${BASH_ENV_MARKER}" ]]; then
  echo "Release helper evaluated inherited BASH_ENV before authentication." >&2
  exit 1
fi
if ! cmp -s "${FIRST_BUILD}" "${PATH_BUILD}"; then
  echo "PATH Rojo impostor changed the authenticated release build." >&2
  exit 1
fi

TOOLCHAIN_FIXTURE="${ROOT_DIR}/scripts/test-fixtures/release-toolchain"
FIXTURE_REPO="${TEMP_ROOT}/fixture-repo"
FIXTURE_HOME="${TEMP_ROOT}/fixture-home"
FIXTURE_ROJO="${FIXTURE_HOME}/.aftman/tool-storage/rojo-rbx/rojo/7.5.1/rojo"
git -c safe.directory="${TEST_REPO}" clone --quiet --no-hardlinks "${TEST_REPO}" "${FIXTURE_REPO}"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" config user.name "Racer Toolchain Test"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" config user.email "racer-toolchain-test@example.invalid"
cp "${TOOLCHAIN_FIXTURE}/manifest.tsv" "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" add scripts/racer-release-toolchain.tsv
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" commit --quiet -m "use deterministic Rojo fixture"
FIXTURE_HELPER="${FIXTURE_REPO}/scripts/build-racer-release.sh"
FIXTURE_COMMIT="$(git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" rev-parse HEAD)"

install_fixture_rojo() {
  rm -rf "${FIXTURE_ROJO}"
  mkdir -p "$(dirname -- "${FIXTURE_ROJO}")"
  cp "$1" "${FIXTURE_ROJO}"
  chmod 0755 "${FIXTURE_ROJO}"
}

run_fixture_build() {
  HOME="${FIXTURE_HOME}" \
  PERL5OPT="-MRacerToolchainPoisonMustNotLoad" \
  PYTHONPATH="${TEMP_ROOT}/python-poison" \
  ROBLOX_API_KEY="sentinel-release-toolchain-fixture" \
  RACER_PUBLISH_API_KEY="sentinel-release-toolchain-fixture" \
  FAKE_ROJO_LOG="${TEMP_ROOT}/forbidden-rojo-log" \
    "${FIXTURE_HELPER}" \
      "$1" \
      "${FIXED_PUBLISHED_AT}" \
      "${LOBBY_PLACE_ID}" \
      "${RACER_PLACE_ID}" \
      "$2"
}

install_fixture_rojo "${TOOLCHAIN_FIXTURE}/fake-rojo"
FIXTURE_BUILD="${TEMP_ROOT}/fixture.rbxlx"
run_fixture_build "${FIXTURE_COMMIT}" "${FIXTURE_BUILD}" >/dev/null
if [[ ! -s "${FIXTURE_BUILD}" ]]; then
  echo "Authenticated deterministic Rojo fixture did not build an artifact." >&2
  exit 1
fi

printf '\n# wrong digest\n' >> "${FIXTURE_ROJO}"
set +e
WRONG_SHA_OUTPUT="$(run_fixture_build "${FIXTURE_COMMIT}" "${TEMP_ROOT}/wrong-sha.rbxlx" 2>&1)"
WRONG_SHA_STATUS="$?"
set -e
if [[ "${WRONG_SHA_STATUS}" -eq 0 || "${WRONG_SHA_OUTPUT}" != *"SHA-256 does not match"* ]]; then
  echo "Release helper did not reject a wrong canonical Rojo SHA-256." >&2
  exit 1
fi

rm -rf "${FIXTURE_ROJO}"
ln -s "${TOOLCHAIN_FIXTURE}/fake-rojo" "${FIXTURE_ROJO}"
set +e
SYMLINK_OUTPUT="$(run_fixture_build "${FIXTURE_COMMIT}" "${TEMP_ROOT}/symlink.rbxlx" 2>&1)"
SYMLINK_STATUS="$?"
set -e
if [[ "${SYMLINK_STATUS}" -eq 0 || "${SYMLINK_OUTPUT}" != *"regular non-symlink"* ]]; then
  echo "Release helper did not reject a canonical Rojo symlink." >&2
  exit 1
fi

rm -rf "${FIXTURE_ROJO}"
mkdir "${FIXTURE_ROJO}"
set +e
NONREGULAR_OUTPUT="$(run_fixture_build "${FIXTURE_COMMIT}" "${TEMP_ROOT}/nonregular.rbxlx" 2>&1)"
NONREGULAR_STATUS="$?"
set -e
if [[ "${NONREGULAR_STATUS}" -eq 0 || "${NONREGULAR_OUTPUT}" != *"regular non-symlink"* ]]; then
  echo "Release helper did not reject a nonregular canonical Rojo path." >&2
  exit 1
fi

cp "${TOOLCHAIN_FIXTURE}/self-mutating-manifest.tsv" "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" add scripts/racer-release-toolchain.tsv
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" commit --quiet -m "use self-mutating Rojo fixture"
SELF_MUTATING_COMMIT="$(git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" rev-parse HEAD)"
install_fixture_rojo "${TOOLCHAIN_FIXTURE}/fake-rojo-self-mutating"
set +e
SELF_MUTATING_OUTPUT="$(run_fixture_build "${SELF_MUTATING_COMMIT}" "${TEMP_ROOT}/self-mutating.rbxlx" 2>&1)"
SELF_MUTATING_STATUS="$?"
set -e
if [[ "${SELF_MUTATING_STATUS}" -eq 0 || "${SELF_MUTATING_OUTPUT}" != *"changed after its version check"* ]]; then
  echo "Release helper did not detect a self-mutating private Rojo copy." >&2
  exit 1
fi

cp "${TOOLCHAIN_FIXTURE}/wrong-version-manifest.tsv" "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" add scripts/racer-release-toolchain.tsv
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" commit --quiet -m "use wrong-version Rojo fixture"
WRONG_VERSION_COMMIT="$(git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" rev-parse HEAD)"
install_fixture_rojo "${TOOLCHAIN_FIXTURE}/fake-rojo-wrong-version"
set +e
WRONG_VERSION_OUTPUT="$(run_fixture_build "${WRONG_VERSION_COMMIT}" "${TEMP_ROOT}/wrong-version.rbxlx" 2>&1)"
WRONG_VERSION_STATUS="$?"
set -e
if [[ "${WRONG_VERSION_STATUS}" -eq 0 || "${WRONG_VERSION_OUTPUT}" != *"require Rojo 7.5.1; found Rojo 7.5.0"* ]]; then
  echo "Release helper did not reject an authenticated Rojo with the wrong version." >&2
  exit 1
fi

printf 'unexpected\tmanifest\trow\n' >> "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" add scripts/racer-release-toolchain.tsv
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" commit --quiet -m "malform toolchain manifest"
MALFORMED_MANIFEST_COMMIT="$(git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" rev-parse HEAD)"
set +e
MALFORMED_MANIFEST_OUTPUT="$(run_fixture_build "${MALFORMED_MANIFEST_COMMIT}" "${TEMP_ROOT}/malformed-manifest.rbxlx" 2>&1)"
MALFORMED_MANIFEST_STATUS="$?"
set -e
if [[ "${MALFORMED_MANIFEST_STATUS}" -eq 0 || "${MALFORMED_MANIFEST_OUTPUT}" != *"contains unexpected fields"* ]]; then
  echo "Release helper did not reject extra toolchain manifest fields." >&2
  exit 1
fi

cp "${TOOLCHAIN_FIXTURE}/manifest.tsv" "${FIXTURE_REPO}/scripts/fixture-toolchain.tsv"
rm "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
ln -s fixture-toolchain.tsv "${FIXTURE_REPO}/scripts/racer-release-toolchain.tsv"
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" add scripts/fixture-toolchain.tsv scripts/racer-release-toolchain.tsv
git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" commit --quiet -m "symlink toolchain manifest"
SYMLINK_MANIFEST_COMMIT="$(git -c safe.directory="${FIXTURE_REPO}" -C "${FIXTURE_REPO}" rev-parse HEAD)"
install_fixture_rojo "${TOOLCHAIN_FIXTURE}/fake-rojo"
set +e
SYMLINK_MANIFEST_OUTPUT="$(run_fixture_build "${SYMLINK_MANIFEST_COMMIT}" "${TEMP_ROOT}/symlink-manifest.rbxlx" 2>&1)"
SYMLINK_MANIFEST_STATUS="$?"
set -e
if [[ "${SYMLINK_MANIFEST_STATUS}" -eq 0 || "${SYMLINK_MANIFEST_OUTPUT}" != *"manifest must be a regular non-symlink"* ]]; then
  echo "Release helper did not reject a snapshot toolchain manifest symlink." >&2
  exit 1
fi

BUILD_SHA256="$(TARGET_FILE="${FIRST_BUILD}" python3 -c 'import hashlib
import os
from pathlib import Path

print(hashlib.sha256(Path(os.environ["TARGET_FILE"]).read_bytes()).hexdigest())')"
echo "Release snapshot integration test passed (${BUILD_SHA256})"
