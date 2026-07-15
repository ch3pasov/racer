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

FAKE_ROJO = r'''#!/usr/bin/env python3
import hashlib
import os
from pathlib import Path
import sys
from xml.sax.saxutils import escape


expected = "sentinel-" + hashlib.sha256(
    b"racer-publish-api-key-transport-test"
).hexdigest()
if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
    print("fake rojo received a credential variable", file=sys.stderr)
    raise SystemExit(89)
if any(expected in value for value in os.environ.values()):
    print("fake rojo received the credential value", file=sys.stderr)
    raise SystemExit(89)

if sys.argv[1:] == ["--version"]:
    print("Rojo 7.5.1")
    raise SystemExit(0)

if len(sys.argv) < 4 or sys.argv[1] != "build" or "--output" not in sys.argv:
    print("fake rojo received an unexpected command", file=sys.stderr)
    raise SystemExit(90)

output_index = sys.argv.index("--output") + 1
if output_index >= len(sys.argv):
    print("fake rojo did not receive an output path", file=sys.stderr)
    raise SystemExit(90)

output = Path(sys.argv[output_index])
output.parent.mkdir(parents=True, exist_ok=True)
build_info = Path("src/shared/GeneratedBuildInfo.lua").read_text()
place_ids = Path("src/shared/GeneratedPlaceIds.lua").read_text()
output.write_text(
    '<roblox version="4">'
    '<Item class="ModuleScript"><Properties>'
    '<string name="Name">GeneratedBuildInfo</string>'
    f'<ProtectedString name="Source">{escape(build_info)}</ProtectedString>'
    '</Properties></Item>'
    '<Item class="ModuleScript"><Properties>'
    '<string name="Name">GeneratedPlaceIds</string>'
    f'<ProtectedString name="Source">{escape(place_ids)}</ProtectedString>'
    '</Properties></Item>'
    '</roblox>\n'
)
'''

FAKE_CURL = r'''#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
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

curl_home = os.environ.get("CURL_HOME", "")
if not curl_home or not (Path(curl_home) / ".curlrc").is_file():
    fail("test curl configuration was not present")

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
import os
from pathlib import Path
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
        ["bash", "-a", "-x", str(repo / "scripts/publish-place.sh"), *arguments],
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
        [
            "bash",
            "-a",
            "-x",
            str(repo / "scripts/finalize-studio-publish.sh"),
            version,
        ],
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
            f"{label} returned {result.returncode}, expected {expected_code}"
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
        repo.mkdir()
        fake_bin.mkdir()
        curl_home.mkdir()
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
            "src/shared/GeneratedBuildInfo.lua",
            "src/shared/GeneratedPlaceIds.lua",
        ):
            source = ROOT / relative
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        state_helper = repo / "scripts/racer-publish-state.py"
        shutil.copy2(
            state_helper, repo / "scripts/racer-publish-state-real.py"
        )
        write_executable(state_helper, FAKE_STATE_HELPER)
        write_executable(fake_bin / "rojo", FAKE_ROJO)
        write_executable(fake_bin / "curl", FAKE_CURL)
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
                "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
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
