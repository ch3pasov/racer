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
- Active-player HUD fixes for `v4+` are in place, including persistent
  `Last Lap`, fullscreen active-player HUD, and mobile side-panel layout.
- Mobile racer controls use on-screen buttons and temporarily disable Roblox
  character controls while the player is inside a racer screen.
- Optional debug overlays exist for `Spriteboxes` and `Collisionboxes`.
- Texture checks verify that every gameplay sprite has a texture rect, stays
  inside the atlas, and touches the bottom edge.

## Not Done Yet

- `v6 Driver Occupants` is not yet a clean standalone version. Existing avatar
  occupant work must be moved behind the `v6` feature boundary.
- `v7 Record Boards` is not yet a clean standalone version. Existing record
  board/DataStore/live billboard work must be moved behind the `v7` boundary.
- Production-quality textures are not done. Current texture art is still a
  deterministic atlas, not final generated or hand-finished art.
- Spectator display desync is still open; active-player rendering is the
  priority, but spectator correctness must be fixed as a shared renderer task.

## Overnight Plan

Each step should be its own commit and, when it affects the Roblox place, should
be published from a clean committed tree.

1. `docs: update racer version roadmap`
   - Replace the old `v5 Lab` roadmap with the explicit `v5/v6/v7` chain above.

2. `version: split driver and records into v6 v7`
   - Add `v6 Driver Occupants` as `v5 + driver/passenger feature flags`.
   - Add `v7 Record Boards` as `v6 + records/live billboard feature flags`.
   - Activate `v6` and `v7` stands in the lab.
   - Move record DataStores, board names, and live billboard replication from
     `RacerV6...` to `RacerV7...`.
   - Update parity checks so the version inheritance cannot silently regress.

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
