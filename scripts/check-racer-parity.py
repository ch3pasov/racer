#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import runpy
import sys
import math
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
RACER_PROJECT = json.loads((ROOT / "racer.project.json").read_text())
CONFIG = (ROOT / "src/racer/shared/RacerConfig.lua").read_text()
CLIENT = (ROOT / "src/racer/client/Main.client.lua").read_text()
SERVER = (ROOT / "src/racer/server/Main.server.lua").read_text()
MATH = (ROOT / "src/racer/shared/RacerMath.lua").read_text()
TEXTURES = (ROOT / "src/racer/shared/RacerTextures.lua").read_text()
PUBLISH_SCRIPT = (ROOT / "scripts/publish-place.sh").read_text()
RELEASE_BUILD_SCRIPT_PATH = ROOT / "scripts/build-racer-release.sh"
RELEASE_BUILD_SCRIPT = RELEASE_BUILD_SCRIPT_PATH.read_text()
TOOLCHAIN_MANIFEST_PATH = ROOT / "scripts/racer-release-toolchain.tsv"
TOOLCHAIN_MANIFEST = TOOLCHAIN_MANIFEST_PATH.read_text()
TOOLCHAIN_FIXTURE_DIR = ROOT / "scripts/test-fixtures/release-toolchain"
RELEASE_BUILD_TEST_PATH = ROOT / "scripts/test-release-snapshot-build.sh"
RELEASE_BUILD_TEST = RELEASE_BUILD_TEST_PATH.read_text()
PUBLISH_STATE_SCRIPT_PATH = ROOT / "scripts/racer-publish-state.py"
PUBLISH_STATE_SCRIPT = PUBLISH_STATE_SCRIPT_PATH.read_text()
PUBLISH_RECOVERY_TEST_PATH = ROOT / "scripts/test-publish-recovery.py"
PUBLISH_RECOVERY_TEST = PUBLISH_RECOVERY_TEST_PATH.read_text()
RELEASE_LOCK_TEST_PATH = ROOT / "scripts/test-release-lock.py"
RELEASE_LOCK_TEST = RELEASE_LOCK_TEST_PATH.read_text()
FINALIZE_SCRIPT_PATH = ROOT / "scripts/finalize-studio-publish.sh"
FINALIZE_SCRIPT = FINALIZE_SCRIPT_PATH.read_text()
LOOKUP_SCRIPT = (ROOT / "scripts/lookup-place-version.sh").read_text()
DOCKERFILE = (ROOT / "Dockerfile").read_text()
DOCKER_COMPOSE = (ROOT / "docker-compose.yml").read_text()
DOCKER_ENTRYPOINT = (ROOT / "scripts/docker-entrypoint.sh").read_text()
DOCKER_BOOTSTRAP_TEST = (ROOT / "scripts/test-docker-bootstrap.py").read_text()
PUBLISH_SECRET_TEST = (ROOT / "scripts/test-publish-api-key-transport.py").read_text()
README = (ROOT / "README.md").read_text()
UPLOAD_SCRIPT = (ROOT / "scripts/upload-racer-textures.py").read_text()


def fail(message: str):
    print(f"FAIL: {message}")
    sys.exit(1)


if "src/shared/GameConfig.lua" not in RACER_PROJECT.get("globIgnorePaths", []):
    fail("Racer Rojo build must exclude the ignored local src/shared/GameConfig.lua")

for token in [
    "set +x",
    "set +a",
    'unset RACER_PUBLISH_API_KEY',
    'if [[ -z "${ROBLOX_API_KEY:-}" ]]; then',
    'RACER_PUBLISH_API_KEY="${ROBLOX_API_KEY}"',
    'export -n RACER_PUBLISH_API_KEY',
    'echo "ROBLOX_API_KEY must not contain CR or LF."',
    '${ROBLOX_RACER_PLACE_ID:?ROBLOX_RACER_PLACE_ID is required}',
    'if [[ "$#" -eq 0 ]]',
    'elif [[ "$#" -eq 1 && "$1" == "--build-only" ]]',
    "status --porcelain=v1 --untracked-files=all --ignore-submodules=none",
    'BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"',
    'STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"',
    'PENDING_REF="refs/racer-publish/pending"',
    'LOCK_CONTEXT_VALUE="racer-release-lock-v1"',
    'SECRET_CONTEXT_VALUE="racer-release-secret-v1"',
    '/usr/bin/python3 -I "${STATE_HELPER}" "${LOCK_ARGUMENTS[@]}"',
    'RACER_RELEASE_LOCK_CONTEXT="${LOCK_CONTEXT_VALUE}" RACER_RELEASE_LOCK_FD=8',
    '/usr/bin/python3 -I "${STATE_HELPER}" assert-release-lock',
    "require_pending_ref_absent",
    'state_helper assert-absent',
    'PRIVATE_ARTIFACT="${TEMP_ROOT}/racer.rbxlx"',
    'atomic_install_artifact',
    'require_release_state',
    'if [[ "${BUILD_ONLY}" == "true" ]]; then',
    "create_pending_ref",
    'create_pending_state "studio"',
    "hashlib.sha256",
    'echo "Commit: ${GIT_COMMIT}"',
    'echo "SHA-256: ${BUILD_SHA256}"',
    'payload.get("versionNumber")',
    'symbolic-ref -q "${PENDING_REF}"',
    'update-ref --no-deref "${PENDING_REF}" "${GIT_COMMIT}" ""',
    'create_pending_state "open-cloud"',
    'state_helper validate-artifact',
    "/usr/bin/curl --disable --fail-with-body",
    "--header @<(builtin printf 'x-api-key: %s\\n' \"${RACER_PUBLISH_API_KEY}\")",
    '--data-binary @"${PRIVATE_ARTIFACT}"',
    'state_helper record-version "${PLACE_VERSION}"',
    'exec /bin/bash -p "${FINALIZER}" "${PLACE_VERSION}"',
]:
    if token not in PUBLISH_SCRIPT:
        fail(f"Racer publish contract is missing: {token}")

xtrace_index = PUBLISH_SCRIPT.index("set +x")
allexport_index = PUBLISH_SCRIPT.index("set +a")
argument_index = PUBLISH_SCRIPT.index('BUILD_ONLY="false"')
secret_reset_index = PUBLISH_SCRIPT.index("unset RACER_PUBLISH_API_KEY")
credential_build_only_index = PUBLISH_SCRIPT.index(
    'if [[ "${BUILD_ONLY}" == "true" ]]; then', secret_reset_index
)
build_only_secret_unset_index = PUBLISH_SCRIPT.index(
    "unset ROBLOX_API_KEY", credential_build_only_index
)
missing_key_index = PUBLISH_SCRIPT.index(
    'if [[ -z "${ROBLOX_API_KEY:-}" ]]; then', credential_build_only_index
)
capture_key_index = PUBLISH_SCRIPT.index(
    'RACER_PUBLISH_API_KEY="${ROBLOX_API_KEY}"', missing_key_index
)
private_key_index = PUBLISH_SCRIPT.index(
    "export -n RACER_PUBLISH_API_KEY", capture_key_index
)
captured_key_unset_index = PUBLISH_SCRIPT.index(
    "unset ROBLOX_API_KEY", private_key_index
)
crlf_check_index = PUBLISH_SCRIPT.index(
    '"${RACER_PUBLISH_API_KEY}" == *$\'\\r\'*', capture_key_index
)
script_dir_index = PUBLISH_SCRIPT.index('SCRIPT_PARENT="$(')
preflight_index = PUBLISH_SCRIPT.index("EARLY_TREE_STATUS=")
secret_pipe_index = PUBLISH_SCRIPT.index("exec 9< <(")
lock_exec_index = PUBLISH_SCRIPT.index('/usr/bin/python3 -I "${STATE_HELPER}" "${LOCK_ARGUMENTS[@]}"')
lock_assert_index = PUBLISH_SCRIPT.index('assert-release-lock; then', lock_exec_index)
snapshot_build_index = PUBLISH_SCRIPT.index('/bin/bash -p "${BUILD_HELPER}" \\')
pending_guard_index = PUBLISH_SCRIPT.index('state_helper assert-absent')
pending_ref_guard_index = PUBLISH_SCRIPT.index("\nrequire_pending_ref_absent\n")
install_index = PUBLISH_SCRIPT.index("atomic_install_artifact", snapshot_build_index)
build_only_index = PUBLISH_SCRIPT.index(
    'if [[ "${BUILD_ONLY}" == "true" ]]; then', install_index
)
build_only_exit_index = PUBLISH_SCRIPT.index("exit 0", build_only_index)
universe_index = PUBLISH_SCRIPT.index(
    ': "${ROBLOX_UNIVERSE_ID:?ROBLOX_UNIVERSE_ID is required}"'
)
curl_index = PUBLISH_SCRIPT.index("/usr/bin/curl --disable --fail-with-body")
studio_pending_index = PUBLISH_SCRIPT.index('create_pending_state "studio"')
studio_ref_index = PUBLISH_SCRIPT.index("create_pending_ref", build_only_index)
cloud_pending_index = PUBLISH_SCRIPT.index('create_pending_state "open-cloud"')
cloud_ref_index = PUBLISH_SCRIPT.index("create_pending_ref", universe_index)
manifest_recheck_index = PUBLISH_SCRIPT.index(
    'state_helper validate-artifact', cloud_pending_index
)
record_version_index = PUBLISH_SCRIPT.index(
    'state_helper record-version "${PLACE_VERSION}"'
)
finalizer_index = PUBLISH_SCRIPT.index('exec /bin/bash -p "${FINALIZER}" "${PLACE_VERSION}"')
network_recheck_index = PUBLISH_SCRIPT.index(
    "require_release_state", universe_index
)
if not (
    xtrace_index
    < allexport_index
    < argument_index
    < secret_reset_index
    < credential_build_only_index
    < build_only_secret_unset_index
    < missing_key_index
    < capture_key_index
    < private_key_index
    < captured_key_unset_index
    < crlf_check_index
    < script_dir_index
    < preflight_index
    < secret_pipe_index
    < lock_exec_index
    < lock_assert_index
    < pending_ref_guard_index
    < pending_guard_index
    < snapshot_build_index
    < install_index
    < build_only_index
    < studio_ref_index
    < studio_pending_index
    < build_only_exit_index
    < universe_index
    < network_recheck_index
    < cloud_ref_index
    < cloud_pending_index
    < manifest_recheck_index
    < curl_index
    < record_version_index
    < finalizer_index
):
    fail(
        "credentials must be isolated before child processes, snapshot build must install "
        "before build-only exits, and network publishing must recheck release state "
        "before curl"
    )

