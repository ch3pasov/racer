#!/usr/bin/env python3
from __future__ import annotations

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

CONTAINER_ENTRYPOINT = "/usr/local/bin/racer-docker-entrypoint"
EXPECTED_COMMAND_ARGUMENTS = ["bash", "-lc", "argument with spaces", ""]

FAKE_AFTMAN = r'''#!__PYTHON__
import json
import os
from pathlib import Path
import sys


event_path = Path(os.environ["RACER_BOOTSTRAP_EVENT"])
arguments = sys.argv[1:]
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
import json
import os
from pathlib import Path
import sys


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
    json.dumps({"arguments": sys.argv[1:], "pid": os.getpid()}, sort_keys=True)
)
'''


def fail(message: str) -> None:
    raise RuntimeError(message)


def write_executable(path: Path, source: str) -> None:
    path.write_text(source.replace("__PYTHON__", sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def check_static_contract() -> None:
    dockerfile = DOCKERFILE.read_text()
    compose = COMPOSE_FILE.read_text()
    entrypoint = ENTRYPOINT.read_text()

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

    statements = [
        line.strip()
        for line in entrypoint.splitlines()
        if line.strip() and not line.startswith("#!")
    ]
    if statements != [
        "set -euo pipefail",
        "aftman install --no-trust-check",
        'exec "$@"',
    ]:
        fail(
            "entrypoint must install pinned tools before execing the requested command"
        )
    if not ENTRYPOINT.stat().st_mode & stat.S_IXUSR:
        fail("repository entrypoint must be executable")


def run_entrypoint(
    environment: dict[str, str], command: Path
) -> tuple[subprocess.Popen[str], str, str]:
    process = subprocess.Popen(
        [str(ENTRYPOINT), str(command), *EXPECTED_COMMAND_ARGUMENTS],
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
        fake_aftman = fake_bin / "aftman"
        fake_command = fake_bin / "container-command"
        event_path = temp_root / "event.json"
        result_path = temp_root / "result.json"
        write_executable(fake_aftman, FAKE_AFTMAN)
        write_executable(fake_command, FAKE_COMMAND)

        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{fake_bin}:{environment.get('PATH', '')}",
                "RACER_BOOTSTRAP_EVENT": str(event_path),
                "RACER_BOOTSTRAP_RESULT": str(result_path),
            }
        )

        process, stdout, stderr = run_entrypoint(environment, fake_command)
        if process.returncode != 0:
            fail(
                "entrypoint runtime check failed "
                f"with {process.returncode}: {stdout}{stderr}"
            )
        result = json.loads(result_path.read_text())
        if result["arguments"] != EXPECTED_COMMAND_ARGUMENTS:
            fail("entrypoint did not preserve the requested command arguments")
        if result["pid"] != process.pid:
            fail("entrypoint must exec the requested command instead of spawning it")

        event_path.unlink()
        result_path.unlink()
        failing_environment = environment | {"FAKE_AFTMAN_EXIT": "37"}
        process, stdout, stderr = run_entrypoint(failing_environment, fake_command)
        if process.returncode != 37:
            fail(
                "entrypoint did not propagate the Aftman failure "
                f"(returned {process.returncode}): {stdout}{stderr}"
            )
        if result_path.exists():
            fail("entrypoint ran the requested command after Aftman failed")


def main() -> None:
    check_static_contract()
    check_runtime_contract()
    print("Docker bootstrap contract test passed")


if __name__ == "__main__":
    main()
