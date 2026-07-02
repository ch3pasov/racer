# Racer Sprites v3 Sources

This folder is the art source for `../racer-sprites-v3.png`.

Each final sprite must be a generated or repainted transparent PNG named after
the runtime sprite key, for example `PLAYER_STRAIGHT.png` or `PALM_TREE.png`.
`tools/generate-racer-textures.py` only packs, scales, bottom-aligns, validates,
and syncs JSON/Lua rects. It must not draw the sprite art procedurally.

Sprites may start from AI contact sheets, but the committed files in this folder
are the project-bound transparent PNG sources. Billboards must contain no brands,
logos, letters, numbers, or tiny text. The palm must be asymmetric and read like
the original right-side roadside palm, leaning from right toward left.

To save an image produced by the built-in Codex image generator, run:

```sh
python3 tools/save-codex-image.py --kind generated --output assets/racer/textures/v3-sheets/name.png
```

Use `--kind input` for the latest image attached in chat. This reads local
Codex session data only; it does not call an image API or require an API key.