publish_statements = [
    line.strip()
    for line in PUBLISH_SCRIPT.splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
if publish_statements[:3] != ["set +x", "set +a", "set -euo pipefail"]:
    fail("Racer publish must disable inherited xtrace/allexport before any other statement")

if PUBLISH_SCRIPT.count("require_release_state") < 3:
    fail("Racer publish must verify the captured release before install and network use")

for forbidden in [
    "ROBLOX_PLACE_ID",
    "git_repo tag -f",
    "git tag -f",
    "restore_build_info",
    'BUILD_INFO_FILE="src/shared/GeneratedBuildInfo.lua"',
    'PLACE_IDS_FILE="src/shared/GeneratedPlaceIds.lua"',
    'rojo build "${PROJECT_FILE}"',
    'git_repo tag "${TAG}"',
    'RELEASE_LOCK_DIR=',
    'mkdir "${RELEASE_LOCK_DIR}"',
    'rmdir "${RELEASE_LOCK_DIR}"',
]:
    if forbidden in PUBLISH_SCRIPT:
        fail(f"Racer publish contract must not contain: {forbidden}")

expected_toolchain_manifest = (
    "schema\tracer-release-toolchain-v1\n"
    "tool\trojo-rbx/rojo\t7.5.1\n"
    "platform\tlinux-x86_64\t"
    "0d600df6c4c48a9d09c701d0c2a109c55c2db833cd9766fd7d1e6e2684843d53\t"
    "72664b9106121eea5f3fefade7d44e70ea01100ed432878af331efd22e31c0ca\n"
    "platform\tdarwin-arm64\t"
    "8a896e097405a084f5aa8fcac6f942a2d2c934601b48b817ffe25d2b42128965\t"
    "586f7877041ad21538c99b1693183def87b69ddbdad61341f937c28948ae98bc\n"
    "platform\tdarwin-x86_64\t"
    "29e87f9c2ef3747143d529aa422b138acc9ca4e6a84038538e8789ae2355f589\t"
    "5336b6986f8ad8be4f6c57da70b03f132d187580ee5ee1d75bd7af0d41b7d0a1\n"
)
if TOOLCHAIN_MANIFEST_PATH.is_symlink() or not TOOLCHAIN_MANIFEST_PATH.is_file():
    fail("Release toolchain manifest must be a tracked regular file")
if TOOLCHAIN_MANIFEST != expected_toolchain_manifest:
    fail("Release toolchain manifest must contain the exact official Rojo 7.5.1 hashes")


def require_toolchain_fixture(
    executable_name: str, manifest_name: str, expected_sha256: str
):
    executable = TOOLCHAIN_FIXTURE_DIR / executable_name
    manifest = TOOLCHAIN_FIXTURE_DIR / manifest_name
    if executable.is_symlink() or not executable.is_file():
        fail(f"Toolchain fixture {executable_name} must be a regular file")
    if executable.stat().st_mode & 0o111 == 0:
        fail(f"Toolchain fixture {executable_name} must be executable")
    actual_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        fail(f"Toolchain fixture {executable_name} changed without a manifest update")
    expected_manifest = (
        "schema\tracer-release-toolchain-v1\n"
        "tool\trojo-rbx/rojo\t7.5.1\n"
        f"platform\tlinux-x86_64\t{expected_sha256}\t{expected_sha256}\n"
        f"platform\tdarwin-arm64\t{expected_sha256}\t{expected_sha256}\n"
        f"platform\tdarwin-x86_64\t{expected_sha256}\t{expected_sha256}\n"
    )
    if manifest.is_symlink() or not manifest.is_file():
        fail(f"Toolchain fixture manifest {manifest_name} must be a regular file")
    if manifest.read_text() != expected_manifest:
        fail(f"Toolchain fixture manifest {manifest_name} has a stale exact hash")


require_toolchain_fixture(
    "fake-rojo",
    "manifest.tsv",
    "dd5d3bb68570d69107410b1f5864755bd5b281e6ea46810cf71e1ffef89ae2e0",
)
require_toolchain_fixture(
    "fake-rojo-self-mutating",
    "self-mutating-manifest.tsv",
    "e07cafc6f578bf3bf7edefdd8c5660f8ecc9b30d1e0c3ab662340645f5278d9c",
)
require_toolchain_fixture(
    "fake-rojo-wrong-version",
    "wrong-version-manifest.tsv",
    "2f42f5d4dc718cef0c7ba1958f102682cb7bea614a64cf4d96798c7adce2661b",
)

if RELEASE_BUILD_SCRIPT_PATH.stat().st_mode & 0o111 == 0:
    fail("Release snapshot builder must be executable")
if not RELEASE_BUILD_SCRIPT.startswith(
    "#!/bin/bash -p\nset +x\nset +a\nset -euo pipefail\n"
):
    fail("Release snapshot builder must enter through privileged absolute Bash")

for token in [
    'EXPECTED_ROJO_VERSION="Rojo 7.5.1"',
    'TOOLCHAIN_MANIFEST_RELATIVE="scripts/racer-release-toolchain.tsv"',
    'RELEASE_PLATFORM="$(detect_release_platform)"',
    '/usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C',
    'GIT_CONFIG_NOSYSTEM=1',
    'GIT_CONFIG_GLOBAL=/dev/null',
    '/usr/bin/git -c safe.directory="${ROOT_DIR}"',
    'git_repo archive --format=tar --output="${ARCHIVE_FILE}" "${GIT_COMMIT}"',
    '/usr/bin/tar -xf "${ARCHIVE_FILE}" -C "${SNAPSHOT_DIR}"',
    'load_toolchain_manifest "${TOOLCHAIN_MANIFEST}"',
    'ROJO_SOURCE="${HOME}/.aftman/tool-storage/rojo-rbx/rojo/${ROJO_STORAGE_VERSION}/rojo"',
    'Release Rojo must be a regular non-symlink file in canonical Aftman storage.',
    'Release Rojo SHA-256 does not match the authenticated platform manifest.',
    '/bin/cp "${ROJO_SOURCE}" "${PRIVATE_ROJO}"',
    '/bin/cat > "${PLACE_IDS_FILE}" <<EOF',
    '/bin/cat > "${BUILD_INFO_FILE}" <<EOF',
    'require_private_rojo_hash "after its version check"',
    'BUILD_INFO_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedBuildInfo.lua"',
    'PLACE_IDS_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedPlaceIds.lua"',
    'cd "${SNAPSHOT_DIR}"',
    '"${PRIVATE_ROJO}" --version',
    '"${PRIVATE_ROJO}" build "racer.project.json" --output "${SNAPSHOT_OUTPUT}"',
    'mv -f "${OUTPUT_TEMP}" "${OUTPUT_FILE}"',
]:
    if token not in RELEASE_BUILD_SCRIPT:
        fail(f"Release snapshot builder contract is missing: {token}")

archive_index = RELEASE_BUILD_SCRIPT.index("git_repo archive")
extract_index = RELEASE_BUILD_SCRIPT.index(
    'tar -xf "${ARCHIVE_FILE}" -C "${SNAPSHOT_DIR}"'
)
manifest_index = RELEASE_BUILD_SCRIPT.index(
    'load_toolchain_manifest "${TOOLCHAIN_MANIFEST}"'
)
canonical_rojo_index = RELEASE_BUILD_SCRIPT.index(
    'ROJO_SOURCE="${HOME}/.aftman/tool-storage/rojo-rbx/rojo/${ROJO_STORAGE_VERSION}/rojo"'
)
private_copy_index = RELEASE_BUILD_SCRIPT.index(
    '/bin/cp "${ROJO_SOURCE}" "${PRIVATE_ROJO}"'
)
metadata_index = RELEASE_BUILD_SCRIPT.index(
    'BUILD_INFO_FILE="${SNAPSHOT_DIR}/src/shared/GeneratedBuildInfo.lua"'
)
snapshot_cwd_index = RELEASE_BUILD_SCRIPT.index('cd "${SNAPSHOT_DIR}"')
version_check_index = RELEASE_BUILD_SCRIPT.index(
    'if [[ "${ACTUAL_ROJO_VERSION}" != "${EXPECTED_ROJO_VERSION}" ]]'
)
rojo_build_index = RELEASE_BUILD_SCRIPT.index(
    '"${PRIVATE_ROJO}" build "racer.project.json" --output "${SNAPSHOT_OUTPUT}"'
)
if not (
    archive_index
    < extract_index
    < manifest_index
    < canonical_rojo_index
    < private_copy_index
    < metadata_index
    < snapshot_cwd_index
    < version_check_index
    < rojo_build_index
):
    fail(
        "Release builder must check pinned Rojo and build from the same archived "
        "snapshot working directory"
    )

for forbidden in [
    '"${ROOT_DIR}/src/shared/GeneratedBuildInfo.lua"',
    '"${ROOT_DIR}/src/shared/GeneratedPlaceIds.lua"',
    "RACER_ROJO_PATH",
    "SKIP_ROJO_SHA",
    "rojo --version",
    'LC_ALL=C rojo build',
    "#!/usr/bin/env bash",
    '\n  git -c safe.directory="${ROOT_DIR}"',
    '\ntar -xf "${ARCHIVE_FILE}"',
    '\ncat > "${PLACE_IDS_FILE}"',
    '\ncat > "${BUILD_INFO_FILE}"',
    "ReleasePlatform =",
    "RojoBinarySha256 =",
    "ToolchainPlatform =",
]:
    if forbidden in RELEASE_BUILD_SCRIPT:
        fail(f"Release snapshot builder must not write a live generated module: {forbidden}")

if RELEASE_BUILD_TEST_PATH.stat().st_mode & 0o111 == 0:
    fail("Release snapshot integration test must be executable")

for token in [
    'FIXED_PUBLISHED_AT="2000-01-02T03:04:05Z"',
    'cmp -s "${FIRST_BUILD}" "${SECOND_BUILD}"',
    'FOREIGN_CALLER_DIR="${TEMP_ROOT}/foreign-caller"',
    'cmp -s "${FIRST_BUILD}" "${FOREIGN_CWD_BUILD}"',
    "Uncommitted integration-test mutation",
    'cmp -s "${FIRST_BUILD}" "${DIRTY_BUILD}"',
    '"${PUBLISHER}" --build-only',
    "Release helper executed a PATH Rojo impostor.",
    "Release helper executed a PATH Bash impostor.",
    "Release helper executed a PATH cat impostor.",
    "Release helper executed a PATH Git impostor.",
    "Release helper executed a PATH tar impostor.",
    "Release helper evaluated inherited BASH_ENV before authentication.",
    'TAR_OPTIONS="--racer-toolchain-poison"',
    "Release helper did not reject a wrong canonical Rojo SHA-256.",
    "Release helper did not reject a canonical Rojo symlink.",
    "Release helper did not reject a nonregular canonical Rojo path.",
    "Release helper did not detect a self-mutating private Rojo copy.",
    "Release helper did not reject an authenticated Rojo with the wrong version.",
    "Release helper did not reject extra toolchain manifest fields.",
    "Release helper did not reject a snapshot toolchain manifest symlink.",
    'PERL5OPT="-MRacerToolchainPoisonMustNotLoad"',
    'scripts/test-fixtures/release-toolchain',
]:
    if token not in RELEASE_BUILD_TEST:
        fail(f"Release snapshot integration coverage is missing: {token}")

if PUBLISH_STATE_SCRIPT_PATH.stat().st_mode & 0o111 == 0:
    fail("Pending publish state helper must be executable")

for token in [
    'STATE_PATH = BUILD_DIR / "racer-publish-pending.json"',
    'os.link(temporary, STATE_PATH)',
    'os.replace(temporary, STATE_PATH)',
    'os.fsync(stream.fileno())',
    'fcntl.flock(descriptor, fcntl.LOCK_EX)',
    'stat.S_IMODE(metadata.st_mode) != 0o600',
    'state == "prepared"',
    '"state"] = "version-recorded"',
    'integer_field(place_ids, "LobbyPlaceId")',
    'integer_field(place_ids, "RacerPlaceId")',
    'STATE_PATH.unlink()',
    'RELEASE_LOCK_NAME = "racer-publish-release.lock"',
    'LEGACY_RELEASE_LOCK_PATH = BUILD_DIR / ".racer-publish-release.lock"',
    'fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)',
    'os.O_NOFOLLOW | os.O_NONBLOCK',
    'descriptor_metadata.st_nlink != 1',
    'descriptor_metadata.st_uid != common_metadata.st_uid',
    'probe_inherited_release_lock(common_descriptor, common_metadata)',
    'validate_just_acquired_release_lock()',
    '"worktree",\n                "list",\n                "--porcelain",\n                "-z"',
    'only the Git common-directory owner may create the',
    'close_unexpected_descriptors(secret=secret)',
    'for directory in ("/dev/fd", "/proc/self/fd")',
    'os.execve(command[0], command, environment)',
    'commands.add_parser("with-release-lock")',
    'commands.add_parser("assert-release-lock")',
]:
    if token not in PUBLISH_STATE_SCRIPT:
        fail(f"Pending publish state contract is missing: {token}")

with_lock_body = PUBLISH_STATE_SCRIPT[
    PUBLISH_STATE_SCRIPT.index("def command_with_release_lock(") :
    PUBLISH_STATE_SCRIPT.index("def command_assert_release_lock(")
]
if "validate_inherited_release_lock()" in with_lock_body:
    fail("Secret-bearing lock acquisition must not run the fork ownership probe")
if not (
    with_lock_body.index("validate_just_acquired_release_lock()")
    < with_lock_body.index("close_unexpected_descriptors(secret=secret)")
    < with_lock_body.index("os.execve(command[0], command, environment)")
):
    fail("Lock acquisition must validate without fork and close ambient FDs before exec")

if PUBLISH_RECOVERY_TEST_PATH.stat().st_mode & 0o111 == 0:
    fail("Pending publish recovery integration test must be executable")

for token in [
    'test_failed_request_and_retry(parent)',
    'test_invalid_responses(parent)',
    'test_build_only(parent)',
    'test_reproducible_artifact_integrity(parent)',
    'test_conflict_and_crash_resume(parent)',
    'test_lookup_failure_resume(parent)',
    'test_recovery_ref_reachability(parent)',
    'test_recovery_ref_crash_resume(parent)',
    'test_recovery_ref_guards(parent)',
    'test_mismatches_and_corruption(parent)',
    'test_atomic_state_operations(parent)',
    'mutate_after_state_create=True',
    'if secret.encode() in raw_pending:',
    'bless_current_artifact_in_manifest(gameplay)',
    'VersionBuild = "tampered"',
    'bless_current_artifact_in_manifest(extra)',
    'UnexpectedGameplay',
    'valid Studio finalization did not rebuild the artifact once',
    '"gc", "--prune=now"',
    'simulated ref deletion crash state was not constructed',
    'symbolic recovery ref failure changed its target branch',
]:
    if token not in PUBLISH_RECOVERY_TEST:
        fail(f"Pending publish recovery coverage is missing: {token}")

if RELEASE_LOCK_TEST_PATH.stat().st_mode & 0o111 == 0:
    fail("Release lock integration test must be executable")

for token in [
    '"second concurrent release"',
    '"contender while critical child survived"',
    '"spoofed unlocked correct inode on FD8"',
    'cases = ("symlink", "hardlink", "mode", "directory", "fifo", "nonempty")',
    '"legacy build lock path"',
    'git(repo, "worktree", "add"',
    '"successful reuse replaced the persistent lock inode"',
    '"release helper did not preserve the exec child\'s signal"',
    '"high ambient FD survived a lowered RLIMIT handoff"',
    '"legacy lock in another linked worktree"',
]:
    if token not in RELEASE_LOCK_TEST:
        fail(f"Release lock dynamic coverage is missing: {token}")

if FINALIZE_SCRIPT_PATH.stat().st_mode & 0o111 == 0:
    fail("Studio publish finalizer must be executable")

finalize_statements = [
    line.strip()
    for line in FINALIZE_SCRIPT.splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
if finalize_statements[:4] != [
    "set +x",
    "set +a",
    "unset ROBLOX_API_KEY RACER_PUBLISH_API_KEY",
    "set -euo pipefail",
]:
    fail("Studio finalizer must scrub inherited credentials before any child process")
if FINALIZE_SCRIPT.count("ROBLOX_API_KEY") != 1:
    fail("Studio finalizer must mention ROBLOX_API_KEY only in its early unset")
if FINALIZE_SCRIPT.count("RACER_PUBLISH_API_KEY") != 1:
    fail("Studio finalizer must mention RACER_PUBLISH_API_KEY only in its early unset")

for token in [
    "unset ROBLOX_API_KEY RACER_PUBLISH_API_KEY",
    '${ROBLOX_RACER_PLACE_ID:?ROBLOX_RACER_PLACE_ID is required}',
    'STATE_HELPER="${SCRIPT_DIR}/racer-publish-state.py"',
    'BUILD_HELPER="${SCRIPT_DIR}/build-racer-release.sh"',
    'PENDING_REF="refs/racer-publish/pending"',
    'LOCK_CONTEXT_VALUE="racer-release-lock-v1"',
    '/usr/bin/python3 -I "${STATE_HELPER}" with-release-lock --',
    '/usr/bin/python3 -I "${STATE_HELPER}" assert-release-lock',
    "status --porcelain=v1 --untracked-files=all --ignore-submodules=none",
    'state_helper inspect',
    'state_helper validate-artifact',
    'ORIGINAL_ARTIFACT_SHA256="$(sha256_file "${ARTIFACT_FILE}")"',
    'ORIGINAL_ARTIFACT_SIZE="$(file_size "${ARTIFACT_FILE}")"',
    'REBUILT_ARTIFACT="${TEMP_ROOT}/racer-rebuilt.rbxlx"',
    'REBUILT_ARTIFACT_SHA256="$(sha256_file "${REBUILT_ARTIFACT}")"',
    'REBUILT_ARTIFACT_SIZE="$(file_size "${REBUILT_ARTIFACT}")"',
    '/usr/bin/cmp -s "${ARTIFACT_FILE}" "${REBUILT_ARTIFACT}"',
    'require_original_artifact_state',
    'state_helper record-version "${PLACE_VERSION}"',
    'update-ref "refs/tags/${TAG}" "${GIT_COMMIT}" ""',
    'refs/tags/${TAG}^{commit}',
    'symbolic-ref -q "${PENDING_REF}"',
    'require_pending_ref_state',
    'update-ref --no-deref -d "${PENDING_REF}" "${GIT_COMMIT}"',
    "delete_pending_ref",
    'state_helper clear \\',
    '--artifact-sha256 "${ARTIFACT_SHA256}"',
]:
    if token not in FINALIZE_SCRIPT:
        fail(f"Studio publish finalizer contract is missing: {token}")

manifest_validation_index = FINALIZE_SCRIPT.index(
    'VALIDATED_SHA256="$(state_helper validate-artifact)"'
)
rebuild_index = FINALIZE_SCRIPT.index('/bin/bash -p "${BUILD_HELPER}" \\', manifest_validation_index)
rebuilt_sha_index = FINALIZE_SCRIPT.index(
    'REBUILT_ARTIFACT_SHA256="$(sha256_file "${REBUILT_ARTIFACT}")"',
    rebuild_index,
)
byte_compare_index = FINALIZE_SCRIPT.index(
    '/usr/bin/cmp -s "${ARTIFACT_FILE}" "${REBUILT_ARTIFACT}"', rebuilt_sha_index
)
first_artifact_recheck_index = FINALIZE_SCRIPT.index(
    "require_original_artifact_state", byte_compare_index
)
record_version_index = FINALIZE_SCRIPT.index(
    'state_helper record-version "${PLACE_VERSION}"',
    first_artifact_recheck_index,
)
second_artifact_recheck_index = FINALIZE_SCRIPT.index(
    "require_original_artifact_state", record_version_index
)
tag_create_index = FINALIZE_SCRIPT.index(
    'update-ref "refs/tags/${TAG}" "${GIT_COMMIT}" ""',
    second_artifact_recheck_index,
)
lookup_index = FINALIZE_SCRIPT.index('LOOKUP_OUTPUT="$(/bin/bash -p "${LOOKUP_SCRIPT}"', tag_create_index)
final_ref_recheck_index = FINALIZE_SCRIPT.index(
    "require_pending_ref_state", lookup_index
)
delete_ref_call_index = FINALIZE_SCRIPT.index(
    "delete_pending_ref", final_ref_recheck_index
)
clear_state_index = FINALIZE_SCRIPT.index(
    'state_helper clear \\', delete_ref_call_index
)
if not (
    manifest_validation_index
    < rebuild_index
    < rebuilt_sha_index
    < byte_compare_index
    < first_artifact_recheck_index
    < record_version_index
    < second_artifact_recheck_index
    < tag_create_index
    < lookup_index
    < final_ref_recheck_index
    < delete_ref_call_index
    < clear_state_index
):
    fail(
        "Studio finalizer must reproducibly rebuild and byte-compare before recording, "
        "then recheck the original artifact before tag creation and retire its recovery "
        "ref only after exact lookup"
    )

if FINALIZE_SCRIPT.count("require_original_artifact_state") < 3:
    fail("Studio finalizer must guard the original artifact before record and tag")

if FINALIZE_SCRIPT.count("require_clean_tree") < 3:
    fail("Studio publish finalizer must check cleanliness before and after validation")

for forbidden in [
    "curl ",
    "git_repo tag ",
    "git tag ",
    "tag -f",
    'update-ref -d "refs/tags/',
    "--force",
    "RELEASE_LOCK_DIR=",
    'mkdir "${RELEASE_LOCK_DIR}"',
    'rmdir "${RELEASE_LOCK_DIR}"',
]:
    if forbidden in FINALIZE_SCRIPT:
        fail(f"Studio publish finalizer must not contain: {forbidden}")

if 'git -c safe.directory="${ROOT_DIR}" -C "${ROOT_DIR}"' not in LOOKUP_SCRIPT:
    fail("PlaceVersion lookup must support the release container's mounted git repository")

if "python3" not in DOCKERFILE:
    fail("The release image must install Python for publish and verification scripts")
for token in [
    "ARG TARGETARCH\n",
    'test "${TARGETARCH}" = "amd64"',
    'test "$(/usr/bin/dpkg --print-architecture)" = "amd64"',
    "194fe81e24ae7cc1f3141fd1d42db6cb60f03d42735d12ae865fe2db11ea6f0e",
    "3b13b10838fb7f7aafae16a9a01085439c75619bb9b78a1b5b787eab81ddf6e4",
    "/usr/bin/curl --disable --fail --silent --show-error --location",
    '/usr/bin/sha256sum --check --strict -',
    '/usr/bin/install -m 0755 "${extracted_path}" /usr/local/bin/aftman',
]:
    if token not in DOCKERFILE:
        fail(f"Docker Aftman authentication contract is missing: {token}")
if "ARG TARGETARCH=" in DOCKERFILE or "ARG AFTMAN_" in DOCKERFILE:
    fail("Docker must not default its architecture or expose overridable Aftman hashes")
for token in [
    "RUN /usr/sbin/groupadd --gid 1000 codex",
    "--uid 1000",
    "--gid codex",
    "--create-home",
    "/usr/bin/install -d -m 0755 -o codex -g codex /home/codex/.aftman",
    'ENV HOME="/home/codex"',
    "USER codex",
]:
    if token not in DOCKERFILE:
        fail(f"Docker non-root runtime contract is missing: {token}")
if not (
    DOCKERFILE.index("/home/codex/.aftman")
    < DOCKERFILE.index("USER codex")
    < DOCKERFILE.index("ENTRYPOINT")
):
    fail("Docker must initialize the owned tool home before its non-root runtime")
if DOCKERFILE.count("USER ") != 1 or "USER root" in DOCKERFILE:
    fail("Docker image must have exactly one final non-root user")

if "ROBLOX_API_KEY" in DOCKER_COMPOSE:
    fail("Compose must not inject the Roblox API key into ordinary commands")
if "\n    user:" in DOCKER_COMPOSE:
    fail("Compose must not override the image's non-root user")
if "\n      HOME:" in DOCKER_COMPOSE:
    fail("Compose must inherit the image's non-root HOME")
if "      - roblox-tools:/home/codex/.aftman\n" not in DOCKER_COMPOSE:
    fail("Compose must mount its tool volume at the owned Aftman directory")
if "nocopy" in DOCKER_COMPOSE:
    fail("Compose must initialize a fresh tool volume from image ownership")
if not DOCKER_ENTRYPOINT.startswith("#!/bin/bash\n"):
    fail("Docker bootstrap must start through the image's trusted absolute Bash")

for token in [
    'if [[ "${EUID}" -eq 0 ]]; then',
    'if [[ -z "${HOME:-}" || "${HOME}" != /* ]]; then',
    'AFTMAN_HOME="${HOME}/.aftman"',
    '! -O "${AFTMAN_HOME}"',
    '! -w "${AFTMAN_HOME}"',
    "follow the README migration",
    "/usr/bin/env -u ROBLOX_API_KEY -u RACER_PUBLISH_API_KEY "
    "/usr/local/bin/aftman install --no-trust-check",
    'exec "$@"',
]:
    if token not in DOCKER_ENTRYPOINT:
        fail(f"Docker non-root bootstrap contract is missing: {token}")
if not (
    DOCKER_ENTRYPOINT.index('if [[ "${EUID}" -eq 0 ]]')
    < DOCKER_ENTRYPOINT.index('AFTMAN_HOME="${HOME}/.aftman"')
    < DOCKER_ENTRYPOINT.index("/usr/local/bin/aftman install")
    < DOCKER_ENTRYPOINT.index('exec "$@"')
):
    fail("Docker bootstrap must guard non-root ownership before installing tools")
for forbidden in ("chown ", "sudo ", "gosu ", "su -"):
    if forbidden in DOCKER_ENTRYPOINT:
        fail("Docker bootstrap must not repair ownership or switch users at runtime")

for token in [
    'CREDENTIAL_NAMES = ("ROBLOX_API_KEY", "RACER_PUBLISH_API_KEY")',
    '"/bin/bash",\n            "-a",\n            "-x",',
    '"credentialsPreserved": True',
    'assert_no_credentials("successful entrypoint output"',
    'if "ROBLOX_API_KEY" in roblox_service:',
    'if "\\n    user:" in roblox_service:',
    'runtime contract must itself run as a non-root user',
    'entrypoint did not reject an unwritable tool volume',
    'entrypoint did not reject a relative HOME',
    'entrypoint did not reject a missing tool volume',
    'entrypoint did not reject a symlink tool volume',
]:
    if token not in DOCKER_BOOTSTRAP_TEST:
        fail(f"Docker bootstrap credential regression coverage is missing: {token}")

for token in [
    "FAKE_GIT =",
    '"direct Studio finalizer"',
    '"ROBLOX_API_KEY",\n            "RACER_PUBLISH_API_KEY",',
    'str(repo / "scripts/finalize-studio-publish.sh")',
    '"BASH_ENV": str(bash_env)',
    '"PYTHONPATH": str(attack_python)',
    'run_hostile_shell_publisher(',
    '"publisher-to-finalizer exec changed PID or lock inode"',
    '"critical curl child inherited an unlocked FD 8"',
    '"secret transport FD 9 remained open in curl"',
]:
    if token not in PUBLISH_SECRET_TEST:
        fail(f"Studio finalizer credential regression coverage is missing: {token}")

if (
    "docker compose run --rm -e ROBLOX_API_KEY roblox scripts/publish-place.sh"
    not in README
):
    fail("README must require explicit API-key injection for container publishing")
if (
    "docker compose run --rm --user root --entrypoint /bin/chown roblox"
    not in README
    or "On native Linux, UID 1000" not in README
    or "Git common directory" not in README
    or 'test "${EUID}" -eq 1000' not in README
    or 'test -O "${HOME}/.aftman"' not in README
):
    fail("README must document tool-volume migration and native-Linux ownership")

for token in [
    "racer-publish-release.lock",
    "same inode",
    "linked worktree",
    "never run a pre-migration release script",
    "cannot coordinate independent clones or different machines",
    "anonymous pipe FD 9",
    "delete, truncate, chmod, replace, symlink, or hard-link it",
]:
    if token not in README:
        fail(f"README release-lock documentation is missing: {token}")

for token in [
    "operation_id(operation)",
    'f"{ASSETS_BASE}/assets/{asset_id}"',
    'DELIVERY_BASE = "https://apis.roblox.com/asset-delivery-api/v1"',
    "moderationState",
    "fetch_cdn_png(location)",
    "delivery_errors_are_transient(errors)",
    "API_OPENER = urllib.request.build_opener(NoRedirectHandler())",
    'STATE_PATH = ROOT / "build/racer-texture-upload-state.json"',
    '"Racer Sprites v3"',
]:
    if token not in UPLOAD_SCRIPT:
        fail(f"Racer texture upload verification is missing: {token}")

upload_runtime = runpy.run_path(
    str(ROOT / "scripts/upload-racer-textures.py"),
    run_name="racer_texture_upload_contract",
)
try:
    upload_runtime["parse_png"](
        (ROOT / "assets/racer/textures/racer-sprites-v3.png").read_bytes(),
        "Racer atlas",
        (1024, 1024),
    )
except upload_runtime["UploadError"] as error:
    fail(f"Racer upload validator rejected the production atlas: {error}")
try:
    upload_runtime["parse_png"](b"\x89PNG\r\n\x1a\n" + b"\x00" * 25, "truncated PNG")
except upload_runtime["UploadError"]:
    pass
else:
    fail("Racer upload validator accepted a truncated PNG")
if upload_runtime["operation_id"]({"path": "operations/id.with.dot"}) != "id.with.dot":
    fail("Racer upload validator rejected a safe operation path segment")
if not upload_runtime["delivery_errors_are_transient"]([{"customErrorCode": 18}]):
    fail("Racer upload validator must retry AssetPendingReview delivery responses")
if not upload_runtime["delivery_errors_are_transient"]([{"customErrorCode": 13}]):
    fail("Racer upload validator must retry propagating AssetNotFound delivery responses")
if upload_runtime["delivery_errors_are_transient"]([{"customErrorCode": 99, "message": "invalid"}]):
    fail("Racer upload validator must reject terminal delivery responses")
try:
    upload_runtime["require_image_asset"](
        {
            "assetId": 1,
            "path": "assets/1",
            "assetType": "Image",
            "revisionId": "1",
            "creationContext": {"creator": {"groupId": 2}},
        },
        1,
        "userId",
        2,
    )
except upload_runtime["UploadError"]:
    pass
else:
    fail("Racer upload validator accepted a conflicting creator kind")


def require(pattern: str, text: str, message: str):
    if not re.search(pattern, text, re.MULTILINE | re.DOTALL):
        fail(message)


def read_png_rgba(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        fail(f"{path} must be a PNG")
    offset = 8
    width = height = None
    color_type = None
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or color_type != 6:
                fail(f"{path} must be an 8-bit RGBA PNG")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None or color_type is None:
        fail(f"{path} has no PNG header")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type != 0:
            fail(f"{path} must use unfiltered scanlines for parity inspection")
        rows.append(row)
        previous = row
    return width, height, rows


SPRITE_SCALE = 0.3 / 80
PLAYER_WIDTH = 80 * SPRITE_SCALE


def overlap(x1: float, w1: float, x2: float, w2: float, percent: float = 1.0) -> bool:
    half = percent / 2
    min1 = x1 - (w1 * half)
    max1 = x1 + (w1 * half)
    min2 = x2 - (w2 * half)
    max2 = x2 + (w2 * half)
    return not ((max1 < min2) or (min1 > max2))


def roadside_center(offset: float, sprite_width: int) -> float:
    side = 1 if offset > 0 else -1
    return offset + (sprite_width * SPRITE_SCALE / 2 * side)


def original_render_sprite_center(offset: float, sprite_width: int) -> float:
    # Render.sprite uses an edge anchor for roadside sprites:
    # offsetX = -1 for left-side sprites, 0 for right-side sprites.
    offset_x = -1 if offset < 0 else 0
    sprite_width_world = sprite_width * SPRITE_SCALE
    return offset + sprite_width_world * (offset_x + 0.5)


version = re.search(r'VersionBuild\s*=\s*"([^"]+)"', CONFIG)
if not version:
    fail("RacerConfig.VersionBuild must be present")

if "game.PlaceVersion" not in SERVER:
    fail("version badge must use DataModel.PlaceVersion instead of a manually bumped build number")

if "label.Text = `build {RacerConfig.VersionBuild}`" in SERVER:
    fail("version badge must not render the manual VersionBuild directly")

texture_asset = re.search(r'Image\s*=\s*"rbxassetid://(\d+)"', TEXTURES)
if not texture_asset:
    fail("RacerTextures.Image must point at an uploaded Roblox image asset")

texture_png = ROOT / "assets/racer/textures/racer-sprites-v3.png"
if not texture_png.exists():
    fail("local racer texture atlas must exist")
texture_meta = ROOT / "assets/racer/textures/racer-sprites-v3.json"
if not texture_meta.exists():
    fail("local racer texture atlas metadata must exist")
texture_meta_data = json.loads(texture_meta.read_text())
if texture_meta_data.get("image") != "racer-sprites-v3.png":
    fail("local racer texture metadata must describe the v3 atlas")
if texture_meta_data.get("robloxAssetId") != texture_asset.group(1):
    fail("RacerTextures.Image must match the uploaded asset recorded in texture metadata")
texture_digest = hashlib.sha256(texture_png.read_bytes()).hexdigest()
if texture_meta_data.get("sha256") != texture_digest:
    fail("local racer texture atlas changed and must be uploaded before publishing")
if texture_meta_data.get("size") != [1024, 1024]:
    fail("local racer texture metadata must describe the 1024x1024 v3 atlas")
texture_width, texture_height, texture_rows = read_png_rgba(texture_png)
if (texture_width, texture_height) != (1024, 1024):
    fail("racer-sprites-v3 atlas must be 1024x1024")
if not re.search(r"SheetSize\s*=\s*Vector2\.new\(1024,\s*1024\)", TEXTURES):
    fail("RacerTextures.SheetSize must match the 1024x1024 v3 atlas")
texture_source_dir = ROOT / "assets/racer/textures/v3-sources"
if not texture_source_dir.exists():
    fail("racer-sprites-v3 must have committed source PNG sprites")
template_player_sprites = {
    "PLAYER_LEFT",
    "PLAYER_STRAIGHT",
    "PLAYER_RIGHT",
    "PLAYER_UPHILL_LEFT",
    "PLAYER_UPHILL_STRAIGHT",
    "PLAYER_UPHILL_RIGHT",
}
texture_rects = {}
template_player_bounds = {}
for match in re.finditer(
    r"([A-Z0-9_]+)\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*w\s*=\s*(\d+),\s*h\s*=\s*(\d+)\s*\}",
    TEXTURES,
):
    name, x, y, w, h = match.groups()
    x, y, w, h = int(x), int(y), int(w), int(h)
    texture_rects[name] = {"x": x, "y": y, "w": w, "h": h}
    if texture_meta_data["sprites"].get(name) != texture_rects[name]:
        fail(f"texture rect for {name} must match racer-sprites-v3.json")
    if x < 0 or y < 0 or x + w > texture_width or y + h > texture_height:
        fail(f"texture rect for {name} is outside the atlas")
    bottom_row = texture_rows[y + h - 1]
    bottom_alpha_count = sum(1 for pixel_x in range(x, x + w) if bottom_row[pixel_x * 4 + 3] > 0)
    if bottom_alpha_count == 0:
        fail(f"texture sprite {name} must touch the bottom of its hitbox rect")
    if name in template_player_sprites:
        visible = [
            (local_x, local_y)
            for local_y in range(h)
            for local_x in range(w)
            if texture_rows[y + local_y][(x + local_x) * 4 + 3] > 0
        ]
        left = min(local_x for local_x, _ in visible)
        top = min(local_y for _, local_y in visible)
        right = max(local_x for local_x, _ in visible)
        bottom = max(local_y for _, local_y in visible)
        visible_width = right - left + 1
        visible_height = bottom - top + 1
        if visible_width < w * 0.95 or visible_height < h * 0.90:
            fail(f"texture sprite {name} must fill its original Racer pose rectangle")
        template_player_bounds[name] = (visible_width, visible_height)

for direction in ("LEFT", "STRAIGHT", "RIGHT"):
    normal_height = template_player_bounds[f"PLAYER_{direction}"][1]
    uphill_height = template_player_bounds[f"PLAYER_UPHILL_{direction}"][1]
    if uphill_height < normal_height + 4:
        fail(f"PLAYER_UPHILL_{direction} must stay visibly taller than its normal-road pose")

for prefix in ("PLAYER_", "PLAYER_UPHILL_"):
    straight_name = f"{prefix}STRAIGHT"
    straight = texture_rects[straight_name]
    for direction in ("LEFT", "RIGHT"):
        turn_name = f"{prefix}{direction}"
        turn = texture_rects[turn_name]
        changed = 0
        for local_y in range(straight["h"]):
            straight_row = texture_rows[straight["y"] + local_y]
            turn_row = texture_rows[turn["y"] + local_y]
            for local_x in range(straight["w"]):
                straight_offset = (straight["x"] + local_x) * 4
                turn_offset = (turn["x"] + local_x) * 4
                if straight_row[straight_offset : straight_offset + 4] != turn_row[turn_offset : turn_offset + 4]:
                    changed += 1
        if changed < straight["w"] * straight["h"] * 0.12:
            fail(f"texture sprite {turn_name} must read distinctly from {straight_name}")

palm_match = re.search(
    r"PALM_TREE\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*w\s*=\s*(\d+),\s*h\s*=\s*(\d+)\s*\}",
    TEXTURES,
)
if not palm_match:
    fail("texture rect missing for PALM_TREE")
palm_x, palm_y, palm_w, palm_h = [int(value) for value in palm_match.groups()]
top_pixels = []
lower_pixels = []
for yy in range(palm_y, palm_y + palm_h):
    for xx in range(palm_x, palm_x + palm_w):
        alpha = texture_rows[yy][xx * 4 + 3]
        if alpha == 0:
            continue
        local_x = xx - palm_x
        local_y = yy - palm_y
        if local_y < palm_h * 0.42:
            top_pixels.append((local_x, alpha))
        elif local_y > palm_h * 0.55:
            lower_pixels.append((local_x, alpha))
if not top_pixels or not lower_pixels:
    fail("PALM_TREE must include visible crown and trunk pixels")
palm_top_center = sum(x * alpha for x, alpha in top_pixels) / sum(alpha for _, alpha in top_pixels)
palm_lower_center = sum(x * alpha for x, alpha in lower_pixels) / sum(alpha for _, alpha in lower_pixels)
palm_left_crown = sum(alpha for x, alpha in top_pixels if x < palm_w * 0.5)
palm_right_crown = sum(alpha for x, alpha in top_pixels if x >= palm_w * 0.5)
if not (palm_top_center < palm_lower_center - palm_w * 0.08 and palm_left_crown > palm_right_crown * 1.2):
    fail("PALM_TREE texture must read right-to-left like the original right-side palm")

expected_sprites = {
    "PALM_TREE": (215, 540),
    "BILLBOARD08": (385, 265),
    "TREE1": (360, 360),
    "DEAD_TREE1": (135, 332),
    "BILLBOARD09": (328, 282),
    "BOULDER3": (320, 220),
    "COLUMN": (200, 315),
    "BILLBOARD01": (300, 170),
    "BILLBOARD06": (298, 190),
    "BILLBOARD05": (298, 190),
    "BILLBOARD07": (298, 190),
    "BOULDER2": (298, 140),
    "TREE2": (282, 295),
    "BILLBOARD04": (268, 170),
    "DEAD_TREE2": (150, 260),
    "BOULDER1": (168, 248),
    "BUSH1": (240, 155),
    "CACTUS": (235, 118),
    "BUSH2": (232, 152),
    "BILLBOARD03": (230, 220),
    "BILLBOARD02": (215, 220),
    "STUMP": (195, 140),
    "SEMI": (122, 144),
    "TRUCK": (100, 78),
    "CAR03": (88, 55),
    "CAR02": (80, 59),
    "CAR04": (80, 57),
    "CAR01": (80, 56),
    "PLAYER_UPHILL_LEFT": (80, 45),
    "PLAYER_UPHILL_STRAIGHT": (80, 45),
    "PLAYER_UPHILL_RIGHT": (80, 45),
    "PLAYER_LEFT": (80, 41),
    "PLAYER_STRAIGHT": (80, 41),
    "PLAYER_RIGHT": (80, 41),
}

for name, (width, height) in expected_sprites.items():
    if not (texture_source_dir / f"{name}.png").exists():
        fail(f"missing source PNG for {name}")
    require(
        rf"{name}\s*=\s*\{{[^}}]*width\s*=\s*{width}[^}}]*height\s*=\s*{height}",
        CONFIG,
        f"{name} dimensions must match javascript-racer common.js",
    )
    require(
        rf"{name}\s*=\s*\{{\s*x\s*=\s*\d+,\s*y\s*=\s*\d+,\s*w\s*=\s*\d+,\s*h\s*=\s*\d+\s*\}}",
        TEXTURES,
        f"texture rect missing for {name}",
    )
    if name.startswith("PLAYER_"):
        rect = texture_rects.get(name)
        if not rect or rect["w"] < round(width * 1.5) or rect["h"] < round(height * 1.5):
            fail(f"{name} texture rect should keep a higher-resolution player sprite source for Roblox scaling")

player_hashes = {
    hashlib.sha256((texture_source_dir / f"{name}.png").read_bytes()).hexdigest()
    for name in expected_sprites
    if name.startswith("PLAYER_")
}
if len(player_hashes) < 6:
    fail("player source PNGs must include distinct steering/hill variants")

expected_player_palette = {
    (16, 17, 22, 255),
    (20, 21, 26, 255),
    (31, 36, 43, 255),
    (53, 55, 61, 255),
    (57, 60, 64, 255),
    (63, 69, 76, 255),
    (137, 88, 0, 255),
    (170, 176, 178, 255),
    (196, 132, 0, 255),
    (224, 45, 29, 255),
    (236, 239, 232, 255),
    (255, 112, 36, 255),
    (255, 210, 42, 255),
    (255, 224, 133, 255),
    (255, 235, 91, 255),
    (255, 250, 190, 255),
}

for name in template_player_sprites:
    source_width, source_height, source_rows = read_png_rgba(texture_source_dir / f"{name}.png")
    if source_width < 320 or source_height < 164:
        fail(f"{name} source must retain high-resolution paint before atlas downsampling")
    source_pixels = {
        tuple(row[offset : offset + 4])
        for row in source_rows
        for offset in range(0, len(row), 4)
    }
    transparent_pixels = {pixel for pixel in source_pixels if pixel[3] == 0}
    if transparent_pixels != {(0, 0, 0, 0)}:
        fail(f"{name} source transparency must not contain hidden RGB")
    source_palette = {pixel for pixel in source_pixels if pixel[3] > 0}
    if source_palette != expected_player_palette:
        missing = sorted(expected_player_palette - source_palette)
        unexpected = sorted(source_palette - expected_player_palette)
        fail(
            f"{name} source must use the deliberate 16-color palette "
            f"(missing={missing}, unexpected={unexpected})"
        )

if abs(PLAYER_WIDTH - 0.3) > 1e-9:
    fail("player collision width must be SPRITES.PLAYER_STRAIGHT.w * SPRITES.SCALE = 0.3")

for offset, sprite_name in [(-1.2, "BILLBOARD07"), (1.2, "BILLBOARD06"), (-2.4, "TREE1")]:
    sprite_width = expected_sprites[sprite_name][0]
    center = roadside_center(offset, sprite_width)
    render_center = original_render_sprite_center(offset, sprite_width)
    if abs(center - render_center) > 1e-9:
        fail(f"{sprite_name} collision center must match original Render.sprite visual center")

if not overlap(-1.06, PLAYER_WIDTH, roadside_center(-1.2, expected_sprites["BILLBOARD07"][0]), expected_sprites["BILLBOARD07"][0] * SPRITE_SCALE):
    fail("left roadside billboard should collide at the original edge-touch boundary")

if not overlap(1.06, PLAYER_WIDTH, roadside_center(1.2, expected_sprites["BILLBOARD06"][0]), expected_sprites["BILLBOARD06"][0] * SPRITE_SCALE):
    fail("right roadside billboard should collide at the original edge-touch boundary")

if overlap(0.95, PLAYER_WIDTH, roadside_center(1.2, expected_sprites["BILLBOARD06"][0]), expected_sprites["BILLBOARD06"][0] * SPRITE_SCALE):
    fail("roadside collision must not trigger while player is still inside the road")

for sample_name in ["PALM_TREE", "TREE1", "BOULDER3", "BUSH1", "COLUMN"]:
    sample_width = expected_sprites[sample_name][0] * SPRITE_SCALE
    sample_center = roadside_center(1.2, expected_sprites[sample_name][0])
    if not overlap(sample_center, PLAYER_WIDTH, sample_center, sample_width):
        fail(f"{sample_name} must use the same roadside collision formula as billboards")

car01_width = expected_sprites["CAR01"][0] * SPRITE_SCALE
if not overlap(0, PLAYER_WIDTH, 0.239, car01_width, 0.8):
    fail("traffic collision should include the original 0.8 overlap edge")

if overlap(0, PLAYER_WIDTH, 0.241, car01_width, 0.8):
    fail("traffic collision should not be wider than original 0.8 overlap")

expected_sets = {
    "Billboards": [
        "BILLBOARD01",
        "BILLBOARD02",
        "BILLBOARD03",
        "BILLBOARD04",
        "BILLBOARD05",
        "BILLBOARD06",
        "BILLBOARD07",
        "BILLBOARD08",
        "BILLBOARD09",
    ],
    "Plants": [
        "TREE1",
        "TREE2",
        "DEAD_TREE1",
        "DEAD_TREE2",
        "PALM_TREE",
        "BUSH1",
        "BUSH2",
        "CACTUS",
        "STUMP",
        "BOULDER1",
        "BOULDER2",
        "BOULDER3",
    ],
    "Cars": ["CAR01", "CAR02", "CAR03", "CAR04", "SEMI", "TRUCK"],
}

for set_name, names in expected_sets.items():
    match = re.search(rf"{set_name}\s*=\s*\{{(.*?)\}}", CONFIG, re.MULTILINE | re.DOTALL)
    if not match:
        fail(f"missing SpriteSets.{set_name}")
    actual = re.findall(r'"([^"]+)"', match.group(1))
    if actual != names:
        fail(f"SpriteSets.{set_name} order must match javascript-racer: {actual} != {names}")

expected_mode_flags = {
    "straight": {
        "curves": False,
        "hills": False,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "curves": {
        "curves": True,
        "hills": False,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "hills": {
        "curves": True,
        "hills": True,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "final": {
        "curves": True,
        "hills": True,
        "sprites": True,
        "traffic": True,
        "laps": True,
        "hud": True,
    },
}

for mode, expected_flags in expected_mode_flags.items():
    require(rf"{mode}\s*=\s*\{{", CONFIG, f"missing mode flags for {mode}")
    if mode == "final":
        require(r"local\s+finalTrack\s*=\s*buildFinalTrack\(\)", CONFIG, "missing inherited final track source")
        require(r"final\s*=\s*finalTrack", CONFIG, "missing final track assignment")
    else:
        require(rf"{mode}\s*=\s*build", CONFIG, f"missing track for {mode}")
    mode_match = re.search(rf"\n\t{mode}\s*=\s*\{{(.*?)\n\t\}},", CONFIG, re.DOTALL)
    if not mode_match:
        fail(f"could not parse mode flags for {mode}")
    actual_flags = {
        name: value == "true"
        for name, value in re.findall(r"(\w+)\s*=\s*(true|false)", mode_match.group(1))
    }
    for flag, expected in expected_flags.items():
        if actual_flags.get(flag) is not expected:
            fail(f"{mode}.{flag} must be {expected} to match v1-v4 feature rollout")

for token in [
    "RacerConfig.Modes.v5 = derive(RacerConfig.Modes.final",
    'codeName = "mobile-controls"',
    "mobileControls = true",
    "RacerConfig.Modes.v6 = derive(RacerConfig.Modes.v5",
    'codeName = "driver-occupants"',
    "driverOccupants = true",
    "RacerConfig.Modes.v7 = derive(RacerConfig.Modes.v6",
    'codeName = "record-boards"',
    "recordBoards = true",
    "function RacerConfig.isV5Plus(mode: string): boolean",
    "function RacerConfig.hasDriverOccupants(mode: string): boolean",
    "function RacerConfig.hasRecordBoards(mode: string): boolean",
    'Name = "v5 Mobile Controls"',
    'Name = "v6 Driver Occupants"',
    'Name = "v7 Record Boards"',
    "v5 = finalTrack",
    "v6 = finalTrack",
    "v7 = finalTrack",
    "local finalSpriteObjects = RacerConfig.buildSpriteObjects(\"final\", 2401)",
    "v5 = shallowArrayCopy(finalSpriteObjects)",
    "v6 = shallowArrayCopy(finalSpriteObjects)",
    "v7 = shallowArrayCopy(finalSpriteObjects)",
]:
    if token not in CONFIG:
        fail(f"v5/v6/v7 must explicitly inherit earlier racer versions before adding version-only behavior: {token}")

for token in [
    'ReplicatedStorage:WaitForChild("RacerV7BillboardText")',
    "if not RacerConfig.hasDriverOccupants(mode) then",
    'createOccupantFallback(car, "DriverFallback", PLAYER_CAR_Z_INDEX + 4)',
    'createOccupantFallback(car, "PassengerFallback", PLAYER_CAR_Z_INDEX + 4)',
    "fallbackOccupantColor(userId, seatIndex)",
    "RacerConfig.hasRecordBoards(mode)",
]:
    if token not in CLIENT:
        fail(f"client must gate driver and record-board features by version flags: {token}")

for token in [
    "local OCCUPANT_THUMBNAIL_RETRY_SECONDS = 5",
    "local avatarImagePending = {}",
    "local avatarImageCacheRevision = 0",
    "local function requestThumbnailForUserId(userId: number)",
    "or avatarImagePending[userId] == true",
    "avatarImagePending[userId] = true\n\ttask.spawn(function()",
    "avatarImageCache[userId] = if hasImage then image else false",
    "avatarImagePending[userId] = nil",
    "task.delay(OCCUPANT_THUMBNAIL_RETRY_SECONDS, function()",
    "avatarImageCache[userId] = nil",
    "local function cachedThumbnailForUserId(userId: number): string?",
    "requestThumbnailForUserId(userId)",
    'driverAvatar.Image = ""\n\t\t\tdriverAvatar.Visible = false',
    'passengerAvatar.Image = ""\n\t\t\tpassengerAvatar.Visible = false',
    'setOccupantFallback("DriverFallback", 0, 1, 0.34, false)',
    'setOccupantFallback("PassengerFallback", 0, 2, 0.52, false)',
    "local driverImage = if showOccupants then cachedThumbnailForUserId(activeUserId) else nil",
    "local passengerUserId = if showOccupants then passengerUserIdFor(activeUserId) else 0",
    "then cachedThumbnailForUserId(passengerUserId)",
    "showOccupants and not showDriverAvatar",
    "showOccupants and passengerUserId > 0 and not showPassengerAvatar",
    "if RacerConfig.hasDriverOccupants(state.mode.Value) then avatarImageCacheRevision else 0",
]:
    if token not in CLIENT:
        fail(f"v6+ occupant thumbnails must be async, cached, and preserve pending fallbacks: {token}")

if CLIENT.count("Players:GetUserThumbnailAsync(") != 1:
    fail("occupant thumbnails must have exactly one request site")
if CLIENT.count("requestThumbnailForUserId(") != 2:
    fail("occupant thumbnail requests must only start through the non-yielding cache helper")
if CLIENT.count("cachedThumbnailForUserId(") != 3:
    fail("only the v6+ driver and passenger paths may resolve occupant thumbnails")
if CLIENT.count("task.delay(OCCUPANT_THUMBNAIL_RETRY_SECONDS, function()") != 1:
    fail("failed occupant thumbnails must schedule exactly one temporary-cache retry")
if CLIENT.count("avatarImageCacheRevision += 1") != 2:
    fail("occupant cache completion and retry expiry must each invalidate world-screen renders")

require(
    r'setOccupantFallback\(\s*"PassengerFallback",\s*passengerUserId,\s*2,\s*0\.52,\s*'
    r"showOccupants and passengerUserId > 0 and not showPassengerAvatar\s*\)",
    CLIENT,
    "v6+ must not invent a passenger fallback when no passenger player exists",
)

require(
    r"avatarImageCache\[userId\] = if hasImage then image else false\s*"
    r"avatarImagePending\[userId\] = nil\s*"
    r"avatarImageCacheRevision \+= 1\s*"
    r"if not hasImage then\s*"
    r"task\.delay\(OCCUPANT_THUMBNAIL_RETRY_SECONDS, function\(\)\s*"
    r"if\s*avatarImageCache\[userId\] == false\s*"
    r"and avatarImagePending\[userId\] ~= true\s*then\s*"
    r"avatarImageCache\[userId\] = nil\s*"
    r"avatarImageCacheRevision \+= 1",
    CLIENT,
    "failed occupant thumbnails must use a guarded temporary negative cache and rerender on expiry",
)

occupant_gate = re.search(
    r"if not RacerConfig\.hasDriverOccupants\(mode\) then(.*?)\n\telse(.*?)\n\tend\n\n\tif RacerConfig\.isFinalLike",
    CLIENT,
    re.DOTALL,
)
if not occupant_gate:
    fail("occupant rendering must have an explicit pre-v6 reset branch")
legacy_occupant_branch, enabled_occupant_branch = occupant_gate.groups()
for forbidden in ["cachedThumbnailForUserId(", "passengerUserIdFor("]:
    if forbidden in legacy_occupant_branch:
        fail(f"v1-v5 must never request or resolve occupant users: {forbidden}")
for required in ["cachedThumbnailForUserId(activeUserId)", "cachedThumbnailForUserId(passengerUserId)"]:
    if required not in enabled_occupant_branch:
        fail(f"v6+ occupant branch must request cached thumbnails without yielding render: {required}")

for token in [
    'recordBillboardText.Name = "RacerV7BillboardText"',
    "local function v7RecordGlobalStore()",
    'recordGlobalStore = DataStoreService:GetOrderedDataStore("RacerV7GlobalLapMsV1")',
    "local function v7RecordPersonalStore()",
    'recordPersonalStore = DataStoreService:GetDataStore("RacerV7PersonalRunsV1")',
    "local function isValidV7RecordLap(session, player: Player?, lapTime: number): boolean",
    "session.activePlayer == player",
    "RacerConfig.hasRecordBoards(session.definition.Mode)",
    "local recordUiEpoch = 0",
    "local function v7ActivePlayer(): Player?",
    "local function beginV7RecordUiRequest(): number",
    "local function isCurrentV7RecordUiRequest(epoch: number, player: Player?): boolean",
    "return epoch == recordUiEpoch and v7ActivePlayer() == player",
    "leaderboardUnavailable",
    "leaderboardLoading",
    "createV7Leaderboards()",
]:
    if token not in SERVER:
        fail(f"server record boards must belong to v7 only: {token}")

if SERVER.count("if not isCurrentV7RecordUiRequest(refreshEpoch, player) then") != 2:
    fail("both asynchronous v7 leaderboard readers must reject stale UI epochs and players")

require(
    r"local function refreshRecordLeaderboards\(player: Player\?\).*?"
    r"if v7ActivePlayer\(\) ~= player then\s*return\s*end\s*"
    r"local refreshEpoch = beginV7RecordUiRequest\(\)",
    SERVER,
    "v7 leaderboard refreshes must validate the active player before claiming a UI epoch",
)

require(
    r"if not player then\s*"
    r'setRecordLeaderboardText\("self", leaderboardEmpty\("v7 Your Top 10"\)\)\s*'
    r'setRecordLeaderboardText\("friends", leaderboardEmpty\(V7_FRIENDS_BOARD_TITLE\)\)\s*'
    r'setRecordLeaderboardText\("global", leaderboardLoading\("v7 Global Top 10"\)\)\s*'
    r"task\.spawn\(function\(\)",
    SERVER,
    "v7 must clear player-specific boards before an empty-cabinet global refresh can yield",
)

require(
    r"if RacerConfig\.isFinalLike\(mode\) and prediction\.position\.Value > playerZ then\s*"
    r"if prediction\.currentLapTime\.Value > 0 and startPosition < playerZ then\s*"
    r"prediction\.lastLapTime\.Value = prediction\.currentLapTime\.Value\s*"
    r"prediction\.currentLapTime\.Value = 0.*?else\s*"
    r"prediction\.currentLapTime\.Value \+= step\s*end\s*end",
    CLIENT,
    "v4+ client lap timing must complete at the original player line after track wrap",
)

require(
    r"if RacerConfig\.isFinalLike\(session\.definition\.Mode\) and session\.position > playerZ then\s*"
    r"if session\.currentLapTime > 0 and startPosition < playerZ then\s*"
    r"session\.lastLapTime = session\.currentLapTime\s*session\.currentLapTime = 0.*?"
    r"recordLapForRecordBoards\(session, session\.activePlayer, session\.lastLapTime\)\s*else\s*"
    r"session\.currentLapTime \+= dt\s*end\s*end",
    SERVER,
    "v4+ server lap timing must complete and persist at the original player line after track wrap",
)

for lap_source in [CLIENT, SERVER]:
    if "startPosition > trackLength - RacerConfig.SegmentLength * 2" in lap_source:
        fail("v4+ lap timing must not complete early at the raw track-coordinate wrap")
    if "lapStarted" in lap_source:
        fail("v4+ lap timing must use the original nonzero current-lap guard, not a sticky flag")

for token in [
    "local DEFAULT_FAST_LAP_TIME = 180",
    "local playerScreenProfiles = {}",
    "local function playerScreenProfile(player: Player, screenId: string)",
    "fastLapTime = DEFAULT_FAST_LAP_TIME",
    "local function hydrateSessionPlayerState(session, player: Player)",
    "local function rememberSessionFastLap(session)",
    "local function clearSessionPlayerState(session)",
    "playerScreenProfiles[player] = nil",
]:
    if token not in SERVER:
        fail(f"fastest laps must be isolated per player and screen: {token}")

if SERVER.count("hydrateSessionPlayerState(session, player)") != 1:
    fail("player session state must be hydrated exactly once when entering a Racer screen")
if SERVER.count("rememberSessionFastLap(session)") != 2:
    fail("a new fastest lap must be written through to exactly one player-screen profile")
if SERVER.count("clearSessionPlayerState(session)") != 3:
    fail("both Racer exit paths must clear player-owned state from the shared cabinet")

require(
    r"local function enterScreen\(player: Player, screenId: string\).*?"
    r"hydrateSessionPlayerState\(session, player\)\s*session\.activePlayer = player\s*"
    r"resetRun\(session\)",
    SERVER,
    "Racer entry must hydrate the new player's screen state before resetting the run",
)

for exit_pattern in [
    r"local function exitScreen\(player: Player, message: string\?\).*?",
    r"Players\.PlayerRemoving:Connect\(function\(player\).*?",
]:
    require(
        exit_pattern
        + r"session\.activePlayer = nil\s*clearSessionPlayerState\(session\)\s*resetRun\(session\)",
        SERVER,
        "Racer exit paths must clear player-owned state before publishing an idle cabinet",
    )

for token in [
    "local function defaultPlayerSettings()",
    "settings = defaultPlayerSettings()",
    "for settingName, value in profile.settings do",
    "local function rememberSessionSetting(",
    "playerScreenProfile(player, session.definition.Id).settings[settingName] = value",
    "for settingName, setting in SETTING_DEFAULTS do",
    "valueObject.Value = setting.default",
]:
    if token not in SERVER:
        fail(f"legacy renderer settings must be isolated per player and screen: {token}")

if SERVER.count("rememberSessionSetting(session, player, settingName, valueObject.Value)") != 2:
    fail("setting changes and resets must both write through to the active player-screen profile")

require(
    r"local function hydrateSessionPlayerState\(session, player: Player\)\s*"
    r"local profile = playerScreenProfile\(player, session\.definition\.Id\)\s*"
    r"session\.fastLapTime = profile\.fastLapTime\s*for settingName, value in profile\.settings do\s*"
    r"local valueObject = session\.values\[`Setting\{settingName\}`\].*?valueObject\.Value = value",
    SERVER,
    "Racer entry must hydrate only the active player's settings into the shared cabinet",
)

require(
    r"local function clearSessionPlayerState\(session\)\s*"
    r"session\.fastLapTime = DEFAULT_FAST_LAP_TIME\s*for settingName, setting in SETTING_DEFAULTS do\s*"
    r"local valueObject = session\.values\[`Setting\{settingName\}`\].*?"
    r"valueObject\.Value = setting\.default",
    SERVER,
    "idle Racer cabinets must not retain the prior player's renderer settings",
)

for token in [
    "local predictedSourceUserId = nil",
    "or predictedSourceUserId ~= source.activeUserId.Value",
    "predictedSourceUserId = source.activeUserId.Value",
]:
    if token not in CLIENT:
        fail(f"client prediction must be isolated across Racer driver handoffs: {token}")

if CLIENT.count("predictedSourceUserId = nil") != 2:
    fail("client prediction must forget its driver identity whenever the active screen is released")

require(
    r"local function ensurePredictedState\(source\)\s*if\s*not predictedState\s*"
    r"or predictedSourceId ~= source\.id\s*"
    r"or predictedSourceUserId ~= source\.activeUserId\.Value\s*then\s*"
    r"predictedState = copyPredictedState\(source\)\s*"
    r"predictedSourceId = source\.id\s*"
    r"predictedSourceUserId = source\.activeUserId\.Value",
    CLIENT,
    "a Racer screen's predicted state must be rebuilt whenever its active driver changes",
)

require(
    r"if not globalOk or not personalOk then.*?"
    r"if isCurrentV7RecordUiRequest\(saveEpoch, player\) then\s*"
    r"setRecordLeaderboardText\(.*?Save failed.*?end\s*end\s*"
    r"refreshRecordLeaderboards\(v7ActivePlayer\(\)\)",
    SERVER,
    "v7 save failure text must be gated while post-save refresh targets the current v7 player",
)

if "RacerV6GlobalLap" in SERVER or "RacerV6PersonalRuns" in SERVER:
    fail("server record board persistence must not use old RacerV6 DataStore names")

friends_board_title = 'V7_FRIENDS_BOARD_TITLE = "v7 Friends in Global Top 100"'
if friends_board_title not in SERVER:
    fail("v7 friends board must truthfully describe its bounded global top-100 source")
if SERVER.count("V7_FRIENDS_BOARD_TITLE") != 6 or "v7 Friends Top 10" in SERVER:
    fail("every v7 friends board state must use the shared truthful title")

for token in [
    "addStraight(track, ROAD.LENGTH.SHORT)",
    "addFinalLowRollingHills(track)",
    "addSCurves(track)",
    "addBumps(track)",
    "addDownhillToEnd(track)",
]:
    if token not in CONFIG:
        fail(f"v4 resetRoad token missing: {token}")

for token in [
	"buildSpriteObjects",
	"BILLBOARD07",
	"PALM_TREE",
	"COLUMN",
	"SpriteSets.Plants",
	"Count = 200",
	"offset = deterministicUnit(trafficSeed + index * 13) * 0.8 * side",
	"* (if spriteSize.height > 100 then 0.25 else 0.5)",
	"PlayerWidth = RacerConfig.PlayerSprite.Width * RacerConfig.SpriteScale",
	"CollisionOverlap = 0.8",
	"RoadsideCollisionSpeed = RacerConfig.MaxSpeed / 5",
	"roadsideCollisionSprite",
	"trafficCollisionPosition",
	"trafficCollisionCar",
	"playerSpriteDef",
	"playerBounce",
	"applyTrafficOffsets",
	"advanceTraffic",
	"createTrafficState",
	"local function deterministicFloorInt",
	"math.floor(minValue + (maxValue - minValue) * deterministicUnit(seed) + 0.5)",
	"math.floor(minValue + (maxValue - minValue + 1) * deterministicUnit(seed))",
	"deterministicFloorInt(trafficSeed + index * 7, 0, segmentCount - 1)",
	"0.5 + deterministicUnit(spriteSeed + n * 3) * 0.5",
	"1 + deterministicUnit(spriteSeed + n * 5) * 2",
	"n += 4 + math.floor(n / 100)",
	"while n < 1000 and n < segmentCount do",
	"n += 5",
	"side * (2 + deterministicUnit(spriteSeed + n * 29) * 5)",
	"n += 3",
	"while n < segmentCount - 50 do",
	"for i = 0, 19 do",
	"side * (1.5 + deterministicUnit(spriteSeed + n * 53 + i))",
	"n += 100",
	"for _, sprite in RacerConfig.spritesForSegment(mode, segmentIndex) do",
	"local spriteWidth = sprite.definition.width * RacerConfig.SpriteScale",
	"local track = RacerConfig.Tracks[mode]",
	"local bySegment = RacerConfig.SpritesBySegment[mode]",
	"function RacerConfig.roadsideSpriteCenter(sprite): number",
	"local spriteCenter = RacerConfig.roadsideSpriteCenter(sprite)",
	"RacerMath.overlap(playerX, playerWidth, spriteCenter, spriteWidth)",
	"function RacerConfig.roadsideCollisionPosition(",
	"function RacerConfig.trafficCollisionPosition(",
	"function RacerConfig.playerSpriteDef(steer: number, updown: number)",
	"local amplitude = 1.5 * deterministicUnit",
	"return amplitude * speedPercent * resolution * sign",
	"PLAYER_UPHILL_LEFT",
	"PLAYER_UPHILL_RIGHT",
	"PLAYER_UPHILL_STRAIGHT",
	"PLAYER_STRAIGHT",
	"segmentIndex * RacerConfig.SegmentLength",
	"return RacerMath.increase(trafficZ, -playerZ, trackLength)",
	"maxSpriteObjectsInDrawWindow",
	"width = car.width * RacerConfig.SpriteScale",
	"local carWidth = item.width",
	"and RacerMath.overlap(item.offset, carWidth, other.offset, other.width, 1.2)",
	"RacerConfig.FinalObjectCount = RacerConfig.Traffic.Count",
	"function RacerConfig.baseTrafficOffsets()",
	"packTrafficOffsets",
	"unpackTrafficOffsets",
	"trafficState.items",
	"trafficState.bySegment",
]:
    if token not in CONFIG:
        fail(f"v4 sprite/traffic parity token missing: {token}")

if "PLAYER_DOWNHILL" in CONFIG or "PLAYER_DOWNHILL" in TEXTURES:
    fail("player sprites must match original six-frame uphill/flat set; no separate downhill sprites")

if "DrawDistance = 300" not in CONFIG:
    fail("default drawDistance must match javascript-racer")

if "MaxDrawDistance = 500" not in CONFIG:
    fail("tweak UI maximum drawDistance must match javascript-racer")

if "DrawDistance = { min = 100, max = RacerConfig.MaxDrawDistance, step = 20, default = 300 }" not in SERVER:
    fail("server setting range must allow the original drawDistance maximum")

for token in [
    "RoadWidth = { min = 500, max = 3000, step = 100, default = 2000 }",
    "CameraHeight = { min = 500, max = 5000, step = 100, default = 1000 }",
    "FieldOfView = { min = 80, max = 140, step = 5, default = 100 }",
    "FogDensity = { min = 0, max = 50, step = 1, default = 5 }",
    "Lanes = { min = 1, max = 4, step = 1, default = 3 }",
]:
    if token not in SERVER:
        fail(f"tweak setting range must match javascript-racer controls: {token}")

adjust_setting_body = re.search(
    r"local function adjustSetting\(.*?\nend",
    SERVER,
    re.MULTILINE | re.DOTALL,
)
if not adjust_setting_body:
    fail("missing adjustSetting")
if "resetRun(" in adjust_setting_body.group(0):
    fail("tweak setting changes must not reset the race or rebuild runtime state")

reset_settings_body = re.search(
    r"local function resetSettings\(.*?\nend",
    SERVER,
    re.MULTILINE | re.DOTALL,
)
if not reset_settings_body:
    fail("missing resetSettings")
if "resetRun(" in reset_settings_body.group(0):
    fail("resetting tweak UI values must not reset the race")

if "Vector3.new(24, 18, 0.5)" not in SERVER:
    fail("world arcade screens must keep the original 1024x768 4:3 canvas aspect ratio")

replicated_state_fields = {
    "ActiveUserId": "activeUserId",
    "ActivePlayerName": "activePlayerName",
    "Position": "position",
    "Speed": "speed",
    "TrafficTime": "trafficTime",
    "TrafficOffsets": "trafficOffsetsBlob",
    "CurrentLapTime": "currentLapTime",
    "LastLapTime": "lastLapTime",
    "FastLapTime": "fastLapTime",
    "PlayerX": "playerX",
    "Steer": "steer",
    "SkyOffset": "skyOffset",
    "HillOffset": "hillOffset",
    "TreeOffset": "treeOffset",
    "Status": "status",
    "ScreenName": "screenName",
    "Mode": "mode",
    "SettingRoadWidth": "settingRoadWidth",
    "SettingCameraHeight": "settingCameraHeight",
    "SettingDrawDistance": "settingDrawDistance",
    "SettingFieldOfView": "settingFieldOfView",
    "SettingFogDensity": "settingFogDensity",
    "SettingLanes": "settingLanes",
}

for server_name, client_name in replicated_state_fields.items():
    if f'"{server_name}"' not in SERVER:
        fail(f"server must create replicated race state field {server_name}")
    if f'{client_name} = folder:WaitForChild("{server_name}")' not in CLIENT:
        fail(f"client must load replicated race state field {server_name} as {client_name}")

published_state_fields = [
    "ActiveUserId",
    "ActivePlayerName",
    "Position",
    "Speed",
    "TrafficTime",
    "TrafficOffsets",
    "CurrentLapTime",
    "LastLapTime",
    "FastLapTime",
    "PlayerX",
    "Steer",
    "SkyOffset",
    "HillOffset",
    "TreeOffset",
]

for field_name in published_state_fields:
    if f"session.values.{field_name}.Value" not in SERVER:
        fail(f"server publishState must update {field_name}")

render_signature_fields = [
    "mode",
    "activePlayerName",
    "trafficOffsetsBlob",
    "position",
    "playerX",
    "speed",
    "trafficTime",
    "steer",
    "skyOffset",
    "hillOffset",
    "treeOffset",
    "settingRoadWidth",
    "settingCameraHeight",
    "settingDrawDistance",
    "settingFieldOfView",
    "settingFogDensity",
    "settingLanes",
    "currentLapTime",
    "lastLapTime",
    "fastLapTime",
]
render_signature_body = re.search(
    r"local function renderSignature\(state\): string(.*?)\nend",
    CLIENT,
    re.MULTILINE | re.DOTALL,
)
if not render_signature_body:
    fail("missing renderSignature")
for client_name in render_signature_fields:
    if f"state.{client_name}" not in render_signature_body.group(1):
        fail(f"renderSignature must include {client_name}")

for token in [
    'fullViewport.Name = "RacerViewport"',
    "local function useMobileSidePanelLayout(): boolean",
    "return UserInputService.TouchEnabled",
    "local aspectRatio = RacerConfig.Width / RacerConfig.Height",
    "height = width / aspectRatio",
    "width = height * aspectRatio",
    "fullViewport.Size = UDim2.fromOffset(viewportWidth, viewportHeight)",
    'local fullRenderer = createRenderer(fullViewport, "LocalScreen")',
]:
    if token not in CLIENT:
        fail(f"fullscreen renderer must keep the original 4:3 canvas while mobile uses side panels: {token}")

expected_track_lengths = {
    "straight": 500,
    "curves": 4221,
    "hills": 3564,
    "final": 6705,
}

expected_track_sequences = {
    "curves": [
        "addStraight(track, ROAD.LENGTH.SHORT / 4)",
        "addFlatSCurves(track)",
        "addStraight(track, ROAD.LENGTH.LONG)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)",
        "addStraight(track)",
        "addFlatSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)",
        "addStraight(track)",
        "addFlatSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.EASY)",
    ],
    "hills": [
        "addStraight(track, ROAD.LENGTH.SHORT / 2)",
        "addHill(track, ROAD.LENGTH.SHORT, ROAD.HILL.LOW)",
        "addLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)",
        "addLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)",
        "addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addDownhillToEnd(track)",
    ],
    "final": [
        "addStraight(track, ROAD.LENGTH.SHORT)",
        "addFinalLowRollingHills(track)",
        "addSCurves(track)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)",
        "addBumps(track)",
        "addFinalLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.LONG * 2, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addHill(track, ROAD.LENGTH.MEDIUM, ROAD.HILL.HIGH)",
        "addSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.NONE)",
        "addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)",
        "addBumps(track)",
        "addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addSCurves(track)",
        "addDownhillToEnd(track)",
    ],
}

if 'SegmentCount = 500' not in CONFIG:
    fail("v1 straight track must contain 500 segments")

if "math.floor(RacerConfig.PlayerZ / RacerConfig.SegmentLength)" not in CONFIG:
    fail("start segments must be fixed from reset-time playerZ, not current camera settings")

ROAD_LENGTHS = {
    "ROAD.LENGTH.SHORT": 25,
    "ROAD.LENGTH.MEDIUM": 50,
    "ROAD.LENGTH.LONG": 100,
}


def eval_length(expr: str | None, default: int) -> float:
    if not expr:
        return default
    expr = expr.strip()
    for token, value in ROAD_LENGTHS.items():
        expr = expr.replace(token, str(value))
    if not re.fullmatch(r"[0-9\s+\-*/.]+", expr):
        fail(f"unsupported road length expression: {expr}")
    return float(eval(expr, {"__builtins__": {}}, {}))


def road_segments(length: float) -> int:
    return math.ceil(length) * 3


def first_arg(line: str) -> str | None:
    match = re.search(r"\(\s*track\s*(?:,\s*([^,\)]+))?", line)
    return match.group(1) if match else None


def computed_track_length(mode: str) -> int:
    match = re.search(
        rf"local function build{mode.capitalize()}Track\(\)(.*?)return track",
        CONFIG,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        fail(f"missing {mode} track builder")
    total = 0
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith("addStraight"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addHill"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addCurve"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addLowRollingHills") or line.startswith("addFinalLowRollingHills"):
            total += road_segments(eval_length(first_arg(line), 25)) * 6
        elif line.startswith("addFlatSCurves") or line.startswith("addSCurves"):
            total += road_segments(50) * 5
        elif line.startswith("addBumps"):
            total += road_segments(10) * 8
        elif line.startswith("addDownhillToEnd"):
            total += road_segments(eval_length(first_arg(line), 200))
    return total


def track_call_sequence(mode: str) -> list[str]:
    match = re.search(
        rf"local function build{mode.capitalize()}Track\(\)(.*?)return track",
        CONFIG,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        fail(f"missing {mode} track builder")
    calls = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith("add"):
            calls.append(line)
    return calls


for mode, expected_count in expected_track_lengths.items():
    actual_count = 500 if mode == "straight" else computed_track_length(mode)
    if actual_count != expected_count:
        fail(f"{mode} track length must match javascript-racer: {actual_count} != {expected_count}")

for mode, expected_calls in expected_track_sequences.items():
    actual_calls = track_call_sequence(mode)
    if actual_calls != expected_calls:
        fail(
            f"{mode} track call sequence must match javascript-racer:\n"
            f"actual={actual_calls}\nexpected={expected_calls}"
        )

for token in [
    "RacerMath.easeIn(0, curve, n / enter)",
    "RacerMath.easeInOut(startY, endY, n / total)",
    "RacerMath.easeInOut(startY, endY, (enter + n) / total)",
    "RacerMath.easeInOut(curve, 0, n / leave)",
    "RacerMath.easeInOut(startY, endY, (enter + hold + n) / total)",
]:
    if token not in CONFIG:
        fail(f"road builder interpolation must match javascript-racer: {token}")


def ease_in(a: float, b: float, percent: float) -> float:
    return a + (b - a) * (percent**2)


def ease_in_out(a: float, b: float, percent: float) -> float:
    return a + (b - a) * ((-math.cos(percent * math.pi) / 2) + 0.5)


ROAD_HILLS = {
    "ROAD.HILL.NONE": 0,
    "ROAD.HILL.LOW": 20,
    "ROAD.HILL.MEDIUM": 40,
    "ROAD.HILL.HIGH": 60,
}

ROAD_CURVES = {
    "ROAD.CURVE.NONE": 0,
    "ROAD.CURVE.EASY": 2,
    "ROAD.CURVE.MEDIUM": 4,
    "ROAD.CURVE.HARD": 6,
}


def eval_track_expr(expr: str | None, default: float, values: dict[str, float]) -> float:
    if not expr:
        return default
    expr = expr.strip()
    for source in (ROAD_LENGTHS, ROAD_HILLS, ROAD_CURVES):
        for token, value in source.items():
            expr = expr.replace(token, str(value))
    if not re.fullmatch(r"[0-9\s+\-*/.]+", expr):
        fail(f"unsupported track expression: {expr}")
    return float(eval(expr, {"__builtins__": {}}, values))


def split_call_args(line: str) -> list[str]:
    match = re.search(r"\((.*)\)", line)
    if not match:
        return []
    raw_args = [part.strip() for part in match.group(1).split(",")]
    return raw_args[1:] if raw_args and raw_args[0] == "track" else raw_args


def add_segment_to(track: list[dict[str, float]], curve_value: float, y_value: float | None = None):
    start_y = 0 if not track else track[-1]["y2"]
    end_y = start_y if y_value is None else y_value
    track.append({"curve": curve_value, "y1": start_y, "y2": end_y})


def add_road_to(track: list[dict[str, float]], enter: float, hold: float, leave: float, curve_value: float, y_value: float = 0):
    start_y = 0 if not track else track[-1]["y2"]
    end_y = start_y + y_value * 200
    total = enter + hold + leave
    n = 0
    while n < enter:
        add_segment_to(track, ease_in(0, curve_value, n / enter), ease_in_out(start_y, end_y, n / total))
        n += 1
    n = 0
    while n < hold:
        add_segment_to(track, curve_value, ease_in_out(start_y, end_y, (enter + n) / total))
        n += 1
    n = 0
    while n < leave:
        add_segment_to(track, ease_in_out(curve_value, 0, n / leave), ease_in_out(start_y, end_y, (enter + hold + n) / total))
        n += 1


def add_flat_s_curves_to(track: list[dict[str, float]]):
    for curve_value in [-2, 4, 2, -2, -4]:
        add_road_to(track, 50, 50, 50, curve_value, 0)


def add_s_curves_to(track: list[dict[str, float]]):
    for curve_value, y_value in [(-2, 0), (4, 40), (2, -20), (-2, 40), (-4, -40)]:
        add_road_to(track, 50, 50, 50, curve_value, y_value)


def add_low_rolling_hills_to(track: list[dict[str, float]], final: bool):
    for curve_value, y_value in [
        (0, 10),
        (0, -20),
        (2 if final else 0, 20),
        (0, 0),
        (-2 if final else 0, 10),
        (0, 0),
    ]:
        add_road_to(track, 25, 25, 25, curve_value, y_value)


def add_bumps_to(track: list[dict[str, float]]):
    for y_value in [5, -2, -5, 8, 5, -7, 5, -2]:
        add_road_to(track, 10, 10, 10, 0, y_value)


def simulated_track_from_calls(calls: list[str]) -> list[dict[str, float]]:
    track: list[dict[str, float]] = []
    for call in calls:
        args = split_call_args(call)
        if call.startswith("addStraight"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            add_road_to(track, length, length, length, 0, 0)
        elif call.startswith("addHill"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            height = eval_track_expr(args[1] if len(args) > 1 else None, 40, {})
            add_road_to(track, length, length, length, 0, height)
        elif call.startswith("addCurve"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            curve_value = eval_track_expr(args[1] if len(args) > 1 else None, 4, {})
            height = eval_track_expr(args[2] if len(args) > 2 else None, 0, {})
            add_road_to(track, length, length, length, curve_value, height)
        elif call.startswith("addLowRollingHills"):
            add_low_rolling_hills_to(track, False)
        elif call.startswith("addFinalLowRollingHills"):
            add_low_rolling_hills_to(track, True)
        elif call.startswith("addFlatSCurves"):
            add_flat_s_curves_to(track)
        elif call.startswith("addSCurves"):
            add_s_curves_to(track)
        elif call.startswith("addBumps"):
            add_bumps_to(track)
        elif call.startswith("addDownhillToEnd"):
            length = eval_track_expr(args[0] if args else None, 200, {})
            add_road_to(track, length, length, length, -2, -(track[-1]["y2"] if track else 0) / 200)
    return track


expected_track_samples = {
    "curves": {
        150: (-0.751310, 0.0, 0.0),
        500: (-0.672800, 0.0, 0.0),
        2110: (0.229487, 0.0, 0.0),
        4220: (-0.000493, 0.0, 0.0),
    },
    "hills": {
        150: (0.0, 4893.717, 4935.455),
        500: (0.0, 7996.491, 7996.491),
        1782: (-4.0, 28702.418, 28743.604),
        3563: (-0.000123, 0.877, 0.219),
    },
    "final": {
        150: (0.0, 1999.123, 1999.123),
        1000: (-0.5, 8492.580, 8533.705),
        3352: (1.095200, 44847.469, 44818.477),
        6704: (-0.000123, 1.283, 0.321),
    },
}

for mode, samples in expected_track_samples.items():
    simulated_track = simulated_track_from_calls(track_call_sequence(mode))
    if len(simulated_track) != expected_track_lengths[mode]:
        fail(f"{mode} simulated track length changed: {len(simulated_track)}")
    for index, (expected_curve, expected_y1, expected_y2) in samples.items():
        segment = simulated_track[index]
        if (
            abs(segment["curve"] - expected_curve) > 1e-5
            or abs(segment["y1"] - expected_y1) > 1e-3
            or abs(segment["y2"] - expected_y2) > 1e-3
        ):
            fail(
                f"{mode} segment {index} must match javascript-racer control point: "
                f"{segment} != {(expected_curve, expected_y1, expected_y2)}"
            )

for token in [
    "x = math.floor(width / 2 + scale * (worldX - cameraX) * width / 2 + 0.5)",
    "y = math.floor(height / 2 - scale * (worldY - cameraY) * height / 2 + 0.5)",
    "w = math.floor(scale * roadWidth * width / 2 + 0.5)",
]:
    if token not in MATH:
        fail(f"Util.project rounding must match javascript-racer: {token}")

for token in [
    "local halfRoadWidth = roadHalfWidthPx / WIDTH",
    "halfRoadWidth / math.max(6, 2 * lanes)",
    "halfRoadWidth / math.max(32, 8 * lanes)",
    "math.clamp(lanes - 1, 0, #row.laneMarkers)",
]:
    if token not in CLIENT:
        fail(f"Render.segment width formula must match javascript-racer: {token}")

for token in [
    "Road = Color3.fromRGB(255, 255, 255)",
    "Grass = Color3.fromRGB(255, 255, 255)",
    "Rumble = Color3.fromRGB(255, 255, 255)",
    "Road = Color3.fromRGB(0, 0, 0)",
    "Grass = Color3.fromRGB(0, 0, 0)",
    "Rumble = Color3.fromRGB(0, 0, 0)",
]:
    if token not in CONFIG:
        fail(f"START/FINISH colors must match javascript-racer white/black: {token}")

for token in [
    "FastLapTime = createValue(folder, \"NumberValue\", \"FastLapTime\", DEFAULT_FAST_LAP_TIME)",
    "fastLapTime = DEFAULT_FAST_LAP_TIME",
    "session.trafficOffsets = RacerConfig.baseTrafficOffsets()",
    "local playerSegmentIndex = math.floor(RacerConfig.PlayerZ / RacerConfig.SegmentLength)",
    "if index == playerSegmentIndex + 2 or index == playerSegmentIndex + 3 then",
    "if index >= RacerConfig.segmentCount(mode) - RacerConfig.RumbleLength then",
]:
    if token not in CONFIG + SERVER:
        fail(f"lap/start-finish reset parity token missing: {token}")

for forbidden in [
	"CollisionDistance",
	"CollisionWidth",
	"\n\tCollisionSpeed",
	"item.width * 0.24",
	"adjustedTrafficOffset",
	"minSpriteSize",
	"math.abs(currentOffset - item.offset)",
	"MAX_PREDICTION_DELTA",
	"RoadsideCollisionLookahead",
	"RoadsideCollisionSegmentRadius",
	"MinSpacing",
	"-1.15",
	"RacerMath.limit(\n\t\t\titem.offset",
	"renderer.car.Rotation = steer",
	"advanceTrafficOffsets",
	"avoidTargetId",
	"avoidDirection",
	"RoadsideCollisionSegmentOffsets",
	"table.sort(objects",
	"table.sort(trafficList",
	"return a.distance > b.distance",
	"minTrafficDistance",
	"distance > minTrafficDistance",
	"math.clamp(playerY",
	"maxY = if RacerConfig.Modes[mode].hills then p1.y else p2.y",
	"prediction.accumulator = math.min(prediction.accumulator, RacerConfig.Step)",
	"accumulator = math.min(accumulator, step)",
	"syncRendererTrafficOffsets",
	"trafficSyncTime",
	"trafficSyncPosition",
	"trafficSyncPlayerX",
	"trafficSyncSpeed",
	"while simTime + RacerConfig.Step <= targetTrafficTime do",
	"((x1 + x2) * 0.5) / WIDTH",
	"((w1 + w2) * 0.5 * 2) / WIDTH",
	"math.max(0.02, (roadHalfWidthPx * 2) / WIDTH)",
	"fog * 0.55",
	"object.BackgroundColor3 = colorWithFog(carData.color",
	"10 + index",
	'createFrame(rowRoot, "Road", RacerConfig.Colors.Light.Road, 2)',
	'createFrame(rowRoot, "LeftRumble", RacerConfig.Colors.Light.Rumble, 3)',
	'createFrame(rowRoot, `LaneMarker_{laneIndex}`, RacerConfig.Colors.Light.Lane, 4)',
]:
	if forbidden in CONFIG + CLIENT + SERVER:
		fail(f"non-original collision tuning must not remain: {forbidden}")

for token in [
    "CurrentLapTime",
    "LastLapTime",
    "FastLapTime",
    "trafficCollisionCar",
    "roadsideCollisionSprite",
    "RoadsideCollisionSpeed",
    "settingDrawDistance.Value",
    "lastLapTime.Value <= prediction.fastLapTime.Value",
    "session.lastLapTime <= session.fastLapTime",
	"prediction.accumulator >= RacerConfig.Step",
	"local step = RacerConfig.Step",
	"MAX_PREDICTION_ACCUMULATED_TIME = 1",
	"MAX_ACCUMULATED_TIME = 1",
	"RacerConfig.advanceTraffic(",
	"trafficItems, trafficBySegment = RacerConfig.advanceTraffic(",
	"prediction.trafficState",
	"session.trafficState",
	"replicatedTrafficOffsets(state)",
	"TrafficOffsets",
    "replicatedTrafficOffsets",
    "prediction.playerX.Value < -1 or prediction.playerX.Value > 1",
    "session.playerX < -1 or session.playerX > 1",
    "local roadsideSprite",
    "RacerConfig.roadsideCollisionSprite(mode, segmentIndex, prediction.playerX.Value)",
    "RacerConfig.trafficCollisionPosition(collisionItem.z, playerZ, trackLength)",
    "RacerConfig.roadsideCollisionSprite(\n\t\t\tsession.definition.Mode,\n\t\t\tsegmentIndex,\n\t\t\tsession.playerX\n\t\t)",
	"local playerXLimit = if RacerConfig.isFinalLike(mode) then 3 else 2",
	"local playerXLimit = if RacerConfig.isFinalLike(session.definition.Mode) then 3 else 2",
	"if RacerConfig.isFinalLike(mode) then\n\t\t\tprediction.trafficTime.Value += step\n\t\tend",
	"if RacerConfig.isFinalLike(session.definition.Mode) then\n\t\tsession.trafficTime += dt\n\tend",
]:
    if token not in SERVER + CLIENT:
        fail(f"runtime parity token missing: {token}")

for token in [
    "function RacerConfig.trafficSnapshot(",
    "function RacerConfig.applyTrafficOffsets(",
]:
    if token not in CONFIG:
        fail(f"shared traffic parity helper missing: {token}")

if "RacerConfig.Traffic.Lookahead - 1" not in CONFIG:
    fail("traffic lookahead loop must match javascript-racer i < lookahead")

if 'string.format("%.4f", offset)' in CONFIG:
    fail("replicated traffic offsets should not be rounded to 4 decimals")

if 'string.format("%.6f", offset)' not in CONFIG:
    fail("replicated traffic offsets should keep enough precision for spectator rendering")

for token in [
    "local function worldScreenNeedsRealtime(state): boolean",
    "return state.activeUserId.Value ~= 0",
    "renderIdleWorldScreens or worldScreenNeedsRealtime(screenState)",
]:
    if token not in CLIENT:
        fail(f"active spectator world screens must render without idle throttling: {token}")

require(
    r"if\s+orderedTrafficBySegment\s*==\s*nil\s*then\s*for\s+_,\s*item\s+in\s+trafficItems\s+or\s+\{\}\s+do",
    CLIENT,
    "traffic render fallback must not duplicate already grouped traffic",
)

require(
    r"function\s+RacerConfig\.playerBounce\(\s*position:\s*number,\s*speedPercent:\s*number,\s*resolution:\s*number\s*\):\s*number",
    CONFIG,
    "player bounce helper must keep the Render.player-style inputs",
)

require(
    r'if\s+not\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*speedPercent',
    CLIENT,
    "client v2/v3 background update must happen before controls using speedPercent",
)
require(
    r'if\s+not\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*speedPercent',
    SERVER,
    "server v2/v3 background update must happen before controls using speedPercent",
)
require(
    r"prediction\.position\.Value\s*=\s*RacerMath\.increase\(.*?if\s+not\s+RacerConfig\.isFinalLike\(mode\).*?if\s+pressedInputs\.left\s+then",
    CLIENT,
    "client update order must match v1-v3: position, background, then player input",
)
require(
    r"session\.position\s*=\s*RacerMath\.increase\(.*?if\s+not\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\).*?if\s+session\.input\.left\s+then",
    SERVER,
    "server update order must match v1-v3: position, background, then player input",
)
require(
    r"RacerConfig\.trafficCollisionCar\([^\n]*.*?local\s+playerXLimit\s*=\s*if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*3\s*else\s*2",
    CLIENT,
    "client collision order must match original: traffic collision before player/speed clamp",
)
require(
    r"RacerConfig\.trafficCollisionCar\([^\n]*.*?local\s+playerXLimit\s*=\s*if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*3\s*else\s*2",
    SERVER,
    "server collision order must match original: traffic collision before player/speed clamp",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic',
    CLIENT,
    "client traffic movement must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic',
    SERVER,
    "server traffic movement must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic.*?prediction\.trafficTime\.Value\s*\+=\s*step.*?prediction\.position\.Value\s*=\s*RacerMath\.increase',
    CLIENT,
    "client v4 update order must match original: updateCars, traffic time, then position",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic.*?session\.trafficTime\s*\+=\s*dt.*?session\.position\s*=\s*RacerMath\.increase',
    SERVER,
    "server v4 update order must match original: updateCars, traffic time, then position",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s+and\s+\(prediction\.playerX\.Value\s*<\s*-1\s+or\s+prediction\.playerX\.Value\s*>\s*1\)\s*then\s*local\s+roadsideSprite\s*=\s*RacerConfig\.roadsideCollisionSprite\(\s*mode,\s*segmentIndex,\s*prediction\.playerX\.Value\s*\)',
    CLIENT,
    "client roadside collisions must use the original pre-move player segment in v4 final",
)
require(
    r"RacerConfig\.roadsideCollisionPosition\(\s*segmentIndex,\s*playerZ,\s*trackLength\s*\)",
    CLIENT,
    "client roadside collision reset position must stop at the front of the original player segment",
)
require(
    r"function\s+RacerConfig\.trafficSnapshot\(.*?width\s*=\s*car\.width\s*\*\s*RacerConfig\.SpriteScale",
    CONFIG,
    "traffic hitboxes must use original sprite.w * SPRITES.SCALE units, not raw placeholder pixels",
)
require(
    r"function\s+RacerConfig\.trafficCollisionCar\(.*?RacerMath\.overlap\(\s*playerX,\s*RacerConfig\.Traffic\.PlayerWidth,\s*item\.offset,\s*item\.width,\s*RacerConfig\.Traffic\.CollisionOverlap",
    CONFIG,
    "traffic collision must compare playerX against scaled car offset/width like javascript-racer",
)
require(
    r"local\s+spriteX\s*=\s*projected\.p1\.x\s*\+\s*scale\s*\*\s*RacerConfig\.roadsideSpriteCenter\(spriteData\).*?local\s+spriteCenter\s*=\s*RacerConfig\.roadsideSpriteCenter\(sprite\)",
    CLIENT + CONFIG,
    "roadside rendering and collision must share the same sprite center formula",
)
require(
    r'local\s+collisionOverlap\s*=\s*RacerConfig\.Traffic\.CollisionOverlap.*?local\s+playerDebugWidthScale\s*=\s*RacerConfig\.Traffic\.PlayerWidth\s*\*\s*scale\s*\*\s*roadWidthSetting\s*/\s*2.*?local\s+collisionboxWidth\s*=\s*math\.max\(\s*0,\s*width\s*\*\s*collisionOverlap\s*-\s*playerDebugWidthScale\s*\*\s*\(1\s*-\s*collisionOverlap\)\s*\).*?placeClippedObject\(\s*object,\s*x,\s*y,\s*width,\s*height,\s*projected\.clip,\s*collisionboxWidth',
    CLIENT,
    "debug traffic hitbox outlines must compensate for the full-width player collision outline",
)
require(
    r"for\s+index\s*=\s*#objectSegments,\s*1,\s*-1\s+do.*?for\s+_,\s*spriteData\s+in\s+RacerConfig\.spritesForSegment\(mode,\s*projected\.index\)\s+do.*?local\s+playerDebugWidth\s*=\s*playerWidth.*?if\s+spriteData\.offset\s*>\s*0\s*then\s*collisionMinWorld\s*=\s*math\.max\(collisionMinWorld,\s*1\).*?else\s*collisionMaxWorld\s*=\s*math\.min\(collisionMaxWorld,\s*-1\).*?local\s+collisionboxMinWorld\s*=\s*collisionMinWorld\s*\+\s*playerDebugWidth\s*/\s*2.*?local\s+collisionboxMaxWorld\s*=\s*collisionMaxWorld\s*-\s*playerDebugWidth\s*/\s*2.*?placeScreenDebugBox\(\s*renderer\.roadsideCollisionboxes\[nextCursor\],\s*collisionboxX,\s*collisionBottomY,\s*collisionboxWidth,\s*collisionboxHeight",
    CLIENT,
    "debug roadside collisionboxes must be previewed for all visible obstacle segments and overlap the player collisionbox exactly when collision can trigger",
)
require(
    r"playerCollisionbox\.Position\s*=\s*UDim2\.fromScale\(0,\s*0\).*?playerCollisionbox\.Size\s*=\s*UDim2\.fromScale\(1,\s*1\)",
    CLIENT,
    "debug player collision outline must match the full player spritebox",
)
require(
    r"function\s+RacerConfig\.trafficOffsetDelta\(.*?local\s+carWidth\s*=\s*item\.width.*?RacerMath\.overlap\(\s*playerX,\s*RacerConfig\.Traffic\.PlayerWidth,\s*item\.offset,\s*carWidth,\s*1\.2",
    CONFIG,
    "traffic avoidance must use the same scaled car width as traffic collision",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s+and\s+\(session\.playerX\s*<\s*-1\s+or\s+session\.playerX\s*>\s*1\)\s*then\s*local\s+roadsideSprite\s*=\s*RacerConfig\.roadsideCollisionSprite\(\s*session\.definition\.Mode,\s*segmentIndex,\s*session\.playerX\s*\)',
    SERVER,
    "server roadside collisions must use the original pre-move player segment in v4 final",
)
require(
    r"RacerConfig\.roadsideCollisionPosition\(\s*segmentIndex,\s*playerZ,\s*trackLength\s*\)",
    SERVER,
    "server roadside collision reset position must stop at the front of the original player segment",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?RacerConfig\.trafficCollisionCar',
    CLIENT,
    "client traffic collision must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?RacerConfig\.trafficCollisionCar',
    SERVER,
    "server traffic collision must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?RacerConfig\.createTrafficState\(\s*trafficTime,\s*trackLength,\s*segmentCount,\s*replicatedTrafficOffsets\(state\),\s*mode\s*\).*?RacerConfig\.spritesForSegment',
    CLIENT,
    "world/object rendering must rebuild v4 final traffic directly from the replicated server snapshot",
)
require(
    r"for\s+index\s*=\s*#objectSegments,\s*1,\s*-1\s*do.*?local\s+trafficList\s*=.*?setTrafficObject.*?local\s+spriteList\s*=.*?setSpriteObject.*?if\s+projected\.index\s*==\s*playerSegmentIndex\s*then\s*playerDrawZIndex\s*=\s*objectZIndex\(drawLayer\)",
    CLIENT,
    "v4 object layering must match original: far-to-near, traffic, roadside sprites, then player at its segment",
)
for token in [
    "status.Visible = false",
    "local function finalHudText(state, speed: number): string",
    "{mph} mph Time:",
    "Last Lap:",
    "Fastest Lap:",
    "if RacerConfig.isFinalLike(mode) and renderer.statusEnabled ~= false then",
    "renderer.status.Text = finalHudText(state, speed)",
    "renderer.status.Text = \"\"",
    "renderer.status.Visible = false",
]:
    if token not in CLIENT:
        fail(f"v4 final must render the original mph/time/last/fastest HUD, and v1-v3 must not render a HUD/status overlay: {token}")
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?local\s+positionDelta.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*positionDelta',
    CLIENT,
    "client v4 background update must use position delta after collisions",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?local\s+positionDelta.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*positionDelta',
    SERVER,
    "server v4 background update must use position delta after collisions",
)
for token in [
    "local skyY = playerY * BACKGROUND_SPEEDS.Sky / 480",
    "local hillY = playerY * BACKGROUND_SPEEDS.Hill / 480",
    "local treeY = playerY * BACKGROUND_SPEEDS.Tree / 480",
]:
    if token not in CLIENT:
        fail(f"background vertical offset must match Render.background scaling: {token}")

if "state.trafficOffsets" not in CLIENT:
    fail("fullscreen render must use predicted traffic offsets for collision/render parity")

if "activeUserId = source.activeUserId" not in CLIENT:
    fail("active player prediction must keep activeUserId for avatar/HUD rendering")

require(
    r"if\s+state\.trafficOffsets\s+then\s*local\s+trafficState\s*=\s*RacerConfig\.createTrafficState\(\s*trafficTime,\s*trackLength,\s*segmentCount,\s*state\.trafficOffsets,\s*mode\s*\)\s*trafficItems\s*=\s*trafficState\.items\s*orderedTrafficBySegment\s*=\s*trafficState\.bySegment",
    CLIENT,
    "traffic offset fallback must rebuild segment.cars-style grouping before rendering",
)

for token in [
	"trafficBySegment = nil",
	"trafficBySegment = if trafficState then trafficState.bySegment else nil",
	"prediction.trafficBySegment = trafficBySegment",
	"local orderedTrafficBySegment = state.trafficBySegment",
	"if state.trafficState and state.trafficState.bySegment then",
]:
    if token not in CLIENT:
        fail(f"active renderer must preserve updateCars segment order: {token}")

if "render(fullRenderer, renderState)" not in CLIENT:
    fail("active player renderer must render every frame like javascript-racer")

require(
    r"predictedState\.fastLapTime\.Value\s*=\s*math\.min\(\s*"
    r"predictedState\.fastLapTime\.Value,\s*source\.fastLapTime\.Value\s*\)",
    CLIENT,
    "active player best lap prediction must not be overwritten by a slower server snapshot",
)

if "source.lastLapTime.Value > 0" not in CLIENT or "source.currentLapTime.Value == 0" not in CLIENT:
    fail("active player last lap prediction must survive stale zero server snapshots")

if "if state.trafficOffsetsBlob then state.trafficOffsetsBlob.Value else \"\"" not in CLIENT:
    fail("world screen render signatures must include replicated traffic offsets")

if "math.floor(state.lastLapTime.Value * 10 + 0.5)" not in CLIENT:
    fail("render signature must include last lap HUD state")

if "renderIfChanged(fullRenderer" in CLIENT:
    fail("active player renderer must not be signature-throttled")

for forbidden in [
    "predictedState.position.Value = source.position.Value",
    "predictedState.speed.Value = source.speed.Value",
    "predictedState.playerX.Value = source.playerX.Value",
    "predictedState.trafficTime.Value = source.trafficTime.Value",
]:
    if forbidden in CLIENT:
        fail(f"active player prediction must not be overwritten by server snapshots: {forbidden}")

for token in [
    "setPlayerCarZIndex",
    "projected.index == playerSegmentIndex",
	"if n > 0 then\n\t\t\t\ttable.insert(objectSegments, projected)\n\t\t\tend",
	"local playerBottomY = HEIGHT",
	"RacerConfig.Modes[mode].hills and playerProjected",
	"local frontFacing = not RacerConfig.Modes[mode].hills or p2.y < p1.y",
	"if p1 and p2 then",
	"p1.cameraZ > cameraDepth and frontFacing and p2.y < maxY",
	"maxY = if RacerConfig.isFinalLike(mode) then p1.y else p2.y",
	"playerProjected.p1.cameraY",
	"ROAD_SCANLINE_HEIGHT = 2",
	"local heightScale = math.max(1 / HEIGHT, bottom - top)",
	"local roadWidth = math.max(0, (roadHalfWidthPx * 2) / WIDTH)",
	"local percent = RacerMath.limit((sampleY - p2.y) / segmentHeight, 0, 1)",
	"RacerMath.interpolate(p2.x, p1.x, percent)",
	"RacerMath.interpolate(p2.w, p1.w, percent)",
	"local ROAD_Z_INDEX = 20",
	"local ROAD_DETAIL_Z_INDEX = ROAD_Z_INDEX + 1",
	"local ROAD_LANE_Z_INDEX = ROAD_Z_INDEX + 2",
	"createFrame(root, `RoadRow_{index}`, RacerConfig.Colors.Light.Grass, ROAD_Z_INDEX)",
	'createFrame(rowRoot, "Road", RacerConfig.Colors.Light.Road, ROAD_DETAIL_Z_INDEX)',
	"ROAD_LANE_Z_INDEX",
	"local playerSprite = RacerConfig.playerSpriteDef(steer, playerSegment.y2 - playerSegment.y1)",
	"playerSprite.width",
	"playerSprite.height",
	"local playerBounce =",
	"RacerConfig.playerBounce(position, speed / RacerConfig.MaxSpeed, HEIGHT / 480)",
	"(playerBottomY + playerBounce) / HEIGHT",
    "renderer.car.Rotation = 0",
    "child.ZIndex = object.ZIndex",
    "child.ZIndex = zIndex",
    "OBJECT_Z_STRIDE = 4",
    "objectZIndex(drawLayer)",
    "screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling",
    "surfaceGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling",
    "local ROW_COUNT = RacerConfig.MaxDrawDistance",
]:
    if token not in CLIENT:
        fail(f"render ordering parity token missing: {token}")

if "ZIndexBehavior = Enum.ZIndexBehavior.Global" in CLIENT:
    fail("nested racer canvas renderer must use sibling ZIndex ordering so road rows stay above the root background")

for token in [
    "local widthPx = widthScale * WIDTH",
    "local heightPx = heightScale * HEIGHT",
    "local leftX = x - widthPx / 2",
    "local topY = bottomY - heightPx",
    "local visibleBottomY = math.min(bottomY, clipY, SCREEN_MAX_Y)",
    "detailRoot.Position = UDim2.fromScale(",
    "(leftX - visibleLeftX) / visibleWidth",
    "(topY - visibleTopY) / visibleHeight",
    "detailRoot.Size = UDim2.fromScale(widthPx / visibleWidth, heightPx / visibleHeight)",
]:
    if token not in CLIENT:
        fail(f"Render.sprite clipping must crop without changing apparent sprite proportions: {token}")

for token in [
    '"SpriteCanopy"',
    '"SpriteTrunk"',
    '"SpriteBody"',
    '"SpriteContact"',
    '"TrafficBody"',
    'if kind == "billboard" then',
    "detailRoot.BackgroundTransparency = 1",
    'and child.Name ~= "LiveBillboardText"',
    "and not isDebugBox(child.Name)",
    "child.Visible = not hasTexture and not isSpriteOnly",
    "local collisionOverlap = RacerConfig.Traffic.CollisionOverlap",
    "local collisionLeft = (1 - collisionOverlap) / 2",
    "UDim2.fromScale(collisionLeft, 0)",
    "UDim2.fromScale(collisionOverlap, 1)",
    "UDim2.fromScale(0.23, 0.86)",
    "UDim2.fromScale(0, 0.9)",
    "UDim2.fromScale(1, 0.1)",
    'elseif kind == "rock" then',
    'elseif kind == "column" then',
]:
    if token not in CLIENT:
        fail(f"placeholder roadside sprites must not render as full opaque sprite rectangles: {token}")

if CLIENT.count('elseif spriteData.sprite == "PALM_TREE" then') != 1:
    fail("placeholder roadside sprites must have exactly one PALM_TREE branch")

for token in [
    "local useSpriteboxDebug = false",
    "local useCollisionboxDebug = false",
    "local function createDebugBox",
    'createDebugBox(parent, "Spritebox"',
    'createDebugBox(parent, "Collisionbox"',
    'box.Name = name',
    "box.BackgroundTransparency = 1",
    'createBoxLine("Top"',
    '"Bottom"',
    'createBoxLine("Left"',
    '"Right"',
    "stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border",
    "createSpritebox(car, PLAYER_CAR_Z_INDEX + 5)",
    "createCollisionbox(car, PLAYER_CAR_Z_INDEX + 7)",
    'child.Name ~= "Texture" and not isDebugBox(child.Name)',
    "playerSpritebox.Visible = RacerConfig.isFinalLike(mode) and useSpriteboxDebug",
    "playerCollisionbox.Visible = RacerConfig.isFinalLike(mode) and useCollisionboxDebug",
    "local boxVisibleLeftX = math.max(boxLeftX, visibleLeftX)",
    "local boxVisibleRightX = math.min(boxRightX, visibleRightX)",
    "local centerX = boxCenterX or x",
    "boxVisibleWidth / visibleWidth",
    "boxVisibleHeight / visibleHeight",
    "local debugLineZIndex = zIndex + 1",
    'Spriteboxes`',
    'Collisionboxes`',
    "not state or not RacerConfig.isFinalLike(state.mode.Value)",
]:
    if token not in CLIENT:
        fail(f"optional v4 hitbox debug outlines missing token: {token}")

for forbidden in [
    "if child.Name == \"Shadow\" then object.ZIndex - 1 else object.ZIndex + 1",
    "child.ZIndex = zIndex + 1",
]:
    if forbidden in CLIENT:
        fail(f"placeholder sprite parts must render as one atomic sprite layer: {forbidden}")

if "local FINAL_OBJECT_COUNT = RacerConfig.FinalObjectCount" not in CLIENT:
    fail("object pool must be derived from v4 traffic + max visible sprite placeholders")

for token in [
    "local ACTIVE_STATUS_MARGIN_TOP = 14",
    "local MOBILE_HUD_MARGIN = 10",
    "local MOBILE_TOPBAR_CLEARANCE = 96",
    "local lastLap = if state.lastLapTime.Value > 0",
    "viewportTop = math.floor((absoluteSize.Y - height) / 2 + 0.5)",
    "viewportTop + ACTIVE_STATUS_MARGIN_TOP",
    "screenGui.IgnoreGuiInset = active",
    "viewportTop + MOBILE_TOPBAR_CLEARANCE",
    "local compactSettingsPanel = state ~= nil and RacerConfig.isV5Plus(state.mode.Value)",
    "local rightPanelButtonWidth =",
    "UDim2.fromOffset(rightPanelRight, viewportTop + MOBILE_HUD_MARGIN + 80)",
    "settingsPanel.AnchorPoint = Vector2.new(0.5, 0.5)",
    "math.floor(absoluteSize.X / 2 + 0.5)",
    "if compactSettingsPanel then 184 else 430",
    "settingsPanel.AnchorPoint = Vector2.new(1, 0)",
    "mobileStatusLeft = createMobileStatusLabel(\"MobileStatusLeft\", Enum.TextXAlignment.Left)",
    "mobileStatusRight = createMobileStatusLabel(\"MobileStatusRight\", Enum.TextXAlignment.Right)",
    "activeStatus.Visible = not mobileLayout",
    "mobileStatusLeft.Visible = mobileLayout",
    "mobileLeftButton.Position = UDim2.fromOffset(leftPanelCenter - 76, bottomY)",
    "mobileGasButton.Position = UDim2.fromOffset(rightPanelCenter, bottomY)",
    "fullRenderer.statusEnabled = false",
    "activeStatus = Instance.new(\"Frame\")",
    "local activeStatusSpeed = createActiveStatusField(",
    "local activeStatusCurrent = createActiveStatusField(",
    "local activeStatusLast = createActiveStatusField(",
    "local activeStatusFast = createActiveStatusField(",
    "local function updateActiveStatus(state)",
    "activeStatusSpeed.Text = `{5 * math.round(state.speed.Value / 500)} mph`",
    "activeStatusCurrent.Text = `Time: {formatTime(state.currentLapTime.Value)}`",
    "activeStatusFast.Text = `Fastest Lap: {formatTime(state.fastLapTime.Value)}`",
    "if state.lastLapTime.Value > 0 then",
    "activeStatusLast.Visible = true",
    "render(fullRenderer, renderState)\n\t\tupdateActiveStatus(renderState)",
    "local hideLegacySettings = state ~= nil and RacerConfig.isV5Plus(state.mode.Value)",
    "row.nameLabel.Visible = visible",
    "local toggleStartY = if hideLegacySettings then 42 else 248",
    "resetButton.Visible = not hideLegacySettings",
]:
    if token not in CLIENT:
        fail(f"active player v4+ HUD must be a fullscreen overlay below the Roblox topbar: {token}")

if "render(fullRenderer, renderState)\n\t\tupdateActiveStatus(state)" in CLIENT:
    fail("active player v4+ HUD must mirror the local active render state, not the spectator replication state")

for token in [
    "local savedChatEnabled = true",
    "local function getCoreGuiEnabled(coreGuiType: Enum.CoreGuiType, fallback: boolean): boolean",
    "StarterGui:GetCoreGuiEnabled(coreGuiType)",
    "local function releaseFocusedTextBox()",
    "StarterGui:SetCore(\"ChatActive\", false)",
    "GuiService.SelectedObject = nil",
    "focusedTextBox:ReleaseFocus(false)",
    "local function handleRacerKeyboardInput(inputObject: InputObject, isDown: boolean)",
    "if not controlsBound then",
    "releaseFocusedTextBox()",
    "local inputNames = { \"left\", \"right\", \"faster\", \"slower\" }",
    "local keyboardInputs = {}",
    "local pointerInputs = {}",
    "local function inputIsDown(inputName: string): boolean",
    "local function publishInput(inputName: string)",
    "inputEvent:FireServer(inputName, isDown)",
    "local function setKeyboardInput(inputName: string, isDown: boolean)",
    "local function setPointerInput(inputName: string, isDown: boolean)",
    "setKeyboardInput(inputName, isDown)",
    "local function syncHeldKeyboardInputs()",
    "local heldInputs = {}",
    "UserInputService:IsKeyDown(keyCode)",
    "setKeyboardInput(inputName, heldInputs[inputName] == true)",
    "setPointerInput(inputName, true)",
    "setPointerInput(inputName, false)",
    "syncHeldKeyboardInputs()\n\t\tlocal renderState = updatePredictedState(state, deltaTime)",
    "UserInputService.InputBegan:Connect(function(inputObject)",
    "UserInputService.InputEnded:Connect(function(inputObject)",
    "savedChatEnabled = getCoreGuiEnabled(Enum.CoreGuiType.Chat, true)",
    "setCoreGuiEnabled(Enum.CoreGuiType.Chat, false)",
    "setCoreGuiEnabled(Enum.CoreGuiType.Chat, savedChatEnabled)",
    "local function getPlayerModuleControls()",
    "playerScripts:WaitForChild(\"PlayerModule\", 2)",
    "playerModuleApi:GetControls()",
    "local function setCharacterControlsEnabled(enabled: boolean)",
    "controls:Disable()",
    "controls:Enable()",
    "setCharacterControlsEnabled(false)",
    "setCharacterControlsEnabled(true)",
    "syncHeldKeyboardInputs()",
]:
    if token not in CLIENT:
        fail(f"active player keyboard controls must feed local prediction and server input directly: {token}")

for token in [
    "local playerGui = player:WaitForChild(\"PlayerGui\")",
    "local racerGuiMarkerNames = {",
    "local function removeForeignRacerGuiFor(instance: Instance)",
    "local function removeForeignRacerHuds()",
    "if child.Name == \"RacerHud\" and child ~= screenGui then",
    "playerGui.ChildAdded:Connect(function(child)",
    "playerGui.DescendantAdded:Connect(function(descendant)",
    "removeForeignRacerHuds()",
    "layers:{layerCount}/{foreignLayerCount}",
    "local latestPerfSummary = \"waiting for perf sample\"",
    "perfLabel.ZIndex = OVERLAY_Z_INDEX + 100",
    "if inputObject.KeyCode == Enum.KeyCode.F6 then\n\t\tperfLabel.Visible = not perfLabel.Visible\n\t\treturn\n\tend\n\tif gameProcessed then",
    "local function inputDebugFlags(source): string",
    "local function racerStateDebugText(label: string, state): string",
    "local function focusDebugText(): string",
    "local function hudDebugText(): string",
    "local function activeDebugText(state): string",
    "`keys K:",
    "inputDebugFlags(keyboardInputs)",
    "inputDebugFlags(pointerInputs)",
    "pressedInputs",
    "racerStateDebugText(\"local\", predictedState)",
    "racerStateDebugText(\"server\", state)",
    "hudDebugText()",
    "local function refreshPerfLabel(state)",
    "refreshPerfLabel(state)",
    "if perfLabel.Visible then\n\t\t\trefreshPerfLabel(state)\n\t\tend",
]:
    if token not in CLIENT:
        fail(f"F6 active racer diagnostics must expose input/local/server HUD state: {token}")

for token in [
    "local perfWindowFocused = true",
    "local perfSkipNextFrame = false",
    "UserInputService.WindowFocusReleased:Connect(function()",
    "UserInputService.WindowFocused:Connect(function()",
    'latestPerfSummary = "paused while window is unfocused"',
    "local collectPerf = perfWindowFocused and not perfSkipNextFrame",
    "if perfStats.stutters > 0 then\n\t\twarn(`[RacerPerf] {summary}`)\n\t\tperfLogEvent:FireServer(summary)\n\tend",
    "if perfWindowFocused and perfStats.elapsed >= PERF_LOG_INTERVAL then",
]:
    if token not in CLIENT:
        fail(f"perf telemetry must ignore unfocused windows and report only focused stutters: {token}")

for token in [
    'local LogService = game:GetService("LogService")',
    'RacerClientLog',
    'RacerClientLogs',
    "LogService.MessageOut:Connect(",
]:
    if token in CLIENT or token in SERVER:
        fail(f"custom client warning/error telemetry bridge must remain removed: {token}")

for token in [
    'player:GetAttribute("Activity") ~= "RacerScreen"',
    'player:GetAttribute("RacerScreenId")',
    'player:GetAttributeChangedSignal("Activity"):Connect(updateHud)',
    'player:GetAttributeChangedSignal("RacerScreenId"):Connect(updateHud)',
    "local function hudNeedsSync(state): boolean",
    "if hudNeedsSync(state) then\n\t\tupdateHud()\n\tend",
]:
    if token not in CLIENT:
        fail(f"active player HUD must follow the player's own screen state every frame: {token}")

print("Racer parity checks passed")
