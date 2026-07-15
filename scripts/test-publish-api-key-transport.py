#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
TEST_VERSION = "424242"
STUDIO_TEST_VERSION = "424243"
TOOLCHAIN_FIXTURE = ROOT / "scripts/test-fixtures/release-toolchain"
FIXTURE_MANIFEST = TOOLCHAIN_FIXTURE / "manifest.tsv"
FIXTURE_ROJO = TOOLCHAIN_FIXTURE / "fake-rojo"
ROJO_STORAGE_RELATIVE = Path(
    ".aftman/tool-storage/rojo-rbx/rojo/7.5.1/rojo"
)

FAKE_CURL = r'''#!/usr/bin/env python3
import hashlib
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
import sys


def fail(message: str) -> None:
    print(f"fake curl validation failed: {message}", file=sys.stderr)
    raise SystemExit(91)


expected = "sentinel-" + hashlib.sha256(
    b"racer-publish-api-key-transport-test"
).hexdigest()
if any(expected in argument for argument in sys.argv):
    fail("API key reached curl argv")
if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
    fail("credential variable remained in the curl environment")
if any(expected in value for value in os.environ.values()):
    fail("API key value reached the curl environment")
if len(sys.argv) < 2 or sys.argv[1] != "--disable":
    fail("--disable was not curl's first option")
if "CURL_HOME" in os.environ or "PYTHONPATH" in os.environ or "BASH_ENV" in os.environ:
    fail("host startup/configuration environment reached curl")
try:
    os.fstat(9)
except OSError:
    pass
else:
    fail("secret transport FD 9 remained open in curl")
try:
    lock_metadata = os.fstat(8)
except OSError:
    fail("release lock FD 8 did not reach the critical curl child")
if not stat.S_ISREG(lock_metadata.st_mode):
    fail("release lock FD 8 was not a regular file")
probe = os.open(".git/racer-publish-release.lock", os.O_RDWR)
try:
    try:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno not in (errno.EACCES, errno.EAGAIN):
            fail(f"independent lock probe failed: {error}")
    else:
        fail("critical curl child inherited an unlocked FD 8")
finally:
    os.close(probe)

state_path = Path("build/racer-publish-pending.json")
if not state_path.is_file():
    fail("pending publish state was not durable before curl")
state = json.loads(state_path.read_text())
if state.get("mode") != "open-cloud" or state.get("state") != "prepared":
    fail("pending publish state was not PREPARED before curl")
if state.get("placeVersion") is not None:
    fail("pending publish state recorded a version before the response")
artifact = Path(state["artifact"]["path"])
if hashlib.sha256(artifact.read_bytes()).hexdigest() != state["artifact"]["sha256"]:
    fail("pending artifact hash was incorrect before curl")
if expected.encode() in state_path.read_bytes():
    fail("pending publish state contained the API key")

headers = []
for index, argument in enumerate(sys.argv):
    if argument != "--header":
        continue
    if index + 1 >= len(sys.argv):
        fail("header argument has no value")
    headers.append(sys.argv[index + 1])

fd_headers = [header for header in headers if header.startswith("@/dev/fd/")]
if len(fd_headers) != 1:
    fail("API header was not supplied through exactly one file descriptor")

header_path = Path(fd_headers[0][1:])
try:
    header_bytes = header_path.read_bytes()
except OSError:
    fail("API header file descriptor was not readable")

expected_header = f"x-api-key: {expected}\n".encode()
if header_bytes != expected_header:
    fail("API header content was incorrect")
if "Content-Type: application/xml" not in headers:
    fail("content type header was missing")

print('{"versionNumber": 424242}')
'''

