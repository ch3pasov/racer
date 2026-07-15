#!/usr/bin/python3 -I
"""Crash-safe local state for traceable Racer place publishes."""

from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build"
STATE_PATH = BUILD_DIR / "racer-publish-pending.json"
STATE_LOCK_PATH = BUILD_DIR / ".racer-publish-state.lock"
LEGACY_RELEASE_LOCK_PATH = BUILD_DIR / ".racer-publish-release.lock"
RELEASE_LOCK_NAME = "racer-publish-release.lock"
RELEASE_LOCK_FD = 8
RELEASE_SECRET_FD = 9
RELEASE_LOCK_CONTEXT_ENV = "RACER_RELEASE_LOCK_CONTEXT"
RELEASE_LOCK_FD_ENV = "RACER_RELEASE_LOCK_FD"
RELEASE_LOCK_CONTEXT = "racer-release-lock-v1"
RELEASE_SECRET_CONTEXT_ENV = "RACER_RELEASE_SECRET_CONTEXT"
RELEASE_SECRET_FD_ENV = "RACER_RELEASE_SECRET_FD"
RELEASE_SECRET_CONTEXT = "racer-release-secret-v1"
ARTIFACT_LABEL = "build/racer.rbxlx"
EXPECTED_KEYS = {
    "artifact",
    "gitCommit",
    "gitCommitShort",
    "lobbyPlaceId",
    "mode",
    "placeVersion",
    "publishedAt",
    "racerPlaceId",
    "schemaVersion",
    "state",
    "universeId",
}
EXPECTED_ARTIFACT_KEYS = {"path", "sha256", "sizeBytes"}
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHORT_COMMIT_RE = re.compile(r"[0-9a-f]{12}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
POSITIVE_DECIMAL_RE = re.compile(r"[1-9][0-9]*")
NONNEGATIVE_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)")
TIMESTAMP_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)


class StateError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise StateError(message)


def descriptor_is_open(descriptor: int) -> bool:
    try:
        os.fstat(descriptor)
    except OSError as error:
        if error.errno == errno.EBADF:
            return False
        raise
    return True


def reject_legacy_release_lock() -> None:
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
        "XDG_CONFIG_HOME": "/dev/null",
    }
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "-c",
                f"safe.directory={ROOT}",
                "-C",
                str(ROOT),
                "worktree",
                "list",
                "--porcelain",
                "-z",
            ],
            check=True,
            close_fds=True,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"cannot enumerate registered Git worktrees for legacy locks: {error}")
    if not result.stdout.endswith(b"\0\0"):
        fail("Git returned a malformed registered-worktree list")

    worktrees = {ROOT}
    for record in result.stdout[:-2].split(b"\0\0"):
        fields = record.split(b"\0")
        if not fields or not fields[0].startswith(b"worktree "):
            fail("Git returned a malformed registered-worktree record")
        if b"bare" in fields[1:]:
            continue
        raw_path = fields[0][len(b"worktree ") :]
        path = Path(os.fsdecode(raw_path))
        if not raw_path or not path.is_absolute():
            fail("Git returned a non-absolute registered-worktree path")
        worktrees.add(path)

    for worktree in worktrees:
        legacy_path = worktree / "build/.racer-publish-release.lock"
        try:
            os.lstat(legacy_path)
        except FileNotFoundError:
            continue
        except OSError as error:
            fail(f"cannot inspect a registered worktree legacy lock: {error}")
        fail(
            "legacy build/.racer-publish-release.lock exists in a registered "
            f"worktree ({worktree}); quiesce every worktree, then remove each "
            "legacy path once"
        )


