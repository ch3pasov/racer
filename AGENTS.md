# Agent Rules

- When the user complains about behavior that belongs to the original Jake
  Gordon Racer feature set, first inspect the original implementation at
  https://jakesgordon.com/games/racer/ and then make this project match that
  behavior. Do not treat such complaints as new feature requests until the
  original behavior has been checked.
- For Racer texture work, sprite art must match the existing gameplay/render
  hitbox. In particular, the visible bottom of each sprite must sit on the
  sprite rectangle bottom edge so cars and roadside objects do not visually
  float above the ground.
- When a requested task has been implemented and local checks pass, publish the
  Racer Lab place if the publish environment is available. Do not wait for a
  separate publish request unless there is a concrete blocker or the user asks
  not to publish.
