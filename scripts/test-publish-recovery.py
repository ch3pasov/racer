#!/usr/bin/env python3
"""Deterministic integration coverage for pending Racer publish recovery."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import stat
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RACER_PLACE_ID = "123630607312596"
LOBBY_PLACE_ID = "93743736131610"
UNIVERSE_ID = "701234567890123"
PENDING_REF = "refs/racer-publish/pending"
API_SENTINEL = "pending-state-secret-" + hashlib.sha256(
    b"racer-pending-publish-recovery"
).hexdigest()
TOOLCHAIN_FIXTURE = ROOT / "scripts/test-fixtures/release-toolchain"
FIXTURE_MANIFEST = TOOLCHAIN_FIXTURE / "manifest.tsv"
FIXTURE_ROJO = TOOLCHAIN_FIXTURE / "fake-rojo"
ROJO_STORAGE_RELATIVE = Path(
    ".aftman/tool-storage/rojo-rbx/rojo/7.5.1/rojo"
)


FAKE_CURL = r'''#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def fail(message: str) -> None:
    print(f"fake curl validation failed: {message}", file=sys.stderr)
    raise SystemExit(91)


secret = os.environ["EXPECTED_TEST_API_KEY"]
if any(secret in argument for argument in sys.argv):
    fail("API key reached argv")
if "ROBLOX_API_KEY" in os.environ:
    fail("API key reached curl environment")

pending_path = Path("build/racer-publish-pending.json")
if not pending_path.is_file():
    fail("POST started before pending state existed")
raw_pending = pending_path.read_bytes()
if secret.encode() in raw_pending:
    fail("API key reached pending state")
pending = json.loads(raw_pending)
if pending["mode"] != "open-cloud" or pending["state"] != "prepared":
    fail("POST did not observe PREPARED open-cloud state")
if pending["placeVersion"] is not None:
    fail("PlaceVersion was recorded before the response")
try:
    recovery_commit = subprocess.check_output(
        ["git", "rev-parse", "refs/racer-publish/pending^{commit}"],
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
except subprocess.CalledProcessError:
    fail("POST did not observe the pending recovery ref")
if recovery_commit != pending["gitCommit"]:
    fail("pending recovery ref did not match the manifest commit")

data_arguments = [
    sys.argv[index + 1]
    for index, argument in enumerate(sys.argv[:-1])
    if argument == "--data-binary"
]
if len(data_arguments) != 1 or not data_arguments[0].startswith("@"):
    fail("curl did not receive exactly one artifact file")
private_artifact = Path(data_arguments[0][1:])
installed_artifact = Path(pending["artifact"]["path"])
expected_hash = pending["artifact"]["sha256"]
for artifact in (private_artifact, installed_artifact):
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected_hash:
        fail("POST artifact did not match pending state")

with Path(os.environ["FAKE_CURL_LOG"]).open("a") as stream:
    stream.write("call\n")

mode = os.environ["FAKE_CURL_MODE"]
if mode == "network-fail":
    print("simulated connection loss", file=sys.stderr)
    raise SystemExit(7)
if mode == "malformed":
    print("not json")
elif mode == "boolean":
    print('{"versionNumber": true}')
elif mode == "zero":
    print('{"versionNumber": 0}')
elif mode == "missing":
    print('{}')
elif mode == "success":
    print(json.dumps({"versionNumber": int(os.environ["FAKE_CURL_VERSION"])}))
else:
    fail(f"unknown mode {mode}")
'''


def write_executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def git(repo: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip() if capture else ""


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text().splitlines())


class Fixture:
    def __init__(
        self,
        parent: Path,
        name: str,
        *,
        broken_lookup: bool = False,
        mutate_after_state_create: bool = False,
    ):
        self.root = parent / name
        self.repo = self.root / "repo"
        self.fake_bin = self.root / "fake-bin"
        self.build_log = self.root / "build.log"
        self.curl_log = self.root / "curl.log"
        self.fixture_home = self.root / "home"
        self.repo.mkdir(parents=True)
        self.fake_bin.mkdir()

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
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        shutil.copy2(
            FIXTURE_MANIFEST, self.repo / "scripts/racer-release-toolchain.tsv"
        )
        fixture_rojo = self.fixture_home / ROJO_STORAGE_RELATIVE
        fixture_rojo.parent.mkdir(parents=True)
        shutil.copy2(FIXTURE_ROJO, fixture_rojo)

        build_helper = self.repo / "scripts/build-racer-release.sh"
        real_build_helper = self.repo / "scripts/build-racer-release-real.sh"
        shutil.copy2(build_helper, real_build_helper)
        write_executable(
            build_helper,
            f'''#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)"
/usr/bin/printf 'call\\n' >> {shlex.quote(str(self.build_log))}
exec "${{SCRIPT_DIR}}/build-racer-release-real.sh" "$@"
''',
        )
        if broken_lookup:
            write_executable(
                self.repo / "scripts/lookup-place-version.sh",
                "#!/usr/bin/env bash\necho 'simulated lookup failure' >&2\nexit 77\n",
            )
        if mutate_after_state_create:
            real_helper = self.repo / "scripts/racer-publish-state-real.py"
            shutil.copy2(self.repo / "scripts/racer-publish-state.py", real_helper)
            write_executable(
                self.repo / "scripts/racer-publish-state.py",
                r'''#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "create" ]]; then
  output="$("${SCRIPT_DIR}/racer-publish-state-real.py" "$@")"
  printf 'changed after manifest creation\n' >> build/racer.rbxlx
  printf '%s\n' "${output}"
else
  exec "${SCRIPT_DIR}/racer-publish-state-real.py" "$@"
fi
''',
            )

        write_executable(self.fake_bin / "curl", FAKE_CURL)

        git(self.repo, "init", "--quiet")
        git(self.repo, "config", "user.name", "Racer Release Test")
        git(
            self.repo,
            "config",
            "user.email",
            "racer-release-test@example.invalid",
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "--quiet", "-m", "pending publish fixture")
        self.release_commit = git(self.repo, "rev-parse", "HEAD", capture=True)

    @property
    def pending(self) -> Path:
        return self.repo / "build/racer-publish-pending.json"

    @property
    def artifact(self) -> Path:
        return self.repo / "build/racer.rbxlx"

    @property
    def state_helper(self) -> Path:
        return self.repo / "scripts/racer-publish-state.py"

    def environment(self, mode: str = "success", version: str = "700001") -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(
            {
                "EXPECTED_TEST_API_KEY": API_SENTINEL,
                "FAKE_CURL_LOG": str(self.curl_log),
                "FAKE_CURL_MODE": mode,
                "FAKE_CURL_VERSION": version,
                "HOME": str(self.fixture_home),
                "PATH": f"{self.fake_bin}{os.pathsep}{environment['PATH']}",
                "ROBLOX_API_KEY": API_SENTINEL,
                "ROBLOX_LOBBY_PLACE_ID": LOBBY_PLACE_ID,
                "ROBLOX_RACER_PLACE_ID": RACER_PLACE_ID,
                "ROBLOX_UNIVERSE_ID": UNIVERSE_ID,
            }
        )
        return environment

    def run(
        self,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.repo,
            env=environment or self.environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def publish(self, mode: str = "success", version: str = "700001") -> subprocess.CompletedProcess[str]:
        return self.run(
            [str(self.repo / "scripts/publish-place.sh")],
            environment=self.environment(mode, version),
        )

    def build_only(self) -> subprocess.CompletedProcess[str]:
        environment = self.environment("success")
        environment.pop("ROBLOX_API_KEY")
        environment.pop("ROBLOX_UNIVERSE_ID")
        return self.run(
            [str(self.repo / "scripts/publish-place.sh"), "--build-only"],
            environment=environment,
        )

    def finalize(
        self, version: str, *, racer_place_id: str = RACER_PLACE_ID
    ) -> subprocess.CompletedProcess[str]:
        environment = self.environment("success", version)
        environment.pop("ROBLOX_API_KEY")
        environment["ROBLOX_RACER_PLACE_ID"] = racer_place_id
        return self.run(
            [str(self.repo / "scripts/finalize-studio-publish.sh"), version],
            environment=environment,
        )

    def load_state(self) -> dict[str, object]:
        return json.loads(self.pending.read_text())

    def tag_commit(self, version: str) -> str:
        return git(
            self.repo,
            "rev-parse",
            f"refs/tags/racer-place-v{version}^{{commit}}",
            capture=True,
        )

    def tag_exists(self, version: str) -> bool:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.repo}",
                "-C",
                str(self.repo),
                "rev-parse",
                "--verify",
                f"refs/tags/racer-place-v{version}^{{commit}}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0

    def pending_ref_commit(self) -> str:
        return git(
            self.repo,
            "rev-parse",
            f"{PENDING_REF}^{{commit}}",
            capture=True,
        )

    def pending_ref_exists(self) -> bool:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={self.repo}",
                "-C",
                str(self.repo),
                "show-ref",
                "--verify",
                "--quiet",
                PENDING_REF,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0


def require_success(result: subprocess.CompletedProcess[str], context: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(
            f"{context} failed with {result.returncode}:\n{result.stdout}{result.stderr}"
        )


def require_failure(result: subprocess.CompletedProcess[str], context: str) -> None:
    if result.returncode == 0:
        raise RuntimeError(f"{context} unexpectedly succeeded")


def bless_current_artifact_in_manifest(fixture: Fixture) -> None:
    payload = fixture.load_state()
    artifact = payload["artifact"]
    if not isinstance(artifact, dict):
        raise RuntimeError("test pending artifact was not an object")
    artifact_bytes = fixture.artifact.read_bytes()
    artifact["sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
    artifact["sizeBytes"] = len(artifact_bytes)
    canonical = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()
    fixture.pending.write_bytes(canonical)
    fixture.pending.chmod(0o600)
    validation = fixture.run([str(fixture.state_helper), "validate-artifact"])
    require_success(validation, "canonical manifest validation after artifact tamper")


def test_success(parent: Path) -> None:
    fixture = Fixture(parent, "success")
    version = "700101"
    result = fixture.publish("success", version)
    require_success(result, "successful Open Cloud publish")
    if fixture.pending.exists():
        raise RuntimeError("successful publish retained pending state")
    if fixture.pending_ref_exists():
        raise RuntimeError("successful publish retained its recovery ref")
    if fixture.tag_commit(version) != fixture.release_commit:
        raise RuntimeError("successful publish tagged the wrong commit")
    if line_count(fixture.curl_log) != 1:
        raise RuntimeError("successful publish did not POST exactly once")
    if API_SENTINEL in result.stdout + result.stderr:
        raise RuntimeError("successful publish exposed the API key")


def test_failed_request_and_retry(parent: Path) -> None:
    fixture = Fixture(parent, "failed-request")
    result = fixture.publish("network-fail", "700102")
    require_failure(result, "simulated connection loss")
    state = fixture.load_state()
    if state["state"] != "prepared" or state["placeVersion"] is not None:
        raise RuntimeError("connection loss did not retain PREPARED state")
    if API_SENTINEL.encode() in fixture.pending.read_bytes():
        raise RuntimeError("failed publish persisted the API key")
    if fixture.pending_ref_commit() != fixture.release_commit:
        raise RuntimeError("failed publish did not retain its recovery ref")
    artifact_hash = hashlib.sha256(fixture.artifact.read_bytes()).hexdigest()
    curl_calls = line_count(fixture.curl_log)
    build_calls = line_count(fixture.build_log)

    retry = fixture.publish("success", "700102")
    require_failure(retry, "unsafe retry while pending")
    if line_count(fixture.curl_log) != curl_calls or line_count(fixture.build_log) != build_calls:
        raise RuntimeError("pending retry reached the release builder or curl")
    if hashlib.sha256(fixture.artifact.read_bytes()).hexdigest() != artifact_hash:
        raise RuntimeError("pending retry overwrote the release artifact")

    recovery = fixture.finalize("700102")
    require_success(recovery, "manual recovery after connection loss")
    if (
        fixture.pending.exists()
        or fixture.pending_ref_exists()
        or fixture.tag_commit("700102") != fixture.release_commit
    ):
        raise RuntimeError("manual recovery did not tag and clear")


def test_invalid_responses(parent: Path) -> None:
    for index, mode in enumerate(("malformed", "boolean", "zero", "missing"), 1):
        fixture = Fixture(parent, f"invalid-response-{mode}")
        result = fixture.publish(mode, str(700110 + index))
        require_failure(result, f"invalid response {mode}")
        state = fixture.load_state()
        if state["state"] != "prepared" or state["placeVersion"] is not None:
            raise RuntimeError(f"invalid response {mode} did not retain PREPARED state")
        if fixture.pending_ref_commit() != fixture.release_commit:
            raise RuntimeError(f"invalid response {mode} lost its recovery ref")
        if line_count(fixture.curl_log) != 1:
            raise RuntimeError(f"invalid response {mode} did not issue exactly one POST")


def test_build_only(parent: Path) -> None:
    fixture = Fixture(parent, "build-only")
    result = fixture.build_only()
    require_success(result, "Studio build-only preparation")
    state = fixture.load_state()
    if state["mode"] != "studio" or state["universeId"] is not None:
        raise RuntimeError("build-only did not create Studio PREPARED state")
    if fixture.pending_ref_commit() != fixture.release_commit:
        raise RuntimeError("build-only did not retain its recovery ref")
    if line_count(fixture.curl_log) != 0:
        raise RuntimeError("build-only called curl")
    artifact_hash = hashlib.sha256(fixture.artifact.read_bytes()).hexdigest()
    build_calls = line_count(fixture.build_log)
    retry = fixture.build_only()
    require_failure(retry, "second build-only while pending")
    if line_count(fixture.build_log) != build_calls:
        raise RuntimeError("second build-only reached the release builder")
    if hashlib.sha256(fixture.artifact.read_bytes()).hexdigest() != artifact_hash:
        raise RuntimeError("second build-only overwrote the pending artifact")
    rebuild_calls_before = line_count(fixture.build_log)
    require_success(fixture.finalize("700120"), "Studio finalization")
    if line_count(fixture.build_log) != rebuild_calls_before + 1:
        raise RuntimeError("valid Studio finalization did not rebuild the artifact once")
    if fixture.pending.exists():
        raise RuntimeError("Studio finalization did not clear pending state")
    if fixture.pending_ref_exists():
        raise RuntimeError("Studio finalization did not clear its recovery ref")


def test_reproducible_artifact_integrity(parent: Path) -> None:
    gameplay = Fixture(parent, "tampered-gameplay")
    require_success(gameplay.build_only(), "gameplay tamper fixture build-only")
    gameplay_text = gameplay.artifact.read_text()
    original = 'VersionBuild = "local"'
    if gameplay_text.count(original) != 1:
        raise RuntimeError("gameplay tamper fixture did not contain its expected source")
    gameplay.artifact.write_text(
        gameplay_text.replace(original, 'VersionBuild = "tampered"', 1)
    )
    bless_current_artifact_in_manifest(gameplay)
    rebuild_calls_before = line_count(gameplay.build_log)
    version = "700121"
    result = gameplay.finalize(version)
    require_failure(result, "manifest-blessed gameplay tamper")
    if line_count(gameplay.build_log) != rebuild_calls_before + 1:
        raise RuntimeError("gameplay tamper rejection did not perform a fresh rebuild")
    state = gameplay.load_state()
    if state["state"] != "prepared" or state["placeVersion"] is not None:
        raise RuntimeError("gameplay tamper was recorded before reproducibility rejection")
    if gameplay.tag_exists(version):
        raise RuntimeError("gameplay tamper created a publish tag")

    extra = Fixture(parent, "tampered-extra-module")
    require_success(extra.build_only(), "extra-module tamper fixture build-only")
    extra_text = extra.artifact.read_text()
    closing = "</roblox>\n"
    if not extra_text.endswith(closing):
        raise RuntimeError("extra-module tamper fixture had an unexpected XML ending")
    injected = (
        '<Item class="ModuleScript"><Properties>'
        '<string name="Name">UnexpectedGameplay</string>'
        '<ProtectedString name="Source">return true</ProtectedString>'
        "</Properties></Item>"
    )
    extra.artifact.write_text(extra_text[: -len(closing)] + injected + closing)
    bless_current_artifact_in_manifest(extra)
    rebuild_calls_before = line_count(extra.build_log)
    version = "700122"
    result = extra.finalize(version)
    require_failure(result, "manifest-blessed extra ModuleScript")
    if line_count(extra.build_log) != rebuild_calls_before + 1:
        raise RuntimeError("extra-module rejection did not perform a fresh rebuild")
    state = extra.load_state()
    if state["state"] != "prepared" or state["placeVersion"] is not None:
        raise RuntimeError("extra ModuleScript was recorded before reproducibility rejection")
    if extra.tag_exists(version):
        raise RuntimeError("extra ModuleScript created a publish tag")


def test_conflict_and_crash_resume(parent: Path) -> None:
    conflict = Fixture(parent, "tag-conflict")
    require_success(conflict.build_only(), "conflict fixture build-only")
    release_commit = conflict.load_state()["gitCommit"]
    git(conflict.repo, "commit", "--quiet", "--allow-empty", "-m", "advanced head")
    conflicting_commit = git(conflict.repo, "rev-parse", "HEAD", capture=True)
    git(
        conflict.repo,
        "update-ref",
        "refs/tags/racer-place-v700130",
        conflicting_commit,
        "",
    )
    result = conflict.finalize("700130")
    require_failure(result, "conflicting immutable tag")
    state = conflict.load_state()
    if state["state"] != "version-recorded" or state["gitCommit"] != release_commit:
        raise RuntimeError("tag conflict did not retain recorded recovery state")
    if conflict.pending_ref_commit() != release_commit:
        raise RuntimeError("tag conflict did not retain its recovery ref")
    git(
        conflict.repo,
        "update-ref",
        "-d",
        "refs/tags/racer-place-v700130",
        conflicting_commit,
    )
    require_success(conflict.finalize("700130"), "conflict recovery")
    if conflict.pending_ref_exists():
        raise RuntimeError("conflict recovery retained its recovery ref")

    resume = Fixture(parent, "same-tag-resume")
    require_success(resume.build_only(), "resume fixture build-only")
    release_commit = str(resume.load_state()["gitCommit"])
    git(
        resume.repo,
        "update-ref",
        "refs/tags/racer-place-v700131",
        release_commit,
        "",
    )
    git(resume.repo, "commit", "--quiet", "--allow-empty", "-m", "head advanced")
    require_success(resume.finalize("700131"), "same-tag crash resume")
    if (
        resume.pending.exists()
        or resume.pending_ref_exists()
        or resume.tag_commit("700131") != release_commit
    ):
        raise RuntimeError("same-tag crash resume did not preserve the release commit")


def test_lookup_failure_resume(parent: Path) -> None:
    fixture = Fixture(parent, "lookup-failure", broken_lookup=True)
    version = "700140"
    result = fixture.publish("success", version)
    require_failure(result, "lookup failure after accepted publish")
    state = fixture.load_state()
    if state["state"] != "version-recorded" or state["placeVersion"] != version:
        raise RuntimeError("lookup failure did not retain VERSION_RECORDED state")
    if fixture.tag_commit(version) != fixture.release_commit:
        raise RuntimeError("lookup failure fixture did not reach tag creation")
    if fixture.pending_ref_commit() != fixture.release_commit:
        raise RuntimeError("lookup failure did not retain its recovery ref")

    shutil.copy2(
        ROOT / "scripts/lookup-place-version.sh",
        fixture.repo / "scripts/lookup-place-version.sh",
    )
    git(fixture.repo, "add", "scripts/lookup-place-version.sh")
    git(fixture.repo, "commit", "--quiet", "-m", "restore lookup")
    require_success(fixture.finalize(version), "lookup crash resume")
    if fixture.pending.exists() or fixture.pending_ref_exists():
        raise RuntimeError("lookup crash resume did not clear pending recovery state")


def test_recovery_ref_reachability(parent: Path) -> None:
    fixture = Fixture(parent, "recovery-ref-gc")
    version = "700141"
    require_success(fixture.build_only(), "recovery ref GC fixture build-only")
    release_commit = fixture.release_commit
    release_tree = git(
        fixture.repo, "rev-parse", f"{release_commit}^{{tree}}", capture=True
    )
    unrelated_commit = git(
        fixture.repo,
        "commit-tree",
        release_tree,
        "-m",
        "unrelated same-tree root",
        capture=True,
    )
    if unrelated_commit == release_commit:
        raise RuntimeError("unrelated recovery fixture unexpectedly reused the release commit")
    git(fixture.repo, "reset", "--hard", unrelated_commit)
    git(
        fixture.repo,
        "reflog",
        "expire",
        "--expire=now",
        "--expire-unreachable=now",
        "--all",
    )
    git(fixture.repo, "gc", "--prune=now")
    git(fixture.repo, "cat-file", "-e", f"{release_commit}^{{commit}}")
    if fixture.pending_ref_commit() != release_commit:
        raise RuntimeError("recovery ref did not preserve the unreachable release commit")

    require_success(fixture.finalize(version), "finalize after unrelated-root GC")
    if (
        fixture.pending.exists()
        or fixture.pending_ref_exists()
        or fixture.tag_commit(version) != release_commit
    ):
        raise RuntimeError("GC recovery did not replace the private ref with the publish tag")


def test_recovery_ref_crash_resume(parent: Path) -> None:
    fixture = Fixture(parent, "recovery-ref-delete-crash")
    version = "700142"
    require_success(fixture.build_only(), "ref deletion crash fixture build-only")
    payload = fixture.load_state()
    artifact = payload["artifact"]
    if not isinstance(artifact, dict):
        raise RuntimeError("ref deletion crash fixture artifact was not an object")
    record = fixture.run(
        [
            str(fixture.state_helper),
            "record-version",
            version,
            "--git-commit",
            fixture.release_commit,
            "--artifact-sha256",
            str(artifact["sha256"]),
        ]
    )
    require_success(record, "record before simulated ref deletion crash")
    git(
        fixture.repo,
        "update-ref",
        f"refs/tags/racer-place-v{version}",
        fixture.release_commit,
        "",
    )
    git(
        fixture.repo,
        "update-ref",
        "-d",
        PENDING_REF,
        fixture.release_commit,
    )
    if not fixture.pending.exists() or fixture.pending_ref_exists():
        raise RuntimeError("simulated ref deletion crash state was not constructed")

    require_success(fixture.finalize(version), "resume after recovery ref deletion")
    if (
        fixture.pending.exists()
        or fixture.pending_ref_exists()
        or fixture.tag_commit(version) != fixture.release_commit
    ):
        raise RuntimeError("ref deletion crash resume was not idempotent")


def test_recovery_ref_guards(parent: Path) -> None:
    orphan = Fixture(parent, "orphan-recovery-ref")
    git(
        orphan.repo,
        "update-ref",
        PENDING_REF,
        orphan.release_commit,
        "",
    )
    result = orphan.publish("success", "700143")
    require_failure(result, "publisher with orphan recovery ref")
    if line_count(orphan.build_log) or line_count(orphan.curl_log):
        raise RuntimeError("orphan recovery ref refusal reached the release builder or curl")
    if orphan.pending.exists() or orphan.pending_ref_commit() != orphan.release_commit:
        raise RuntimeError("orphan recovery ref refusal changed recovery state")

    foreign = Fixture(parent, "foreign-recovery-ref")
    require_success(foreign.build_only(), "foreign recovery ref fixture build-only")
    git(foreign.repo, "commit", "--quiet", "--allow-empty", "-m", "foreign commit")
    foreign_commit = git(foreign.repo, "rev-parse", "HEAD", capture=True)
    git(
        foreign.repo,
        "update-ref",
        PENDING_REF,
        foreign_commit,
        foreign.release_commit,
    )
    require_failure(foreign.finalize("700144"), "foreign recovery ref finalizer")
    if not foreign.pending.exists() or foreign.pending_ref_commit() != foreign_commit:
        raise RuntimeError("foreign recovery ref failure did not fail closed")

    noncommit = Fixture(parent, "noncommit-recovery-ref")
    require_success(noncommit.build_only(), "noncommit recovery ref fixture build-only")
    tree_id = git(noncommit.repo, "rev-parse", "HEAD^{tree}", capture=True)
    git(
        noncommit.repo,
        "update-ref",
        PENDING_REF,
        tree_id,
        noncommit.release_commit,
    )
    require_failure(noncommit.finalize("700145"), "noncommit recovery ref finalizer")
    if not noncommit.pending.exists() or not noncommit.pending_ref_exists():
        raise RuntimeError("noncommit recovery ref failure did not retain state")

    corrupt = Fixture(parent, "corrupt-recovery-ref")
    require_success(corrupt.build_only(), "corrupt recovery ref fixture build-only")
    corrupt_ref_path = corrupt.repo / ".git/refs/racer-publish/pending"
    if not corrupt_ref_path.is_file():
        raise RuntimeError("corrupt recovery ref fixture did not create a loose ref")
    corrupt_ref_path.write_text("not-an-object-id\n")
    require_failure(corrupt.finalize("700146"), "corrupt recovery ref finalizer")
    if not corrupt.pending.exists() or not corrupt_ref_path.exists():
        raise RuntimeError("corrupt recovery ref failure did not fail closed")

    symbolic = Fixture(parent, "symbolic-recovery-ref")
    require_success(symbolic.build_only(), "symbolic recovery ref fixture build-only")
    head_ref = git(symbolic.repo, "symbolic-ref", "HEAD", capture=True)
    head_commit = git(symbolic.repo, "rev-parse", head_ref, capture=True)
    git(
        symbolic.repo,
        "update-ref",
        "--no-deref",
        "-d",
        PENDING_REF,
        symbolic.release_commit,
    )
    git(symbolic.repo, "symbolic-ref", PENDING_REF, head_ref)
    require_failure(symbolic.finalize("700147"), "symbolic recovery ref finalizer")
    if git(symbolic.repo, "symbolic-ref", PENDING_REF, capture=True) != head_ref:
        raise RuntimeError("symbolic recovery ref failure changed the recovery symref")
    if git(symbolic.repo, "rev-parse", head_ref, capture=True) != head_commit:
        raise RuntimeError("symbolic recovery ref failure changed its target branch")
    if not symbolic.pending.exists() or symbolic.tag_exists("700147"):
        raise RuntimeError("symbolic recovery ref failure changed publish state")


def test_mismatches_and_corruption(parent: Path) -> None:
    locked = Fixture(parent, "release-lock")
    lock_path = locked.repo / "build/.racer-publish-release.lock"
    lock_path.mkdir(parents=True)
    publish = locked.publish("success", "700149")
    require_failure(publish, "single-writer release lock")
    if line_count(locked.build_log) or line_count(locked.curl_log):
        raise RuntimeError("release-lock refusal reached the release builder or curl")

    boundary = Fixture(
        parent, "post-manifest-mutation", mutate_after_state_create=True
    )
    publish = boundary.publish("success", "700148")
    require_failure(publish, "post-manifest artifact mutation")
    if line_count(boundary.curl_log):
        raise RuntimeError("post-manifest artifact mutation reached curl")
    if boundary.load_state()["state"] != "prepared":
        raise RuntimeError("post-manifest mutation did not retain PREPARED state")

    artifact = Fixture(parent, "artifact-mismatch")
    require_success(artifact.build_only(), "artifact mismatch fixture")
    with artifact.artifact.open("ab") as stream:
        stream.write(b"changed")
    require_failure(artifact.finalize("700150"), "changed artifact")
    if not artifact.pending.exists():
        raise RuntimeError("changed artifact cleared pending state")

    place = Fixture(parent, "place-mismatch")
    require_success(place.build_only(), "place mismatch fixture")
    require_failure(
        place.finalize("700151", racer_place_id="999"), "wrong Racer place id"
    )
    if not place.pending.exists():
        raise RuntimeError("place mismatch cleared pending state")

    corrupt = Fixture(parent, "corrupt-state")
    corrupt.pending.parent.mkdir(parents=True, exist_ok=True)
    corrupt.pending.write_text("{")
    corrupt.pending.chmod(0o600)
    publish = corrupt.publish("success", "700152")
    require_failure(publish, "corrupt pending publisher refusal")
    if line_count(corrupt.build_log) or line_count(corrupt.curl_log):
        raise RuntimeError("corrupt pending state reached the release builder or curl")
    require_failure(corrupt.finalize("700152"), "corrupt pending finalizer refusal")

    symlink = Fixture(parent, "symlink-state")
    symlink.pending.parent.mkdir(parents=True, exist_ok=True)
    target = symlink.pending.parent / "untrusted-state.json"
    target.write_text("{}\n")
    symlink.pending.symlink_to(target.name)
    publish = symlink.publish("success", "700153")
    require_failure(publish, "symlink pending publisher refusal")
    if line_count(symlink.build_log) or line_count(symlink.curl_log):
        raise RuntimeError("symlink pending state reached the release builder or curl")


def test_atomic_state_operations(parent: Path) -> None:
    fixture = Fixture(parent, "atomic-state")
    require_success(fixture.build_only(), "atomic state fixture")
    raw = fixture.pending.read_bytes()
    payload = json.loads(raw)
    expected = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode()
    if raw != expected:
        raise RuntimeError("pending state was not canonical JSON")
    if stat.S_IMODE(fixture.pending.stat().st_mode) != 0o600:
        raise RuntimeError("pending state mode was not 0600")

    create_again = fixture.run(
        [
            str(fixture.state_helper),
            "create",
            "--mode",
            "studio",
            "--git-commit",
            str(payload["gitCommit"]),
            "--git-commit-short",
            str(payload["gitCommitShort"]),
            "--published-at",
            str(payload["publishedAt"]),
            "--racer-place-id",
            str(payload["racerPlaceId"]),
            "--lobby-place-id",
            str(payload["lobbyPlaceId"]),
        ]
    )
    require_failure(create_again, "no-clobber state creation")
    if fixture.pending.read_bytes() != raw:
        raise RuntimeError("no-clobber state creation changed the manifest")

    processes = [
        subprocess.Popen(
            [
                str(fixture.state_helper),
                "record-version",
                version,
                "--git-commit",
                str(payload["gitCommit"]),
                "--artifact-sha256",
                str(payload["artifact"]["sha256"]),
            ],
            cwd=fixture.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for version in ("700160", "700161")
    ]
    results = [process.communicate() + (process.returncode,) for process in processes]
    if sum(returncode == 0 for _, _, returncode in results) != 1:
        raise RuntimeError("concurrent record-version CAS did not choose exactly one value")
    recorded = fixture.load_state()["placeVersion"]
    if recorded not in {"700160", "700161"}:
        raise RuntimeError("concurrent record-version wrote an invalid value")
    wrong = "700161" if recorded == "700160" else "700160"
    clear = fixture.run(
        [
            str(fixture.state_helper),
            "clear",
            "--git-commit",
            str(payload["gitCommit"]),
            "--artifact-sha256",
            str(payload["artifact"]["sha256"]),
            "--place-version",
            wrong,
        ]
    )
    require_failure(clear, "clear CAS mismatch")
    if not fixture.pending.exists():
        raise RuntimeError("clear CAS mismatch deleted pending state")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="racer-publish-recovery-test-") as temp:
        parent = Path(temp)
        test_success(parent)
        test_failed_request_and_retry(parent)
        test_invalid_responses(parent)
        test_build_only(parent)
        test_reproducible_artifact_integrity(parent)
        test_conflict_and_crash_resume(parent)
        test_lookup_failure_resume(parent)
        test_recovery_ref_reachability(parent)
        test_recovery_ref_crash_resume(parent)
        test_recovery_ref_guards(parent)
        test_mismatches_and_corruption(parent)
        test_atomic_state_operations(parent)
    print("Pending Racer publish recovery tests passed")


if __name__ == "__main__":
    main()
