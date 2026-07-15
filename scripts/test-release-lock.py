#!/usr/bin/python3 -I
"""Dynamic security and crash coverage for the Racer release lock."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import resource


ROOT = Path(__file__).resolve().parents[1]
HELPER_RELATIVE = Path("scripts/racer-publish-state.py")
LOCK_NAME = "racer-publish-release.lock"
LOCK_CONTEXT = "racer-release-lock-v1"
PYTHON = "/usr/bin/python3"
GIT = "/usr/bin/git"


def environment(home: Path, temporary: Path) -> dict[str, str]:
    return {
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
    }


def git(repo: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        [GIT, "-c", f"safe.directory={repo}", "-C", str(repo), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.stdout.strip() if capture else ""


def make_repo(parent: Path, name: str) -> tuple[Path, Path, Path]:
    repo = parent / name
    home = parent / f"{name}-home"
    temporary = parent / f"{name}-tmp"
    (repo / "scripts").mkdir(parents=True)
    home.mkdir()
    temporary.mkdir()
    shutil.copy2(ROOT / HELPER_RELATIVE, repo / HELPER_RELATIVE)
    git(repo, "init", "--quiet")
    git(repo, "config", "user.name", "Racer Release Lock Test")
    git(repo, "config", "user.email", "racer-lock@example.invalid")
    git(repo, "add", str(HELPER_RELATIVE))
    git(repo, "commit", "--quiet", "-m", "release lock fixture")
    return repo, home, temporary


def helper_command(repo: Path, *arguments: str) -> list[str]:
    return [PYTHON, "-I", str(repo / HELPER_RELATIVE), *arguments]


def run_helper(
    repo: Path,
    home: Path,
    temporary: Path,
    *arguments: str,
    extra_environment: dict[str, str] | None = None,
    pass_fds: tuple[int, ...] = (),
    preexec_fn=None,
) -> subprocess.CompletedProcess[str]:
    child_environment = environment(home, temporary)
    if extra_environment:
        child_environment.update(extra_environment)
    return subprocess.run(
        helper_command(repo, *arguments),
        cwd=repo,
        env=child_environment,
        pass_fds=pass_fds,
        preexec_fn=preexec_fn,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def require_failure(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode == 0:
        raise RuntimeError(f"{label} unexpectedly succeeded")


def wait_for(path: Path, process: subprocess.Popen[str], label: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"{label} exited before readiness ({process.returncode}): "
                f"{stdout}{stderr}"
            )
        time.sleep(0.02)
    process.kill()
    process.wait()
    raise RuntimeError(f"timed out waiting for {label}")


def kill_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=10)


def kill_pid(process_id: int | None) -> None:
    if process_id is None:
        return
    try:
        os.kill(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass


def common_dir(repo: Path) -> Path:
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir", capture=True))


def start_holder(
    repo: Path,
    home: Path,
    temporary: Path,
    ready: Path,
    *,
    orphan_child: Path | None = None,
) -> subprocess.Popen[str]:
    if orphan_child is None:
        body = f"builtin printf '%s\\n' \"$$\" > {str(ready)!r}; exec /bin/sleep 30"
    else:
        body = (
            "/bin/sleep 30 </dev/null >/dev/null 2>&1 & child=$!; "
            f"builtin printf '%s\\n' \"${{child}}\" > {str(orphan_child)!r}; "
            f"builtin printf '%s\\n' \"$$\" > {str(ready)!r}; "
            "builtin wait \"${child}\""
        )
    return subprocess.Popen(
        helper_command(
            repo,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            body,
        ),
        cwd=repo,
        env=environment(home, temporary),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def basic_and_crash_tests(parent: Path) -> None:
    repo, home, temporary = make_repo(parent, "basic")
    lock_path = common_dir(repo) / LOCK_NAME

    exact = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 37",
    )
    if exact.returncode != 37:
        raise RuntimeError(f"release helper changed exact exit status: {exact.returncode}")
    metadata = lock_path.lstat()
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("persistent release lock is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
        raise RuntimeError("persistent release lock metadata is not 0600/single-link")
    if metadata.st_size != 0:
        raise RuntimeError("persistent release lock is not empty")
    inode = (metadata.st_dev, metadata.st_ino)

    inherited = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        PYTHON,
        "-I",
        str(repo / HELPER_RELATIVE),
        "assert-release-lock",
    )
    if inherited.returncode != 0:
        raise RuntimeError(f"inherited lock assertion failed: {inherited.stderr}")
    if (lock_path.stat().st_dev, lock_path.stat().st_ino) != inode:
        raise RuntimeError("successful reuse replaced the persistent lock inode")

    signaled = subprocess.Popen(
        helper_command(
            repo,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "builtin kill -TERM $$",
        ),
        cwd=repo,
        env=environment(home, temporary),
    )
    if signaled.wait(timeout=10) != -signal.SIGTERM:
        raise RuntimeError("release helper did not preserve the exec child's signal")

    ready = parent / "holder-ready"
    holder = start_holder(repo, home, temporary, ready)
    try:
        wait_for(ready, holder, "release-lock holder")
        contention = run_helper(
            repo,
            home,
            temporary,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "exit 0",
        )
        require_failure(contention, "second concurrent release")
        if "another Racer release operation" not in contention.stderr:
            raise RuntimeError("contention did not report the held release lock")
        holder.kill()
        if holder.wait(timeout=10) != -signal.SIGKILL:
            raise RuntimeError("release-lock holder did not die by SIGKILL")
    finally:
        kill_process(holder)

    recovered = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
    )
    if recovered.returncode != 0:
        raise RuntimeError(f"lock did not recover after SIGKILL: {recovered.stderr}")
    if (lock_path.stat().st_dev, lock_path.stat().st_ino) != inode:
        raise RuntimeError("SIGKILL recovery replaced the persistent lock inode")

    orphan_ready = parent / "orphan-ready"
    orphan_pid_path = parent / "orphan-child-pid"
    parent_process = start_holder(
        repo,
        home,
        temporary,
        orphan_ready,
        orphan_child=orphan_pid_path,
    )
    child_pid = None
    try:
        wait_for(orphan_ready, parent_process, "orphaning lock holder")
        child_pid = int(orphan_pid_path.read_text().strip())
        parent_process.kill()
        parent_process.wait(timeout=10)
        still_held = run_helper(
            repo,
            home,
            temporary,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "exit 0",
        )
        require_failure(still_held, "contender while critical child survived")
    finally:
        kill_pid(child_pid)
        kill_process(parent_process)
    deadline = time.monotonic() + 10
    while True:
        after_child = run_helper(
            repo,
            home,
            temporary,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "exit 0",
        )
        if after_child.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("lock remained held after the last critical child died")
        time.sleep(0.02)


def spoof_and_inode_tests(parent: Path) -> None:
    repo, home, temporary = make_repo(parent, "spoof")
    lock_path = common_dir(repo) / LOCK_NAME
    created = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
    )
    if created.returncode != 0:
        raise RuntimeError(created.stderr)

    contexts = {
        "RACER_RELEASE_LOCK_CONTEXT": LOCK_CONTEXT,
        "RACER_RELEASE_LOCK_FD": "8",
    }
    missing = run_helper(
        repo,
        home,
        temporary,
        "assert-release-lock",
        extra_environment=contexts,
    )
    require_failure(missing, "context without FD8")

    source = os.open(lock_path, os.O_RDWR)
    try:
        os.dup2(source, 8, inheritable=True)
        unlocked = run_helper(
            repo,
            home,
            temporary,
            "assert-release-lock",
            extra_environment=contexts,
            pass_fds=(8,),
        )
    finally:
        os.close(8)
        os.close(source)
    require_failure(unlocked, "spoofed unlocked correct inode on FD8")
    if "not already locked" not in unlocked.stderr:
        raise RuntimeError(
            f"spoofed unlocked FD8 failed for the wrong reason: {unlocked.stderr}"
        )

    wrong_path = parent / "wrong-fd"
    wrong_path.write_bytes(b"")
    wrong_path.chmod(0o600)
    wrong = os.open(wrong_path, os.O_RDWR)
    try:
        os.dup2(wrong, 8, inheritable=True)
        wrong_result = run_helper(
            repo,
            home,
            temporary,
            "assert-release-lock",
            extra_environment=contexts,
            pass_fds=(8,),
        )
    finally:
        os.close(8)
        os.close(wrong)
    require_failure(wrong_result, "wrong inode on FD8")

    partial = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
        extra_environment={"RACER_RELEASE_LOCK_CONTEXT": LOCK_CONTEXT},
    )
    require_failure(partial, "partial preexisting lock context")

    soft_limit, _hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    target_fd = min(200, int(soft_limit) - 1)
    if target_fd > 32:
        source = os.open(os.devnull, os.O_RDONLY)
        try:
            os.dup2(source, target_fd, inheritable=True)

            def lower_descriptor_limit() -> None:
                resource.setrlimit(
                    resource.RLIMIT_NOFILE,
                    (32, 32),
                )

            ambient = run_helper(
                repo,
                home,
                temporary,
                "with-release-lock",
                "--",
                PYTHON,
                "-I",
                "-c",
                (
                    "import os,sys\n"
                    f"try: os.fstat({target_fd})\n"
                    "except OSError: raise SystemExit(0)\n"
                    "raise SystemExit(93)\n"
                ),
                pass_fds=(target_fd,),
                preexec_fn=lower_descriptor_limit,
            )
        finally:
            os.close(target_fd)
            os.close(source)
        if ambient.returncode != 0:
            raise RuntimeError("high ambient FD survived a lowered RLIMIT handoff")


def malformed_lock_tests(parent: Path) -> None:
    cases = ("symlink", "hardlink", "mode", "directory", "fifo", "nonempty")
    for case in cases:
        repo, home, temporary = make_repo(parent, f"malformed-{case}")
        lock_path = common_dir(repo) / LOCK_NAME
        target = parent / f"{case}-target"
        if case == "symlink":
            target.write_bytes(b"")
            target.chmod(0o600)
            lock_path.symlink_to(target)
        elif case == "hardlink":
            target.write_bytes(b"")
            target.chmod(0o600)
            os.link(target, lock_path)
        elif case == "mode":
            lock_path.write_bytes(b"")
            lock_path.chmod(0o644)
        elif case == "directory":
            lock_path.mkdir()
        elif case == "fifo":
            os.mkfifo(lock_path, 0o600)
        elif case == "nonempty":
            lock_path.write_bytes(b"not empty")
            lock_path.chmod(0o600)
        result = run_helper(
            repo,
            home,
            temporary,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "exit 0",
        )
        require_failure(result, f"malformed {case} lock inode")

    repo, home, temporary = make_repo(parent, "legacy")
    legacy = repo / "build/.racer-publish-release.lock"
    legacy.mkdir(parents=True)
    result = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
    )
    require_failure(result, "legacy build lock path")
    if "legacy build/.racer-publish-release.lock exists" not in result.stderr:
        raise RuntimeError("legacy lock refusal did not explain one-time migration")


def linked_worktree_test(parent: Path) -> None:
    repo, home, temporary = make_repo(parent, "worktree-main")
    linked = parent / "worktree-linked"
    git(repo, "worktree", "add", "--quiet", "-b", "lock-linked", str(linked))
    main_common = common_dir(repo)
    linked_common = common_dir(linked)
    if main_common.resolve() != linked_common.resolve():
        raise RuntimeError("linked worktrees did not resolve one Git common directory")
    main_git_dir = git(repo, "rev-parse", "--absolute-git-dir", capture=True)
    linked_git_dir = git(linked, "rev-parse", "--absolute-git-dir", capture=True)
    if main_git_dir == linked_git_dir:
        raise RuntimeError("linked-worktree fixture did not have distinct Git dirs")

    linked_legacy = linked / "build/.racer-publish-release.lock"
    linked_legacy.mkdir(parents=True)
    legacy_result = run_helper(
        repo,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
    )
    require_failure(legacy_result, "legacy lock in another linked worktree")
    if "registered worktree" not in legacy_result.stderr:
        raise RuntimeError("cross-worktree legacy guard failed for the wrong reason")
    linked_legacy.rmdir()
    linked_legacy.parent.rmdir()

    ready = parent / "linked-holder-ready"
    holder = start_holder(repo, home, temporary, ready)
    try:
        wait_for(ready, holder, "main-worktree lock holder")
        linked_result = run_helper(
            linked,
            home,
            temporary,
            "with-release-lock",
            "--",
            "/bin/bash",
            "-p",
            "-c",
            "exit 0",
        )
        require_failure(linked_result, "linked-worktree concurrent release")
        inode = (main_common / LOCK_NAME).stat().st_ino
        holder.kill()
        holder.wait(timeout=10)
    finally:
        kill_process(holder)
    after = run_helper(
        linked,
        home,
        temporary,
        "with-release-lock",
        "--",
        "/bin/bash",
        "-p",
        "-c",
        "exit 0",
    )
    if after.returncode != 0:
        raise RuntimeError(f"linked worktree did not acquire released lock: {after.stderr}")
    if (linked_common / LOCK_NAME).stat().st_ino != inode:
        raise RuntimeError("linked worktree did not reuse the persistent lock inode")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="racer-release-lock-test-") as temp:
        parent = Path(temp)
        basic_and_crash_tests(parent)
        spoof_and_inode_tests(parent)
        malformed_lock_tests(parent)
        linked_worktree_test(parent)
    print("Release lock test passed")


if __name__ == "__main__":
    main()
