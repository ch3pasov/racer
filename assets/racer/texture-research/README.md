# Racer Texture Research

Research scope: optional texture mode only. The no-texture renderer is not part
of this experiment and should not change.

## Current Texture Pipeline

- Production atlas: `assets/racer/textures/racer-sprites-v3.png`
- Atlas size: 1024 x 1024 RGBA
- Art sources: `assets/racer/textures/v3-sources/*.png`
- Runtime mapping: `src/racer/shared/RacerTextures.lua`
- Important constraint: texture rects may change, but gameplay sprite dimensions
  in `RacerConfig` and visible sprite bottom alignment must stay unchanged.
- Current Roblox image asset: `116610660748551`
- Previous published Roblox image asset: `87016509555518`

## Roblox Creator Marketplace Search

Searched Roblox Open Cloud toolbox/marketplace endpoints for Decals, Models, and
Meshes with queries including:

- `racing sprite pack`
- `racing car sprite`
- `race car sprites`
- `car sprite sheet`
- `pixel car sprite`
- `outrun car sprite`
- `palm tree sprite`
- `low poly tree texture`
- `arcade racer sprites`
- `2d racing assets`
- `rear view racing car sprite pack`
- `arcade racer spritesheet`
- `pseudo 3d racing sprites`
- `pixel racing car rear`
- `outrun car sprite sheet`
- `2d racing asset pack`
- `low poly arcade sports car`

Most results were not suitable for this project. Common problems:

- mixed side/front/rear views instead of consistent rear-view pseudo-3D sprites;
- copyrighted/fan-art source material;
- realistic 3D/photo cutouts that clash with the arcade atlas;
- mesh/model assets instead of 2D atlas textures;
- standalone decals rather than a coherent full racer sprite set;
- low vote/metadata signal, making reuse quality and licensing hard to trust.

Notable candidates checked are recorded below using the full listing and Toolbox
metadata. Creator Store does not expose original pixel dimensions for these
Decals, so those records say `not exposed` instead of substituting a thumbnail
size. Transparency is likewise marked unverified when native pixels were not
available. `N/A` is reserved for fields that do not apply to that asset type.

### [108410694017959 — spritesheet2](https://create.roblox.com/store/asset/108410694017959)

- Creator: `@e1ectricdog`; free Decal listing, no votes or provenance evidence.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: not verified from native pixels.
- Available views: one flat sheet of mixed side-view ship/car-like sprites; no
  coherent rear-view sequence.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); the mixed sheet contains unrelated sprites.
- Style match: no; the mixed side-view sheet does not match the rear pseudo-3D
  NPC-car language.
- Six-pose readiness: no normal/uphill rear L/S/R set.
- Obvious IP/licensing concern: no named franchise in the listing, but originality
  and source licensing are not established.
- Rejection: wrong viewpoint, mixed content, incomplete pose set, and weak
  provenance.

### [14831485180 — DELOREAN SPRITE SHEET](https://create.roblox.com/store/asset/14831485180)

- Creator: `@MRZ_106`; free Decal listing with no votes.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: not verified from native pixels.
- Available views: one flat sheet with mixed vehicle views rather than six
  controlled rear poses.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); the sheet is vehicle art, but not the required pose set.
- Style match: visually detailed, but its franchise-specific rendering and mixed
  views do not match the project NPC cars.
- Six-pose readiness: no coherent normal/uphill rear L/S/R set.
- Obvious IP/licensing concern: explicit DeLorean design/name and likely fan-art
  provenance create third-party trademark/copyright risk.
- Rejection: mixed views, unsafe provenance, and no production-ready six-frame
  sequence.

### [78927027680410 — F Zero Sprites](https://create.roblox.com/store/asset/78927027680410)

- Creator: `Hotdog Pizza` group; latest listed updater `@KNum_5`; free Decal with
  no votes.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: not verified from native pixels.
- Available views: one flat multi-sprite sheet, not a controlled six-pose rear
  render of one car.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); multiple franchise sprites are unrelated to the required single car.
- Style match: no; the F-Zero vehicle language does not match `CAR01`–`CAR04`.
- Six-pose readiness: no normal/uphill rear L/S/R set for one coherent car.
- Obvious IP/licensing concern: the listing explicitly identifies Nintendo's
  F-Zero property, so direct reuse is unsafe.
- Rejection: third-party IP, mixed subjects, incompatible style, and missing
  poses.

### [16261426165 — street car sprite sheet](https://create.roblox.com/store/asset/16261426165)

- Creator: `@papa201763`; free Decal listing with no votes and only the description
  `madeinstudio` as provenance.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: not verified from native pixels.
