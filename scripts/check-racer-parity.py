#!/usr/bin/env python3
from pathlib import Path
import re
import sys
import math
import struct
import zlib


ROOT = Path(__file__).resolve().parents[1]
CONFIG = (ROOT / "src/racer/shared/RacerConfig.lua").read_text()
CLIENT = (ROOT / "src/racer/client/Main.client.lua").read_text()
SERVER = (ROOT / "src/racer/server/Main.server.lua").read_text()
MATH = (ROOT / "src/racer/shared/RacerMath.lua").read_text()
TEXTURES = (ROOT / "src/racer/shared/RacerTextures.lua").read_text()


def fail(message: str):
    print(f"FAIL: {message}")
    sys.exit(1)


def require(pattern: str, text: str, message: str):
    if not re.search(pattern, text, re.MULTILINE | re.DOTALL):
        fail(message)


def read_png_rgba(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        fail(f"{path} must be a PNG")
    offset = 8
    width = height = None
    color_type = None
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or color_type != 6:
                fail(f"{path} must be an 8-bit RGBA PNG")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None or color_type is None:
        fail(f"{path} has no PNG header")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type != 0:
            fail(f"{path} must use unfiltered scanlines for parity inspection")
        rows.append(row)
        previous = row
    return width, height, rows


SPRITE_SCALE = 0.3 / 80
PLAYER_WIDTH = 80 * SPRITE_SCALE


def overlap(x1: float, w1: float, x2: float, w2: float, percent: float = 1.0) -> bool:
    half = percent / 2
    min1 = x1 - (w1 * half)
    max1 = x1 + (w1 * half)
    min2 = x2 - (w2 * half)
    max2 = x2 + (w2 * half)
    return not ((max1 < min2) or (min1 > max2))


def roadside_center(offset: float, sprite_width: int) -> float:
    side = 1 if offset > 0 else -1
    return offset + (sprite_width * SPRITE_SCALE / 2 * side)


def original_render_sprite_center(offset: float, sprite_width: int) -> float:
    # Render.sprite uses an edge anchor for roadside sprites:
    # offsetX = -1 for left-side sprites, 0 for right-side sprites.
    offset_x = -1 if offset < 0 else 0
    sprite_width_world = sprite_width * SPRITE_SCALE
    return offset + sprite_width_world * (offset_x + 0.5)


version = re.search(r'VersionBuild\s*=\s*"([^"]+)"', CONFIG)
if not version:
    fail("RacerConfig.VersionBuild must be present")

if "game.PlaceVersion" not in SERVER:
    fail("version badge must use DataModel.PlaceVersion instead of a manually bumped build number")

if "label.Text = `build {RacerConfig.VersionBuild}`" in SERVER:
    fail("version badge must not render the manual VersionBuild directly")

texture_asset = re.search(r'Image\s*=\s*"rbxassetid://(\d+)"', TEXTURES)
if not texture_asset:
    fail("RacerTextures.Image must point at an uploaded Roblox image asset")

texture_png = ROOT / "assets/racer/textures/racer-sprites-v2.png"
if not texture_png.exists():
    fail("local racer texture atlas must exist")
texture_width, texture_height, texture_rows = read_png_rgba(texture_png)
for match in re.finditer(
    r"([A-Z0-9_]+)\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+),\s*w\s*=\s*(\d+),\s*h\s*=\s*(\d+)\s*\}",
    TEXTURES,
):
    name, x, y, w, h = match.groups()
    x, y, w, h = int(x), int(y), int(w), int(h)
    if x < 0 or y < 0 or x + w > texture_width or y + h > texture_height:
        fail(f"texture rect for {name} is outside the atlas")
    bottom_row = texture_rows[y + h - 1]
    bottom_alpha_count = sum(1 for pixel_x in range(x, x + w) if bottom_row[pixel_x * 4 + 3] > 0)
    if bottom_alpha_count == 0:
        fail(f"texture sprite {name} must touch the bottom of its hitbox rect")

expected_sprites = {
    "PALM_TREE": (215, 540),
    "BILLBOARD08": (385, 265),
    "TREE1": (360, 360),
    "DEAD_TREE1": (135, 332),
    "BILLBOARD09": (328, 282),
    "BOULDER3": (320, 220),
    "COLUMN": (200, 315),
    "BILLBOARD01": (300, 170),
    "BILLBOARD06": (298, 190),
    "BILLBOARD05": (298, 190),
    "BILLBOARD07": (298, 190),
    "BOULDER2": (298, 140),
    "TREE2": (282, 295),
    "BILLBOARD04": (268, 170),
    "DEAD_TREE2": (150, 260),
    "BOULDER1": (168, 248),
    "BUSH1": (240, 155),
    "CACTUS": (235, 118),
    "BUSH2": (232, 152),
    "BILLBOARD03": (230, 220),
    "BILLBOARD02": (215, 220),
    "STUMP": (195, 140),
    "SEMI": (122, 144),
    "TRUCK": (100, 78),
    "CAR03": (88, 55),
    "CAR02": (80, 59),
    "CAR04": (80, 57),
    "CAR01": (80, 56),
    "PLAYER_UPHILL_LEFT": (80, 45),
    "PLAYER_UPHILL_STRAIGHT": (80, 45),
    "PLAYER_UPHILL_RIGHT": (80, 45),
    "PLAYER_LEFT": (80, 41),
    "PLAYER_STRAIGHT": (80, 41),
    "PLAYER_RIGHT": (80, 41),
    "PLAYER_DOWNHILL_LEFT": (80, 41),
    "PLAYER_DOWNHILL_STRAIGHT": (80, 41),
    "PLAYER_DOWNHILL_RIGHT": (80, 41),
}

for name, (width, height) in expected_sprites.items():
    require(
        rf"{name}\s*=\s*\{{[^}}]*width\s*=\s*{width}[^}}]*height\s*=\s*{height}",
        CONFIG,
        f"{name} dimensions must match javascript-racer common.js",
    )
    require(
        rf"{name}\s*=\s*\{{\s*x\s*=\s*\d+,\s*y\s*=\s*\d+,\s*w\s*=\s*\d+,\s*h\s*=\s*\d+\s*\}}",
        TEXTURES,
        f"texture rect missing for {name}",
    )

if abs(PLAYER_WIDTH - 0.3) > 1e-9:
    fail("player collision width must be SPRITES.PLAYER_STRAIGHT.w * SPRITES.SCALE = 0.3")

for offset, sprite_name in [(-1.2, "BILLBOARD07"), (1.2, "BILLBOARD06"), (-2.4, "TREE1")]:
    sprite_width = expected_sprites[sprite_name][0]
    center = roadside_center(offset, sprite_width)
    render_center = original_render_sprite_center(offset, sprite_width)
    if abs(center - render_center) > 1e-9:
        fail(f"{sprite_name} collision center must match original Render.sprite visual center")

if not overlap(-1.06, PLAYER_WIDTH, roadside_center(-1.2, expected_sprites["BILLBOARD07"][0]), expected_sprites["BILLBOARD07"][0] * SPRITE_SCALE):
    fail("left roadside billboard should collide at the original edge-touch boundary")

if not overlap(1.06, PLAYER_WIDTH, roadside_center(1.2, expected_sprites["BILLBOARD06"][0]), expected_sprites["BILLBOARD06"][0] * SPRITE_SCALE):
    fail("right roadside billboard should collide at the original edge-touch boundary")

if overlap(0.95, PLAYER_WIDTH, roadside_center(1.2, expected_sprites["BILLBOARD06"][0]), expected_sprites["BILLBOARD06"][0] * SPRITE_SCALE):
    fail("roadside collision must not trigger while player is still inside the road")

for sample_name in ["PALM_TREE", "TREE1", "BOULDER3", "BUSH1", "COLUMN"]:
    sample_width = expected_sprites[sample_name][0] * SPRITE_SCALE
    sample_center = roadside_center(1.2, expected_sprites[sample_name][0])
    if not overlap(sample_center, PLAYER_WIDTH, sample_center, sample_width):
        fail(f"{sample_name} must use the same roadside collision formula as billboards")

car01_width = expected_sprites["CAR01"][0] * SPRITE_SCALE
if not overlap(0, PLAYER_WIDTH, 0.239, car01_width, 0.8):
    fail("traffic collision should include the original 0.8 overlap edge")

if overlap(0, PLAYER_WIDTH, 0.241, car01_width, 0.8):
    fail("traffic collision should not be wider than original 0.8 overlap")

expected_sets = {
    "Billboards": [
        "BILLBOARD01",
        "BILLBOARD02",
        "BILLBOARD03",
        "BILLBOARD04",
        "BILLBOARD05",
        "BILLBOARD06",
        "BILLBOARD07",
        "BILLBOARD08",
        "BILLBOARD09",
    ],
    "Plants": [
        "TREE1",
        "TREE2",
        "DEAD_TREE1",
        "DEAD_TREE2",
        "PALM_TREE",
        "BUSH1",
        "BUSH2",
        "CACTUS",
        "STUMP",
        "BOULDER1",
        "BOULDER2",
        "BOULDER3",
    ],
    "Cars": ["CAR01", "CAR02", "CAR03", "CAR04", "SEMI", "TRUCK"],
}

for set_name, names in expected_sets.items():
    match = re.search(rf"{set_name}\s*=\s*\{{(.*?)\}}", CONFIG, re.MULTILINE | re.DOTALL)
    if not match:
        fail(f"missing SpriteSets.{set_name}")
    actual = re.findall(r'"([^"]+)"', match.group(1))
    if actual != names:
        fail(f"SpriteSets.{set_name} order must match javascript-racer: {actual} != {names}")

expected_mode_flags = {
    "straight": {
        "curves": False,
        "hills": False,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "curves": {
        "curves": True,
        "hills": False,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "hills": {
        "curves": True,
        "hills": True,
        "sprites": False,
        "traffic": False,
        "laps": False,
        "hud": False,
    },
    "final": {
        "curves": True,
        "hills": True,
        "sprites": True,
        "traffic": True,
        "laps": True,
        "hud": True,
    },
}

for mode, expected_flags in expected_mode_flags.items():
    require(rf"{mode}\s*=\s*\{{", CONFIG, f"missing mode flags for {mode}")
    if mode == "final":
        require(r"local\s+finalTrack\s*=\s*buildFinalTrack\(\)", CONFIG, "missing inherited final track source")
        require(r"final\s*=\s*finalTrack", CONFIG, "missing final track assignment")
    else:
        require(rf"{mode}\s*=\s*build", CONFIG, f"missing track for {mode}")
    mode_match = re.search(rf"\n\t{mode}\s*=\s*\{{(.*?)\n\t\}},", CONFIG, re.DOTALL)
    if not mode_match:
        fail(f"could not parse mode flags for {mode}")
    actual_flags = {
        name: value == "true"
        for name, value in re.findall(r"(\w+)\s*=\s*(true|false)", mode_match.group(1))
    }
    for flag, expected in expected_flags.items():
        if actual_flags.get(flag) is not expected:
            fail(f"{mode}.{flag} must be {expected} to match v1-v4 feature rollout")

for token in [
    "RacerConfig.Modes.v5 = derive(RacerConfig.Modes.final",
    "v5 = finalTrack",
    "local finalSpriteObjects = RacerConfig.buildSpriteObjects(\"final\", 2401)",
    "v5 = shallowArrayCopy(finalSpriteObjects)",
]:
    if token not in CONFIG:
        fail(f"v5 must explicitly inherit v4 final before adding v5-only behavior: {token}")

for token in [
    "addStraight(track, ROAD.LENGTH.SHORT)",
    "addFinalLowRollingHills(track)",
    "addSCurves(track)",
    "addBumps(track)",
    "addDownhillToEnd(track)",
]:
    if token not in CONFIG:
        fail(f"v4 resetRoad token missing: {token}")

for token in [
	"buildSpriteObjects",
	"BILLBOARD07",
	"PALM_TREE",
	"COLUMN",
	"SpriteSets.Plants",
	"Count = 200",
	"offset = deterministicUnit(trafficSeed + index * 13) * 0.8 * side",
	"* (if spriteSize.height > 100 then 0.25 else 0.5)",
	"PlayerWidth = RacerConfig.PlayerSprite.Width * RacerConfig.SpriteScale",
	"CollisionOverlap = 0.8",
	"RoadsideCollisionSpeed = RacerConfig.MaxSpeed / 5",
	"roadsideCollisionSprite",
	"trafficCollisionPosition",
	"trafficCollisionCar",
	"playerSpriteDef",
	"playerBounce",
	"applyTrafficOffsets",
	"advanceTraffic",
	"createTrafficState",
	"local function deterministicFloorInt",
	"math.floor(minValue + (maxValue - minValue) * deterministicUnit(seed) + 0.5)",
	"math.floor(minValue + (maxValue - minValue + 1) * deterministicUnit(seed))",
	"deterministicFloorInt(trafficSeed + index * 7, 0, segmentCount - 1)",
	"0.5 + deterministicUnit(spriteSeed + n * 3) * 0.5",
	"1 + deterministicUnit(spriteSeed + n * 5) * 2",
	"n += 4 + math.floor(n / 100)",
	"while n < 1000 and n < segmentCount do",
	"n += 5",
	"side * (2 + deterministicUnit(spriteSeed + n * 29) * 5)",
	"n += 3",
	"while n < segmentCount - 50 do",
	"for i = 0, 19 do",
	"side * (1.5 + deterministicUnit(spriteSeed + n * 53 + i))",
	"n += 100",
	"for _, sprite in RacerConfig.spritesForSegment(mode, segmentIndex) do",
	"local spriteWidth = sprite.definition.width * RacerConfig.SpriteScale",
	"local track = RacerConfig.Tracks[mode]",
	"local bySegment = RacerConfig.SpritesBySegment[mode]",
	"function RacerConfig.roadsideSpriteCenter(sprite): number",
	"local spriteCenter = RacerConfig.roadsideSpriteCenter(sprite)",
	"RacerMath.overlap(playerX, playerWidth, spriteCenter, spriteWidth)",
	"function RacerConfig.roadsideCollisionPosition(",
	"function RacerConfig.trafficCollisionPosition(",
	"function RacerConfig.playerSpriteDef(steer: number, updown: number)",
	"local amplitude = 1.5 * deterministicUnit",
	"return amplitude * speedPercent * resolution * sign",
	"PLAYER_UPHILL_LEFT",
	"PLAYER_UPHILL_RIGHT",
	"PLAYER_UPHILL_STRAIGHT",
	"PLAYER_DOWNHILL_LEFT",
	"PLAYER_DOWNHILL_RIGHT",
	"PLAYER_DOWNHILL_STRAIGHT",
	"PLAYER_STRAIGHT",
	"segmentIndex * RacerConfig.SegmentLength",
	"return RacerMath.increase(trafficZ, -playerZ, trackLength)",
	"maxSpriteObjectsInDrawWindow",
	"width = car.width * RacerConfig.SpriteScale",
	"local carWidth = item.width",
	"and RacerMath.overlap(item.offset, carWidth, other.offset, other.width, 1.2)",
	"RacerConfig.FinalObjectCount = RacerConfig.Traffic.Count",
	"function RacerConfig.baseTrafficOffsets()",
	"packTrafficOffsets",
	"unpackTrafficOffsets",
	"trafficState.items",
	"trafficState.bySegment",
]:
    if token not in CONFIG:
        fail(f"v4 sprite/traffic parity token missing: {token}")

if "DrawDistance = 300" not in CONFIG:
    fail("default drawDistance must match javascript-racer")

if "MaxDrawDistance = 500" not in CONFIG:
    fail("tweak UI maximum drawDistance must match javascript-racer")

if "DrawDistance = { min = 100, max = RacerConfig.MaxDrawDistance, step = 20, default = 300 }" not in SERVER:
    fail("server setting range must allow the original drawDistance maximum")

for token in [
    "RoadWidth = { min = 500, max = 3000, step = 100, default = 2000 }",
    "CameraHeight = { min = 500, max = 5000, step = 100, default = 1000 }",
    "FieldOfView = { min = 80, max = 140, step = 5, default = 100 }",
    "FogDensity = { min = 0, max = 50, step = 1, default = 5 }",
    "Lanes = { min = 1, max = 4, step = 1, default = 3 }",
]:
    if token not in SERVER:
        fail(f"tweak setting range must match javascript-racer controls: {token}")

adjust_setting_body = re.search(
    r"local function adjustSetting\(.*?\nend",
    SERVER,
    re.MULTILINE | re.DOTALL,
)
if not adjust_setting_body:
    fail("missing adjustSetting")
if "resetRun(" in adjust_setting_body.group(0):
    fail("tweak setting changes must not reset the race or rebuild runtime state")

reset_settings_body = re.search(
    r"local function resetSettings\(.*?\nend",
    SERVER,
    re.MULTILINE | re.DOTALL,
)
if not reset_settings_body:
    fail("missing resetSettings")
if "resetRun(" in reset_settings_body.group(0):
    fail("resetting tweak UI values must not reset the race")

if "Vector3.new(24, 18, 0.5)" not in SERVER:
    fail("world arcade screens must keep the original 1024x768 4:3 canvas aspect ratio")

replicated_state_fields = {
    "ActiveUserId": "activeUserId",
    "ActivePlayerName": "activePlayerName",
    "Position": "position",
    "Speed": "speed",
    "TrafficTime": "trafficTime",
    "TrafficOffsets": "trafficOffsetsBlob",
    "CurrentLapTime": "currentLapTime",
    "LastLapTime": "lastLapTime",
    "FastLapTime": "fastLapTime",
    "PlayerX": "playerX",
    "Steer": "steer",
    "SkyOffset": "skyOffset",
    "HillOffset": "hillOffset",
    "TreeOffset": "treeOffset",
    "Status": "status",
    "ScreenName": "screenName",
    "Mode": "mode",
    "SettingRoadWidth": "settingRoadWidth",
    "SettingCameraHeight": "settingCameraHeight",
    "SettingDrawDistance": "settingDrawDistance",
    "SettingFieldOfView": "settingFieldOfView",
    "SettingFogDensity": "settingFogDensity",
    "SettingLanes": "settingLanes",
}

for server_name, client_name in replicated_state_fields.items():
    if f'"{server_name}"' not in SERVER:
        fail(f"server must create replicated race state field {server_name}")
    if f'{client_name} = folder:WaitForChild("{server_name}")' not in CLIENT:
        fail(f"client must load replicated race state field {server_name} as {client_name}")

published_state_fields = [
    "ActiveUserId",
    "ActivePlayerName",
    "Position",
    "Speed",
    "TrafficTime",
    "TrafficOffsets",
    "CurrentLapTime",
    "LastLapTime",
    "FastLapTime",
    "PlayerX",
    "Steer",
    "SkyOffset",
    "HillOffset",
    "TreeOffset",
]

for field_name in published_state_fields:
    if f"session.values.{field_name}.Value" not in SERVER:
        fail(f"server publishState must update {field_name}")

render_signature_fields = [
    "mode",
    "activePlayerName",
    "trafficOffsetsBlob",
    "position",
    "playerX",
    "speed",
    "trafficTime",
    "steer",
    "skyOffset",
    "hillOffset",
    "treeOffset",
    "settingRoadWidth",
    "settingCameraHeight",
    "settingDrawDistance",
    "settingFieldOfView",
    "settingFogDensity",
    "settingLanes",
    "currentLapTime",
    "lastLapTime",
    "fastLapTime",
]
render_signature_body = re.search(
    r"local function renderSignature\(state\): string(.*?)\nend",
    CLIENT,
    re.MULTILINE | re.DOTALL,
)
if not render_signature_body:
    fail("missing renderSignature")
for client_name in render_signature_fields:
    if f"state.{client_name}" not in render_signature_body.group(1):
        fail(f"renderSignature must include {client_name}")

for token in [
    'fullViewport.Name = "RacerViewport"',
    "local aspectRatio = RacerConfig.Width / RacerConfig.Height",
    "height = width / aspectRatio",
    "width = height * aspectRatio",
    'local fullRenderer = createRenderer(fullViewport, "LocalScreen")',
]:
    if token not in CLIENT:
        fail(f"fullscreen renderer must preserve the original 4:3 canvas aspect ratio: {token}")

expected_track_lengths = {
    "straight": 500,
    "curves": 4221,
    "hills": 3564,
    "final": 6705,
}

expected_track_sequences = {
    "curves": [
        "addStraight(track, ROAD.LENGTH.SHORT / 4)",
        "addFlatSCurves(track)",
        "addStraight(track, ROAD.LENGTH.LONG)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)",
        "addStraight(track)",
        "addFlatSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)",
        "addStraight(track)",
        "addFlatSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.EASY)",
    ],
    "hills": [
        "addStraight(track, ROAD.LENGTH.SHORT / 2)",
        "addHill(track, ROAD.LENGTH.SHORT, ROAD.HILL.LOW)",
        "addLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)",
        "addLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)",
        "addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addDownhillToEnd(track)",
    ],
    "final": [
        "addStraight(track, ROAD.LENGTH.SHORT)",
        "addFinalLowRollingHills(track)",
        "addSCurves(track)",
        "addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)",
        "addBumps(track)",
        "addFinalLowRollingHills(track)",
        "addCurve(track, ROAD.LENGTH.LONG * 2, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addHill(track, ROAD.LENGTH.MEDIUM, ROAD.HILL.HIGH)",
        "addSCurves(track)",
        "addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.NONE)",
        "addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)",
        "addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)",
        "addBumps(track)",
        "addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)",
        "addStraight(track)",
        "addSCurves(track)",
        "addDownhillToEnd(track)",
    ],
}

if 'SegmentCount = 500' not in CONFIG:
    fail("v1 straight track must contain 500 segments")

if "math.floor(RacerConfig.PlayerZ / RacerConfig.SegmentLength)" not in CONFIG:
    fail("start segments must be fixed from reset-time playerZ, not current camera settings")

ROAD_LENGTHS = {
    "ROAD.LENGTH.SHORT": 25,
    "ROAD.LENGTH.MEDIUM": 50,
    "ROAD.LENGTH.LONG": 100,
}


def eval_length(expr: str | None, default: int) -> float:
    if not expr:
        return default
    expr = expr.strip()
    for token, value in ROAD_LENGTHS.items():
        expr = expr.replace(token, str(value))
    if not re.fullmatch(r"[0-9\s+\-*/.]+", expr):
        fail(f"unsupported road length expression: {expr}")
    return float(eval(expr, {"__builtins__": {}}, {}))


def road_segments(length: float) -> int:
    return math.ceil(length) * 3


def first_arg(line: str) -> str | None:
    match = re.search(r"\(\s*track\s*(?:,\s*([^,\)]+))?", line)
    return match.group(1) if match else None


def computed_track_length(mode: str) -> int:
    match = re.search(
        rf"local function build{mode.capitalize()}Track\(\)(.*?)return track",
        CONFIG,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        fail(f"missing {mode} track builder")
    total = 0
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith("addStraight"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addHill"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addCurve"):
            total += road_segments(eval_length(first_arg(line), 50))
        elif line.startswith("addLowRollingHills") or line.startswith("addFinalLowRollingHills"):
            total += road_segments(eval_length(first_arg(line), 25)) * 6
        elif line.startswith("addFlatSCurves") or line.startswith("addSCurves"):
            total += road_segments(50) * 5
        elif line.startswith("addBumps"):
            total += road_segments(10) * 8
        elif line.startswith("addDownhillToEnd"):
            total += road_segments(eval_length(first_arg(line), 200))
    return total


def track_call_sequence(mode: str) -> list[str]:
    match = re.search(
        rf"local function build{mode.capitalize()}Track\(\)(.*?)return track",
        CONFIG,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        fail(f"missing {mode} track builder")
    calls = []
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if line.startswith("add"):
            calls.append(line)
    return calls


for mode, expected_count in expected_track_lengths.items():
    actual_count = 500 if mode == "straight" else computed_track_length(mode)
    if actual_count != expected_count:
        fail(f"{mode} track length must match javascript-racer: {actual_count} != {expected_count}")

for mode, expected_calls in expected_track_sequences.items():
    actual_calls = track_call_sequence(mode)
    if actual_calls != expected_calls:
        fail(
            f"{mode} track call sequence must match javascript-racer:\n"
            f"actual={actual_calls}\nexpected={expected_calls}"
        )

for token in [
    "RacerMath.easeIn(0, curve, n / enter)",
    "RacerMath.easeInOut(startY, endY, n / total)",
    "RacerMath.easeInOut(startY, endY, (enter + n) / total)",
    "RacerMath.easeInOut(curve, 0, n / leave)",
    "RacerMath.easeInOut(startY, endY, (enter + hold + n) / total)",
]:
    if token not in CONFIG:
        fail(f"road builder interpolation must match javascript-racer: {token}")


def ease_in(a: float, b: float, percent: float) -> float:
    return a + (b - a) * (percent**2)


def ease_in_out(a: float, b: float, percent: float) -> float:
    return a + (b - a) * ((-math.cos(percent * math.pi) / 2) + 0.5)


ROAD_HILLS = {
    "ROAD.HILL.NONE": 0,
    "ROAD.HILL.LOW": 20,
    "ROAD.HILL.MEDIUM": 40,
    "ROAD.HILL.HIGH": 60,
}

ROAD_CURVES = {
    "ROAD.CURVE.NONE": 0,
    "ROAD.CURVE.EASY": 2,
    "ROAD.CURVE.MEDIUM": 4,
    "ROAD.CURVE.HARD": 6,
}


def eval_track_expr(expr: str | None, default: float, values: dict[str, float]) -> float:
    if not expr:
        return default
    expr = expr.strip()
    for source in (ROAD_LENGTHS, ROAD_HILLS, ROAD_CURVES):
        for token, value in source.items():
            expr = expr.replace(token, str(value))
    if not re.fullmatch(r"[0-9\s+\-*/.]+", expr):
        fail(f"unsupported track expression: {expr}")
    return float(eval(expr, {"__builtins__": {}}, values))


def split_call_args(line: str) -> list[str]:
    match = re.search(r"\((.*)\)", line)
    if not match:
        return []
    raw_args = [part.strip() for part in match.group(1).split(",")]
    return raw_args[1:] if raw_args and raw_args[0] == "track" else raw_args


def add_segment_to(track: list[dict[str, float]], curve_value: float, y_value: float | None = None):
    start_y = 0 if not track else track[-1]["y2"]
    end_y = start_y if y_value is None else y_value
    track.append({"curve": curve_value, "y1": start_y, "y2": end_y})


def add_road_to(track: list[dict[str, float]], enter: float, hold: float, leave: float, curve_value: float, y_value: float = 0):
    start_y = 0 if not track else track[-1]["y2"]
    end_y = start_y + y_value * 200
    total = enter + hold + leave
    n = 0
    while n < enter:
        add_segment_to(track, ease_in(0, curve_value, n / enter), ease_in_out(start_y, end_y, n / total))
        n += 1
    n = 0
    while n < hold:
        add_segment_to(track, curve_value, ease_in_out(start_y, end_y, (enter + n) / total))
        n += 1
    n = 0
    while n < leave:
        add_segment_to(track, ease_in_out(curve_value, 0, n / leave), ease_in_out(start_y, end_y, (enter + hold + n) / total))
        n += 1


def add_flat_s_curves_to(track: list[dict[str, float]]):
    for curve_value in [-2, 4, 2, -2, -4]:
        add_road_to(track, 50, 50, 50, curve_value, 0)


def add_s_curves_to(track: list[dict[str, float]]):
    for curve_value, y_value in [(-2, 0), (4, 40), (2, -20), (-2, 40), (-4, -40)]:
        add_road_to(track, 50, 50, 50, curve_value, y_value)


def add_low_rolling_hills_to(track: list[dict[str, float]], final: bool):
    for curve_value, y_value in [
        (0, 10),
        (0, -20),
        (2 if final else 0, 20),
        (0, 0),
        (-2 if final else 0, 10),
        (0, 0),
    ]:
        add_road_to(track, 25, 25, 25, curve_value, y_value)


def add_bumps_to(track: list[dict[str, float]]):
    for y_value in [5, -2, -5, 8, 5, -7, 5, -2]:
        add_road_to(track, 10, 10, 10, 0, y_value)


def simulated_track_from_calls(calls: list[str]) -> list[dict[str, float]]:
    track: list[dict[str, float]] = []
    for call in calls:
        args = split_call_args(call)
        if call.startswith("addStraight"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            add_road_to(track, length, length, length, 0, 0)
        elif call.startswith("addHill"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            height = eval_track_expr(args[1] if len(args) > 1 else None, 40, {})
            add_road_to(track, length, length, length, 0, height)
        elif call.startswith("addCurve"):
            length = eval_track_expr(args[0] if args else None, 50, {})
            curve_value = eval_track_expr(args[1] if len(args) > 1 else None, 4, {})
            height = eval_track_expr(args[2] if len(args) > 2 else None, 0, {})
            add_road_to(track, length, length, length, curve_value, height)
        elif call.startswith("addLowRollingHills"):
            add_low_rolling_hills_to(track, False)
        elif call.startswith("addFinalLowRollingHills"):
            add_low_rolling_hills_to(track, True)
        elif call.startswith("addFlatSCurves"):
            add_flat_s_curves_to(track)
        elif call.startswith("addSCurves"):
            add_s_curves_to(track)
        elif call.startswith("addBumps"):
            add_bumps_to(track)
        elif call.startswith("addDownhillToEnd"):
            length = eval_track_expr(args[0] if args else None, 200, {})
            add_road_to(track, length, length, length, -2, -(track[-1]["y2"] if track else 0) / 200)
    return track


expected_track_samples = {
    "curves": {
        150: (-0.751310, 0.0, 0.0),
        500: (-0.672800, 0.0, 0.0),
        2110: (0.229487, 0.0, 0.0),
        4220: (-0.000493, 0.0, 0.0),
    },
    "hills": {
        150: (0.0, 4893.717, 4935.455),
        500: (0.0, 7996.491, 7996.491),
        1782: (-4.0, 28702.418, 28743.604),
        3563: (-0.000123, 0.877, 0.219),
    },
    "final": {
        150: (0.0, 1999.123, 1999.123),
        1000: (-0.5, 8492.580, 8533.705),
        3352: (1.095200, 44847.469, 44818.477),
        6704: (-0.000123, 1.283, 0.321),
    },
}

for mode, samples in expected_track_samples.items():
    simulated_track = simulated_track_from_calls(track_call_sequence(mode))
    if len(simulated_track) != expected_track_lengths[mode]:
        fail(f"{mode} simulated track length changed: {len(simulated_track)}")
    for index, (expected_curve, expected_y1, expected_y2) in samples.items():
        segment = simulated_track[index]
        if (
            abs(segment["curve"] - expected_curve) > 1e-5
            or abs(segment["y1"] - expected_y1) > 1e-3
            or abs(segment["y2"] - expected_y2) > 1e-3
        ):
            fail(
                f"{mode} segment {index} must match javascript-racer control point: "
                f"{segment} != {(expected_curve, expected_y1, expected_y2)}"
            )

for token in [
    "x = math.floor(width / 2 + scale * (worldX - cameraX) * width / 2 + 0.5)",
    "y = math.floor(height / 2 - scale * (worldY - cameraY) * height / 2 + 0.5)",
    "w = math.floor(scale * roadWidth * width / 2 + 0.5)",
]:
    if token not in MATH:
        fail(f"Util.project rounding must match javascript-racer: {token}")

for token in [
    "local halfRoadWidth = roadHalfWidthPx / WIDTH",
    "halfRoadWidth / math.max(6, 2 * lanes)",
    "halfRoadWidth / math.max(32, 8 * lanes)",
    "math.clamp(lanes - 1, 0, #row.laneMarkers)",
]:
    if token not in CLIENT:
        fail(f"Render.segment width formula must match javascript-racer: {token}")

for token in [
    "Road = Color3.fromRGB(255, 255, 255)",
    "Grass = Color3.fromRGB(255, 255, 255)",
    "Rumble = Color3.fromRGB(255, 255, 255)",
    "Road = Color3.fromRGB(0, 0, 0)",
    "Grass = Color3.fromRGB(0, 0, 0)",
    "Rumble = Color3.fromRGB(0, 0, 0)",
]:
    if token not in CONFIG:
        fail(f"START/FINISH colors must match javascript-racer white/black: {token}")

for token in [
    "FastLapTime = createValue(folder, \"NumberValue\", \"FastLapTime\", 180)",
    "fastLapTime = 180",
    "session.trafficOffsets = RacerConfig.baseTrafficOffsets()",
    "local playerSegmentIndex = math.floor(RacerConfig.PlayerZ / RacerConfig.SegmentLength)",
    "if index == playerSegmentIndex + 2 or index == playerSegmentIndex + 3 then",
    "if index >= RacerConfig.segmentCount(mode) - RacerConfig.RumbleLength then",
]:
    if token not in CONFIG + SERVER:
        fail(f"lap/start-finish reset parity token missing: {token}")

for forbidden in [
	"CollisionDistance",
	"CollisionWidth",
	"\n\tCollisionSpeed",
	"item.width * 0.24",
	"adjustedTrafficOffset",
	"minSpriteSize",
	"math.abs(currentOffset - item.offset)",
	"MAX_PREDICTION_DELTA",
	"RoadsideCollisionLookahead",
	"RoadsideCollisionSegmentRadius",
	"MinSpacing",
	"-1.15",
	"RacerMath.limit(\n\t\t\titem.offset",
	"renderer.car.Rotation = steer",
	"advanceTrafficOffsets",
	"avoidTargetId",
	"avoidDirection",
	"RoadsideCollisionSegmentOffsets",
	"table.sort(objects",
	"table.sort(trafficList",
	"return a.distance > b.distance",
	"minTrafficDistance",
	"distance > minTrafficDistance",
	"math.clamp(playerY",
	"maxY = if RacerConfig.Modes[mode].hills then p1.y else p2.y",
	"prediction.accumulator = math.min(prediction.accumulator, RacerConfig.Step)",
	"accumulator = math.min(accumulator, step)",
	"syncRendererTrafficOffsets",
	"trafficSyncTime",
	"trafficSyncPosition",
	"trafficSyncPlayerX",
	"trafficSyncSpeed",
	"while simTime + RacerConfig.Step <= targetTrafficTime do",
	"((x1 + x2) * 0.5) / WIDTH",
	"((w1 + w2) * 0.5 * 2) / WIDTH",
	"math.max(0.02, (roadHalfWidthPx * 2) / WIDTH)",
	"fog * 0.55",
	"object.BackgroundColor3 = colorWithFog(carData.color",
	"10 + index",
	'createFrame(rowRoot, "Road", RacerConfig.Colors.Light.Road, 2)',
	'createFrame(rowRoot, "LeftRumble", RacerConfig.Colors.Light.Rumble, 3)',
	'createFrame(rowRoot, `LaneMarker_{laneIndex}`, RacerConfig.Colors.Light.Lane, 4)',
]:
	if forbidden in CONFIG + CLIENT + SERVER:
		fail(f"non-original collision tuning must not remain: {forbidden}")

for token in [
    "CurrentLapTime",
    "LastLapTime",
    "FastLapTime",
    "trafficCollisionCar",
    "roadsideCollisionSprite",
    "RoadsideCollisionSpeed",
    "settingDrawDistance.Value",
    "lastLapTime.Value <= prediction.fastLapTime.Value",
    "session.lastLapTime <= session.fastLapTime",
	"prediction.accumulator >= RacerConfig.Step",
	"local step = RacerConfig.Step",
	"MAX_PREDICTION_ACCUMULATED_TIME = 1",
	"MAX_ACCUMULATED_TIME = 1",
	"RacerConfig.advanceTraffic(",
	"trafficItems, trafficBySegment = RacerConfig.advanceTraffic(",
	"prediction.trafficState",
	"session.trafficState",
	"replicatedTrafficOffsets(state)",
	"TrafficOffsets",
    "replicatedTrafficOffsets",
    "prediction.playerX.Value < -1 or prediction.playerX.Value > 1",
    "session.playerX < -1 or session.playerX > 1",
    "local roadsideSprite",
    "RacerConfig.roadsideCollisionSprite(mode, segmentIndex, prediction.playerX.Value)",
    "RacerConfig.trafficCollisionPosition(collisionItem.z, playerZ, trackLength)",
    "RacerConfig.roadsideCollisionSprite(\n\t\t\tsession.definition.Mode,\n\t\t\tsegmentIndex,\n\t\t\tsession.playerX\n\t\t)",
	"local playerXLimit = if RacerConfig.isFinalLike(mode) then 3 else 2",
	"local playerXLimit = if RacerConfig.isFinalLike(session.definition.Mode) then 3 else 2",
	"if RacerConfig.isFinalLike(mode) then\n\t\t\tprediction.trafficTime.Value += step\n\t\tend",
	"if RacerConfig.isFinalLike(session.definition.Mode) then\n\t\tsession.trafficTime += dt\n\tend",
]:
    if token not in SERVER + CLIENT:
        fail(f"runtime parity token missing: {token}")

for token in [
    "function RacerConfig.trafficSnapshot(",
    "function RacerConfig.applyTrafficOffsets(",
]:
    if token not in CONFIG:
        fail(f"shared traffic parity helper missing: {token}")

if "RacerConfig.Traffic.Lookahead - 1" not in CONFIG:
    fail("traffic lookahead loop must match javascript-racer i < lookahead")

if 'string.format("%.4f", offset)' in CONFIG:
    fail("replicated traffic offsets should not be rounded to 4 decimals")

if 'string.format("%.6f", offset)' not in CONFIG:
    fail("replicated traffic offsets should keep enough precision for spectator rendering")

require(
    r"if\s+orderedTrafficBySegment\s*==\s*nil\s*then\s*for\s+_,\s*item\s+in\s+trafficItems\s+or\s+\{\}\s+do",
    CLIENT,
    "traffic render fallback must not duplicate already grouped traffic",
)

require(
    r"function\s+RacerConfig\.playerBounce\(\s*position:\s*number,\s*speedPercent:\s*number,\s*resolution:\s*number\s*\):\s*number",
    CONFIG,
    "player bounce helper must keep the Render.player-style inputs",
)

require(
    r'if\s+not\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*speedPercent',
    CLIENT,
    "client v2/v3 background update must happen before controls using speedPercent",
)
require(
    r'if\s+not\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*speedPercent',
    SERVER,
    "server v2/v3 background update must happen before controls using speedPercent",
)
require(
    r"prediction\.position\.Value\s*=\s*RacerMath\.increase\(.*?if\s+not\s+RacerConfig\.isFinalLike\(mode\).*?if\s+pressedInputs\.left\s+then",
    CLIENT,
    "client update order must match v1-v3: position, background, then player input",
)
require(
    r"session\.position\s*=\s*RacerMath\.increase\(.*?if\s+not\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\).*?if\s+session\.input\.left\s+then",
    SERVER,
    "server update order must match v1-v3: position, background, then player input",
)
require(
    r"RacerConfig\.trafficCollisionCar\([^\n]*.*?local\s+playerXLimit\s*=\s*if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*3\s*else\s*2",
    CLIENT,
    "client collision order must match original: traffic collision before player/speed clamp",
)
require(
    r"RacerConfig\.trafficCollisionCar\([^\n]*.*?local\s+playerXLimit\s*=\s*if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*3\s*else\s*2",
    SERVER,
    "server collision order must match original: traffic collision before player/speed clamp",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic',
    CLIENT,
    "client traffic movement must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic',
    SERVER,
    "server traffic movement must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic.*?prediction\.trafficTime\.Value\s*\+=\s*step.*?prediction\.position\.Value\s*=\s*RacerMath\.increase',
    CLIENT,
    "client v4 update order must match original: updateCars, traffic time, then position",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then\s*trafficItems,\s*trafficBySegment\s*=\s*RacerConfig\.advanceTraffic.*?session\.trafficTime\s*\+=\s*dt.*?session\.position\s*=\s*RacerMath\.increase',
    SERVER,
    "server v4 update order must match original: updateCars, traffic time, then position",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s+and\s+\(prediction\.playerX\.Value\s*<\s*-1\s+or\s+prediction\.playerX\.Value\s*>\s*1\)\s*then\s*local\s+roadsideSprite\s*=\s*RacerConfig\.roadsideCollisionSprite\(\s*mode,\s*segmentIndex,\s*prediction\.playerX\.Value\s*\)',
    CLIENT,
    "client roadside collisions must use the original pre-move player segment in v4 final",
)
require(
    r"RacerConfig\.roadsideCollisionPosition\(\s*segmentIndex,\s*playerZ,\s*trackLength\s*\)",
    CLIENT,
    "client roadside collision reset position must stop at the front of the original player segment",
)
require(
    r"function\s+RacerConfig\.trafficSnapshot\(.*?width\s*=\s*car\.width\s*\*\s*RacerConfig\.SpriteScale",
    CONFIG,
    "traffic hitboxes must use original sprite.w * SPRITES.SCALE units, not raw placeholder pixels",
)
require(
    r"function\s+RacerConfig\.trafficCollisionCar\(.*?RacerMath\.overlap\(\s*playerX,\s*RacerConfig\.Traffic\.PlayerWidth,\s*item\.offset,\s*item\.width,\s*RacerConfig\.Traffic\.CollisionOverlap",
    CONFIG,
    "traffic collision must compare playerX against scaled car offset/width like javascript-racer",
)
require(
    r"local\s+spriteX\s*=\s*projected\.p1\.x\s*\+\s*scale\s*\*\s*RacerConfig\.roadsideSpriteCenter\(spriteData\).*?local\s+spriteCenter\s*=\s*RacerConfig\.roadsideSpriteCenter\(sprite\)",
    CLIENT + CONFIG,
    "roadside rendering and collision must share the same sprite center formula",
)
require(
    r'local\s+collisionboxWidth\s*=\s*width\s*\*\s*RacerConfig\.Traffic\.CollisionOverlap.*?placeClippedObject\(\s*object,\s*x,\s*y,\s*width,\s*height,\s*projected\.clip,\s*collisionboxWidth',
    CLIENT,
    "debug traffic collisionboxes must use the original NPC collision overlap window",
)
require(
    r"for\s+_,\s*spriteData\s+in\s+RacerConfig\.spritesForSegment\(mode,\s*playerSegmentIndex\)\s+do.*?local\s+playerHalfWidth\s*=\s*RacerConfig\.Traffic\.PlayerWidth\s*/\s*2.*?if\s+spriteData\.offset\s*>\s*0\s*then\s*collisionMinWorld\s*=\s*math\.max\(collisionMinWorld,\s*1\).*?else\s*collisionMaxWorld\s*=\s*math\.min\(collisionMaxWorld,\s*-1\).*?placeScreenDebugBox\(\s*collisionbox,\s*collisionboxX,\s*collisionBottomY,\s*collisionboxWidth,\s*playerHeight",
    CLIENT,
    "debug roadside collisionbox overlay must show the current-segment off-road player-center collision zone",
)
require(
    r"function\s+RacerConfig\.trafficOffsetDelta\(.*?local\s+carWidth\s*=\s*item\.width.*?RacerMath\.overlap\(\s*playerX,\s*RacerConfig\.Traffic\.PlayerWidth,\s*item\.offset,\s*carWidth,\s*1\.2",
    CONFIG,
    "traffic avoidance must use the same scaled car width as traffic collision",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s+and\s+\(session\.playerX\s*<\s*-1\s+or\s+session\.playerX\s*>\s*1\)\s*then\s*local\s+roadsideSprite\s*=\s*RacerConfig\.roadsideCollisionSprite\(\s*session\.definition\.Mode,\s*segmentIndex,\s*session\.playerX\s*\)',
    SERVER,
    "server roadside collisions must use the original pre-move player segment in v4 final",
)
require(
    r"RacerConfig\.roadsideCollisionPosition\(\s*segmentIndex,\s*playerZ,\s*trackLength\s*\)",
    SERVER,
    "server roadside collision reset position must stop at the front of the original player segment",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?RacerConfig\.trafficCollisionCar',
    CLIENT,
    "client traffic collision must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?RacerConfig\.trafficCollisionCar',
    SERVER,
    "server traffic collision must only run in v4 final",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?RacerConfig\.createTrafficState\(\s*trafficTime,\s*trackLength,\s*segmentCount,\s*replicatedTrafficOffsets\(state\),\s*mode\s*\).*?RacerConfig\.spritesForSegment',
    CLIENT,
    "world/object rendering must rebuild v4 final traffic directly from the replicated server snapshot",
)
require(
    r"for\s+index\s*=\s*#objectSegments,\s*1,\s*-1\s*do.*?local\s+trafficList\s*=.*?setTrafficObject.*?local\s+spriteList\s*=.*?setSpriteObject.*?if\s+projected\.index\s*==\s*playerSegmentIndex\s*then\s*playerDrawZIndex\s*=\s*objectZIndex\(drawLayer\)",
    CLIENT,
    "v4 object layering must match original: far-to-near, traffic, roadside sprites, then player at its segment",
)
for token in [
    "status.Visible = false",
    "local function finalHudText(state, speed: number): string",
    "{mph} mph Time:",
    "Last Lap:",
    "Fastest Lap:",
    "if RacerConfig.isFinalLike(mode) and renderer.statusEnabled ~= false then",
    "renderer.status.Text = finalHudText(state, speed)",
    "renderer.status.Text = \"\"",
    "renderer.status.Visible = false",
]:
    if token not in CLIENT:
        fail(f"v4 final must render the original mph/time/last/fastest HUD, and v1-v3 must not render a HUD/status overlay: {token}")
require(
    r'if\s+RacerConfig\.isFinalLike\(mode\)\s*then.*?local\s+positionDelta.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*positionDelta',
    CLIENT,
    "client v4 background update must use position delta after collisions",
)
require(
    r'if\s+RacerConfig\.isFinalLike\(session\.definition\.Mode\)\s*then.*?local\s+positionDelta.*?BACKGROUND_SPEEDS\.Sky\s*\*\s*curve\s*\*\s*positionDelta',
    SERVER,
    "server v4 background update must use position delta after collisions",
)
for token in [
    "local skyY = playerY * BACKGROUND_SPEEDS.Sky / 480",
    "local hillY = playerY * BACKGROUND_SPEEDS.Hill / 480",
    "local treeY = playerY * BACKGROUND_SPEEDS.Tree / 480",
]:
    if token not in CLIENT:
        fail(f"background vertical offset must match Render.background scaling: {token}")

if "state.trafficOffsets" not in CLIENT:
    fail("fullscreen render must use predicted traffic offsets for collision/render parity")

if "activeUserId = source.activeUserId" not in CLIENT:
    fail("active player prediction must keep activeUserId for avatar/HUD rendering")

require(
    r"if\s+state\.trafficOffsets\s+then\s*local\s+trafficState\s*=\s*RacerConfig\.createTrafficState\(\s*trafficTime,\s*trackLength,\s*segmentCount,\s*state\.trafficOffsets,\s*mode\s*\)\s*trafficItems\s*=\s*trafficState\.items\s*orderedTrafficBySegment\s*=\s*trafficState\.bySegment",
    CLIENT,
    "traffic offset fallback must rebuild segment.cars-style grouping before rendering",
)

for token in [
	"trafficBySegment = nil",
	"trafficBySegment = if trafficState then trafficState.bySegment else nil",
	"prediction.trafficBySegment = trafficBySegment",
	"local orderedTrafficBySegment = state.trafficBySegment",
	"if state.trafficState and state.trafficState.bySegment then",
]:
    if token not in CLIENT:
        fail(f"active renderer must preserve updateCars segment order: {token}")

if "render(fullRenderer, renderState)" not in CLIENT:
    fail("active player renderer must render every frame like javascript-racer")

if "math.min(\n\t\tpredictedState.fastLapTime.Value,\n\t\tsource.fastLapTime.Value" not in CLIENT:
    fail("active player best lap prediction must not be overwritten by a slower server snapshot")

if "source.lastLapTime.Value > 0" not in CLIENT or "source.currentLapTime.Value == 0" not in CLIENT:
    fail("active player last lap prediction must survive stale zero server snapshots")

if "if state.trafficOffsetsBlob then state.trafficOffsetsBlob.Value else \"\"" not in CLIENT:
    fail("world screen render signatures must include replicated traffic offsets")

if "math.floor(state.lastLapTime.Value * 10 + 0.5)" not in CLIENT:
    fail("render signature must include last lap HUD state")

if "renderIfChanged(fullRenderer" in CLIENT:
    fail("active player renderer must not be signature-throttled")

for forbidden in [
    "predictedState.position.Value = source.position.Value",
    "predictedState.speed.Value = source.speed.Value",
    "predictedState.playerX.Value = source.playerX.Value",
    "predictedState.trafficTime.Value = source.trafficTime.Value",
]:
    if forbidden in CLIENT:
        fail(f"active player prediction must not be overwritten by server snapshots: {forbidden}")

for token in [
    "setPlayerCarZIndex",
    "projected.index == playerSegmentIndex",
	"if n > 0 then\n\t\t\t\ttable.insert(objectSegments, projected)\n\t\t\tend",
	"local playerBottomY = HEIGHT",
	"RacerConfig.Modes[mode].hills and playerProjected",
	"local frontFacing = not RacerConfig.Modes[mode].hills or p2.y < p1.y",
	"if p1 and p2 then",
	"p1.cameraZ > cameraDepth and frontFacing and p2.y < maxY",
	"maxY = if RacerConfig.isFinalLike(mode) then p1.y else p2.y",
	"playerProjected.p1.cameraY",
	"ROAD_SCANLINE_HEIGHT = 2",
	"local heightScale = math.max(1 / HEIGHT, bottom - top)",
	"local roadWidth = math.max(0, (roadHalfWidthPx * 2) / WIDTH)",
	"local percent = RacerMath.limit((sampleY - p2.y) / segmentHeight, 0, 1)",
	"RacerMath.interpolate(p2.x, p1.x, percent)",
	"RacerMath.interpolate(p2.w, p1.w, percent)",
	"local ROAD_Z_INDEX = 20",
	"local ROAD_DETAIL_Z_INDEX = ROAD_Z_INDEX + 1",
	"local ROAD_LANE_Z_INDEX = ROAD_Z_INDEX + 2",
	"createFrame(root, `RoadRow_{index}`, RacerConfig.Colors.Light.Grass, ROAD_Z_INDEX)",
	'createFrame(rowRoot, "Road", RacerConfig.Colors.Light.Road, ROAD_DETAIL_Z_INDEX)',
	"ROAD_LANE_Z_INDEX",
	"local playerSprite = RacerConfig.playerSpriteDef(steer, playerSegment.y2 - playerSegment.y1)",
	"playerSprite.width",
	"playerSprite.height",
	"local playerBounce =",
	"RacerConfig.playerBounce(position, speed / RacerConfig.MaxSpeed, HEIGHT / 480)",
	"(playerBottomY + playerBounce) / HEIGHT",
    "renderer.car.Rotation = 0",
    "child.ZIndex = object.ZIndex",
    "child.ZIndex = zIndex",
    "OBJECT_Z_STRIDE = 4",
    "objectZIndex(drawLayer)",
    "screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling",
    "surfaceGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling",
    "local ROW_COUNT = RacerConfig.MaxDrawDistance",
]:
    if token not in CLIENT:
        fail(f"render ordering parity token missing: {token}")

if "ZIndexBehavior = Enum.ZIndexBehavior.Global" in CLIENT:
    fail("nested racer canvas renderer must use sibling ZIndex ordering so road rows stay above the root background")

for token in [
    "local widthPx = widthScale * WIDTH",
    "local heightPx = heightScale * HEIGHT",
    "local leftX = x - widthPx / 2",
    "local topY = bottomY - heightPx",
    "local visibleBottomY = math.min(bottomY, clipY, SCREEN_MAX_Y)",
    "detailRoot.Position = UDim2.fromScale(",
    "(leftX - visibleLeftX) / visibleWidth",
    "(topY - visibleTopY) / visibleHeight",
    "detailRoot.Size = UDim2.fromScale(widthPx / visibleWidth, heightPx / visibleHeight)",
]:
    if token not in CLIENT:
        fail(f"Render.sprite clipping must crop without changing apparent sprite proportions: {token}")

for token in [
    '"SpriteCanopy"',
    '"SpriteTrunk"',
    '"SpriteBody"',
    '"SpriteContact"',
    '"TrafficBody"',
    'if kind == "billboard" then',
    "detailRoot.BackgroundTransparency = 1",
    'and child.Name ~= "LiveBillboardText"',
    "and not isDebugBox(child.Name)",
    "child.Visible = not hasTexture and not isSpriteOnly",
    "local collisionOverlap = RacerConfig.Traffic.CollisionOverlap",
    "local collisionLeft = (1 - collisionOverlap) / 2",
    "UDim2.fromScale(collisionLeft, 0)",
    "UDim2.fromScale(collisionOverlap, 1)",
    "UDim2.fromScale(0.23, 0.86)",
    "UDim2.fromScale(0, 0.9)",
    "UDim2.fromScale(1, 0.1)",
    'elseif kind == "rock" then',
    'elseif kind == "column" then',
]:
    if token not in CLIENT:
        fail(f"placeholder roadside sprites must not render as full opaque sprite rectangles: {token}")

if CLIENT.count('elseif spriteData.sprite == "PALM_TREE" then') != 1:
    fail("placeholder roadside sprites must have exactly one PALM_TREE branch")

for token in [
    "local useSpriteboxDebug = false",
    "local useCollisionboxDebug = false",
    "local function createDebugBox",
    'createDebugBox(parent, "Spritebox"',
    'createDebugBox(parent, "Collisionbox"',
    'box.Name = name',
    "box.BackgroundTransparency = 1",
    'createBoxLine("Top"',
    '"Bottom"',
    'createBoxLine("Left"',
    '"Right"',
    "stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border",
    "createSpritebox(car, PLAYER_CAR_Z_INDEX + 5)",
    "createCollisionbox(car, PLAYER_CAR_Z_INDEX + 7)",
    'child.Name ~= "Texture" and not isDebugBox(child.Name)',
    "playerSpritebox.Visible = RacerConfig.isFinalLike(mode) and useSpriteboxDebug",
    "playerCollisionbox.Position = UDim2.new(0.5, -2, 0, 0)",
    "playerCollisionbox.Size = UDim2.new(0, 4, 1, 0)",
    "playerCollisionbox.Visible = RacerConfig.isFinalLike(mode) and useCollisionboxDebug",
    "local boxVisibleLeftX = math.max(boxLeftX, visibleLeftX)",
    "local boxVisibleRightX = math.min(boxRightX, visibleRightX)",
    "local centerX = boxCenterX or x",
    "boxVisibleWidth / visibleWidth",
    "boxVisibleHeight / visibleHeight",
    "local debugLineZIndex = zIndex + 1",
    'Spriteboxes`',
    'Collisionboxes`',
    "not state or not RacerConfig.isFinalLike(state.mode.Value)",
]:
    if token not in CLIENT:
        fail(f"optional v4 hitbox debug outlines missing token: {token}")

for forbidden in [
    "if child.Name == \"Shadow\" then object.ZIndex - 1 else object.ZIndex + 1",
    "child.ZIndex = zIndex + 1",
]:
    if forbidden in CLIENT:
        fail(f"placeholder sprite parts must render as one atomic sprite layer: {forbidden}")

if "local FINAL_OBJECT_COUNT = RacerConfig.FinalObjectCount" not in CLIENT:
    fail("object pool must be derived from v4 traffic + max visible sprite placeholders")

for token in [
    "local ACTIVE_STATUS_MARGIN_TOP = 14",
    "local lastLap = if state.lastLapTime.Value > 0",
    "local viewportTop = math.floor((absoluteSize.Y - height) / 2 + 0.5)",
    "viewportTop + ACTIVE_STATUS_MARGIN_TOP",
    "fullRenderer.statusEnabled = false",
    "activeStatus = Instance.new(\"Frame\")",
    "local activeStatusSpeed = createActiveStatusField(",
    "local activeStatusCurrent = createActiveStatusField(",
    "local activeStatusLast = createActiveStatusField(",
    "local activeStatusFast = createActiveStatusField(",
    "local function updateActiveStatus(state)",
    "activeStatusSpeed.Text = `{5 * math.round(state.speed.Value / 500)} mph`",
    "activeStatusCurrent.Text = `Time: {formatTime(state.currentLapTime.Value)}`",
    "activeStatusFast.Text = `Fastest Lap: {formatTime(state.fastLapTime.Value)}`",
    "if state.lastLapTime.Value > 0 then",
    "activeStatusLast.Visible = true",
    "render(fullRenderer, renderState)\n\t\tupdateActiveStatus(renderState)",
]:
    if token not in CLIENT:
        fail(f"active player v4+ HUD must be a fullscreen overlay below the Roblox topbar: {token}")

if "render(fullRenderer, renderState)\n\t\tupdateActiveStatus(state)" in CLIENT:
    fail("active player v4+ HUD must mirror the local active render state, not the spectator replication state")

for token in [
    "local savedChatEnabled = true",
    "local function getCoreGuiEnabled(coreGuiType: Enum.CoreGuiType, fallback: boolean): boolean",
    "StarterGui:GetCoreGuiEnabled(coreGuiType)",
    "local function releaseFocusedTextBox()",
    "StarterGui:SetCore(\"ChatActive\", false)",
    "GuiService.SelectedObject = nil",
    "focusedTextBox:ReleaseFocus(false)",
    "local function handleRacerKeyboardInput(inputObject: InputObject, isDown: boolean)",
    "if not controlsBound then",
    "releaseFocusedTextBox()",
    "local inputNames = { \"left\", \"right\", \"faster\", \"slower\" }",
    "local keyboardInputs = {}",
    "local pointerInputs = {}",
    "local function inputIsDown(inputName: string): boolean",
    "local function publishInput(inputName: string)",
    "inputEvent:FireServer(inputName, isDown)",
    "local function setKeyboardInput(inputName: string, isDown: boolean)",
    "local function setPointerInput(inputName: string, isDown: boolean)",
    "setKeyboardInput(inputName, isDown)",
    "local function syncHeldKeyboardInputs()",
    "local heldInputs = {}",
    "UserInputService:IsKeyDown(keyCode)",
    "setKeyboardInput(inputName, heldInputs[inputName] == true)",
    "setPointerInput(inputName, true)",
    "setPointerInput(inputName, false)",
    "syncHeldKeyboardInputs()\n\t\tlocal renderState = updatePredictedState(state, deltaTime)",
    "UserInputService.InputBegan:Connect(function(inputObject)",
    "UserInputService.InputEnded:Connect(function(inputObject)",
    "savedChatEnabled = getCoreGuiEnabled(Enum.CoreGuiType.Chat, true)",
    "setCoreGuiEnabled(Enum.CoreGuiType.Chat, false)",
    "setCoreGuiEnabled(Enum.CoreGuiType.Chat, savedChatEnabled)",
    "syncHeldKeyboardInputs()",
]:
    if token not in CLIENT:
        fail(f"active player keyboard controls must feed local prediction and server input directly: {token}")

for token in [
    "local playerGui = player:WaitForChild(\"PlayerGui\")",
    "local racerGuiMarkerNames = {",
    "local function removeForeignRacerGuiFor(instance: Instance)",
    "local function removeForeignRacerHuds()",
    "if child.Name == \"RacerHud\" and child ~= screenGui then",
    "playerGui.ChildAdded:Connect(function(child)",
    "playerGui.DescendantAdded:Connect(function(descendant)",
    "removeForeignRacerHuds()",
    "layers:{layerCount}/{foreignLayerCount}",
    "local latestPerfSummary = \"waiting for perf sample\"",
    "perfLabel.ZIndex = OVERLAY_Z_INDEX + 100",
    "if inputObject.KeyCode == Enum.KeyCode.F6 then\n\t\tperfLabel.Visible = not perfLabel.Visible\n\t\treturn\n\tend\n\tif gameProcessed then",
    "local function inputDebugFlags(source): string",
    "local function racerStateDebugText(label: string, state): string",
    "local function focusDebugText(): string",
    "local function hudDebugText(): string",
    "local function activeDebugText(state): string",
    "`keys K:{inputDebugFlags(keyboardInputs)} P:{inputDebugFlags(pointerInputs)} I:{inputDebugFlags(pressedInputs)}`",
    "racerStateDebugText(\"local\", predictedState)",
    "racerStateDebugText(\"server\", state)",
    "hudDebugText()",
    "local function refreshPerfLabel(state)",
    "refreshPerfLabel(state)",
    "if perfLabel.Visible then\n\t\t\trefreshPerfLabel(state)\n\t\tend",
]:
    if token not in CLIENT:
        fail(f"F6 active racer diagnostics must expose input/local/server HUD state: {token}")

for token in [
    'local LogService = game:GetService("LogService")',
    'RacerClientLog',
    'RacerClientLogs',
    "LogService.MessageOut:Connect(",
]:
    if token in CLIENT or token in SERVER:
        fail(f"custom client warning/error telemetry bridge must remain removed: {token}")

for token in [
    'player:GetAttribute("Activity") ~= "RacerScreen"',
    'player:GetAttribute("RacerScreenId")',
    'player:GetAttributeChangedSignal("Activity"):Connect(updateHud)',
    'player:GetAttributeChangedSignal("RacerScreenId"):Connect(updateHud)',
    "local function hudNeedsSync(state): boolean",
    "if hudNeedsSync(state) then\n\t\tupdateHud()\n\tend",
]:
    if token not in CLIENT:
        fail(f"active player HUD must follow the player's own screen state every frame: {token}")

print("Racer parity checks passed")
