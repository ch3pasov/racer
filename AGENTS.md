# Agent Rules

- When the user complains about behavior that belongs to the original Jake
  Gordon Racer feature set, first inspect the original implementation at
  https://jakesgordon.com/games/racer/ and then make this project match that
  behavior. Do not treat such complaints as new feature requests until the
  original behavior has been checked.
- Keep each feature change in its own commit. If a request changes multiple
  features, prefer multiple focused commits so any one feature can be reverted
  independently.
- Versions v1 through v4 must fully match the original Jake Gordon Racer
  behavior.
- Each new version must inherit the previous version plus only the features
  specific to that new version. For example, when fixing a bug in versions v4
  and newer, change the v4 implementation and let v5 and newer inherit that fix
  automatically; versions v3 and older must not be affected.
- Prioritize fixing the game for the active player inside the entered racer
  screen first. Spectator/observer display fixes for people standing nearby and
  watching someone else's game can be handled later unless the user explicitly
  asks for spectator mode work.
- For Racer texture work, sprite art must match the existing gameplay/render
  hitbox. In particular, the visible bottom of each sprite must sit on the
  sprite rectangle bottom edge so cars and roadside objects do not visually
  float above the ground.
- Every published Roblox place version must be traceable back to the exact git
  commit that produced it. Publish only from a committed, clean tree; ensure the
  publish embeds the commit in build metadata and records the Roblox
  `PlaceVersion` to commit mapping; after publishing, verify that the published
  version can be looked up by version number.
- When a requested task has been implemented and local checks pass, publish the
  Racer Lab place if the publish environment is available. Do not wait for a
  separate publish request unless there is a concrete blocker or the user asks
  not to publish.