- Available views: one flat sheet; inspection found no coherent rear normal/uphill
  L/S/R sequence.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); no useful non-car content, but the frames are too small/dark.
- Style match: no; tonal range and pixel size are too dark and small for the road
  renderer and existing NPC cars.
- Six-pose readiness: no production-ready six-frame rear set.
- Obvious IP/licensing concern: no recognizable brand or franchise, but the short
  description does not establish original authorship or reuse provenance.
- Rejection: unreadable gameplay scale, incomplete pose set, and weak provenance.

### [18757616108 — Tropical palm tree cut-out!](https://create.roblox.com/store/asset/18757616108)

- Creator: `@WhoooooyuFan9000`; free Decal listing with no votes.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: listing/preview presents a cutout, but native alpha was not
  verified.
- Available views: one flat palm cutout; no alternate views.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); no unrelated instances.
- Style match: readable, but its cartoon outline clashes with the current
  roadside art.
- Six-pose readiness: no; `N/A` as a non-vehicle candidate.
- Obvious IP/licensing concern: the uploader explicitly says they do not know the
  original creator, so provenance is unacceptable.
- Rejection: incompatible style and explicitly unknown original authorship.

### [70636676983090 — Palm Tree 1](https://create.roblox.com/store/asset/70636676983090)

- Creator: `@Kxyuum`; free Decal listing with no votes.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: preview reads as a cutout, but native alpha was not verified.
- Available views: one flat realistic palm cutout; no alternate views.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); no unrelated instances.
- Style match: no; the photo/3D-like finish conflicts with arcade texture mode.
- Six-pose readiness: no; `N/A` as a non-vehicle candidate.
- Obvious IP/licensing concern: no recognizable brand, but the listing provides no
  source attribution for the realistic image.
- Rejection: incompatible photographic finish and insufficient provenance.

### [5455116793 — Low+Poly_Simple+Tree+Texture](https://create.roblox.com/store/asset/5455116793)

- Creator: `@Mekrouu`; free Decal listing with no votes.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: not verified; it is presented as a mesh surface texture rather
  than a standalone cutout.
- Available views: one flat texture intended for a low-poly tree mesh.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); no unrelated instances.
- Style match: no as a 2D roadside sprite; it requires geometry to read correctly.
- Six-pose readiness: no; `N/A` as a non-vehicle candidate.
- Obvious IP/licensing concern: no recognizable third-party IP, but original
  texture provenance is not documented.
- Rejection: wrong asset role and unusable without a 3D mesh.

### [107091801827045 — Pixel Racer 3D Transparent](https://create.roblox.com/store/asset/107091801827045)

- Creator: `@devgstreams`; verified Creator Store account, free Decal, and no
  votes/reviews.
- Native dimensions: not exposed by the Creator Store listing or Toolbox metadata.
- Transparency: claimed by the title/preview, but native alpha was not verified.
- Available views: one side-view logo/text decal; no rear vehicle views.
- Scripts/unrelated content: 0 scripts (`N/A` for executable instances in a
  Decal); the logo/text itself is unrelated to the required car sprite.
- Style match: no; it is branding artwork rather than `CAR01`–`CAR04`-style car
  art.
- Six-pose readiness: no; it supplies zero required rear poses.
- Obvious IP/licensing concern: no recognizable franchise, but embedded branding
  and unproven image provenance make direct reuse undesirable.
- Rejection: wrong subject and viewpoint, embedded text/logo, no pose set, and no
  review signal.

### [17135134153 — Low Poly Car](https://create.roblox.com/store/asset/17135134153)

- Creator: `@KyIord`; verified Creator Store account, free Model, and no votes or
  reviews.
- Native dimensions: `N/A` for a Model; 6 MeshParts, 2,308 triangles, and 3,756
  vertices.
- Transparency: `N/A` for evaluating this 3D model as a raster source.
- Available views: rotatable 3D model inspected beyond its thumbnail; rear and
  three-quarter geometry is too primitive for the target silhouettes.
- Scripts/unrelated content: 0 scripts, animations, decals, audio, or tools; no
  unrelated instances were found.
- Style match: weak; generic low-poly geometry lacks the established arcade
  sprite finish and rear detail.
- Six-pose readiness: potentially renderable from six cameras, but no authored
  sprites and insufficient rear geometry for production output.
- Obvious IP/licensing concern: no recognizable brand or franchise; however, the
  listing has no ratings or other evidence establishing original provenance.
- Rejection: weak rear geometry, no ready sprite poses, and insufficient
  provenance/quality signal.