FAKE_STATE_HELPER = r'''#!/usr/bin/env python3
import hashlib
import fcntl
import os
from pathlib import Path
import stat
import sys


expected = "sentinel-" + hashlib.sha256(
    b"racer-publish-api-key-transport-test"
).hexdigest()
if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
    print("state helper received a credential variable", file=sys.stderr)
    raise SystemExit(88)
if any(expected in value for value in os.environ.values()):
    print("state helper received the credential value", file=sys.stderr)
    raise SystemExit(88)

command = sys.argv[1] if len(sys.argv) > 1 else ""
secret_handoff = command == "with-release-lock" and "--secret-fd" in sys.argv
if command == "with-release-lock":
    try:
        os.fstat(8)
    except OSError:
        pass
    else:
        print("acquisition wrapper received a preexisting FD 8", file=sys.stderr)
        raise SystemExit(88)
    try:
        secret_metadata = os.fstat(9)
    except OSError:
        secret_open = False
    else:
        secret_open = True
    if secret_open != secret_handoff:
        print("acquisition wrapper received the wrong FD 9 state", file=sys.stderr)
        raise SystemExit(88)
    if secret_open:
        flags = fcntl.fcntl(9, fcntl.F_GETFL)
        if not stat.S_ISFIFO(secret_metadata.st_mode) or flags & os.O_ACCMODE != os.O_RDONLY:
            print("FD 9 was not a read-only pipe", file=sys.stderr)
            raise SystemExit(88)
else:
    try:
        os.fstat(9)
    except OSError:
        pass
    else:
        print("secret FD 9 remained open after handoff", file=sys.stderr)
        raise SystemExit(88)
    try:
        lock_metadata = os.fstat(8)
    except OSError:
        print("critical state helper did not inherit FD 8", file=sys.stderr)
        raise SystemExit(88)

Path("build").mkdir(exist_ok=True)
with Path("build/test-helper-calls.log").open("a") as stream:
    details = ""
    if command != "with-release-lock":
        details = (
            f" parent={os.getppid()}"
            f" inode={lock_metadata.st_dev}:{lock_metadata.st_ino}"
        )
    stream.write(
        f"{command} {'secret' if secret_handoff else 'no-secret'}{details}\n"
    )

real_helper = Path(__file__).with_name("racer-publish-state-real.py")
os.execv(str(real_helper), [str(real_helper), *sys.argv[1:]])
'''

FAKE_GIT = r'''#!/usr/bin/env python3
import hashlib
import os
import sys


expected = "sentinel-" + hashlib.sha256(
    b"racer-publish-api-key-transport-test"
).hexdigest()
if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
    print("git wrapper received a credential variable", file=sys.stderr)
    raise SystemExit(87)
if any(expected in value for value in os.environ.values()):
    print("git wrapper received the credential value", file=sys.stderr)
    raise SystemExit(87)

real_git = __REAL_GIT__
os.execv(real_git, [real_git, *sys.argv[1:]])
'''


def write_executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_checked(command: list[str], cwd: Path) -> None:
    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_publisher(
    repo: Path, environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "scripts/publish-place.sh"), *arguments],
        cwd=repo,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_hostile_shell_publisher(
    repo: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-a", "-x", str(repo / "scripts/publish-place.sh")],
        cwd=repo,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_finalizer(
    repo: Path, environment: dict[str, str], version: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "scripts/finalize-studio-publish.sh"), version],
        cwd=repo,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_result(
    result: subprocess.CompletedProcess[str],
    label: str,
    expected_code: int,
    *forbidden_values: str,
) -> None:
    combined_output = result.stdout + result.stderr
    if any(value and value in combined_output for value in forbidden_values):
        raise RuntimeError(f"{label} exposed a credential in its output")
    if result.returncode != expected_code:
        raise RuntimeError(
            f"{label} returned {result.returncode}, expected {expected_code}: "
            f"{combined_output}"
        )


