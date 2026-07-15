#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
COMPOSE_FILE = ROOT / "docker-compose.yml"
ENTRYPOINT = ROOT / "scripts/docker-entrypoint.sh"
README = ROOT / "README.md"

CONTAINER_ENTRYPOINT = "/usr/local/bin/racer-docker-entrypoint"
EXPECTED_AFTMAN_ARCHIVE_SHA256 = (
    "194fe81e24ae7cc1f3141fd1d42db6cb60f03d42735d12ae865fe2db11ea6f0e"
)
EXPECTED_AFTMAN_BINARY_SHA256 = (
    "3b13b10838fb7f7aafae16a9a01085439c75619bb9b78a1b5b787eab81ddf6e4"
)
EXPECTED_COMMAND_ARGUMENTS = ["bash", "-lc", "argument with spaces", ""]
CREDENTIAL_NAMES = ("ROBLOX_API_KEY", "RACER_PUBLISH_API_KEY")
API_SENTINEL = "bootstrap-api-" + hashlib.sha256(
    b"racer-docker-bootstrap-api-key"
).hexdigest()
PRIVATE_SENTINEL = "bootstrap-private-" + hashlib.sha256(
    b"racer-docker-bootstrap-private-key"
).hexdigest()

FAKE_AFTMAN = r'''#!__PYTHON__
import hashlib
import json
import os
from pathlib import Path
import sys


secrets = (
    "bootstrap-api-" + hashlib.sha256(b"racer-docker-bootstrap-api-key").hexdigest(),
    "bootstrap-private-"
    + hashlib.sha256(b"racer-docker-bootstrap-private-key").hexdigest(),
)
if "ROBLOX_API_KEY" in os.environ or "RACER_PUBLISH_API_KEY" in os.environ:
    print("bootstrap received a credential variable", file=sys.stderr)
    raise SystemExit(80)
if any(secret in value for value in os.environ.values() for secret in secrets):
    print("bootstrap received a credential value", file=sys.stderr)
    raise SystemExit(80)

event_path = Path(os.environ["RACER_BOOTSTRAP_EVENT"])
arguments = sys.argv[1:]
if any(secret in argument for argument in arguments for secret in secrets):
    print("bootstrap received a credential argument", file=sys.stderr)
    raise SystemExit(80)
if arguments != ["install", "--no-trust-check"]:
    print(f"unexpected aftman arguments: {arguments!r}", file=sys.stderr)
    raise SystemExit(81)
if event_path.exists():
    print("aftman was not the first bootstrap command", file=sys.stderr)
    raise SystemExit(82)

event_path.write_text(json.dumps(["aftman", *arguments]))
raise SystemExit(int(os.environ.get("FAKE_AFTMAN_EXIT", "0")))
'''

FAKE_COMMAND = r'''#!__PYTHON__
import hashlib
import json
import os
from pathlib import Path
import sys


api_secret = "bootstrap-api-" + hashlib.sha256(
    b"racer-docker-bootstrap-api-key"
).hexdigest()
private_secret = "bootstrap-private-" + hashlib.sha256(
    b"racer-docker-bootstrap-private-key"
).hexdigest()
if os.environ.get("ROBLOX_API_KEY") != api_secret:
    print("requested command did not retain the explicit API key", file=sys.stderr)
    raise SystemExit(84)
if os.environ.get("RACER_PUBLISH_API_KEY") != private_secret:
    print("requested command did not retain the explicit private key", file=sys.stderr)
    raise SystemExit(84)

event_path = Path(os.environ["RACER_BOOTSTRAP_EVENT"])
result_path = Path(os.environ["RACER_BOOTSTRAP_RESULT"])
expected_event = ["aftman", "install", "--no-trust-check"]
if not event_path.is_file() or json.loads(event_path.read_text()) != expected_event:
    print(
        "container command ran before the pinned tools were installed",
        file=sys.stderr,
    )
    raise SystemExit(83)

result_path.write_text(
    json.dumps(
        {
            "arguments": sys.argv[1:],
            "credentialsPreserved": True,
            "pid": os.getpid(),
        },
        sort_keys=True,
    )
)
'''

POISONED_AFTMAN = r'''#!__PYTHON__
import os
from pathlib import Path


Path(os.environ["RACER_POISONED_AFTMAN_MARKER"]).write_text("invoked\n")
raise SystemExit(85)
'''


def fail(message: str) -> None:
    raise RuntimeError(message)


