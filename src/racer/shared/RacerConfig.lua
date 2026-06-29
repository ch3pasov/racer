local RacerMath = require(script.Parent.RacerMath)

local RacerConfig = {
	Name = "Racer Lab",
	VersionBuild = "local",
	Fps = 60,
	Width = 1024,
	Height = 768,
	SegmentLength = 200,
	RumbleLength = 3,
	SegmentCount = 500,
	RoadWidth = 2000,
	Lanes = 3,
	FieldOfView = 100,
	CameraHeight = 1000,
	DrawDistance = 300,
	MaxDrawDistance = 500,
	FogDensity = 5,
}

local function derive(base, overrides)
	local result = table.clone(base)
	for key, value in overrides do
		result[key] = value
	end
	return result
end

local function shallowArrayCopy(items)
	return table.clone(items)
end

RacerConfig.Modes = {
	straight = {
		curves = false,
		hills = false,
		sprites = false,
		traffic = false,
		laps = false,
		hud = false,
	},
	curves = {
		curves = true,
		hills = false,
		sprites = false,
		traffic = false,
		laps = false,
		hud = false,
	},
	hills = {
		curves = true,
		hills = true,
		sprites = false,
		traffic = false,
		laps = false,
		hud = false,
	},
	final = {
		curves = true,
		hills = true,
		sprites = true,
		traffic = true,
		laps = true,
		hud = true,
	},
}
RacerConfig.Modes.v5 = derive(RacerConfig.Modes.final, {
	codeName = "mobile-controls",
	mobileControls = true,
	v5 = true,
})
RacerConfig.Modes.v6 = derive(RacerConfig.Modes.v5, {
	codeName = "driver-occupants",
	driverOccupants = true,
	v6 = true,
})
RacerConfig.Modes.v7 = derive(RacerConfig.Modes.v6, {
	codeName = "record-boards",
	recordBoards = true,
	liveBillboards = true,
	v7 = true,
})

function RacerConfig.isFinalLike(mode: string): boolean
	local definition = RacerConfig.Modes[mode]
	return definition ~= nil and definition.traffic == true and definition.laps == true
end

function RacerConfig.isV5Plus(mode: string): boolean
	local definition = RacerConfig.Modes[mode]
	return definition ~= nil and definition.v5 == true
end

function RacerConfig.hasDriverOccupants(mode: string): boolean
	local definition = RacerConfig.Modes[mode]
	return definition ~= nil and definition.driverOccupants == true
end

function RacerConfig.hasRecordBoards(mode: string): boolean
	local definition = RacerConfig.Modes[mode]
	return definition ~= nil and definition.recordBoards == true
end

RacerConfig.Screens = {
	{
		Id = "straight",
		Name = "v1 Straight",
		Mode = "straight",
		Position = Vector3.new(-54, 0, -24),
		Color = Color3.fromRGB(255, 202, 88),
	},
	{
		Id = "curves",
		Name = "v2 Curves",
		Mode = "curves",
		Position = Vector3.new(-18, 0, -24),
		Color = Color3.fromRGB(108, 221, 205),
	},
	{
		Id = "hills",
		Name = "v3 Hills",
		Mode = "hills",
		Position = Vector3.new(18, 0, -24),
		Color = Color3.fromRGB(122, 148, 255),
	},
	{
		Id = "final",
		Name = "v4 Final",
		Mode = "final",
		Position = Vector3.new(54, 0, -24),
		Color = Color3.fromRGB(255, 116, 128),
	},
	{
		Id = "v5",
		Name = "v5 Mobile Controls",
		Mode = "v5",
		Position = Vector3.new(-36, 0, 44),
		Color = Color3.fromRGB(134, 240, 150),
	},
	{
		Id = "v6",
		Name = "v6 Driver Occupants",
		Mode = "v6",
		Position = Vector3.new(0, 0, 44),
		Color = Color3.fromRGB(108, 221, 205),
	},
	{
		Id = "v7",
		Name = "v7 Record Boards",
		Mode = "v7",
		Position = Vector3.new(36, 0, 44),
		Color = Color3.fromRGB(255, 221, 78),
	},
}

RacerConfig.Step = 1 / RacerConfig.Fps
RacerConfig.CameraDepth = 1 / math.tan(math.rad(RacerConfig.FieldOfView / 2))
RacerConfig.PlayerZ = RacerConfig.CameraHeight * RacerConfig.CameraDepth
RacerConfig.MaxSpeed = RacerConfig.SegmentLength / RacerConfig.Step
RacerConfig.Accel = RacerConfig.MaxSpeed / 5
RacerConfig.Braking = -RacerConfig.MaxSpeed
RacerConfig.Decel = -RacerConfig.MaxSpeed / 5
RacerConfig.OffRoadDecel = -RacerConfig.MaxSpeed / 2
RacerConfig.OffRoadLimit = RacerConfig.MaxSpeed / 4
RacerConfig.SpriteScale = 0.3 / 80
RacerConfig.PlayerSprite = {
	Width = 80,
	Height = 41,
	UphillHeight = 45,
}

