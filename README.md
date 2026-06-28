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
- `scripts/publish-place.sh` builds and publishes Racer Lab through Roblox Open
  Cloud.
- `scripts/lookup-place-version.sh` maps a Roblox place version back to the git
  commit tagged during publish.

## Required Secrets For Publishing

Do not commit secrets. Put them in your shell or in a local `.env` file:

```sh
export ROBLOX_API_KEY="..."
export ROBLOX_UNIVERSE_ID="..."
export ROBLOX_RACER_PLACE_ID="..."
```

`ROBLOX_LOBBY_PLACE_ID` is optional. If present, the place can keep a portal back
to the lobby.

The API key should be an Open Cloud key with only the permissions needed to
create place versions for this Racer Lab place.

## Bootstrap Limitation

Roblox Open Cloud can publish a new version of an existing place, but it cannot
create the first experience/place from scratch. The first
`ROBLOX_UNIVERSE_ID` and `ROBLOX_RACER_PLACE_ID` still need to come from a place
created once through Roblox Studio or another machine that can run Roblox Studio.
After that, this VPS project can build and publish Racer Lab updates without
Studio.

## Local Container Workflow

```sh
docker compose run --rm roblox bash
python3 scripts/check-racer-parity.py
rojo build racer.project.json --output build/racer.rbxlx
scripts/publish-place.sh
```

Publishing refuses to run from a dirty git tree. The published place includes
the source commit in `ReplicatedStorage.Shared.GeneratedBuildInfo`, and the
publish script tags successful Roblox versions as `racer-place-v<version>`.
For example, `scripts/lookup-place-version.sh 153` shows the commit published as
Roblox place version 153.
