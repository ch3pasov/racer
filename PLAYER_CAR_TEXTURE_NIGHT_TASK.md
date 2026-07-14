# Night task: replacement player-car sprites

Date: 2026-07-14

## Goal

Replace the player car art from scratch with a production-quality set of six
rear-view sprites:

- normal road: left, straight, right;
- uphill: left, straight, right.

The current player-car result is rejected. Do not use any current generated
player-car image, paint sheet, or in-game screenshot as a visual reference.
Use the original Jake Gordon Racer frames only as pose, silhouette, framing,
and perspective templates. The car's rendering style should match the good NPC
cars already in this project (`CAR01` through `CAR04`).

## User requirements

- The car must contain no people. Driver-icon sprites will be composited over
  the car later.
- Keep a clearly readable empty cockpit/interior, not transparent holes through
  the body.
- The left and right turns must read immediately during play. They cannot be
  near-identical straight sprites with a small horizontal shift.
- Normal and uphill frames must have visibly different camera pitch, matching
  the original Racer poses.
- The uphill car must not look substantially smaller than the normal car.
- Keep the original rear-view composition. In particular, front wheels must not
  become visible.
- Keep crisp, deliberate edges and solid body panels. No broken alpha, pinholes,
  smeared highlights, noisy AI fragments, or blur from repeated resizing.
- The visible bottom pixel of every sprite must touch the bottom edge of its
  sprite rectangle, so the car never floats above the road.
- Preserve the gameplay dimensions and hitbox. This is an art replacement, not
  a handling or collision change.
- Once a replacement is accepted, remove obsolete rejected generated
  player-car sheets instead of retaining them as future references.

## Visual reference hierarchy

1. Original Jake Gordon Racer player frames: geometry, steering poses, uphill
   pitch, framing, and bottom alignment only.
2. Current project NPC cars: palette language, pixel density, outline weight,
   lighting, taillights, bumper, and overall finish.
3. A legally usable Creator Store asset, if a genuinely suitable one is found:
   vehicle design/details only.
4. Never use the current player-car attempts as a reference.

Six extracted original-pose files currently exist at
`/tmp/original-player_*.png`. Treat that location as ephemeral; recover the
original frames again if they are unavailable when the task runs.

## First task: search Roblox Creator Store

Search Decals, Images, Models, and MeshParts for coherent assets using terms
such as:

- `rear view racing car sprite pack`
- `arcade racer spritesheet`
- `pseudo 3d racing sprites`
- `pixel racing car rear`
- `outrun car sprite sheet`
- `2d racing asset pack`
- `low poly arcade sports car`

Do not accept a result from its thumbnail alone. For every plausible candidate,
inspect the full asset and record:

- Creator Store URL and asset ID;
- creator name and whether the upload looks original/trustworthy;
- asset type, native image dimensions, transparency, and available views;
- whether it contains scripts or unrelated instances;
- whether it has branding, watermarks, fan-art, or obvious third-party IP;
- whether it can provide all six required poses at gameplay quality.

Reject side-view packs, top-down packs, front-view packs, single tiny decals,
mixed-style sheets, copyrighted franchise/fan-art uploads, and assets whose
reuse rights or provenance are dubious. Previous research is in
`assets/racer/texture-research/README.md`; the candidates listed there were
already judged unsuitable and should not be proposed again without new
evidence.

An acceptable ready-made six-frame 2D pack is preferred. If none exists, a
clean, script-free, legally usable 3D car model may be considered as a source:
render it from six controlled rear camera poses and fit those renders to the
original silhouettes. Do not put a 3D model into gameplay; the production
result must remain six transparent PNG sprites in the existing atlas.

If the Creator Store has no suitable source, state that clearly. Do not force a
bad marketplace asset into the game just to complete the search step.

## Current project state

- Last clean implementation commit before this handoff:
  `bb1a7ea07790` (`textures: restore high-detail player car paint`).
- Current published Roblox place: `PlaceVersion 226`.
- Current published texture asset: `87016509555518`.
- Production atlas: `assets/racer/textures/racer-sprites-v3.png` (1024 x 1024).
- Sprite sources: `assets/racer/textures/v3-sources/PLAYER_*.png`.
- Rejected generated sheets: `assets/racer/textures/v3-sheets/`.
- Runtime atlas mapping: `src/racer/shared/RacerTextures.lua`.
- Gameplay dimensions: `src/racer/shared/RacerConfig.lua`.
- Packing pipeline: `tools/generate-racer-textures.py`.
- Current rejected repaint pipeline:
  `tools/prepare-original-template-player-car.py`.

Runtime/gameplay sizes must remain:

| Pose | Width | Height |
| --- | ---: | ---: |
| normal left/straight/right | 80 | 41 |
| uphill left/straight/right | 80 | 45 |

Current atlas rectangles are 120 x 62 for normal frames and 120 x 68 for
uphill frames. They may change only if the atlas packer/runtime mapping is
updated together and the gameplay dimensions above remain unchanged.

## Why the current result failed

- Original alpha masks cut generated paint into holes and damaged solid body
  panels.
- Several resizing/compositing passes turned highlights and outlines into
  blurry, uneven pixels.
- Earlier turn variants did not communicate steering strongly enough.
- Earlier uphill variants changed apparent car size more than camera pitch.
- AI paint details were forced through geometry they were not drawn for.

Do not solve these failures by adding another paint layer to the current files.
Build or acquire six coherent sprites whose artwork already fits each final
pose.

## Implementation constraints

- Keep transparent RGBA PNG sources.
- Work at a consistent integer scale and downsample at most once to final atlas
  resolution. Avoid repeated resize/mask/resize cycles.
- Alpha outside the silhouette must be clean. Body, bumper, taillights, plate,
  and interior surfaces must not contain accidental transparent pixels.
- Keep all six sprites stylistically and proportionally consistent.
- Keep the image bottom-aligned through source, atlas, and runtime rendering.
- Do not alter v1-v4 original Racer behavior or unrelated texture sprites.
- Do not change player physics, collision, steering thresholds, or camera code.
- Do not add scripts from Creator Store models to the repository or place.

## Acceptance checks

Create a six-pose contact sheet at native size and a second preview enlarged
with nearest-neighbor scaling. Check all of the following before publishing:

- all six poses are present and belong to the same car;
- left/straight/right are distinguishable without labels;
- normal/uphill are distinguishable by pitch, not by shrinking the car;
- no people are painted into any frame;
- no front wheels are visible;
- no internal alpha holes or detached fragments exist;
- each silhouette reaches its frame's bottom row;
- the car remains readable against both light and dark road/background areas;
- the in-game result is crisp at the actual Racer viewport scale;
- driver-icon overlay space remains unobstructed.

Run the texture packer and parity checks, then test in Roblox while steering
left/right on level road and while cresting/climbing a hill. Capture screenshots
of at least straight, hard left, hard right, and uphill straight states. A
contact sheet alone is not sufficient acceptance evidence.

## Commit and publish

Keep this replacement in one focused feature commit. Publish only after checks
pass and the tree is committed and clean. Embed the exact commit in build
metadata, record the resulting Roblox `PlaceVersion` to commit mapping, and
verify that the published version can be looked up by version number. Do not
publish an exploratory Creator Store candidate before it passes the visual
checks above.
