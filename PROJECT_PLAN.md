# Project Plan

## Goals

1. Reach 1:1 gameplay-logic parity with https://jakesgordon.com/games/racer/
   across all four versions.
2. Fix spectator display desync. Player rendering currently stays correct, but
   spectator rendering starts drifting after some time and the mismatch grows.

## Texture Work Constraints

- Keep the existing placeholder visuals intact.
- Add new texture art as an optional renderer mode controlled by a settings
  checkbox.
- The user must be able to turn the new textures off and return to the current
  placeholder visuals at any time.
- Texture sprites must visually match their gameplay/render hitboxes. The
  visible bottom of every sprite should align with the sprite rectangle bottom,
  especially for cars and roadside objects, so nothing appears to float above
  the projected ground contact point.

## Feature Roadmap

Each feature should be a separate commit. It is fine to push a batch of commits
to GitHub later, but the local history should stay split by feature so each
change can be reviewed or reverted independently.

### Done

- `v5 Lab` exists as a fifth stand and inherits `v4 Final` physics, traffic,
  laps, HUD, and collision behavior without changing v1-v4.
  Commit: `fb1895a Add v5 racer stand`.
- The player car has visible driver/passenger shapes in the texture atlas.
  Commit: `29c4b70 Add people to racer player car`.
- `v5` can overlay Roblox avatar thumbnails for the driver and a passenger
  when available, with the atlas people remaining as fallback.
  Commit: `29c4b70 Add people to racer player car`.
- `v5` has three physical leaderboard panels for personal, friends, and global
  top-10 lap records backed by DataStore.
  Commit: `bf70c12 Add v5 lap leaderboards`.
- Some `v5` billboards can show live leaderboard content, currently global
  top-1 text.
  Commit: `698e328 Add live v5 billboard content`.
- `v5` has decorative visual-only intersections and T-junctions, with traffic
  filtered out of the junction buffer.
  Commit: `9b1e40d Add v5 visual intersections`.
- The `v5` area is moved away from spawn and the lab floor/walls are expanded.
  Commit: `44ba29e Improve v5 spacing and sprite textures`.
- Texture checks now verify that every gameplay sprite has a texture rect and
  that every rect stays inside the atlas and touches the bottom edge.
  Commit: `44ba29e Improve v5 spacing and sprite textures`.

### Not Done Yet

- Production-quality textures are not done. Current textures are a deterministic
  atlas with improved details, not final generated/hand-finished art.
- The avatar driver is a 2D Roblox thumbnail overlay, not a true rear-view
  extraction from the player's character.
- The passenger selection is simple: another server player if one is available,
  otherwise the drawn fallback remains visible.
- Friend/global leaderboards need in-game validation in a published server with
  DataStore and friend APIs enabled.
- Spectator display desync is still a separate future task after player-facing
  game behavior is stable.

### Next Feature Commits

1. `art: add production racer texture source pack`
   - Generate or draw proper source sprites for player car, traffic, roadside
     objects, billboards, and intersection decoration.
   - Keep transparent source assets separate from the packed Roblox atlas.
   - Acceptance: source images exist, are visually inspectable, and are not
     merely procedural placeholders.

2. `art: pack production texture atlas`
   - Pack the source sprites into `assets/racer/textures`.
   - Update `RacerTextures.lua` rects and uploaded Roblox image asset.
   - Keep the placeholder toggle intact.
   - Acceptance: all sprite rects pass parity-check, bottom alignment passes,
     and old placeholders still work when textures are disabled.

3. `v5: improve avatar car occupants`
   - Replace thumbnail overlay with a better rear-view/avatar-derived occupant
     pipeline if Roblox APIs allow it.
   - Keep fallback people visible when avatar images fail.
   - Acceptance: driver/passenger stay inside the car cabin across straight,
     turning, uphill, and downhill frames.

4. `v5: validate persistent leaderboards`
   - Test personal, friends, and global lists in a published server.
   - Confirm best-lap writes only after valid v5 laps.
   - Acceptance: top-10 lists update without breaking the race if DataStore or
     friends data is unavailable.

5. `v5: tune intersections`
   - Adjust junction placement and visuals based on in-game driving.
   - Confirm traffic never appears inside junction segments or the buffer.
   - Acceptance: intersections are visible decoration only; driving physics and
     collision remain v4-compatible.

6. `bug: fix spectator desync`
   - Investigate spectator rendering only after player-facing v1-v5 behavior is
     good enough.
   - Acceptance: spectator view no longer drifts over time relative to the
     player view.

### Always Check

- `python3 scripts/check-racer-parity.py`
- `rojo build racer.project.json --output build/racer.rbxlx`
- Publish Racer place after code/art changes that affect the Roblox place.
- Keep an eye on context/quota during long work. If a concrete remaining-token
  budget exists and it drops below 10%, stop and report progress before making
  more changes.
