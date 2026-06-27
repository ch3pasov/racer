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

## Current Feature Requests

Already tracked:

- Reach practical 1:1 player gameplay logic parity with the original Jake
  Gordon Racer across `v1 Straight`, `v2 Curves`, `v3 Hills`, and `v4 Final`.
- Fix spectator display desync after the player-facing game logic is solid.
- Keep old placeholder visuals available behind a settings toggle while adding
  optional texture art.
- Ensure every texture sprite matches its gameplay/render hitbox, especially
  along the bottom edge.

New requests:

1. Add visible people inside the player car sprite, matching the spirit of the
   original Racer car-with-driver look.
2. Redraw textures for the whole game with correct sprite frames and hitbox
   alignment.
3. Add `v5`, a new version/mode for features that did not exist in the
   original game.
4. In `v5`, use the actual player's avatar as the driver sprite when possible:
   extract a rear-view player image and place it into the car.
5. In `v5`, use either a placeholder passenger sprite or another server
   player's avatar as the second person in the car.
6. Add a `v5` leaderboard near the `v5` entrance/display with three top-10
   lists: the current player's own best runs, best runs among friends, and
   global best runs.
7. Put automatic/live content on some billboards, such as the current top-1
   ranked player.
8. Add visual-only intersections to the road with no traffic spawned inside
   them, including occasional T-junctions to the left or right.
