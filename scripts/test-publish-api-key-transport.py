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

FAKE_ROJO = r'''#!/usr/bin/env python3
from pathlib import Path
import sys


if len(sys.argv) < 4 or sys.argv[1] != "build" or "--output" not in sys.argv:
    print("fake rojo received an unexpected command", file=sys.stderr)
    raise SystemExit(90)

output_index = sys.argv.index("--output") + 1
if output_index >= len(sys.argv):
    print("fake rojo did not receive an output path", file=sys.stderr)
    raise SystemExit(90)

output = Path(sys.argv[output_index])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text('<roblox version="4"></roblox>\n')
'''

FAKE_CURL = r'''#!/usr/bin/env python3
import os
from pathlib import Path
import sys


def fail(message: str) -> None:
    print(f"fake curl validation failed: {message}", file=sys.stderr)
    raise SystemExit(91)


expected = os.environ.get("EXPECTED_TEST_API_KEY", "")
if not expected:
    fail("missing test expectation")
if any(expected in argument for argument in sys.argv):
    fail("API key reached curl argv")
if "ROBLOX_API_KEY" in os.environ:
    fail("API key remained in the curl environment")

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


def main() -> None:
    sentinel = "sentinel-" + hashlib.sha256(
        b"racer-publish-api-key-transport-test"
    ).hexdigest()

    with tempfile.TemporaryDirectory(prefix="racer-publish-secret-test-") as temp:
        temp_root = Path(temp)
        repo = temp_root / "repo"
        fake_bin = temp_root / "fake-bin"
        repo.mkdir()
        fake_bin.mkdir()

        for relative in (
            ".gitignore",
            "racer.project.json",
            "scripts/lookup-place-version.sh",
            "scripts/publish-place.sh",
            "src/shared/GeneratedBuildInfo.lua",
            "src/shared/GeneratedPlaceIds.lua",
        ):
            source = ROOT / relative
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        write_executable(fake_bin / "rojo", FAKE_ROJO)
        write_executable(fake_bin / "curl", FAKE_CURL)

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
                "EXPECTED_TEST_API_KEY": sentinel,
                "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                "ROBLOX_API_KEY": sentinel,
                "ROBLOX_RACER_PLACE_ID": "123",
                "ROBLOX_UNIVERSE_ID": "456",
            }
        )
        result = subprocess.run(
            [str(repo / "scripts/publish-place.sh")],
            cwd=repo,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        combined_output = result.stdout + result.stderr
        if sentinel in combined_output:
            raise RuntimeError("publish command exposed the API key in its output")
        if result.returncode != 0:
            raise RuntimeError(
                f"publish command failed secret-transport validation with exit {result.returncode}"
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

        if (repo / "src/shared/GeneratedBuildInfo.lua").read_bytes() != original_build_info:
            raise RuntimeError("publish test did not restore GeneratedBuildInfo.lua")
        if (repo / "src/shared/GeneratedPlaceIds.lua").read_bytes() != original_place_ids:
            raise RuntimeError("publish test did not restore GeneratedPlaceIds.lua")

        sentinel_bytes = sentinel.encode()
        for path in repo.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            if sentinel_bytes in path.read_bytes():
                raise RuntimeError("publish command persisted the API key in the fixture")

    print("Publish API key transport test passed")


if __name__ == "__main__":
    main()