RacerConfig.Colors = {
	Sky = Color3.fromRGB(114, 215, 238),
	Hills = Color3.fromRGB(78, 142, 118),
	Trees = Color3.fromRGB(0, 81, 8),
	Fog = Color3.fromRGB(0, 81, 8),
	Light = {
		Road = Color3.fromRGB(107, 107, 107),
		Grass = Color3.fromRGB(16, 170, 16),
		Rumble = Color3.fromRGB(85, 85, 85),
		Lane = Color3.fromRGB(204, 204, 204),
	},
	Dark = {
		Road = Color3.fromRGB(105, 105, 105),
		Grass = Color3.fromRGB(0, 154, 0),
		Rumble = Color3.fromRGB(187, 187, 187),
		Lane = nil,
	},
	Start = {
		Road = Color3.fromRGB(255, 255, 255),
		Grass = Color3.fromRGB(255, 255, 255),
		Rumble = Color3.fromRGB(255, 255, 255),
		Lane = nil,
	},
	Finish = {
		Road = Color3.fromRGB(0, 0, 0),
		Grass = Color3.fromRGB(0, 0, 0),
		Rumble = Color3.fromRGB(0, 0, 0),
		Lane = nil,
	},
}

RacerConfig.Traffic = {
	Count = 200,
	CollisionOverlap = 0.8,
	Lookahead = 20,
	PlayerWidth = RacerConfig.PlayerSprite.Width * RacerConfig.SpriteScale,
	Palette = {
		Color3.fromRGB(226, 72, 72),
		Color3.fromRGB(255, 213, 75),
		Color3.fromRGB(80, 156, 230),
		Color3.fromRGB(236, 236, 230),
		Color3.fromRGB(84, 210, 142),
		Color3.fromRGB(238, 126, 66),
	},
}
RacerConfig.RoadsideCollisionSpeed = RacerConfig.MaxSpeed / 5