### [163028407 — 2014 CES Motors Ampustar](https://create.roblox.com/store/asset/163028407)

- Creator: `@Fifteenth_Vessel`; verified Creator Store account, free Model, and no
  votes.
- Native dimensions: `N/A` for a Model; 2,602 triangles and 4,580 vertices.
- Transparency: `N/A` for evaluating this 3D model as a raster source.
- Available views: rotatable 3D model, but no authored rear normal/uphill sprite
  sequence.
- Scripts/unrelated content: 0 scripts, MeshParts, animations, decals, audio, or
  tools in Toolbox metadata; no unrelated gameplay content was found.
- Style match: weak; the older 3D vehicle would need a new render and full pixel-art
  treatment to match the atlas.
- Six-pose readiness: theoretically renderable, but it supplies no ready poses or
  reproducible sprite-render setup.
- Obvious IP/licensing concern: no recognizable external franchise, but the old
  listing has no ratings or reliable authorship/reuse evidence beyond its uploader.
- Rejection: no ready sprite output, weak provenance signal, and substantial
  conversion work with no quality advantage.

### [6433323089 — Sports Car](https://create.roblox.com/store/asset/6433323089)

- Creator: official verified `@Roblox`; endorsed free Model with a strong rating
  signal.
- Native dimensions: `N/A` for a Model; 92 MeshParts, 54,816 triangles, and
  62,864 vertices.
- Transparency: `N/A` for evaluating this 3D model as a raster source.
- Available views: full rotatable 3D vehicle, but no authored six-frame 2D sprite
  set.
- Scripts/unrelated content: 12 scripts plus 6 animations, 16 decals, and 24 audio
  instances; realistic driving systems and media are unrelated to sprite capture.
- Style match: no without extensive rerendering and repainting; detail density and
  realistic finish exceed the NPC-car language.
- Six-pose readiness: camera renders are possible, but no ready normal/uphill rear
  L/S/R frames exist and the model is excessive for this pipeline.
- Obvious IP/licensing concern: no obvious concern for Roblox-platform reuse; it is
  an official Roblox asset.
- Rejection: script-heavy, over-complex, mismatched finish, and no production-ready
  six-pose sprite output.

Conclusion: no inspected Creator Store decal supplied a coherent six-pose
rear-view pack, and no inspected model combined safe provenance, rear geometry,
low complexity, and a reproducible six-pose render path. No Store asset was
imported into the player-car sources.

## Generated Candidates

Generated locally using the existing procedural atlas generator, redirected into
this research folder so production texture mode remains unchanged:

- `generated/procedural-current-style.png`
- `generated/procedural-neon-style.png`

The `procedural-current-style` candidate verifies that the existing generator can
rebuild the current atlas shape safely in a separate output path. The
`procedural-neon-style` candidate tests a brighter arcade palette while keeping
the same sprite geometry and atlas slots.

An AI image-generation concept pass was also tested with this prompt direction:

> Cohesive retro arcade racing sprite atlas concept, 1024x1024, Jake
> Gordon-style pseudo-3D road racer, rear-view cars only, roadside objects,
> colorful billboards, no logos, no copyrighted vehicles, no text.

The generated concept was directionally better than Marketplace search results
as a style exploration, but not precise enough to drop into the existing atlas
without a manual cleanup/repaint step.

For the 2026-07-15 player-car replacement, a new six-pose image-generation pass
was inspected and rejected as raster input: the turning frames exposed forward
wheels, the open rollbar area would become alpha holes after chroma removal, and
all six cars floated inside their cells. It was not copied, keyed, cropped, or
packed. The accepted player car was instead authored directly on six exact RGBA
source canvases with shared deterministic geometry and the project's established
NPC palette language. This leaves the production artwork with no external asset
or rejected-sheet dependency.

## Recommendation

Best path: keep the deterministic source-and-atlas workflow and improve it
incrementally. It is safer than Marketplace reuse because it gives us:

- exact atlas coordinates;
- exact bottom alignment;
- no copyright/fan-art dependency;
- consistent rear-view car language;
- reproducible edits and small diffs.

The first production-quality iteration is `racer-sprites-v3.png` from the
procedural generator, focused on:

- cleaner palm/tree silhouettes at distance;
- more distinctive NPC car colors and roofs;
- less flat billboard art;
- slightly stronger outlines on roadside objects;
- preserving all existing sprite rectangles and collision/render parity.

The v3 palm is intentionally asymmetric: it follows the original right-side
roadside read, with the trunk/crown direction moving from right toward left
across the road. The generator and parity check both validate that silhouette so
future edits do not accidentally replace it with a centered or right-facing
palm.
