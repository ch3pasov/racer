# Project Plan

## Goals

1. Keep versions `v1` through `v4` at 1:1 gameplay-logic parity with
   https://jakesgordon.com/games/racer/.
2. Build new features as an explicit inheritance chain:
   `v5 Mobile Controls` -> `v6 Driver Occupants` -> `v7 Record Boards`.
3. Fix shared renderer issues, including spectator desync and texture/hitbox
   alignment, in common code so every relevant version benefits at once.

## Version Roadmap

- `v1 Straight`, `v2 Curves`, `v3 Hills`, and `v4 Final` are protected original
  versions. Do not add new feature behavior there unless matching the original.
- `v5 Mobile Controls` inherits `v4 Final` and adds only mobile-player UI and
  input improvements.
- `v6 Driver Occupants` inherits `v5` and adds improved driver/passenger
  presentation inside the player car.
- `v7 Record Boards` inherits `v6` and adds persistent personal, friends, and
  global lap records plus live billboard/board presentation.
- Spectator fixes and texture/rendering fixes are shared fixes, not new
  version-only features. Apply them at the lowest common implementation point
  that preserves `v1-v4` original behavior.

## Done

- `v5 Mobile Controls` exists as the current fifth stand and inherits `v4 Final`
  without changing `v1-v4`.
- `v6 Driver Occupants` and `v7 Record Boards` exist as explicit inherited
  versions in code: `v6` derives from `v5`, `v7` derives from `v6`, and both
  have dedicated feature gates.
- Active-player HUD fixes for `v4+` are in place, including persistent
  `Last Lap`, fullscreen active-player HUD, and mobile side-panel layout.
- Mobile racer controls use on-screen buttons and temporarily disable Roblox
  character controls while the player is inside a racer screen.
- Optional debug overlays exist for `Spriteboxes` and `Collisionboxes`.
- Record board persistence, DataStore names, and live billboard replication use
  `RacerV7...` naming and are guarded by the `v7` record-board feature flag.
- Texture checks verify that every gameplay sprite has a texture rect, stays
  inside the atlas, and touches the bottom edge.

## Not Done Yet

- `v6 Driver Occupants` still needs a better in-car avatar/passenger
  presentation and deterministic fallback people when avatar imagery fails.
- `v7 Record Boards` still needs published-server validation and more graceful
  handling around DataStore or friends API failures.
- Production-quality textures are not done. Current texture art is still a
  deterministic atlas, not final generated or hand-finished art.
- Spectator display desync is still open; active-player rendering is the
  priority, but spectator correctness must be fixed as a shared renderer task.

## Overnight Plan

Each step should be its own commit and, when it affects the Roblox place, should
be published from a clean committed tree.

1. `docs: update racer version roadmap`
   - Keep the plan synchronized with the current code-backed `v5/v6/v7` chain
     and record which roadmap items are already implemented.

2. `version: harden driver and records boundaries`
   - Keep `v5` limited to mobile controls, `v6` limited to driver/passenger
     presentation, and `v7` limited to records/live billboard features.
   - Ensure record DataStores, board names, and live billboard replication stay
     under `RacerV7...` names.
   - Keep parity checks covering version inheritance and feature gates so the
     boundaries cannot silently regress.

3. `v6: improve avatar car occupants`
   - Improve driver/passenger presentation only after the `v6` boundary is
     clean.
   - Keep deterministic fallback people visible when avatar imagery fails.

4. `v7: validate persistent record boards`
   - Test personal, friends, and global record boards in a published server.
   - Confirm best-lap writes only after valid `v7` laps.
   - Confirm failures in DataStore or friends APIs do not break racing.

5. Shared fixes after the version split
   - `fix: repair spectator renderer desync`
   - `fix: align texture rendering with gameplay hitboxes`

## Always Check

- `python3 scripts/check-racer-parity.py`
- `rojo build racer.project.json --output build/racer.rbxlx`
- `git diff --check`
- For place-affecting commits: publish Racer place, then verify
  `PlaceVersion -> git commit` with `scripts/lookup-place-version.sh`.