def write_executable(path: Path, source: str) -> None:
    path.write_text(source.replace("__PYTHON__", sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def assert_no_credentials(label: str, content: str) -> None:
    forbidden = (*CREDENTIAL_NAMES, API_SENTINEL, PRIVATE_SENTINEL)
    if any(value in content for value in forbidden):
        fail(f"{label} exposed a bootstrap credential")


def check_static_contract() -> None:
    dockerfile = DOCKERFILE.read_text()
    compose = COMPOSE_FILE.read_text()
    entrypoint = ENTRYPOINT.read_text()
    readme = README.read_text()

    copy_instruction = (
        "COPY --chmod=755 scripts/docker-entrypoint.sh " + CONTAINER_ENTRYPOINT
    )
    entrypoint_instruction = f'ENTRYPOINT ["{CONTAINER_ENTRYPOINT}"]'
    if copy_instruction not in dockerfile:
        fail("Dockerfile must copy the executable bootstrap entrypoint into the image")
    if entrypoint_instruction not in dockerfile:
        fail("Dockerfile must run the bootstrap through ENTRYPOINT for every command")
    if "aftman-0.3.0-linux-x86_64.zip" not in dockerfile:
        fail("Dockerfile must retain the pinned x86_64 Aftman 0.3.0 archive")
    if "ARG TARGETARCH\n" not in dockerfile or "ARG TARGETARCH=" in dockerfile:
        fail("Dockerfile must require BuildKit to provide the selected target architecture")
    if 'test "${TARGETARCH}" = "amd64"' not in dockerfile:
        fail("Dockerfile must reject every target architecture except amd64")
    if 'test "$(/usr/bin/dpkg --print-architecture)" = "amd64"' not in dockerfile:
        fail("Dockerfile must verify the base image package architecture")
    if dockerfile.count(EXPECTED_AFTMAN_ARCHIVE_SHA256) != 1:
        fail("Dockerfile must pin the official Aftman 0.3.0 archive SHA-256 once")
    if dockerfile.count(EXPECTED_AFTMAN_BINARY_SHA256) != 1:
        fail("Dockerfile must pin the official Aftman 0.3.0 binary SHA-256 once")
    if "ARG AFTMAN_" in dockerfile:
        fail("Dockerfile must not allow Aftman hashes to be overridden by build args")
    curl_command = (
        "/usr/bin/curl --disable --fail --silent --show-error --location"
    )
    if curl_command not in dockerfile:
        fail("Dockerfile must download Aftman with absolute config-free curl")
    archive_check = (
        "/usr/bin/printf '%s  %s\\n' \"${archive_sha256}\" \"${archive_path}\""
    )
    extracted_check = (
        "/usr/bin/printf '%s  %s\\n' \"${binary_sha256}\" \"${extracted_path}\""
    )
    installed_check = (
        "/usr/bin/printf '%s  %s\\n' \"${binary_sha256}\" /usr/local/bin/aftman"
    )
    for token in (archive_check, extracted_check, installed_check):
        if token not in dockerfile:
            fail("Dockerfile is missing an authenticated Aftman checksum stage")
    download_index = dockerfile.index(curl_command)
    archive_check_index = dockerfile.index(archive_check)
    unzip_index = dockerfile.index('/usr/bin/unzip -j "${archive_path}"')
    extracted_check_index = dockerfile.index(extracted_check)
    install_index = dockerfile.index(
        '/usr/bin/install -m 0755 "${extracted_path}" /usr/local/bin/aftman'
    )
    installed_check_index = dockerfile.index(installed_check)
    if not (
        download_index
        < archive_check_index
        < unzip_index
        < extracted_check_index
        < install_index
        < installed_check_index
    ):
        fail(
            "Dockerfile must verify archive, extracted binary, and installed Aftman "
            "in that order"
        )
    if not entrypoint.startswith("#!/bin/bash\n"):
        fail("entrypoint must start through the image's trusted absolute Bash")

    try:
        roblox_service = compose.split("  roblox:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    except IndexError as error:
        raise RuntimeError(
            "docker-compose.yml must define the roblox service"
        ) from error
    if "    platform: linux/amd64\n" not in roblox_service:
        fail("roblox service must force linux/amd64 for the x86_64-only Aftman binary")
    if "\n    entrypoint:" in roblox_service:
        fail("Compose must not bypass the image bootstrap entrypoint")
    if "ROBLOX_API_KEY" in roblox_service:
        fail("Compose must not inject the API key into ordinary container commands")
    if (
        "docker compose run --rm -e ROBLOX_API_KEY roblox "
        "scripts/publish-place.sh"
    ) not in readme:
        fail("README must document explicit API-key injection for one-shot publishing")

    statements = [
        line.strip()
        for line in entrypoint.splitlines()
        if line.strip() and not line.startswith("#!")
    ]
    if statements != [
        "set +x",
        "set +a",
        "set -euo pipefail",
        "/usr/bin/env -u ROBLOX_API_KEY -u RACER_PUBLISH_API_KEY "
        "/usr/local/bin/aftman install --no-trust-check",
        'exec "$@"',
    ]:
        fail(
            "entrypoint must privately install pinned tools through absolute paths "
            "before execing the requested command"
        )
    if not ENTRYPOINT.stat().st_mode & stat.S_IXUSR:
        fail("repository entrypoint must be executable")


def run_entrypoint(
    entrypoint: Path, environment: dict[str, str], command: Path
) -> tuple[subprocess.Popen[str], str, str]:
    process = subprocess.Popen(
        [
            "/bin/bash",
            "-a",
            "-x",
            str(entrypoint),
            str(command),
            *EXPECTED_COMMAND_ARGUMENTS,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    return process, stdout, stderr


def check_runtime_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="racer-docker-bootstrap-test-") as temp:
        temp_root = Path(temp)
        fake_bin = temp_root / "bin"
        fake_bin.mkdir()
        trusted_aftman = temp_root / "trusted-aftman"
        poisoned_aftman = fake_bin / "aftman"
        fake_command = fake_bin / "container-command"
        runtime_entrypoint = temp_root / "docker-entrypoint-under-test.sh"
        event_path = temp_root / "event.json"
        result_path = temp_root / "result.json"
        poison_marker = temp_root / "poisoned-aftman-ran"
        write_executable(trusted_aftman, FAKE_AFTMAN)
        write_executable(poisoned_aftman, POISONED_AFTMAN)
        write_executable(fake_command, FAKE_COMMAND)

        entrypoint_source = ENTRYPOINT.read_text()
        if entrypoint_source.count("/usr/local/bin/aftman") != 1:
            fail("entrypoint must contain exactly one trusted Aftman path")
        write_executable(
            runtime_entrypoint,
            entrypoint_source.replace("/usr/local/bin/aftman", str(trusted_aftman)),
        )

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
                "RACER_BOOTSTRAP_EVENT": str(event_path),
                "RACER_BOOTSTRAP_RESULT": str(result_path),
                "RACER_POISONED_AFTMAN_MARKER": str(poison_marker),
                "RACER_PUBLISH_API_KEY": PRIVATE_SENTINEL,
                "ROBLOX_API_KEY": API_SENTINEL,
            }
        )

        process, stdout, stderr = run_entrypoint(
            runtime_entrypoint, environment, fake_command
        )
        assert_no_credentials("successful entrypoint output", stdout + stderr)
        if process.returncode != 0:
            fail(
                "entrypoint runtime check failed "
                f"with {process.returncode}: {stdout}{stderr}"
            )
        result = json.loads(result_path.read_text())
        if result["arguments"] != EXPECTED_COMMAND_ARGUMENTS:
            fail("entrypoint did not preserve the requested command arguments")
        if result["credentialsPreserved"] is not True:
            fail("entrypoint did not preserve credentials for the requested command")
        if result["pid"] != process.pid:
            fail("entrypoint must exec the requested command instead of spawning it")
        if poison_marker.exists():
            fail("entrypoint resolved Aftman through mutable PATH")
        for generated in (event_path, result_path):
            assert_no_credentials(
                f"generated bootstrap file {generated.name}", generated.read_text()
            )

        event_path.unlink()
        result_path.unlink()
        failing_environment = environment | {"FAKE_AFTMAN_EXIT": "37"}
        process, stdout, stderr = run_entrypoint(
            runtime_entrypoint, failing_environment, fake_command
        )
        assert_no_credentials("failing entrypoint output", stdout + stderr)
        if process.returncode != 37:
            fail(
                "entrypoint did not propagate the Aftman failure "
                f"(returned {process.returncode}): {stdout}{stderr}"
            )
        if result_path.exists():
            fail("entrypoint ran the requested command after Aftman failed")
        if poison_marker.exists():
            fail("failing entrypoint resolved Aftman through mutable PATH")
        assert_no_credentials("failing bootstrap event", event_path.read_text())


def main() -> None:
    check_static_contract()
    check_runtime_contract()
    print("Docker bootstrap contract test passed")


if __name__ == "__main__":
    main()