def git_common_dir() -> Path:
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "/",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
        "XDG_CONFIG_HOME": "/dev/null",
    }
    try:
        result = subprocess.run(
            [
                "/usr/bin/git",
                "-c",
                f"safe.directory={ROOT}",
                "-C",
                str(ROOT),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            close_fds=True,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        fail(f"cannot resolve the Git common directory: {error}")
    lines = result.stdout.splitlines()
    if len(lines) != 1 or not os.path.isabs(lines[0]):
        fail("Git returned an invalid common-directory path")
    try:
        return Path(lines[0]).resolve(strict=True)
    except OSError as error:
        fail(f"cannot resolve the Git common-directory path: {error}")


@contextlib.contextmanager
def open_git_common_dir():
    common_dir = git_common_dir()
    required_flags = ("O_CLOEXEC", "O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required_flags):
        fail("release locking requires O_DIRECTORY and O_NOFOLLOW support")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(common_dir, flags)
    except OSError as error:
        fail(f"cannot securely open the Git common directory: {error}")
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(common_dir, follow_symlinks=False)
        if not stat.S_ISDIR(descriptor_metadata.st_mode):
            fail("resolved Git common directory is not a directory")
        if (
            descriptor_metadata.st_dev,
            descriptor_metadata.st_ino,
        ) != (path_metadata.st_dev, path_metadata.st_ino):
            fail("Git common-directory path changed while it was opened")
        yield common_dir, descriptor, descriptor_metadata
    finally:
        os.close(descriptor)


def validate_release_lock_inode(
    descriptor: int,
    common_descriptor: int,
    common_metadata: os.stat_result,
) -> os.stat_result:
    try:
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(
            RELEASE_LOCK_NAME,
            dir_fd=common_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        fail(f"cannot validate the persistent Racer release lock: {error}")
    if not stat.S_ISREG(descriptor_metadata.st_mode):
        fail("persistent Racer release lock must be a regular file")
    if stat.S_IMODE(descriptor_metadata.st_mode) != 0o600:
        fail("persistent Racer release lock must have mode 0600")
    if descriptor_metadata.st_nlink != 1:
        fail("persistent Racer release lock must have exactly one link")
    if descriptor_metadata.st_uid != common_metadata.st_uid:
        fail("persistent Racer release lock owner must match the Git common directory")
    if descriptor_metadata.st_size != 0:
        fail("persistent Racer release lock must remain empty")
    if (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ) != (path_metadata.st_dev, path_metadata.st_ino):
        fail("persistent Racer release lock path does not match its open inode")
    return descriptor_metadata


def open_release_lock() -> int:
    reject_legacy_release_lock()
    with open_git_common_dir() as (_common_dir, common_descriptor, common_metadata):
        flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        created = False
        try:
            descriptor = os.open(
                RELEASE_LOCK_NAME,
                flags,
                dir_fd=common_descriptor,
            )
        except FileNotFoundError:
            if common_metadata.st_uid != os.geteuid():
                fail(
                    "only the Git common-directory owner may create the "
                    "persistent Racer release lock"
                )
            try:
                descriptor = os.open(
                    RELEASE_LOCK_NAME,
                    flags | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=common_descriptor,
                )
                created = True
            except FileExistsError:
                try:
                    descriptor = os.open(
                        RELEASE_LOCK_NAME,
                        flags,
                        dir_fd=common_descriptor,
                    )
                except OSError as error:
                    fail(
                        "cannot securely open the raced persistent Racer "
                        f"release lock: {error}"
                    )
            except OSError as error:
                fail(f"cannot securely create the persistent Racer release lock: {error}")
        except OSError as error:
            fail(f"cannot securely open the persistent Racer release lock: {error}")
        try:
            if created:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    fail(f"cannot lock the newly created Racer release lock: {error}")
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
                os.fsync(common_descriptor)
            validate_release_lock_inode(
                descriptor, common_descriptor, common_metadata
            )
            if not created:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES, errno.EAGAIN):
                        fail("another Racer release operation holds the persistent lock")
                    fail(f"cannot acquire the persistent Racer release lock: {error}")
            validate_release_lock_inode(
                descriptor, common_descriptor, common_metadata
            )
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise


def require_exact_lock_context() -> None:
    context = os.environ.get(RELEASE_LOCK_CONTEXT_ENV)
    descriptor = os.environ.get(RELEASE_LOCK_FD_ENV)
    if context != RELEASE_LOCK_CONTEXT or descriptor != str(RELEASE_LOCK_FD):
        fail("Racer release lock context is missing, partial, or spoofed")


def reject_existing_lock_context() -> None:
    names = (RELEASE_LOCK_CONTEXT_ENV, RELEASE_LOCK_FD_ENV)
    if any(name in os.environ for name in names):
        fail("Racer release lock acquisition received a preexisting context")


def reject_existing_secret_context() -> None:
    names = (RELEASE_SECRET_CONTEXT_ENV, RELEASE_SECRET_FD_ENV)
    if any(name in os.environ for name in names):
        fail("Racer release lock acquisition received a preexisting secret context")


def reject_secret_context() -> None:
    names = (RELEASE_SECRET_CONTEXT_ENV, RELEASE_SECRET_FD_ENV)
    if any(name in os.environ for name in names):
        fail("Racer release secret context must be consumed before lock assertion")
    if descriptor_is_open(RELEASE_SECRET_FD):
        fail("Racer release secret FD must be closed before lock assertion")


def validate_secret_descriptor(descriptor: int) -> None:
    if descriptor != RELEASE_SECRET_FD:
        fail(f"release secret must use fixed FD {RELEASE_SECRET_FD}")
    try:
        metadata = os.fstat(descriptor)
    except OSError as error:
        fail(f"release secret FD is not open: {error}")
    if not stat.S_ISFIFO(metadata.st_mode):
        fail("release secret FD must be an anonymous pipe")
    flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
    if flags & os.O_ACCMODE != os.O_RDONLY:
        fail("release secret FD must be the read end of an anonymous pipe")


def exec_environment(*, secret: bool) -> dict[str, str]:
    home = os.environ.get("HOME", "")
    if not os.path.isabs(home):
        fail("release lock handoff requires an absolute HOME")
    temporary = os.environ.get("TMPDIR", "/tmp")
    if not os.path.isabs(temporary):
        fail("release lock handoff requires an absolute TMPDIR")
    environment = {
        "HOME": home,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        RELEASE_LOCK_CONTEXT_ENV: RELEASE_LOCK_CONTEXT,
        RELEASE_LOCK_FD_ENV: str(RELEASE_LOCK_FD),
        "TMPDIR": temporary,
        "TZ": "UTC",
    }
    for name in (
        "ROBLOX_LOBBY_PLACE_ID",
        "ROBLOX_RACER_PLACE_ID",
        "ROBLOX_UNIVERSE_ID",
    ):
        if name in os.environ:
            environment[name] = os.environ[name]
    if secret:
        environment[RELEASE_SECRET_CONTEXT_ENV] = RELEASE_SECRET_CONTEXT
        environment[RELEASE_SECRET_FD_ENV] = str(RELEASE_SECRET_FD)
    return environment


def close_unexpected_descriptors(*, secret: bool) -> None:
    allowed = {0, 1, 2, RELEASE_LOCK_FD}
    if secret:
        allowed.add(RELEASE_SECRET_FD)
    for directory in ("/dev/fd", "/proc/self/fd"):
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            if not name.isdecimal():
                continue
            descriptor = int(name)
            if descriptor in allowed:
                continue
            try:
                os.close(descriptor)
            except OSError as error:
                if error.errno != errno.EBADF:
                    raise
        return

    fail("cannot securely enumerate open descriptors before release handoff")


def canonical_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail(f"pending publish state contains duplicate field {key}")
        result[key] = value
    return result


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def state_lock():
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(STATE_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def write_temp(payload: dict[str, object]) -> Path:
    descriptor, raw_path = tempfile.mkstemp(prefix=".racer-publish-pending.", dir=BUILD_DIR)
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def create_no_clobber(payload: dict[str, object]) -> None:
    temporary = write_temp(payload)
    try:
        try:
            os.link(temporary, STATE_PATH)
        except FileExistsError:
            fail(f"pending publish state already exists: {STATE_PATH.relative_to(ROOT)}")
        fsync_directory(BUILD_DIR)
    finally:
        temporary.unlink(missing_ok=True)
        fsync_directory(BUILD_DIR)


def replace_atomic(payload: dict[str, object]) -> None:
    temporary = write_temp(payload)
    try:
        os.replace(temporary, STATE_PATH)
        fsync_directory(BUILD_DIR)
    finally:
        temporary.unlink(missing_ok=True)


def decimal_string(value: object, field: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str):
        fail(f"{field} must be a decimal string")
    expression = NONNEGATIVE_DECIMAL_RE if allow_zero else POSITIVE_DECIMAL_RE
    if expression.fullmatch(value) is None:
        qualifier = "zero or a positive" if allow_zero else "a positive"
        fail(f"{field} must be {qualifier} canonical decimal string")
    return value


def strict_state(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        fail("pending publish state must be a JSON object")
    if set(payload) != EXPECTED_KEYS:
        fail("pending publish state has missing or unknown fields")
    if payload["schemaVersion"] != 1 or isinstance(payload["schemaVersion"], bool):
        fail("unsupported pending publish schemaVersion")

    mode = payload["mode"]
    if mode not in {"open-cloud", "studio"}:
        fail("mode must be open-cloud or studio")
    state = payload["state"]
    if state not in {"prepared", "version-recorded"}:
        fail("state must be prepared or version-recorded")

    commit = payload["gitCommit"]
    short_commit = payload["gitCommitShort"]
    published_at = payload["publishedAt"]
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        fail("gitCommit must be a full lowercase SHA-1 object id")
    if not isinstance(short_commit, str) or SHORT_COMMIT_RE.fullmatch(short_commit) is None:
        fail("gitCommitShort must be a 12-character lowercase object id")
    if not commit.startswith(short_commit):
        fail("gitCommitShort is not a prefix of gitCommit")
    if not isinstance(published_at, str) or TIMESTAMP_RE.fullmatch(published_at) is None:
        fail("publishedAt must use YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        fail("publishedAt must be a valid UTC calendar timestamp")

    decimal_string(payload["racerPlaceId"], "racerPlaceId")
    decimal_string(payload["lobbyPlaceId"], "lobbyPlaceId", allow_zero=True)
    universe_id = payload["universeId"]
    if mode == "open-cloud":
        decimal_string(universe_id, "universeId")
    elif universe_id is not None:
        fail("studio pending state must have a null universeId")

    place_version = payload["placeVersion"]
    if state == "prepared":
        if place_version is not None:
            fail("prepared pending state must have a null placeVersion")
    else:
        decimal_string(place_version, "placeVersion")

    artifact = payload["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != EXPECTED_ARTIFACT_KEYS:
        fail("artifact has missing or unknown fields")
    if artifact["path"] != ARTIFACT_LABEL:
        fail(f"artifact.path must be {ARTIFACT_LABEL}")
    artifact_sha = artifact["sha256"]
    artifact_size = artifact["sizeBytes"]
    if not isinstance(artifact_sha, str) or SHA256_RE.fullmatch(artifact_sha) is None:
        fail("artifact.sha256 must be a lowercase SHA-256 digest")
    if (
        not isinstance(artifact_size, int)
        or isinstance(artifact_size, bool)
        or artifact_size <= 0
    ):
        fail("artifact.sizeBytes must be a positive integer")
    return payload


def load_state() -> dict[str, object]:
    try:
        metadata = STATE_PATH.lstat()
    except FileNotFoundError:
        fail(f"missing pending publish state: {STATE_PATH.relative_to(ROOT)}")
    if not stat.S_ISREG(metadata.st_mode) or STATE_PATH.is_symlink():
        fail("pending publish state must be a regular non-symlink file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        fail("pending publish state must have mode 0600")
    try:
        raw = STATE_PATH.read_bytes()
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot read pending publish state: {error}")
    strict_state(payload)
    if raw != canonical_bytes(payload):
        fail("pending publish state is not canonical JSON")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_path(payload: dict[str, object]) -> Path:
    artifact = payload["artifact"]
    assert isinstance(artifact, dict)
    return ROOT / str(artifact["path"])


def module_source(root: ET.Element, name: str) -> str:
    matches: list[str] = []
    for item in root.iter("Item"):
        if item.get("class") != "ModuleScript":
            continue
        properties = item.find("Properties")
        if properties is None:
            continue
        values = {node.get("name"): node.text or "" for node in properties}
        if values.get("Name") == name:
            if "Source" not in values:
                fail(f"release artifact {name} has no Source property")
            matches.append(values["Source"])
    if len(matches) != 1:
        fail(f"release artifact must contain exactly one {name} ModuleScript")
    return matches[0]


def string_field(source: str, key: str) -> str:
    values = re.findall(
        rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"\r\n]*)"\s*,?\s*$', source
    )
    if len(values) != 1:
        fail(f"release artifact must contain exactly one string field {key}")
    return values[0]


def integer_field(source: str, key: str) -> str:
    values = re.findall(
        rf"(?m)^\s*{re.escape(key)}\s*=\s*([0-9]+)\s*,?\s*$", source
    )
    if len(values) != 1:
        fail(f"release artifact must contain exactly one integer field {key}")
    return values[0]


def validate_artifact(payload: dict[str, object]) -> str:
    path = artifact_path(payload)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        fail(f"missing pending Racer release artifact: {path.relative_to(ROOT)}")
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        fail("pending Racer release artifact must be a regular non-symlink file")
    artifact = payload["artifact"]
    assert isinstance(artifact, dict)
    if metadata.st_size != artifact["sizeBytes"]:
        fail("pending Racer release artifact size does not match its manifest")
    digest = file_sha256(path)
    if digest != artifact["sha256"]:
        fail("pending Racer release artifact SHA-256 does not match its manifest")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        fail(f"cannot parse pending Racer release artifact: {error}")

    build_info = module_source(root, "GeneratedBuildInfo")
    place_ids = module_source(root, "GeneratedPlaceIds")
    checks = {
        "GitCommit": (string_field(build_info, "GitCommit"), payload["gitCommit"]),
        "GitCommitShort": (
            string_field(build_info, "GitCommitShort"),
            payload["gitCommitShort"],
        ),
        "PublishedAt": (
            string_field(build_info, "PublishedAt"),
            payload["publishedAt"],
        ),
        "RacerPlaceId": (
            integer_field(place_ids, "RacerPlaceId"),
            payload["racerPlaceId"],
        ),
        "LobbyPlaceId": (
            integer_field(place_ids, "LobbyPlaceId"),
            payload["lobbyPlaceId"],
        ),
    }
    for key, (actual, expected) in checks.items():
        if actual != expected:
            fail(f"release artifact {key} mismatch: embedded {actual}, expected {expected}")
    return digest


def command_assert_absent(_arguments: argparse.Namespace) -> None:
    with state_lock():
        try:
            STATE_PATH.lstat()
        except FileNotFoundError:
            return
        try:
            payload = load_state()
        except StateError as error:
            fail(f"a pending publish state exists and is invalid ({error})")
        version = payload["placeVersion"] or "unknown"
        fail(
            "a Racer publish is already pending "
            f"(commit {payload['gitCommitShort']}, mode {payload['mode']}, "
            f"PlaceVersion {version}); finalize it before building or publishing again"
        )


def probe_inherited_release_lock(
    common_descriptor: int,
    common_metadata: os.stat_result,
) -> None:
    """Prove FD 8 was already locked, rather than acquiring a spoofed open FD."""
    try:
        child = os.fork()
    except OSError as error:
        fail(f"cannot fork the inherited release-lock ownership probe: {error}")
    if child == 0:
        result = 72
        try:
            os.close(RELEASE_LOCK_FD)
            probe = os.open(
                RELEASE_LOCK_NAME,
                os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=common_descriptor,
            )
            try:
                validate_release_lock_inode(
                    probe, common_descriptor, common_metadata
                )
                try:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    if error.errno in (errno.EACCES, errno.EAGAIN):
                        result = 0
                    else:
                        result = 73
                else:
                    result = 71
            finally:
                os.close(probe)
        except BaseException:
            result = 74
        os._exit(result)

    while True:
        try:
            _pid, status = os.waitpid(child, 0)
            break
        except InterruptedError:
            continue
        except OSError as error:
            fail(f"cannot wait for the inherited release-lock probe: {error}")
    if not os.WIFEXITED(status):
        fail("inherited release-lock ownership probe terminated abnormally")
    result = os.WEXITSTATUS(status)
    if result == 71:
        fail("inherited Racer release lock FD was open but not already locked")
    if result != 0:
        fail(f"inherited release-lock ownership probe failed ({result})")


def validate_just_acquired_release_lock() -> None:
    """Validate the helper-owned FD without forking while secret FD 9 is live."""
    if not descriptor_is_open(RELEASE_LOCK_FD):
        fail(f"acquired Racer release lock FD {RELEASE_LOCK_FD} is not open")
    if not os.get_inheritable(RELEASE_LOCK_FD):
        fail("acquired Racer release lock FD is not marked inheritable")
    with open_git_common_dir() as (_common_dir, common_descriptor, common_metadata):
        validate_release_lock_inode(
            RELEASE_LOCK_FD, common_descriptor, common_metadata
        )
        try:
            fcntl.flock(RELEASE_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            fail(f"cannot validate the acquired Racer release lock: {error}")
        validate_release_lock_inode(
            RELEASE_LOCK_FD, common_descriptor, common_metadata
        )


def validate_inherited_release_lock() -> None:
    reject_legacy_release_lock()
    if not descriptor_is_open(RELEASE_LOCK_FD):
        fail(f"inherited Racer release lock FD {RELEASE_LOCK_FD} is not open")
    if not os.get_inheritable(RELEASE_LOCK_FD):
        fail("inherited Racer release lock FD is not marked inheritable")
    with open_git_common_dir() as (_common_dir, common_descriptor, common_metadata):
        validate_release_lock_inode(
            RELEASE_LOCK_FD, common_descriptor, common_metadata
        )
        probe_inherited_release_lock(common_descriptor, common_metadata)
        try:
            fcntl.flock(
                RELEASE_LOCK_FD,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                fail("inherited Racer release lock FD does not own the lock")
            fail(f"cannot assert the inherited Racer release lock: {error}")
        validate_release_lock_inode(
            RELEASE_LOCK_FD, common_descriptor, common_metadata
        )


def command_with_release_lock(arguments: argparse.Namespace) -> None:
    if not sys.flags.isolated:
        fail("release lock acquisition requires isolated Python (-I)")
    if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
        fail("release lock acquisition must not receive a publish credential")
    reject_existing_lock_context()
    reject_existing_secret_context()
    if descriptor_is_open(RELEASE_LOCK_FD):
        fail(f"release lock acquisition requires unused FD {RELEASE_LOCK_FD}")

    secret = arguments.secret_fd is not None
    if secret:
        validate_secret_descriptor(arguments.secret_fd)
    elif descriptor_is_open(RELEASE_SECRET_FD):
        fail(f"release lock acquisition received unexpected FD {RELEASE_SECRET_FD}")

    command = list(arguments.exec_command)
    if command and command[0] == "--":
        command.pop(0)
    if not command or not os.path.isabs(command[0]):
        fail("release lock handoff command must use an absolute executable path")

    descriptor = open_release_lock()
    try:
        if descriptor != RELEASE_LOCK_FD:
            os.dup2(descriptor, RELEASE_LOCK_FD, inheritable=True)
            os.close(descriptor)
            descriptor = RELEASE_LOCK_FD
        else:
            os.set_inheritable(descriptor, True)
        if secret:
            os.set_inheritable(RELEASE_SECRET_FD, True)
        validate_just_acquired_release_lock()
        environment = exec_environment(secret=secret)
        close_unexpected_descriptors(secret=secret)
        try:
            os.execve(command[0], command, environment)
        except OSError as error:
            fail(f"cannot exec the release-lock handoff command: {error}")
    finally:
        if descriptor_is_open(descriptor):
            os.close(descriptor)


def command_assert_release_lock(_arguments: argparse.Namespace) -> None:
    if not sys.flags.isolated:
        fail("release lock assertion requires isolated Python (-I)")
    require_exact_lock_context()
    reject_secret_context()
    validate_inherited_release_lock()


def command_create(arguments: argparse.Namespace) -> None:
    artifact = ROOT / ARTIFACT_LABEL
    try:
        artifact_metadata = artifact.lstat()
    except FileNotFoundError:
        fail(f"missing release artifact: {ARTIFACT_LABEL}")
    if not stat.S_ISREG(artifact_metadata.st_mode) or artifact.is_symlink():
        fail("release artifact must be a regular non-symlink file")
    payload: dict[str, object] = {
        "artifact": {
            "path": ARTIFACT_LABEL,
            "sha256": file_sha256(artifact),
            "sizeBytes": artifact_metadata.st_size,
        },
        "gitCommit": arguments.git_commit,
        "gitCommitShort": arguments.git_commit_short,
        "lobbyPlaceId": arguments.lobby_place_id,
        "mode": arguments.mode,
        "placeVersion": None,
        "publishedAt": arguments.published_at,
        "racerPlaceId": arguments.racer_place_id,
        "schemaVersion": 1,
        "state": "prepared",
        "universeId": arguments.universe_id,
    }
    strict_state(payload)
    validate_artifact(payload)
    with state_lock():
        create_no_clobber(payload)
    print(payload["artifact"]["sha256"])


def command_inspect(_arguments: argparse.Namespace) -> None:
    with state_lock():
        payload = load_state()
    artifact = payload["artifact"]
    assert isinstance(artifact, dict)
    values = [
        payload["mode"],
        payload["state"],
        payload["gitCommit"],
        payload["gitCommitShort"],
        payload["publishedAt"],
        artifact["path"],
        artifact["sha256"],
        str(artifact["sizeBytes"]),
        payload["universeId"] if payload["universeId"] is not None else "-",
        payload["racerPlaceId"],
        payload["lobbyPlaceId"],
        payload["placeVersion"] if payload["placeVersion"] is not None else "-",
    ]
    print("\n".join(str(value) for value in values))


def command_validate_artifact(_arguments: argparse.Namespace) -> None:
    with state_lock():
        payload = load_state()
        digest = validate_artifact(payload)
    print(digest)


def command_record_version(arguments: argparse.Namespace) -> None:
    decimal_string(arguments.place_version, "placeVersion")
    if COMMIT_RE.fullmatch(arguments.git_commit) is None:
        fail("git commit record guard must be a full lowercase SHA-1 object id")
    if SHA256_RE.fullmatch(arguments.artifact_sha256) is None:
        fail("artifact record guard must be a lowercase SHA-256 digest")
    with state_lock():
        payload = load_state()
        artifact = payload["artifact"]
        assert isinstance(artifact, dict)
        if payload["gitCommit"] != arguments.git_commit:
            fail("pending publish commit changed before PlaceVersion record")
        if artifact["sha256"] != arguments.artifact_sha256:
            fail("pending publish artifact changed before PlaceVersion record")
        current = payload["placeVersion"]
        if current is not None:
            if current != arguments.place_version:
                fail(
                    f"pending publish already records PlaceVersion {current}, "
                    f"not {arguments.place_version}"
                )
            return
        payload["state"] = "version-recorded"
        payload["placeVersion"] = arguments.place_version
        strict_state(payload)
        replace_atomic(payload)


def command_clear(arguments: argparse.Namespace) -> None:
    decimal_string(arguments.place_version, "placeVersion")
    if COMMIT_RE.fullmatch(arguments.git_commit) is None:
        fail("git commit clear guard must be a full lowercase SHA-1 object id")
    if SHA256_RE.fullmatch(arguments.artifact_sha256) is None:
        fail("artifact clear guard must be a lowercase SHA-256 digest")
    with state_lock():
        payload = load_state()
        artifact = payload["artifact"]
        assert isinstance(artifact, dict)
        if payload["gitCommit"] != arguments.git_commit:
            fail("pending publish commit changed before clear")
        if artifact["sha256"] != arguments.artifact_sha256:
            fail("pending publish artifact changed before clear")
        if payload["state"] != "version-recorded":
            fail("pending publish cannot be cleared before PlaceVersion is recorded")
        if payload["placeVersion"] != arguments.place_version:
            fail("pending publish PlaceVersion changed before clear")
        STATE_PATH.unlink()
        fsync_directory(BUILD_DIR)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    assert_absent = commands.add_parser("assert-absent")
    assert_absent.set_defaults(handler=command_assert_absent)

    with_lock = commands.add_parser("with-release-lock")
    with_lock.add_argument("--secret-fd", type=int)
    with_lock.add_argument("exec_command", nargs=argparse.REMAINDER)
    with_lock.set_defaults(handler=command_with_release_lock)

    assert_lock = commands.add_parser("assert-release-lock")
    assert_lock.set_defaults(handler=command_assert_release_lock)

    create = commands.add_parser("create")
    create.add_argument("--mode", choices=("open-cloud", "studio"), required=True)
    create.add_argument("--git-commit", required=True)
    create.add_argument("--git-commit-short", required=True)
    create.add_argument("--published-at", required=True)
    create.add_argument("--universe-id")
    create.add_argument("--racer-place-id", required=True)
    create.add_argument("--lobby-place-id", required=True)
    create.set_defaults(handler=command_create)

    inspect = commands.add_parser("inspect")
    inspect.set_defaults(handler=command_inspect)

    validate = commands.add_parser("validate-artifact")
    validate.set_defaults(handler=command_validate_artifact)

    record = commands.add_parser("record-version")
    record.add_argument("place_version")
    record.add_argument("--git-commit", required=True)
    record.add_argument("--artifact-sha256", required=True)
    record.set_defaults(handler=command_record_version)

    clear = commands.add_parser("clear")
    clear.add_argument("--git-commit", required=True)
    clear.add_argument("--artifact-sha256", required=True)
    clear.add_argument("--place-version", required=True)
    clear.set_defaults(handler=command_clear)
    return result


def main() -> None:
    arguments = parser().parse_args()
    try:
        arguments.handler(arguments)
    except StateError as error:
        print(f"Racer publish state error: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
