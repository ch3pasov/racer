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
- Published Roblox image asset: `97168588013133`

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

Most results were not suitable for this project. Common problems:

- mixed side/front/rear views instead of consistent rear-view pseudo-3D sprites;
- copyrighted/fan-art source material;
- realistic 3D/photo cutouts that clash with the arcade atlas;
- mesh/model assets instead of 2D atlas textures;
- standalone decals rather than a coherent full racer sprite set;
- low vote/metadata signal, making reuse quality and licensing hard to trust.

Notable candidates checked:

| Asset | Type | Notes |
| --- | --- | --- |
| [108410694017959](https://create.roblox.com/store/asset/108410694017959) | Decal | `spritesheet2`; side-view ship/car-like sprites, not compatible with rear-view racer. |
| [14831485180](https://create.roblox.com/store/asset/14831485180) | Decal | DeLorean sprite sheet; visually rich but fan-art/copyright/attribution concerns and mixed views. |
| [78927027680410](https://create.roblox.com/store/asset/78927027680410) | Decal | F-Zero-style sprite sheet; useful style reference, not safe or stylistically aligned enough as a direct asset. |
| [16261426165](https://create.roblox.com/store/asset/16261426165) | Decal | Street car sprite sheet; too dark/small for this road renderer. |
| [18757616108](https://create.roblox.com/store/asset/18757616108) | Decal | Tropical palm cutout; readable, but cartoon-outline style clashes with the current atlas. |
| [70636676983090](https://create.roblox.com/store/asset/70636676983090) | Decal | Realistic palm cutout; too photo/3D-like for arcade texture mode. |
| [5455116793](https://create.roblox.com/store/asset/5455116793) | Decal | Low-poly tree texture for a mesh, not a usable 2D roadside sprite. |

Conclusion: Roblox Marketplace is useful for reference, but not as a direct
source for a full replacement texture atlas.

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

## Recommendation

Best path: keep the current code-generated atlas workflow and improve it
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
