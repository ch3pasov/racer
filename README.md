# Racer Lab

Code-first Roblox place for the `Racer Lab` pseudo-3D racing prototype.

This repository intentionally contains only the Racer Lab place. Lobby work,
archived proofs of concept, and other Roblox places should live in separate
repositories.

## Layout

- `racer.project.json` maps the Racer Lab place for Rojo.
- `src/racer` contains Racer Lab scripts.
- `src/shared/GeneratedPlaceIds.lua` contains non-secret place ids used by the
  optional in-game lobby return portal.
- `scripts/check-racer-parity.py` runs static parity checks for the racer model.
- `scripts/build-racer-release.sh` builds an exact release artifact from an
  immutable git snapshot with the pinned Rojo version.
- `scripts/publish-place.sh` builds and publishes Racer Lab through Roblox Open
  Cloud.
- `scripts/racer-publish-state.py` preserves the exact artifact and release
  identity across uncertain publish outcomes.
- `scripts/test-release-snapshot-build.sh` verifies release-build determinism,
  worktree isolation, dirty-tree refusal, and the Rojo version pin.
- `scripts/test-docker-bootstrap.py` verifies that every container command first
  installs the pinned Aftman tools and that Compose uses the supported CPU
  architecture.
- `scripts/finalize-studio-publish.sh` safely records the immutable git mapping
  after a manually verified Roblox Studio publish.
- `scripts/lookup-place-version.sh` maps a Roblox place version back to the git
  commit tagged during publish.
- `scripts/read-roblox-server-logs.py` reads live server logs through Roblox
  Open Cloud Server Management.

## Required Secrets For Publishing

Do not commit secrets. Non-secret ids can live in your shell or a local `.env`
file. Export the API key only in the shell that invokes a command that needs it:

```sh
export ROBLOX_API_KEY="..."
export ROBLOX_UNIVERSE_ID="..."
export ROBLOX_RACER_PLACE_ID="..."
```

`ROBLOX_LOBBY_PLACE_ID` is optional. If present, the place can keep a portal back
to the lobby.

The API key should be an Open Cloud key with only the permissions needed to
create place versions for this Racer Lab place.

## Reading Live Server Logs

Do not put the Open Cloud key in Roblox client code, LocalScripts, frontend
code, or committed files. Keep it in the server-side environment:

```sh
export ROBLOX_API_KEY="..."
export ROBLOX_UNIVERSE_ID="..."
export ROBLOX_RACER_PLACE_ID="..."
export ROBLOX_VERSION_NUMBER="189"

scripts/read-roblox-server-logs.py --warnings-and-errors --pretty
```

The key must have read access to the target universe and Server Management read
operations, including listing game servers and listing game server logs.

## Bootstrap Limitation

Roblox Open Cloud can publish a new version of an existing place, but it cannot
create the first experience/place from scratch. The first
`ROBLOX_UNIVERSE_ID` and `ROBLOX_RACER_PLACE_ID` still need to come from a place
created once through Roblox Studio or another machine that can run Roblox Studio.
After that, this VPS project can build and publish Racer Lab updates without
Studio.

## Local Container Workflow

Start a key-free shell for builds and checks:

```sh
docker compose run --rm roblox bash
python3 scripts/test-docker-bootstrap.py
python3 scripts/check-racer-parity.py
scripts/test-release-snapshot-build.sh
python3 scripts/test-publish-recovery.py
scripts/publish-place.sh --build-only
```

Compose does not automatically put `ROBLOX_API_KEY` into ordinary container
commands. Pass it explicitly only to a one-shot command that needs Open Cloud,
such as publishing or reading server logs:

```sh
docker compose run --rm -e ROBLOX_API_KEY roblox scripts/publish-place.sh
docker compose run --rm -e ROBLOX_API_KEY roblox \
  scripts/read-roblox-server-logs.py --warnings-and-errors --pretty
```

Compose runs this service as `linux/amd64`, including on Apple Silicon, because
the pinned Aftman 0.3.0 binary is x86_64-only. The image entrypoint runs the
image-installed Aftman through absolute trusted paths before every requested
container command. Bootstrap receives neither publish-key variable, while the
requested one-shot command still receives a key explicitly passed with `-e`.
Even a fresh `docker compose run --rm roblox bash` therefore has the
repository-pinned tools available without exposing the publish key to bootstrap.