RacerConfig.SpriteDefs = {
	PALM_TREE = { width = 215, height = 540, kind = "plant", color = Color3.fromRGB(31, 125, 39) },
	BILLBOARD08 = {
		width = 385,
		height = 265,
		kind = "billboard",
		color = Color3.fromRGB(250, 225, 96),
	},
	TREE1 = { width = 360, height = 360, kind = "tree", color = Color3.fromRGB(20, 112, 36) },
	DEAD_TREE1 = {
		width = 135,
		height = 332,
		kind = "plant",
		color = Color3.fromRGB(112, 96, 72),
	},
	BILLBOARD09 = {
		width = 328,
		height = 282,
		kind = "billboard",
		color = Color3.fromRGB(238, 126, 66),
	},
	BOULDER3 = { width = 320, height = 220, kind = "rock", color = Color3.fromRGB(124, 124, 116) },
	COLUMN = { width = 200, height = 315, kind = "column", color = Color3.fromRGB(222, 218, 198) },
	BILLBOARD01 = {
		width = 300,
		height = 170,
		kind = "billboard",
		color = Color3.fromRGB(236, 236, 230),
	},
	BILLBOARD06 = {
		width = 298,
		height = 190,
		kind = "billboard",
		color = Color3.fromRGB(80, 156, 230),
	},
	BILLBOARD05 = {
		width = 298,
		height = 190,
		kind = "billboard",
		color = Color3.fromRGB(226, 72, 72),
	},
	BILLBOARD07 = {
		width = 298,
		height = 190,
		kind = "billboard",
		color = Color3.fromRGB(84, 210, 142),
	},
	BOULDER2 = { width = 298, height = 140, kind = "rock", color = Color3.fromRGB(132, 132, 124) },
	TREE2 = { width = 282, height = 295, kind = "tree", color = Color3.fromRGB(24, 132, 44) },
	BILLBOARD04 = {
		width = 268,
		height = 170,
		kind = "billboard",
		color = Color3.fromRGB(255, 213, 75),
	},
	DEAD_TREE2 = {
		width = 150,
		height = 260,
		kind = "plant",
		color = Color3.fromRGB(122, 105, 78),
	},
	BOULDER1 = { width = 168, height = 248, kind = "rock", color = Color3.fromRGB(116, 116, 108) },
	BUSH1 = { width = 240, height = 155, kind = "plant", color = Color3.fromRGB(18, 116, 38) },
	CACTUS = { width = 235, height = 118, kind = "plant", color = Color3.fromRGB(28, 128, 72) },
	BUSH2 = { width = 232, height = 152, kind = "plant", color = Color3.fromRGB(26, 140, 44) },
	BILLBOARD03 = {
		width = 230,
		height = 220,
		kind = "billboard",
		color = Color3.fromRGB(122, 148, 255),
	},
	BILLBOARD02 = {
		width = 215,
		height = 220,
		kind = "billboard",
		color = Color3.fromRGB(108, 221, 205),
	},
	STUMP = { width = 195, height = 140, kind = "plant", color = Color3.fromRGB(118, 88, 62) },
	SEMI = { width = 122, height = 144, kind = "car", color = Color3.fromRGB(236, 236, 230) },
	TRUCK = { width = 100, height = 78, kind = "car", color = Color3.fromRGB(238, 126, 66) },
	CAR03 = { width = 88, height = 55, kind = "car", color = Color3.fromRGB(80, 156, 230) },
	CAR02 = { width = 80, height = 59, kind = "car", color = Color3.fromRGB(255, 213, 75) },
	CAR04 = { width = 80, height = 57, kind = "car", color = Color3.fromRGB(84, 210, 142) },
	CAR01 = { width = 80, height = 56, kind = "car", color = Color3.fromRGB(226, 72, 72) },
	PLAYER_UPHILL_LEFT = {
		width = 80,
		height = 45,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_UPHILL_STRAIGHT = {
		width = 80,
		height = 45,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_UPHILL_RIGHT = {
		width = 80,
		height = 45,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_LEFT = { width = 80, height = 41, kind = "player", color = Color3.fromRGB(255, 221, 78) },
	PLAYER_STRAIGHT = {
		width = 80,
		height = 41,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_RIGHT = {
		width = 80,
		height = 41,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_DOWNHILL_LEFT = {
		width = 80,
		height = 41,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_DOWNHILL_STRAIGHT = {
		width = 80,
		height = 41,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
	PLAYER_DOWNHILL_RIGHT = {
		width = 80,
		height = 41,
		kind = "player",
		color = Color3.fromRGB(255, 221, 78),
	},
}

for spriteName, spriteDef in RacerConfig.SpriteDefs do
	spriteDef.name = spriteName
end

function RacerConfig.playerSpriteDef(steer: number, updown: number)
	local spriteName
	if steer < 0 then
		if updown > 0 then
			spriteName = "PLAYER_UPHILL_LEFT"
		elseif updown < 0 then
			spriteName = "PLAYER_DOWNHILL_LEFT"
		else
			spriteName = "PLAYER_LEFT"
		end
	elseif steer > 0 then
		if updown > 0 then
			spriteName = "PLAYER_UPHILL_RIGHT"
		elseif updown < 0 then
			spriteName = "PLAYER_DOWNHILL_RIGHT"
		else
			spriteName = "PLAYER_RIGHT"
		end
	else
		if updown > 0 then
			spriteName = "PLAYER_UPHILL_STRAIGHT"
		elseif updown < 0 then
			spriteName = "PLAYER_DOWNHILL_STRAIGHT"
		else
			spriteName = "PLAYER_STRAIGHT"
		end
	end
	return RacerConfig.SpriteDefs[spriteName]
end

RacerConfig.SpriteSets = {
	Billboards = {
		"BILLBOARD01",
		"BILLBOARD02",
		"BILLBOARD03",
		"BILLBOARD04",
		"BILLBOARD05",
		"BILLBOARD06",
		"BILLBOARD07",
		"BILLBOARD08",
		"BILLBOARD09",
	},
	Plants = {
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
	},
	Cars = { "CAR01", "CAR02", "CAR03", "CAR04", "SEMI", "TRUCK" },
}

local function deterministicUnit(seed: number): number
	local value = math.sin(seed * 12.9898) * 43758.5453
	return value - math.floor(value)
end

function RacerConfig.playerBounce(
	position: number,
	speedPercent: number,
	resolution: number
): number
	local amplitude = 1.5 * deterministicUnit(position * 0.017 + speedPercent * 31)
	local sign = if deterministicUnit(position * 0.031 + speedPercent * 47) < 0.5 then -1 else 1
	return amplitude * speedPercent * resolution * sign
end

local function deterministicInt(seed: number, minValue: number, maxValue: number): number
	return RacerMath.limit(
		math.floor(minValue + (maxValue - minValue) * deterministicUnit(seed) + 0.5),
		minValue,
		maxValue
	)
end

local function deterministicFloorInt(seed: number, minValue: number, maxValue: number): number
	return RacerMath.limit(
		math.floor(minValue + (maxValue - minValue + 1) * deterministicUnit(seed)),
		minValue,
		maxValue
	)
end

local function deterministicChoice(options, seed: number)
	return options[deterministicInt(seed, 1, #options)]
end

local function buildTrafficCars(trackLength: number, seed: number?)
	local cars = {}
	local trafficSeed = seed or 1701
	local segmentCount = math.floor(trackLength / RacerConfig.SegmentLength)
	for index = 1, RacerConfig.Traffic.Count do
		local side = if deterministicUnit(trafficSeed + index * 5) < 0.5 then -1 else 1
		local spriteName =
			deterministicChoice(RacerConfig.SpriteSets.Cars, trafficSeed + index * 19)
		local spriteSize = RacerConfig.SpriteDefs[spriteName]
		table.insert(cars, {
			id = index,
			sprite = spriteName,
			z = deterministicFloorInt(trafficSeed + index * 7, 0, segmentCount - 1)
				* RacerConfig.SegmentLength,
			offset = deterministicUnit(trafficSeed + index * 13) * 0.8 * side,
			speed = RacerConfig.MaxSpeed
				* (
					0.25
					+ deterministicUnit(trafficSeed + index * 17)
						* (if spriteSize.height > 100 then 0.25 else 0.5)
				),
			width = spriteSize.width,
			height = spriteSize.height,
			color = spriteSize.color,
		})
	end
	return cars
end

local ROAD = {
	LENGTH = { NONE = 0, SHORT = 25, MEDIUM = 50, LONG = 100 },
	HILL = { NONE = 0, LOW = 20, MEDIUM = 40, HIGH = 60 },
	CURVE = { NONE = 0, EASY = 2, MEDIUM = 4, HARD = 6 },
}

local function lastY(track): number
	return if #track == 0 then 0 else track[#track].y2
end

local function addSegment(track, curve: number, y: number?)
	local startY = lastY(track)
	local index = #track
	local endY = y or startY
	table.insert(track, {
		index = index,
		curve = curve,
		y1 = startY,
		y2 = endY,
		p1 = {
			world = {
				y = startY,
				z = index * RacerConfig.SegmentLength,
			},
		},
		p2 = {
			world = {
				y = endY,
				z = (index + 1) * RacerConfig.SegmentLength,
			},
		},
		sprites = {},
		cars = {},
	})
end

local function addRoad(track, enter: number, hold: number, leave: number, curve: number, y: number?)
	local startY = lastY(track)
	local endY = startY + (y or 0) * RacerConfig.SegmentLength
	local total = enter + hold + leave
	local n = 0
	while n < enter do
		addSegment(
			track,
			RacerMath.easeIn(0, curve, n / enter),
			RacerMath.easeInOut(startY, endY, n / total)
		)
		n += 1
	end

	n = 0
	while n < hold do
		addSegment(track, curve, RacerMath.easeInOut(startY, endY, (enter + n) / total))
		n += 1
	end

	n = 0
	while n < leave do
		addSegment(
			track,
			RacerMath.easeInOut(curve, 0, n / leave),
			RacerMath.easeInOut(startY, endY, (enter + hold + n) / total)
		)
		n += 1
	end
end

local function addStraight(track, num: number?)
	local length = num or ROAD.LENGTH.MEDIUM
	addRoad(track, length, length, length, 0, 0)
end

local function addHill(track, num: number?, height: number?)
	local length = num or ROAD.LENGTH.MEDIUM
	addRoad(track, length, length, length, 0, height or ROAD.HILL.MEDIUM)
end

local function addCurve(track, num: number?, curve: number?, height: number?)
	local length = num or ROAD.LENGTH.MEDIUM
	addRoad(track, length, length, length, curve or ROAD.CURVE.MEDIUM, height or ROAD.HILL.NONE)
end

local function addLowRollingHills(track, num: number?, height: number?)
	local length = num or ROAD.LENGTH.SHORT
	local hillHeight = height or ROAD.HILL.LOW
	addRoad(track, length, length, length, 0, hillHeight / 2)
	addRoad(track, length, length, length, 0, -hillHeight)
	addRoad(track, length, length, length, 0, hillHeight)
	addRoad(track, length, length, length, 0, 0)
	addRoad(track, length, length, length, 0, hillHeight / 2)
	addRoad(track, length, length, length, 0, 0)
end

local function addFinalLowRollingHills(track, num: number?, height: number?)
	local length = num or ROAD.LENGTH.SHORT
	local hillHeight = height or ROAD.HILL.LOW
	addRoad(track, length, length, length, 0, hillHeight / 2)
	addRoad(track, length, length, length, 0, -hillHeight)
	addRoad(track, length, length, length, ROAD.CURVE.EASY, hillHeight)
	addRoad(track, length, length, length, 0, 0)
	addRoad(track, length, length, length, -ROAD.CURVE.EASY, hillHeight / 2)
	addRoad(track, length, length, length, 0, 0)
end

local function addBumps(track)
	addRoad(track, 10, 10, 10, 0, 5)
	addRoad(track, 10, 10, 10, 0, -2)
	addRoad(track, 10, 10, 10, 0, -5)
	addRoad(track, 10, 10, 10, 0, 8)
	addRoad(track, 10, 10, 10, 0, 5)
	addRoad(track, 10, 10, 10, 0, -7)
	addRoad(track, 10, 10, 10, 0, 5)
	addRoad(track, 10, 10, 10, 0, -2)
end

local function addFlatSCurves(track)
	addRoad(track, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, -ROAD.CURVE.EASY)
	addRoad(track, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM)
	addRoad(track, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.CURVE.EASY)
	addRoad(track, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, -ROAD.CURVE.EASY)
	addRoad(track, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, ROAD.LENGTH.MEDIUM, -ROAD.CURVE.MEDIUM)
end

local function addSCurves(track)
	addRoad(
		track,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		-ROAD.CURVE.EASY,
		ROAD.HILL.NONE
	)
	addRoad(
		track,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.CURVE.MEDIUM,
		ROAD.HILL.MEDIUM
	)
	addRoad(
		track,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.CURVE.EASY,
		-ROAD.HILL.LOW
	)
	addRoad(
		track,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		-ROAD.CURVE.EASY,
		ROAD.HILL.MEDIUM
	)
	addRoad(
		track,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		ROAD.LENGTH.MEDIUM,
		-ROAD.CURVE.MEDIUM,
		-ROAD.HILL.MEDIUM
	)
end

local function addDownhillToEnd(track, num: number?)
	local length = num or 200
	addRoad(
		track,
		length,
		length,
		length,
		-ROAD.CURVE.EASY,
		-lastY(track) / RacerConfig.SegmentLength
	)
end

local function buildStraightTrack()
	local track = {}
	for _ = 1, RacerConfig.SegmentCount do
		addSegment(track, 0, 0)
	end
	return track
end

local function buildCurvesTrack()
	local track = {}
	addStraight(track, ROAD.LENGTH.SHORT / 4)
	addFlatSCurves(track)
	addStraight(track, ROAD.LENGTH.LONG)
	addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM)
	addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)
	addStraight(track)
	addFlatSCurves(track)
	addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM)
	addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM)
	addStraight(track)
	addFlatSCurves(track)
	addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.EASY)
	return track
end

local function buildHillsTrack()
	local track = {}
	addStraight(track, ROAD.LENGTH.SHORT / 2)
	addHill(track, ROAD.LENGTH.SHORT, ROAD.HILL.LOW)
	addLowRollingHills(track)
	addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)
	addLowRollingHills(track)
	addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)
	addStraight(track)
	addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)
	addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)
	addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)
	addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)
	addStraight(track)
	addDownhillToEnd(track)
	return track
