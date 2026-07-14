# Racer Sprites v3 Sources

This folder is the art source for `../racer-sprites-v3.png`.

Each final sprite is a project-bound transparent PNG named after the runtime
sprite key, for example `PLAYER_STRAIGHT.png` or `PALM_TREE.png`.
`tools/generate-racer-textures.py` packs, validates, and syncs JSON/Lua rects.
It must not redraw or independently fit the player car.

Sprites may start from AI contact sheets, but the committed files in this folder
are the project-bound transparent PNG sources. Billboards must contain no brands,
logos, letters, numbers, or tiny text. The palm must be asymmetric and read like
the original right-side roadside palm, leaning from right toward left.

The six player-car sources are authored from scratch by the deterministic shared
geometry in `tools/create-player-car-sprites.py`. They use no third-party raster,
original-game paint, alpha mask, screenshot, or rejected sheet. Regenerate them
and the atlas with:

```sh
python3 tools/create-player-car-sprites.py
python3 tools/generate-racer-textures.py
```

Player normal sources are exactly 320 x 164 RGBA; uphill sources are exactly
320 x 180 RGBA. Their connected opaque silhouettes touch only the bottom canvas
edge. The packer validates the six-file inventory, dimensions, alpha topology,
bottom contact, steering perspective, uphill pitch, and apparent size. It then
area-downsamples each full canvas once in premultiplied alpha to 120 x 62 or
120 x 68. Gameplay and hitbox sizes remain 80 x 41 or 80 x 45.