The image and Compose service run as the non-root `codex` user with UID/GID
1000. If `roblox-tools` was created by an older checkout that ran Compose as
root, migrate that named volume once after rebuilding the image:

```sh
docker compose build
docker compose run --rm --user root --entrypoint /bin/chown roblox \
  -R codex:codex /home/codex/.aftman
```

That one-time command intentionally bypasses the normal non-root entrypoint. If
the cached Aftman downloads are disposable, `docker compose down --volumes`
followed by `docker compose build` is an equivalent reset. Normal commands now
refuse to bootstrap as root or to use a tool volume that is not owned and
writable by the container user.

Verify the normal runtime identity and tool-volume ownership after migrating or
recreating the volume:

```sh
docker compose run --rm roblox bash -lc \
  'test "${EUID}" -eq 1000 && test -O "${HOME}/.aftman" && test -w "${HOME}/.aftman"'
```

On native Linux, UID 1000 in the container must match the owner allowed to write
this checkout, including its resolved Git common directory. Treat a mismatch as
a blocker for container publishing: use the host release workflow or align the
repository ownership before continuing. Docker Desktop performs bind-mount UID
mapping, so validate actual write access there instead of comparing numeric host
and container UIDs.

Publishing refuses to run from a dirty git tree. The published place includes
the source commit in `ReplicatedStorage.Shared.GeneratedBuildInfo`, and the
publish script tags successful Roblox versions as `racer-place-v<version>`.
For example, `scripts/lookup-place-version.sh 153` shows the commit published as
Roblox place version 153. Release builds require the repository-pinned Rojo
7.5.1; a direct `rojo build` remains suitable for development checks but is not
the traceable release path.

Every release handoff creates the ignored, non-secret
`build/racer-publish-pending.json` before Roblox can receive the artifact. While
that record exists, another build or publish is refused, so an uncertain network
result cannot create an untracked second PlaceVersion or overwrite the artifact.
Do not delete or edit it after a failed request. Recover the accepted version in
Studio or publish the exact recorded artifact there, then run the finalizer.

## Building For a Studio Fallback

From a committed, fully clean tree, build the exact release artifact without an
Open Cloud key, universe id, or network request:

```sh
export ROBLOX_RACER_PLACE_ID="..."
scripts/publish-place.sh --build-only
```

The command captures `HEAD`, exports that commit with `git archive`, writes
release metadata only inside the private snapshot, and atomically installs the
result as `build/racer.rbxlx`. Live tracked generated files are never changed.
It prints the artifact's full commit and SHA-256 for Studio version notes and
atomically creates a pending Studio handoff. It does not require or read an API
key or universe id and performs no network request. Publish that exact file
through Studio before finalizing its mapping. A second build is intentionally
blocked until this handoff is finalized.

## Finalizing a Studio Publish

Before recording a Studio publish, reopen the published Racer place in Studio
and verify its `game.PlaceId`, `game.PlaceVersion`, and embedded
`GeneratedBuildInfo.GitCommit`. Then record that exact version from a clean tree:

```sh
export ROBLOX_RACER_PLACE_ID="..."
scripts/finalize-studio-publish.sh <verified-place-version>
```

The finalizer performs no network operation, does not need an API key, scrubs any
inherited publish key before starting child processes, and never moves an
existing release tag. It consumes the pending record, validates the
artifact SHA-256, size, embedded commit, timestamp, Racer place, and lobby place,
then rebuilds that commit with the exact recorded timestamp and place ids. The
recorded artifact must match both the fresh build's SHA-256 and its exact bytes;
editing the rbxlx and updating the pending hash cannot bless a different build.
Only after this reproducibility check does the finalizer record the version and
atomically create its tag. It can recover an older pending commit after `HEAD`
advances and resume a matching tag created before an interrupted lookup. The
pending record is cleared only after the tag and exact PlaceVersion-to-commit
lookup both succeed.