end

local function buildFinalTrack()
	local track = {}
	addStraight(track, ROAD.LENGTH.SHORT)
	addFinalLowRollingHills(track)
	addSCurves(track)
	addCurve(track, ROAD.LENGTH.MEDIUM, ROAD.CURVE.MEDIUM, ROAD.HILL.LOW)
	addBumps(track)
	addFinalLowRollingHills(track)
	addCurve(track, ROAD.LENGTH.LONG * 2, ROAD.CURVE.MEDIUM, ROAD.HILL.MEDIUM)
	addStraight(track)
	addHill(track, ROAD.LENGTH.MEDIUM, ROAD.HILL.HIGH)
	addSCurves(track)
	addCurve(track, ROAD.LENGTH.LONG, -ROAD.CURVE.MEDIUM, ROAD.HILL.NONE)
	addHill(track, ROAD.LENGTH.LONG, ROAD.HILL.HIGH)
	addCurve(track, ROAD.LENGTH.LONG, ROAD.CURVE.MEDIUM, -ROAD.HILL.LOW)
	addBumps(track)
	addHill(track, ROAD.LENGTH.LONG, -ROAD.HILL.MEDIUM)
	addStraight(track)
	addSCurves(track)
	addDownhillToEnd(track)
	return track
end

local finalTrack = buildFinalTrack()
RacerConfig.Tracks = {
	straight = buildStraightTrack(),
	curves = buildCurvesTrack(),
	hills = buildHillsTrack(),
	final = finalTrack,
	v5 = finalTrack,
	v6 = finalTrack,
	v7 = finalTrack,
}