def main() -> None:
    sentinel = "sentinel-" + hashlib.sha256(
        b"racer-publish-api-key-transport-test"
    ).hexdigest()

    with tempfile.TemporaryDirectory(prefix="racer-publish-secret-test-") as temp:
        temp_root = Path(temp)
        repo = temp_root / "repo"
        fake_bin = temp_root / "fake-bin"
        curl_home = temp_root / "curl-home"
        fixture_home = temp_root / "home"
        attack_python = temp_root / "attack-python"
        startup_marker = temp_root / "bash-env-ran"
        python_marker = temp_root / "python-startup-ran"
        path_python_marker = temp_root / "path-python-ran"
        repo.mkdir()
        fake_bin.mkdir()
        curl_home.mkdir()
        attack_python.mkdir()
        (curl_home / ".curlrc").write_text(
            "verbose\n"
            "trace-ascii = build/curlrc-trace.txt\n"
            "retry = 9\n"
            "url = https://curl-config-must-not-run.invalid/\n"
        )

        for relative in (
            ".gitignore",
            "racer.project.json",
            "scripts/build-racer-release.sh",
            "scripts/finalize-studio-publish.sh",
            "scripts/lookup-place-version.sh",
            "scripts/publish-place.sh",
            "scripts/racer-publish-state.py",
            "src/racer/shared/RacerConfig.lua",
            "src/shared/GeneratedBuildInfo.lua",
            "src/shared/GeneratedPlaceIds.lua",
        ):
            source = ROOT / relative
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        shutil.copy2(
            FIXTURE_MANIFEST, repo / "scripts/racer-release-toolchain.tsv"
        )
        fixture_rojo = fixture_home / ROJO_STORAGE_RELATIVE
        fixture_rojo.parent.mkdir(parents=True)
        shutil.copy2(FIXTURE_ROJO, fixture_rojo)

        state_helper = repo / "scripts/racer-publish-state.py"
        shutil.copy2(
            state_helper, repo / "scripts/racer-publish-state-real.py"
        )
        write_executable(state_helper, FAKE_STATE_HELPER)
        write_executable(fake_bin / "curl", FAKE_CURL)
        write_executable(
            fake_bin / "python3",
            "#!/bin/sh\n"
            f"/usr/bin/touch {path_python_marker}\n"
            "exec /usr/bin/python3 \"$@\"\n",
        )
        bash_env = temp_root / "host-bash-env"
        bash_env.write_text(f"/usr/bin/touch {startup_marker}\n")
        (attack_python / "sitecustomize.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(python_marker)!r}).write_text('ran')\n"
        )
        fake_curl_path = fake_bin / "curl"
        publisher = repo / "scripts/publish-place.sh"
        publisher_text = publisher.read_text()
        expected_curl = "/usr/bin/curl --disable --fail-with-body"
        if publisher_text.count(expected_curl) != 1:
            raise RuntimeError("publisher did not contain one absolute curl call")
        publisher.write_text(
            publisher_text.replace(
                expected_curl,
                f"{fake_curl_path} --disable --fail-with-body",
            )
        )
        real_git = shutil.which("git")
        if real_git is None:
            raise RuntimeError("git is required for the publish credential test")
        write_executable(
            fake_bin / "git",
            FAKE_GIT.replace("__REAL_GIT__", repr(real_git)),
        )

        run_checked(["git", "init", "--quiet"], repo)
        run_checked(["git", "config", "user.name", "Racer Release Test"], repo)
        run_checked(
            ["git", "config", "user.email", "racer-release-test@example.invalid"],
            repo,
        )
        run_checked(["git", "add", "."], repo)
        run_checked(["git", "commit", "--quiet", "-m", "test fixture"], repo)

        original_build_info = (repo / "src/shared/GeneratedBuildInfo.lua").read_bytes()
        original_place_ids = (repo / "src/shared/GeneratedPlaceIds.lua").read_bytes()

        environment = os.environ.copy()
        environment.update(
            {
                "CURL_HOME": str(curl_home),
                "HOME": str(fixture_home),
                "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                "BASH_ENV": str(bash_env),
                "PYTHONPATH": str(attack_python),
                "RACER_PUBLISH_API_KEY": sentinel,
                "ROBLOX_API_KEY": sentinel,
                "ROBLOX_RACER_PLACE_ID": "123",
                "ROBLOX_UNIVERSE_ID": "456",
            }
        )

        missing_environment = environment.copy()
        missing_environment.pop("ROBLOX_API_KEY")
        missing_result = run_publisher(repo, missing_environment)
        require_result(missing_result, "missing-key publish", 2, sentinel)
        if (repo / "build").exists():
            raise RuntimeError("missing-key publish reached a child build operation")

        crlf_secret = sentinel + "\r\nheader-injection"
        crlf_environment = environment.copy()
        crlf_environment["ROBLOX_API_KEY"] = crlf_secret
        crlf_result = run_publisher(repo, crlf_environment)
        require_result(crlf_result, "CR/LF-key publish", 2, sentinel, crlf_secret)
        if (repo / "build").exists():
            raise RuntimeError("CR/LF-key publish reached a child build operation")

        result = run_publisher(repo, environment)
        require_result(
            result,
            "normal publish",
            0,
            sentinel,
        )
        helper_log = repo / "build/test-helper-calls.log"
        normal_calls = helper_log.read_text().splitlines()
        if sum(line == "with-release-lock secret" for line in normal_calls) != 1:
            raise RuntimeError("normal publish did not acquire once with FD 9")
        if any(line == "with-release-lock no-secret" for line in normal_calls):
            raise RuntimeError("publisher-to-finalizer handoff reacquired the release lock")
        normal_assertions = [
            line for line in normal_calls if line.startswith("assert-release-lock ")
        ]
        if len(normal_assertions) != 2:
            raise RuntimeError("normal publisher/finalizer did not both assert FD 8")
        assertion_identity = [line.split(" parent=", 1)[1] for line in normal_assertions]
        if assertion_identity[0] != assertion_identity[1]:
            raise RuntimeError("publisher-to-finalizer exec changed PID or lock inode")
        if any(path.exists() for path in (startup_marker, python_marker, path_python_marker)):
            raise RuntimeError("host shell/Python/PATH startup code ran during publish")
        if (repo / "build/curlrc-trace.txt").exists():
            raise RuntimeError("curl loaded the hostile host configuration")

        hostile_shell_environment = environment.copy()
        hostile_shell_environment.pop("BASH_ENV")
        hostile_shell_environment.pop("PYTHONPATH")
        hostile_shell_result = run_hostile_shell_publisher(
            repo, hostile_shell_environment
        )
        require_result(
            hostile_shell_result,
            "bash -a -x publish",
            0,
            sentinel,
        )
        hostile_shell_calls = helper_log.read_text().splitlines()
        if sum(line == "with-release-lock secret" for line in hostile_shell_calls) != 2:
            raise RuntimeError("bash -a -x publish did not use one FD 9 acquisition")

        tag_commit = subprocess.check_output(
            ["git", "rev-parse", f"refs/tags/racer-place-v{TEST_VERSION}^{{commit}}"],
            cwd=repo,
            text=True,
        ).strip()
        head_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
        if tag_commit != head_commit:
            raise RuntimeError("fake publish tag did not resolve to the fixture commit")
        if (repo / "build/racer-publish-pending.json").exists():
            raise RuntimeError("successful publish did not clear pending state")

        if (repo / "src/shared/GeneratedBuildInfo.lua").read_bytes() != original_build_info:
            raise RuntimeError("publish test did not restore GeneratedBuildInfo.lua")
        if (repo / "src/shared/GeneratedPlaceIds.lua").read_bytes() != original_place_ids:
            raise RuntimeError("publish test did not restore GeneratedPlaceIds.lua")

        build_only_environment = environment.copy()
        build_only_environment["ROBLOX_API_KEY"] = crlf_secret
        build_only_result = run_publisher(
            repo, build_only_environment, "--build-only"
        )
        build_only_calls = helper_log.read_text().splitlines()
        if sum(line == "with-release-lock no-secret" for line in build_only_calls) != 1:
            raise RuntimeError("build-only did not acquire once without FD 9")
        require_result(
            build_only_result,
            "build-only publish",
            0,
            sentinel,
            crlf_secret,
        )
        if not (repo / "build/racer-publish-pending.json").is_file():
            raise RuntimeError("build-only publish did not retain Studio pending state")

        direct_finalize_environment = environment.copy()
        direct_finalize_environment["ROBLOX_API_KEY"] = sentinel
        direct_finalize_environment["RACER_PUBLISH_API_KEY"] = sentinel
        direct_finalize_result = run_finalizer(
            repo, direct_finalize_environment, STUDIO_TEST_VERSION
        )
        final_calls = helper_log.read_text().splitlines()
        if sum(line == "with-release-lock no-secret" for line in final_calls) != 2:
            raise RuntimeError("direct finalizer did not acquire its own release lock")
        require_result(
            direct_finalize_result,
            "direct Studio finalizer",
            0,
            sentinel,
            "ROBLOX_API_KEY",
            "RACER_PUBLISH_API_KEY",
        )
        if (repo / "build/racer-publish-pending.json").exists():
            raise RuntimeError("direct Studio finalizer retained pending state")
        pending_ref = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", "refs/racer-publish/pending"],
            cwd=repo,
        )
        if pending_ref.returncode == 0:
            raise RuntimeError("direct Studio finalizer retained its recovery ref")
        if pending_ref.returncode != 1:
            raise RuntimeError("direct Studio finalizer recovery ref check failed")
        studio_tag_commit = subprocess.check_output(
            [
                "git",
                "rev-parse",
                f"refs/tags/racer-place-v{STUDIO_TEST_VERSION}^{{commit}}",
            ],
            cwd=repo,
            text=True,
        ).strip()
        if studio_tag_commit != head_commit:
            raise RuntimeError("direct Studio finalizer tagged the wrong commit")

        sentinel_bytes = sentinel.encode()
        for path in repo.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if sentinel_bytes in path.read_bytes():
                raise RuntimeError("publish command persisted the API key in the fixture")

    print("Publish API key transport test passed")


if __name__ == "__main__":
    main()