RacerConfig.V5Junctions = {
	{ segment = 880, length = 26, kind = "cross" },
	{ segment = 2160, length = 22, kind = "left" },
	{ segment = 3650, length = 24, kind = "right" },
	{ segment = 5280, length = 28, kind = "cross" },
}
RacerConfig.V5JunctionTrafficBuffer = 8

function RacerConfig.junctionForSegment(mode: string, segmentIndex: number, buffer: number?): string?
	return nil
end

function RacerConfig.buildTraffic(mode: string, seed: number?)
	local track = RacerConfig.Tracks[mode] or RacerConfig.Tracks.straight
	return buildTrafficCars(#track * RacerConfig.SegmentLength, seed)
end

local function buildSpriteObjectsForTrack(mode: string, seed: number?)
	if not RacerConfig.Modes[mode] or not RacerConfig.Modes[mode].sprites then
		return {}
	end

	local spriteSeed = seed or 2401
	local track = RacerConfig.Tracks[mode] or RacerConfig.Tracks.straight
	local segmentCount = #track
	local objects = {}

	local function addSprite(segmentIndex: number, spriteName: string, offset: number)
		local wrappedIndex = ((segmentIndex % segmentCount) + segmentCount) % segmentCount
		table.insert(objects, {
			segmentIndex = wrappedIndex,
			sprite = spriteName,
			offset = offset,
			definition = RacerConfig.SpriteDefs[spriteName],
		})
	end

	addSprite(20, "BILLBOARD07", -1)
	addSprite(40, "BILLBOARD06", -1)
	addSprite(60, "BILLBOARD08", -1)
	addSprite(80, "BILLBOARD09", -1)
	addSprite(100, "BILLBOARD01", -1)
	addSprite(120, "BILLBOARD02", -1)
	addSprite(140, "BILLBOARD03", -1)
	addSprite(160, "BILLBOARD04", -1)
	addSprite(180, "BILLBOARD05", -1)
	addSprite(240, "BILLBOARD07", -1.2)
	addSprite(240, "BILLBOARD06", 1.2)
	addSprite(segmentCount - 25, "BILLBOARD07", -1.2)
	addSprite(segmentCount - 25, "BILLBOARD06", 1.2)

	local n = 10
	while n < 200 do
		addSprite(n, "PALM_TREE", 0.5 + deterministicUnit(spriteSeed + n * 3) * 0.5)
		addSprite(n, "PALM_TREE", 1 + deterministicUnit(spriteSeed + n * 5) * 2)
		n += 4 + math.floor(n / 100)
	end

	n = 250
	while n < 1000 and n < segmentCount do
		addSprite(n, "COLUMN", 1.1)
		addSprite(
			n + deterministicInt(spriteSeed + n * 7, 0, 5),
			"TREE1",
			-1 - deterministicUnit(spriteSeed + n * 11) * 2
		)
		addSprite(
			n + deterministicInt(spriteSeed + n * 13, 0, 5),
			"TREE2",
			-1 - deterministicUnit(spriteSeed + n * 17) * 2
		)
		n += 5
	end

	n = 200
	while n < segmentCount do
		local side = if deterministicUnit(spriteSeed + n * 19) < 0.5 then -1 else 1
		addSprite(
			n,
			deterministicChoice(RacerConfig.SpriteSets.Plants, spriteSeed + n * 23),
			side * (2 + deterministicUnit(spriteSeed + n * 29) * 5)
		)
		n += 3
	end

	n = 1000
	while n < segmentCount - 50 do
		local side = if deterministicUnit(spriteSeed + n * 31) < 0.5 then -1 else 1
		addSprite(
			n + deterministicInt(spriteSeed + n * 37, 0, 50),
			deterministicChoice(RacerConfig.SpriteSets.Billboards, spriteSeed + n * 41),
			-side
		)
		for i = 0, 19 do
			addSprite(
				n + deterministicInt(spriteSeed + n * 43 + i, 0, 50),
				deterministicChoice(RacerConfig.SpriteSets.Plants, spriteSeed + n * 47 + i),
				side * (1.5 + deterministicUnit(spriteSeed + n * 53 + i))
			)
		end
		n += 100
	end

	return objects
end

function RacerConfig.buildSpriteObjects(mode: string, seed: number?)
	return buildSpriteObjectsForTrack(mode, seed)
end

local finalSpriteObjects = RacerConfig.buildSpriteObjects("final", 2401)
RacerConfig.Traffic.Cars = RacerConfig.buildTraffic("final", 1701)
RacerConfig.SpriteObjects = {
	final = finalSpriteObjects,
	v5 = shallowArrayCopy(finalSpriteObjects),
	v6 = shallowArrayCopy(finalSpriteObjects),
	v7 = shallowArrayCopy(finalSpriteObjects),
}
RacerConfig.SpritesBySegment = {
	final = {},
	v5 = {},
	v6 = {},
	v7 = {},
}

function RacerConfig.segmentCount(mode: string): number
	local track = RacerConfig.Tracks[mode] or RacerConfig.Tracks.straight
	return #track
end

function RacerConfig.trackLength(mode: string): number
	return RacerConfig.segmentCount(mode) * RacerConfig.SegmentLength
end

RacerConfig.TrackLength = RacerConfig.trackLength("straight")

for mode, sprites in RacerConfig.SpriteObjects do
	for _, sprite in sprites do
		local bySegment = RacerConfig.SpritesBySegment[mode]
		local list = bySegment[sprite.segmentIndex]
		if not list then
			list = {}
		end
		table.insert(list, sprite)
		bySegment[sprite.segmentIndex] = list
	end
end

function RacerConfig.maxSpriteObjectsInDrawWindow(mode: string, drawDistance: number): number
	local segmentCount = RacerConfig.segmentCount(mode)
	local bySegment = RacerConfig.SpritesBySegment[mode]
	if not bySegment or segmentCount <= 0 then
		return 0
	end

	local maxCount = 0
	for startIndex = 0, segmentCount - 1 do
		local count = 0
		for offset = 0, drawDistance - 1 do
			count += #(bySegment[(startIndex + offset) % segmentCount] or {})
		end
		maxCount = math.max(maxCount, count)
	end
	return maxCount
end

RacerConfig.FinalObjectCount = RacerConfig.Traffic.Count
	+ RacerConfig.maxSpriteObjectsInDrawWindow("final", RacerConfig.MaxDrawDistance)

function RacerConfig.spriteObjectsFor(mode: string)
	return RacerConfig.SpriteObjects[mode] or {}
end

function RacerConfig.spritesForSegment(mode: string, index: number)
	local bySegment = RacerConfig.SpritesBySegment[mode]
	return if bySegment then bySegment[index] or {} else {}
end

function RacerConfig.roadsideSpriteCenter(sprite): number
	local spriteWidth = sprite.definition.width * RacerConfig.SpriteScale
	local side = if sprite.offset > 0 then 1 else -1
	return sprite.offset + spriteWidth / 2 * side
end

function RacerConfig.roadsideCollisionSprite(mode: string, segmentIndex: number, playerX: number)
	local playerWidth = RacerConfig.Traffic.PlayerWidth
	for _, sprite in RacerConfig.spritesForSegment(mode, segmentIndex) do
		local spriteWidth = sprite.definition.width * RacerConfig.SpriteScale
		local spriteCenter = RacerConfig.roadsideSpriteCenter(sprite)
		if RacerMath.overlap(playerX, playerWidth, spriteCenter, spriteWidth) then
			return sprite
		end
	end
	return nil
end

function RacerConfig.roadsideCollisionPosition(
	segmentIndex: number,
	playerZ: number,
	trackLength: number
): number
	return RacerMath.increase(segmentIndex * RacerConfig.SegmentLength, -playerZ, trackLength)
end

function RacerConfig.trafficCollisionCar(
	trafficItems,
	playerSegmentIndex: number,
	playerX: number,
	playerSpeed: number,
	_segmentCount: number,
	trafficBySegment
)
	local currentTraffic = if trafficBySegment
		then trafficBySegment[playerSegmentIndex] or {}
		else trafficItems
	for _, item in currentTraffic do
		if
			item.segmentIndex == playerSegmentIndex
			and playerSpeed > item.speed
			and RacerMath.overlap(
				playerX,
				RacerConfig.Traffic.PlayerWidth,
				item.offset,
				item.width,
				RacerConfig.Traffic.CollisionOverlap
			)
		then
			return item
		end
	end
	return nil
end

function RacerConfig.trafficCollisionPosition(
	trafficZ: number,
	playerZ: number,
	trackLength: number
): number
	return RacerMath.increase(trafficZ, -playerZ, trackLength)
end

function RacerConfig.trafficSnapshot(
	trafficTime: number,
	trackLength: number,
	segmentCount: number,
	mode: string?
)
	local items = {}
	for _, car in RacerConfig.Traffic.Cars do
		local z = RacerMath.increase(car.z, car.speed * trafficTime, trackLength)
		local segmentIndex = math.floor(z / RacerConfig.SegmentLength) % segmentCount
		if not RacerConfig.junctionForSegment(mode or "final", segmentIndex, RacerConfig.V5JunctionTrafficBuffer) then
			table.insert(items, {
				car = car,
				z = z,
				segmentIndex = segmentIndex,
				percent = RacerMath.percentRemaining(z, RacerConfig.SegmentLength),
				offset = car.offset,
				speed = car.speed,
				width = car.width * RacerConfig.SpriteScale,
			})
		end
	end
	return items
end

function RacerConfig.trafficBySegment(trafficItems)
	local bySegment = {}
	for _, item in trafficItems do
		local list = bySegment[item.segmentIndex]
		if not list then
			list = {}
			bySegment[item.segmentIndex] = list
		end
		table.insert(list, item)
	end
	return bySegment
end

function RacerConfig.createTrafficState(
	trafficTime: number,
	trackLength: number,
	segmentCount: number,
	trafficOffsets,
	mode: string?
)
	local trafficItems = RacerConfig.trafficSnapshot(trafficTime, trackLength, segmentCount, mode)
	if trafficOffsets then
		RacerConfig.applyTrafficOffsets(trafficOffsets, trafficItems)
	end
	return {
		items = trafficItems,
		bySegment = RacerConfig.trafficBySegment(trafficItems),
		time = trafficTime,
	}
end

function RacerConfig.applyTrafficOffsets(trafficOffsets, trafficItems)
	for _, item in trafficItems do
		local currentOffset = trafficOffsets[item.car.id]
		if currentOffset ~= nil then
			item.offset = currentOffset
		end
	end
	return trafficItems
end

function RacerConfig.baseTrafficOffsets()
	local offsets = {}
	for _, car in RacerConfig.Traffic.Cars do
		offsets[car.id] = car.offset
	end
	return offsets
end

function RacerConfig.packTrafficOffsets(trafficOffsets): string
	local values = {}
	for _, car in RacerConfig.Traffic.Cars do
		local offset = trafficOffsets[car.id]
		if offset == nil then
			offset = car.offset
		end
		table.insert(values, string.format("%.6f", offset))
	end
	return table.concat(values, ",")
end

function RacerConfig.unpackTrafficOffsets(blob: string)
	local trafficOffsets = {}
	local values = string.split(blob, ",")
	for index, value in values do
		local car = RacerConfig.Traffic.Cars[index]
		if car then
			local offset = tonumber(value)
			if offset then
				trafficOffsets[car.id] = offset
			end
		end
	end
	return trafficOffsets
end

local function removeTrafficFromSegment(trafficBySegment, segmentIndex: number, item)
	local list = trafficBySegment[segmentIndex]
	if not list then
		return
	end
	for index, candidate in list do
		if candidate == item then
			table.remove(list, index)
			break
		end
	end
end

local function insertTrafficIntoSegment(trafficBySegment, segmentIndex: number, item)
	local list = trafficBySegment[segmentIndex]
	if not list then
		list = {}
		trafficBySegment[segmentIndex] = list
	end
	table.insert(list, item)
end

function RacerConfig.advanceTraffic(
	trafficOffsets,
	trafficTime: number,
	dt: number,
	trackLength: number,
	segmentCount: number,
	playerSegmentIndex: number,
	playerX: number,
	playerSpeed: number,
	drawDistance: number?,
	trafficState,
	mode: string?
)
	local trafficItems = nil
	local trafficBySegment = nil
	if
		trafficState
		and trafficState.items
		and trafficState.bySegment
		and trafficState.time
		and math.abs(trafficState.time - trafficTime) <= RacerConfig.Step * 1.5
	then
		trafficItems = trafficState.items
		trafficBySegment = trafficState.bySegment
	else
		local rebuiltState =
			RacerConfig.createTrafficState(trafficTime, trackLength, segmentCount, trafficOffsets, mode)
		trafficItems = rebuiltState.items
		trafficBySegment = rebuiltState.bySegment
		if trafficState then
			trafficState.items = trafficItems
			trafficState.bySegment = trafficBySegment
			trafficState.time = trafficTime
		end
	end

	for _, item in trafficItems do
		local oldSegmentIndex = item.segmentIndex
		item.offset += RacerConfig.trafficOffsetDelta(
			item,
			trafficItems,
			playerSegmentIndex,
			playerX,
			playerSpeed,
			segmentCount,
			trafficBySegment,
			drawDistance
		)
		trafficOffsets[item.car.id] = item.offset

		item.z = RacerMath.increase(item.z, item.speed * dt, trackLength)
		item.percent = RacerMath.percentRemaining(item.z, RacerConfig.SegmentLength)
		item.segmentIndex = math.floor(item.z / RacerConfig.SegmentLength) % segmentCount
		if item.segmentIndex ~= oldSegmentIndex then
			removeTrafficFromSegment(trafficBySegment, oldSegmentIndex, item)
			insertTrafficIntoSegment(trafficBySegment, item.segmentIndex, item)
		end
	end
	if trafficState then
		trafficState.time = trafficTime + dt
	end

	return trafficItems, trafficBySegment
end

function RacerConfig.trafficOffsetDelta(
	item,
	trafficItems,
	playerSegmentIndex: number,
	playerX: number,
	playerSpeed: number,
	segmentCount: number,
	trafficBySegment,
	drawDistance: number?
): number
	local car = item.car
	local carWidth = item.width
	local delta = 0
	if item.segmentIndex - playerSegmentIndex > (drawDistance or RacerConfig.DrawDistance) then
		return 0
	end

	for lookahead = 1, RacerConfig.Traffic.Lookahead - 1 do
		local segmentIndex = (item.segmentIndex + lookahead) % segmentCount
		if
			segmentIndex == playerSegmentIndex
			and car.speed > playerSpeed
			and RacerMath.overlap(
				playerX,
				RacerConfig.Traffic.PlayerWidth,
				item.offset,
				carWidth,
				1.2
			)
		then
			local direction
			if playerX > 0.5 then
				direction = -1
			elseif playerX < -0.5 then
				direction = 1
			else
				direction = if item.offset > playerX then 1 else -1
			end
			delta = direction * (1 / lookahead) * ((car.speed - playerSpeed) / RacerConfig.MaxSpeed)
			break
		end

		local nearbyTraffic = if trafficBySegment
			then trafficBySegment[segmentIndex] or {}
			else trafficItems
		for _, other in nearbyTraffic do
			if other ~= item and (trafficBySegment or other.segmentIndex == segmentIndex) then
				if
					car.speed > other.speed
					and RacerMath.overlap(item.offset, carWidth, other.offset, other.width, 1.2)
				then
					local direction
					if other.offset > 0.5 then
						direction = -1
					elseif other.offset < -0.5 then
						direction = 1
					else
						direction = if item.offset > other.offset then 1 else -1
					end
					delta = direction
						* (1 / lookahead)
						* ((car.speed - other.speed) / RacerConfig.MaxSpeed)
					break
				end
			end
		end

		if delta ~= 0 then
			break
		end
	end

	if delta == 0 then
		if item.offset < -0.9 then
			delta = 0.1
		elseif item.offset > 0.9 then
			delta = -0.1
		end
	end

	return delta
end

function RacerConfig.segmentColor(mode: string, index: number, _playerZ: number)
	local color = if math.floor(index / RacerConfig.RumbleLength) % 2 == 0
		then RacerConfig.Colors.Light
		else RacerConfig.Colors.Dark

	local playerSegmentIndex = math.floor(RacerConfig.PlayerZ / RacerConfig.SegmentLength)
	if index == playerSegmentIndex + 2 or index == playerSegmentIndex + 3 then
		return RacerConfig.Colors.Start
	end
	if index >= RacerConfig.segmentCount(mode) - RacerConfig.RumbleLength then
		return RacerConfig.Colors.Finish
	end
	return color
end

function RacerConfig.curveFor(mode: string, index: number): number
	local track = RacerConfig.Tracks[mode] or RacerConfig.Tracks.straight
	return track[(index % #track) + 1].curve
end

function RacerConfig.segmentFor(mode: string, index: number)
	local track = RacerConfig.Tracks[mode] or RacerConfig.Tracks.straight
	return track[(index % #track) + 1]
end

return RacerConfig
