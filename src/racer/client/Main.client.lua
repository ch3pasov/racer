local Players = game:GetService("Players")
local ContextActionService = game:GetService("ContextActionService")
local GuiService = game:GetService("GuiService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local StarterGui = game:GetService("StarterGui")
local UserInputService = game:GetService("UserInputService")
local Workspace = game:GetService("Workspace")

local racerShared = ReplicatedStorage:WaitForChild("RacerShared")
local RacerConfig = require(racerShared.RacerConfig)
local RacerMath = require(racerShared.RacerMath)
local RacerTextures = require(racerShared.RacerTextures)

local player = Players.LocalPlayer
local actionEvent = ReplicatedStorage:WaitForChild("RacerAction")
local inputEvent = ReplicatedStorage:WaitForChild("RacerInput")
local perfLogEvent = ReplicatedStorage:WaitForChild("RacerPerfLog")
local v5BillboardText = ReplicatedStorage:WaitForChild("RacerV5BillboardText") :: StringValue
local statesFolder = ReplicatedStorage:WaitForChild("RacerStates")

local WIDTH = RacerConfig.Width
local HEIGHT = RacerConfig.Height
local ROW_COUNT = RacerConfig.MaxDrawDistance
local ROAD_SCANLINE_HEIGHT = 2
local CONTROL_ACTION = "RacerScreenControls"
local OVERLAY_Z_INDEX = 10000
local ACTIVE_STATUS_MARGIN_TOP = 14
local ROAD_Z_INDEX = 20
local ROAD_DETAIL_Z_INDEX = ROAD_Z_INDEX + 1
local ROAD_LANE_Z_INDEX = ROAD_Z_INDEX + 2
local OBJECT_Z_BASE = 300
local PLAYER_CAR_Z_INDEX = 420
local FINAL_OBJECT_COUNT = RacerConfig.FinalObjectCount
local WORLD_RENDER_INTERVAL = 1 / 20
local WORLD_SCREEN_MAX_DISTANCE = 185
local SETTINGS_LABEL_INTERVAL = 0.2
local PERF_LOG_INTERVAL = 5
local OBJECT_Z_STRIDE = 4
local STUTTER_FRAME_TIME = 1 / 30
local SEVERE_STUTTER_FRAME_TIME = 1 / 15
local MAX_PREDICTION_ACCUMULATED_TIME = 1
local MAX_PREDICTION_STEPS_PER_FRAME = 8
local SCREEN_MIN_X = 0
local SCREEN_MAX_X = WIDTH
local SCREEN_MIN_Y = 0
local SCREEN_MAX_Y = HEIGHT

local BACKGROUND_SPEEDS = {
	Sky = 0.001,
	Hill = 0.002,
	Tree = 0.003,
}

local useTextureArt = true
local avatarImageCache = {}

local keyMap = {
	[Enum.KeyCode.A] = "left",
	[Enum.KeyCode.Left] = "left",
	[Enum.KeyCode.D] = "right",
	[Enum.KeyCode.Right] = "right",
	[Enum.KeyCode.W] = "faster",
	[Enum.KeyCode.Up] = "faster",
	[Enum.KeyCode.S] = "slower",
	[Enum.KeyCode.Down] = "slower",
}

local inputNames = { "left", "right", "faster", "slower" }
local states = {}
local pressedInputs = {}
local keyboardInputs = {}
local pointerInputs = {}

local function valueProxy(value)
	return { Value = value }
end

local function loadState(screenId: string)
	local folder = statesFolder:WaitForChild(screenId)
	local state = {
		id = screenId,
		folder = folder,
		activeUserId = folder:WaitForChild("ActiveUserId") :: IntValue,
		activePlayerName = folder:WaitForChild("ActivePlayerName") :: StringValue,
		position = folder:WaitForChild("Position") :: NumberValue,
		speed = folder:WaitForChild("Speed") :: NumberValue,
		trafficTime = folder:WaitForChild("TrafficTime") :: NumberValue,
		trafficOffsetsBlob = folder:WaitForChild("TrafficOffsets") :: StringValue,
		currentLapTime = folder:WaitForChild("CurrentLapTime") :: NumberValue,
		lastLapTime = folder:WaitForChild("LastLapTime") :: NumberValue,
		fastLapTime = folder:WaitForChild("FastLapTime") :: NumberValue,
		visibleCars = folder:WaitForChild("VisibleCars") :: IntValue,
		visibleSprites = folder:WaitForChild("VisibleSprites") :: IntValue,
		clippedObjects = folder:WaitForChild("ClippedObjects") :: IntValue,
		playerX = folder:WaitForChild("PlayerX") :: NumberValue,
		steer = folder:WaitForChild("Steer") :: NumberValue,
		skyOffset = folder:WaitForChild("SkyOffset") :: NumberValue,
		hillOffset = folder:WaitForChild("HillOffset") :: NumberValue,
		treeOffset = folder:WaitForChild("TreeOffset") :: NumberValue,
		status = folder:WaitForChild("Status") :: StringValue,
		screenName = folder:WaitForChild("ScreenName") :: StringValue,
		mode = folder:WaitForChild("Mode") :: StringValue,
		settingRoadWidth = folder:WaitForChild("SettingRoadWidth") :: NumberValue,
		settingCameraHeight = folder:WaitForChild("SettingCameraHeight") :: NumberValue,
		settingDrawDistance = folder:WaitForChild("SettingDrawDistance") :: NumberValue,
		settingFieldOfView = folder:WaitForChild("SettingFieldOfView") :: NumberValue,
		settingFogDensity = folder:WaitForChild("SettingFogDensity") :: NumberValue,
		settingLanes = folder:WaitForChild("SettingLanes") :: NumberValue,
	}
	states[screenId] = state
	return state
end

for _, definition in RacerConfig.Screens do
	loadState(definition.Id)
end

local function activeState()
	for _, state in states do
		if state.activeUserId.Value == player.UserId then
			return state
		end
	end
	return nil
end

local function thumbnailForUserId(userId: number): string?
	if userId <= 0 then
		return nil
	end
	if avatarImageCache[userId] ~= nil then
		return avatarImageCache[userId]
	end
	local ok, image = pcall(function()
		return Players:GetUserThumbnailAsync(
			userId,
			Enum.ThumbnailType.AvatarBust,
			Enum.ThumbnailSize.Size100x100
		)
	end)
	avatarImageCache[userId] = if ok then image else false
	return if ok then image else nil
end

local function passengerUserIdFor(activeUserId: number): number
	for _, otherPlayer in Players:GetPlayers() do
		if otherPlayer.UserId ~= activeUserId then
			return otherPlayer.UserId
		end
	end
	return 0
end

local function anyBusyStatus(): string?
	for _, state in states do
		if state.activeUserId.Value ~= 0 then
			return state.status.Value
		end
	end
	return nil
end

local predictedState = nil
local predictedSourceId = nil

local function replicatedTrafficOffsets(state)
	if state.trafficOffsetsBlob == nil or state.trafficOffsetsBlob.Value == "" then
		return nil
	end
	if state.decodedTrafficOffsetsBlob ~= state.trafficOffsetsBlob.Value then
		state.decodedTrafficOffsetsBlob = state.trafficOffsetsBlob.Value
		state.decodedTrafficOffsets =
			RacerConfig.unpackTrafficOffsets(state.decodedTrafficOffsetsBlob)
	end
	return state.decodedTrafficOffsets
end

local function cloneTrafficOffsets(source)
	local clone = {}
	if source then
		for id, offset in source do
			clone[id] = offset
		end
	end
	return clone
end

local function copyPredictedState(source)
	local trafficOffsets = cloneTrafficOffsets(replicatedTrafficOffsets(source))
	local mode = source.mode.Value
	local trafficState = nil
	if RacerConfig.isFinalLike(mode) then
		local trackLength = RacerConfig.trackLength(mode)
		local segmentCount = RacerConfig.segmentCount(mode)
		trafficState = RacerConfig.createTrafficState(
			source.trafficTime.Value,
			trackLength,
			segmentCount,
			trafficOffsets,
			mode
		)
	end
	return {
		id = source.id,
		activePlayerName = source.activePlayerName,
		position = valueProxy(source.position.Value),
		speed = valueProxy(source.speed.Value),
		trafficTime = valueProxy(source.trafficTime.Value),
		currentLapTime = valueProxy(source.currentLapTime.Value),
		lastLapTime = valueProxy(source.lastLapTime.Value),
		fastLapTime = valueProxy(source.fastLapTime.Value),
		lapStarted = source.currentLapTime.Value > 0,
		playerX = valueProxy(source.playerX.Value),
		steer = valueProxy(source.steer.Value),
		skyOffset = valueProxy(source.skyOffset.Value),
		hillOffset = valueProxy(source.hillOffset.Value),
		treeOffset = valueProxy(source.treeOffset.Value),
		trafficOffsets = trafficOffsets,
		trafficState = trafficState,
		trafficBySegment = if trafficState then trafficState.bySegment else nil,
		mode = source.mode,
		settingRoadWidth = source.settingRoadWidth,
		settingCameraHeight = source.settingCameraHeight,
		settingDrawDistance = source.settingDrawDistance,
		settingFieldOfView = source.settingFieldOfView,
		settingFogDensity = source.settingFogDensity,
		settingLanes = source.settingLanes,
		accumulator = 0,
	}
end

local function ensurePredictedState(source)
	if not predictedState or predictedSourceId ~= source.id then
		predictedState = copyPredictedState(source)
		predictedSourceId = source.id
		return predictedState
	end

	predictedState.fastLapTime.Value = math.min(
		predictedState.fastLapTime.Value,
		source.fastLapTime.Value
	)
	predictedState.lastLapTime.Value = source.lastLapTime.Value
	return predictedState
end

local function updatePredictedState(source, dt: number)
	local prediction = ensurePredictedState(source)
	prediction.accumulator += math.min(dt, MAX_PREDICTION_ACCUMULATED_TIME)

	local steps = 0
	while prediction.accumulator >= RacerConfig.Step and steps < MAX_PREDICTION_STEPS_PER_FRAME do
		local step = RacerConfig.Step
		local mode = prediction.mode.Value
		local trackLength = RacerConfig.trackLength(mode)
		local speedPercent = prediction.speed.Value / RacerConfig.MaxSpeed
		local dx = step * 2 * speedPercent
		local startPosition = prediction.position.Value
		local fieldOfView = prediction.settingFieldOfView.Value
		local cameraHeight = prediction.settingCameraHeight.Value
		local cameraDepth = 1 / math.tan(math.rad(fieldOfView / 2))
		local playerZ = cameraHeight * cameraDepth
		local segmentCount = RacerConfig.segmentCount(mode)
		local segmentIndex = math.floor(
			(prediction.position.Value + playerZ) / RacerConfig.SegmentLength
		) % segmentCount
		local curve = RacerConfig.curveFor(mode, segmentIndex)
		local trafficItems = nil
		local trafficBySegment = nil

		if RacerConfig.isFinalLike(mode) then
			trafficItems, trafficBySegment = RacerConfig.advanceTraffic(
				prediction.trafficOffsets,
				prediction.trafficTime.Value,
				step,
				trackLength,
				segmentCount,
				segmentIndex,
				prediction.playerX.Value,
				prediction.speed.Value,
				prediction.settingDrawDistance.Value,
				prediction.trafficState,
				mode
			)
			prediction.trafficBySegment = trafficBySegment
		else
			prediction.trafficBySegment = nil
		end

		if RacerConfig.isFinalLike(mode) then
			prediction.trafficTime.Value += step
		end
		prediction.position.Value = RacerMath.increase(
			prediction.position.Value,
			step * prediction.speed.Value,
			trackLength
		)
		if not RacerConfig.isFinalLike(mode) then
			prediction.skyOffset.Value = RacerMath.increase(
				prediction.skyOffset.Value,
				BACKGROUND_SPEEDS.Sky * curve * speedPercent,
				1
			)
			prediction.hillOffset.Value = RacerMath.increase(
				prediction.hillOffset.Value,
				BACKGROUND_SPEEDS.Hill * curve * speedPercent,
				1
			)
			prediction.treeOffset.Value = RacerMath.increase(
				prediction.treeOffset.Value,
				BACKGROUND_SPEEDS.Tree * curve * speedPercent,
				1
			)
		end

		prediction.steer.Value = 0
		if pressedInputs.left then
			prediction.steer.Value = -1
			prediction.playerX.Value -= dx
		elseif pressedInputs.right then
			prediction.steer.Value = 1
			prediction.playerX.Value += dx
		end
		prediction.playerX.Value -= dx * speedPercent * curve * 0.3

		if pressedInputs.faster then
			prediction.speed.Value =
				RacerMath.accelerate(prediction.speed.Value, RacerConfig.Accel, step)
		elseif pressedInputs.slower then
			prediction.speed.Value =
				RacerMath.accelerate(prediction.speed.Value, RacerConfig.Braking, step)
		else
			prediction.speed.Value =
				RacerMath.accelerate(prediction.speed.Value, RacerConfig.Decel, step)
		end

		if
			(prediction.playerX.Value < -1 or prediction.playerX.Value > 1)
			and prediction.speed.Value > RacerConfig.OffRoadLimit
		then
			prediction.speed.Value =
				RacerMath.accelerate(prediction.speed.Value, RacerConfig.OffRoadDecel, step)
		end

		if RacerConfig.isFinalLike(mode) and (prediction.playerX.Value < -1 or prediction.playerX.Value > 1) then
			local roadsideSprite =
				RacerConfig.roadsideCollisionSprite(mode, segmentIndex, prediction.playerX.Value)
			if roadsideSprite then
				prediction.speed.Value = RacerConfig.RoadsideCollisionSpeed
				prediction.position.Value =
					RacerConfig.roadsideCollisionPosition(segmentIndex, playerZ, trackLength)
			end
		end

		if RacerConfig.isFinalLike(mode) then
			local collisionItem = RacerConfig.trafficCollisionCar(
				trafficItems,
				segmentIndex,
				prediction.playerX.Value,
				prediction.speed.Value,
				segmentCount,
				trafficBySegment
			)
			if collisionItem then
				local car = collisionItem.car
				prediction.speed.Value = car.speed
					* (car.speed / math.max(prediction.speed.Value, 1))
				prediction.position.Value =
					RacerConfig.trafficCollisionPosition(collisionItem.z, playerZ, trackLength)
			end
		end

		local playerXLimit = if RacerConfig.isFinalLike(mode) then 3 else 2
		prediction.playerX.Value =
			RacerMath.limit(prediction.playerX.Value, -playerXLimit, playerXLimit)
		prediction.speed.Value = RacerMath.limit(prediction.speed.Value, 0, RacerConfig.MaxSpeed)

		if RacerConfig.isFinalLike(mode) then
			local positionDelta = (prediction.position.Value - startPosition)
				/ RacerConfig.SegmentLength
			prediction.skyOffset.Value = RacerMath.increase(
				prediction.skyOffset.Value,
				BACKGROUND_SPEEDS.Sky * curve * positionDelta,
				1
			)
			prediction.hillOffset.Value = RacerMath.increase(
				prediction.hillOffset.Value,
				BACKGROUND_SPEEDS.Hill * curve * positionDelta,
				1
			)
			prediction.treeOffset.Value = RacerMath.increase(
				prediction.treeOffset.Value,
				BACKGROUND_SPEEDS.Tree * curve * positionDelta,
				1
			)
		end

		if RacerConfig.isFinalLike(mode) then
			local completedLap = prediction.lapStarted
				and startPosition > trackLength - RacerConfig.SegmentLength * 2
				and prediction.position.Value < playerZ
			if completedLap then
				prediction.currentLapTime.Value += step
				prediction.lastLapTime.Value = prediction.currentLapTime.Value
				prediction.currentLapTime.Value = 0
				if prediction.lastLapTime.Value <= prediction.fastLapTime.Value then
					prediction.fastLapTime.Value = prediction.lastLapTime.Value
				end
			elseif prediction.lapStarted then
				prediction.currentLapTime.Value += step
			elseif prediction.position.Value > playerZ then
				prediction.lapStarted = true
				prediction.currentLapTime.Value += step
			end
		end

		prediction.accumulator -= step
		steps += 1
	end

	return prediction
end

local function colorWithFog(color: Color3, fog: number): Color3
	return color:Lerp(RacerConfig.Colors.Fog, 1 - fog)
end

local function objectZIndex(layer: number): number
	return OBJECT_Z_BASE + layer * OBJECT_Z_STRIDE + 2
end

local function formatTime(seconds: number): string
	local minutes = math.floor(seconds / 60)
	local wholeSeconds = math.floor(seconds - minutes * 60)
	local tenths = math.floor(10 * (seconds - math.floor(seconds)))
	if minutes > 0 then
		return `{minutes}.{if wholeSeconds < 10 then "0" else ""}{wholeSeconds}.{tenths}`
	end
	return `{wholeSeconds}.{tenths}`
end

local function finalHudText(state, speed: number): string
	local mph = 5 * math.round(speed / 500)
	local lastLap = if state.lastLapTime.Value > 0
		then ` Last Lap: {formatTime(state.lastLapTime.Value)}`
		else ""
	return `{mph} mph Time: {formatTime(state.currentLapTime.Value)}{lastLap} Fastest Lap: {formatTime(
		state.fastLapTime.Value
	)}`
end

local function rounded(instance: GuiObject, radius: number)
	local corner = Instance.new("UICorner")
	corner.CornerRadius = UDim.new(0, radius)
	corner.Parent = instance
end

local function createLabel(
	parent: Instance,
	name: string,
	position: UDim2,
	size: UDim2,
	textSize: number
)
	local label = Instance.new("TextLabel")
	label.Name = name
	label.BackgroundColor3 = Color3.fromRGB(12, 16, 24)
	label.BackgroundTransparency = 0.1
	label.BorderSizePixel = 0
	label.Font = Enum.Font.GothamBold
	label.Position = position
	label.Size = size
	label.Text = ""
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.TextSize = textSize
	label.TextWrapped = true
	label.Parent = parent

	local padding = Instance.new("UIPadding")
	padding.PaddingBottom = UDim.new(0, 8)
	padding.PaddingLeft = UDim.new(0, 12)
	padding.PaddingRight = UDim.new(0, 12)
	padding.PaddingTop = UDim.new(0, 8)
	padding.Parent = label
	return label
end

local function createFrame(parent: Instance, name: string, color: Color3, zIndex: number)
	local frame = Instance.new("Frame")
	frame.Name = name
	frame.BackgroundColor3 = color
	frame.BorderSizePixel = 0
	frame.ZIndex = zIndex
	frame.Parent = parent
	return frame
end

local function textureAtlasImage(): string?
	if RacerTextures.Image == nil or RacerTextures.Image == "" then
		return nil
	end
	return RacerTextures.Image
end

local function textureArtEnabled(): boolean
	return useTextureArt and textureAtlasImage() ~= nil
end

local function createTextureImage(parent: Instance, zIndex: number)
	local image = Instance.new("ImageLabel")
	image.Name = "Texture"
	image.AnchorPoint = Vector2.new(0, 0)
	image.BackgroundTransparency = 1
	image.BorderSizePixel = 0
	image.Position = UDim2.fromScale(0, 0)
	image.ScaleType = Enum.ScaleType.Stretch
	image.Size = UDim2.fromScale(1, 1)
	image.Visible = false
	image.ZIndex = zIndex
	image.Parent = parent
	return image
end

local function applyTextureImage(texture: Instance?, spriteName: string?): boolean
	local image = textureAtlasImage()
	if not image or not spriteName or not texture or not texture:IsA("ImageLabel") then
		return false
	end
	local rect = RacerTextures.Sprites[spriteName]
	if not rect then
		return false
	end
	texture.Image = image
	texture.ImageRectOffset = Vector2.new(rect.x, rect.y)
	texture.ImageRectSize = Vector2.new(rect.w, rect.h)
	texture.Visible = true
	return true
end

local function createLayer(parent: Instance, name: string, zIndex: number)
	local layer = createFrame(parent, name, Color3.fromRGB(0, 0, 0), zIndex)
	layer.BackgroundTransparency = 1
	layer.ClipsDescendants = false
	layer.Size = UDim2.new(3, 0, 1, 0)
	return layer
end

local function placeRepeatedFrame(
	layer: Instance,
	name: string,
	color: Color3,
	zIndex: number,
	x: number,
	y: number,
	width: number,
	height: number,
	radius: number?
)
	for repeatIndex = 0, 2 do
		local item = createFrame(layer, `{name}_{repeatIndex}`, color, zIndex)
		item.Position = UDim2.new((repeatIndex + x) / 3, 0, y, 0)
		item.Size = UDim2.new(width / 3, 0, height, 0)
		if radius then
			rounded(item, radius)
		end
	end
end

local function createRenderer(
	parent: Instance,
	name: string,
	carBottom: number?,
	includeFinalObjects: boolean?
)
	local root = Instance.new("Frame")
	root.Name = name
	root.BackgroundColor3 = RacerConfig.Colors.Sky
	root.BorderSizePixel = 0
	root.ClipsDescendants = true
	root.Size = UDim2.fromScale(1, 1)
	root.Parent = parent

	local sky = createFrame(root, "Sky", RacerConfig.Colors.Sky, 1)
	sky.Size = UDim2.new(1, 0, 0.48, 0)

	local cloudLayer = createLayer(root, "CloudLayer", 2)
	for index, cloud in
		{
			{ x = 0.14, y = 0.09, w = 0.11, h = 0.04 },
			{ x = 0.54, y = 0.13, w = 0.16, h = 0.045 },
			{ x = 0.82, y = 0.08, w = 0.13, h = 0.042 },
			{ x = 0.34, y = 0.17, w = 0.07, h = 0.025 },
		}
	do
		placeRepeatedFrame(
			cloudLayer,
			`Cloud_{index}`,
			Color3.fromRGB(238, 248, 250),
			2,
			cloud.x,
			cloud.y,
			cloud.w,
			cloud.h,
			20
		)
	end

	local hillLayer = createLayer(root, "HillLayer", 3)
	placeRepeatedFrame(
		hillLayer,
		"FarHill",
		Color3.fromRGB(162, 226, 68),
		3,
		0.2,
		0.28,
		0.7,
		0.18,
		180
	)
	placeRepeatedFrame(
		hillLayer,
		"NearHill",
		Color3.fromRGB(106, 204, 56),
		4,
		-0.12,
		0.36,
		1.2,
		0.18,
		120
	)

	local horizonFill = createFrame(root, "HorizonFill", Color3.fromRGB(92, 199, 54), 7)
	horizonFill.Position = UDim2.new(0, 0, 0.39, 0)
	horizonFill.Size = UDim2.new(1, 0, 0.22, 0)

	local groundFill = createFrame(root, "GroundFill", RacerConfig.Colors.Light.Grass, 8)
	groundFill.Position = UDim2.new(0, 0, 0.54, 0)
	groundFill.Size = UDim2.new(1, 0, 0.46, 0)

	local treeLayer = createLayer(root, "TreeLayer", 9)
	placeRepeatedFrame(treeLayer, "Trees", RacerConfig.Colors.Trees, 9, -0.2, 0.46, 1.4, 0.09)

	for index, cap in
		{
			{ x = 0.04, w = 0.12, h = 0.035 },
			{ x = 0.18, w = 0.18, h = 0.045 },
			{ x = 0.41, w = 0.15, h = 0.032 },
			{ x = 0.63, w = 0.2, h = 0.04 },
			{ x = 0.88, w = 0.16, h = 0.05 },
		}
	do
		placeRepeatedFrame(
			treeLayer,
			`TreeCap_{index}`,
			RacerConfig.Colors.Trees,
			10,
			cap.x,
			0.435,
			cap.w,
			cap.h,
			20
		)
	end

	local rows = {}
	for index = 1, ROW_COUNT do
		local rowRoot =
			createFrame(root, `RoadRow_{index}`, RacerConfig.Colors.Light.Grass, ROAD_Z_INDEX)
		rowRoot.Visible = false

		local road =
			createFrame(rowRoot, "Road", RacerConfig.Colors.Light.Road, ROAD_DETAIL_Z_INDEX)
		local junctionLeft =
			createFrame(rowRoot, "JunctionLeft", RacerConfig.Colors.Light.Road, ROAD_DETAIL_Z_INDEX)
		junctionLeft.Visible = false
		local junctionRight = createFrame(
			rowRoot,
			"JunctionRight",
			RacerConfig.Colors.Light.Road,
			ROAD_DETAIL_Z_INDEX
		)
		junctionRight.Visible = false
		local leftRumble =
			createFrame(rowRoot, "LeftRumble", RacerConfig.Colors.Light.Rumble, ROAD_DETAIL_Z_INDEX)
		local rightRumble = createFrame(
			rowRoot,
			"RightRumble",
			RacerConfig.Colors.Light.Rumble,
			ROAD_DETAIL_Z_INDEX
		)
		local laneMarkers = {}
		for laneIndex = 1, 5 do
			table.insert(
				laneMarkers,
				createFrame(
					rowRoot,
					`LaneMarker_{laneIndex}`,
					RacerConfig.Colors.Light.Lane,
					ROAD_LANE_Z_INDEX
				)
			)
		end

		table.insert(rows, {
			root = rowRoot,
			road = road,
			junctionLeft = junctionLeft,
			junctionRight = junctionRight,
			leftRumble = leftRumble,
			rightRumble = rightRumble,
			laneMarkers = laneMarkers,
		})
	end

	local finalObjects = {}
	if includeFinalObjects ~= false then
		for index = 1, FINAL_OBJECT_COUNT do
			local object =
				createFrame(root, `FinalObject_{index}`, Color3.fromRGB(255, 230, 96), 760)
			object.AnchorPoint = Vector2.new(0, 0)
			object.BackgroundTransparency = 1
			object.ClipsDescendants = true
			object.Visible = false

			local content = createFrame(object, "Content", Color3.fromRGB(255, 230, 96), 761)
			content.AnchorPoint = Vector2.new(0, 0)
			content.Position = UDim2.fromScale(0, 0)
			content.Size = UDim2.fromScale(1, 1)
			rounded(content, 2)
			createTextureImage(content, 765)

			local liveText = Instance.new("TextLabel")
			liveText.Name = "LiveBillboardText"
			liveText.BackgroundTransparency = 1
			liveText.Font = Enum.Font.GothamBold
			liveText.Position = UDim2.new(0.1, 0, 0.2, 0)
			liveText.Size = UDim2.new(0.8, 0, 0.42, 0)
			liveText.Text = ""
			liveText.TextColor3 = Color3.fromRGB(14, 18, 24)
			liveText.TextScaled = true
			liveText.TextWrapped = true
			liveText.Visible = false
			liveText.ZIndex = 766
			liveText.Parent = content

			local shadow = createFrame(content, "Shadow", Color3.fromRGB(13, 17, 20), 759)
			shadow.AnchorPoint = Vector2.new(0.5, 1)
			shadow.BackgroundTransparency = 0.35
			shadow.Position = UDim2.new(0.5, 0, 1.16, 0)
			shadow.Size = UDim2.new(1.15, 0, 0.3, 0)
			rounded(shadow, 5)

			local roof = createFrame(content, "Roof", Color3.fromRGB(255, 255, 255), 762)
			roof.Position = UDim2.new(0.22, 0, -0.34, 0)
			roof.Size = UDim2.new(0.56, 0, 0.42, 0)
			rounded(roof, 3)

			local windshield = createFrame(content, "Windshield", Color3.fromRGB(38, 53, 68), 763)
			windshield.Position = UDim2.new(0.28, 0, -0.22, 0)
			windshield.Size = UDim2.new(0.44, 0, 0.22, 0)
			rounded(windshield, 2)

			local leftLight = createFrame(content, "LeftLight", Color3.fromRGB(245, 245, 225), 764)
			leftLight.Position = UDim2.new(0.08, 0, 0.68, 0)
			leftLight.Size = UDim2.new(0.18, 0, 0.16, 0)
			rounded(leftLight, 2)

			local rightLight =
				createFrame(content, "RightLight", Color3.fromRGB(245, 245, 225), 764)
			rightLight.Position = UDim2.new(0.74, 0, 0.68, 0)
			rightLight.Size = UDim2.new(0.18, 0, 0.16, 0)
			rounded(rightLight, 2)

			table.insert(finalObjects, object)
		end
	end

	local car = Instance.new("Frame")
	car.Name = "PlayerCar"
	car.AnchorPoint = Vector2.new(0.5, 1)
	car.BackgroundColor3 = Color3.fromRGB(255, 221, 78)
	car.BorderSizePixel = 0
	car.Position = UDim2.new(0.5, 0, carBottom or 0.93, 0)
	car.Size = UDim2.new(0.14, 0, 0.055, 0)
	car.ZIndex = PLAYER_CAR_Z_INDEX
	car.Parent = root
	rounded(car, 4)

	local windshield =
		createFrame(car, "Windshield", Color3.fromRGB(40, 58, 72), PLAYER_CAR_Z_INDEX + 1)
	windshield.Position = UDim2.new(0.26, 0, 0.13, 0)
	windshield.Size = UDim2.new(0.48, 0, 0.23, 0)
	rounded(windshield, 2)

	local hood = createFrame(car, "Hood", Color3.fromRGB(255, 236, 92), PLAYER_CAR_Z_INDEX + 2)
	hood.Position = UDim2.new(0.07, 0, 0.62, 0)
	hood.Size = UDim2.new(0.86, 0, 0.18, 0)
	rounded(hood, 2)
	createTextureImage(car, PLAYER_CAR_Z_INDEX + 3)

	local driverAvatar = Instance.new("ImageLabel")
	driverAvatar.Name = "DriverAvatar"
	driverAvatar.BackgroundTransparency = 1
	driverAvatar.Position = UDim2.new(0.34, 0, 0.18, 0)
	driverAvatar.Size = UDim2.new(0.14, 0, 0.24, 0)
	driverAvatar.ZIndex = PLAYER_CAR_Z_INDEX + 4
	driverAvatar.Visible = false
	driverAvatar.Parent = car
	rounded(driverAvatar, 3)

	local passengerAvatar = Instance.new("ImageLabel")
	passengerAvatar.Name = "PassengerAvatar"
	passengerAvatar.BackgroundTransparency = 1
	passengerAvatar.Position = UDim2.new(0.52, 0, 0.18, 0)
	passengerAvatar.Size = UDim2.new(0.14, 0, 0.24, 0)
	passengerAvatar.ZIndex = PLAYER_CAR_Z_INDEX + 4
	passengerAvatar.Visible = false
	passengerAvatar.Parent = car
	rounded(passengerAvatar, 3)

	local status =
		createLabel(root, "Status", UDim2.new(0.5, -320, 0, 12), UDim2.fromOffset(640, 42), 15)
	status.ZIndex = OVERLAY_Z_INDEX + 10
	status.Visible = false

	return {
		root = root,
		background = {
			cloudLayer = cloudLayer,
			hillLayer = hillLayer,
			treeLayer = treeLayer,
		},
		rows = rows,
		finalObjects = finalObjects,
		finalObjectVisibleCount = 0,
		lastSignature = nil,
		car = car,
		carBottom = carBottom or 0.93,
		status = status,
		statusEnabled = true,
	}
end

local function hideObjectDetails(object)
	local content = object:FindFirstChild("Content")
	local detailRoot = if content and content:IsA("GuiObject") then content else object
	for _, child in detailRoot:GetChildren() do
		if child:IsA("GuiObject") then
			child.Visible = false
		end
	end
end

local function showTrafficDetails(object)
	local content = object:FindFirstChild("Content")
	local detailRoot = if content and content:IsA("GuiObject") then content else object
	detailRoot.ZIndex = object.ZIndex
	for _, child in detailRoot:GetChildren() do
		if child:IsA("GuiObject") then
			child.Visible = true
			child.ZIndex = object.ZIndex
		end
	end
end

local function setPlayerCarZIndex(car: GuiObject, zIndex: number)
	car.ZIndex = zIndex
	for _, child in car:GetChildren() do
		if child:IsA("GuiObject") then
			child.ZIndex = zIndex
		end
	end
end

local function setSpriteObject(object, spriteData, mode: string)
	hideObjectDetails(object)
	local content = object:FindFirstChild("Content")
	local detailRoot = if content and content:IsA("GuiObject") then content else object
	detailRoot.ZIndex = object.ZIndex
	detailRoot.BackgroundColor3 = spriteData.definition.color
	detailRoot.BackgroundTransparency = 0
	detailRoot.Rotation = 0
	object.Rotation = 0
	local texture = detailRoot:FindFirstChild("Texture")
	if texture and texture:IsA("GuiObject") then
		texture.ZIndex = object.ZIndex
	end
	if textureArtEnabled() and applyTextureImage(texture, spriteData.sprite) then
		detailRoot.BackgroundTransparency = 1
	else
		if texture and texture:IsA("GuiObject") then
			texture.Visible = false
		end
	end
	local liveText = detailRoot:FindFirstChild("LiveBillboardText")
	if liveText and liveText:IsA("TextLabel") then
		local liveCopy = v5BillboardText.Value
		local showLive = mode == "v5"
			and spriteData.definition.kind == "billboard"
			and liveCopy ~= ""
		liveText.Text = liveCopy
		liveText.Visible = showLive
		liveText.ZIndex = object.ZIndex + 1
	end
end

local function setTrafficObject(object, car)
	showTrafficDetails(object)
	local content = object:FindFirstChild("Content")
	local detailRoot = if content and content:IsA("GuiObject") then content else object
	detailRoot.ZIndex = object.ZIndex
	detailRoot.BackgroundColor3 = car.color
	detailRoot.BackgroundTransparency = 0
	detailRoot.Rotation = 0
	object.Rotation = 0

	local texture = detailRoot:FindFirstChild("Texture")
	local hasTexture = textureArtEnabled() and applyTextureImage(texture, car.sprite)
	for _, child in detailRoot:GetChildren() do
		if child:IsA("GuiObject") and child.Name ~= "Texture" then
			child.Visible = not hasTexture
		end
	end
	if hasTexture then
		detailRoot.BackgroundTransparency = 1
	elseif texture and texture:IsA("GuiObject") then
		texture.Visible = false
	end

	local roof = detailRoot:FindFirstChild("Roof")
	if roof and roof:IsA("GuiObject") then
		roof.BackgroundColor3 = car.color:Lerp(Color3.fromRGB(255, 255, 255), 0.18)
	end
end

local function spriteSizeScale(
	spriteWidth: number,
	spriteHeight: number,
	scale: number,
	roadWidth: number
)
	local spriteRoadScale = RacerConfig.SpriteScale * roadWidth
	return (spriteWidth * scale * WIDTH / 2 * spriteRoadScale) / WIDTH,
		(spriteHeight * scale * WIDTH / 2 * spriteRoadScale) / HEIGHT
end

local function placeClippedObject(
	object,
	x: number,
	bottomY: number,
	widthScale: number,
	heightScale: number,
	clipY: number
): boolean
	local widthPx = widthScale * WIDTH
	local heightPx = heightScale * HEIGHT
	local leftX = x - widthPx / 2
	local rightX = x + widthPx / 2
	local topY = bottomY - heightPx
	local visibleLeftX = math.max(leftX, SCREEN_MIN_X)
	local visibleRightX = math.min(rightX, SCREEN_MAX_X)
	local visibleTopY = math.max(topY, SCREEN_MIN_Y)
	local visibleBottomY = math.min(bottomY, clipY, SCREEN_MAX_Y)
	local visibleWidth = visibleRightX - visibleLeftX
	local visibleHeight = visibleBottomY - topY
	if visibleWidth <= 0 or visibleHeight <= 0 then
		object.Visible = false
		return false
	end
	visibleHeight = visibleBottomY - visibleTopY
	if visibleHeight <= 0 then
		object.Visible = false
		return false
	end

	local content = object:FindFirstChild("Content")
	local detailRoot = if content and content:IsA("GuiObject") then content else object
	object.Position = UDim2.fromScale(visibleLeftX / WIDTH, visibleTopY / HEIGHT)
	object.Size = UDim2.fromScale(visibleWidth / WIDTH, visibleHeight / HEIGHT)
	if detailRoot ~= object then
		detailRoot.Position = UDim2.fromScale(
			(leftX - visibleLeftX) / visibleWidth,
			(topY - visibleTopY) / visibleHeight
		)
		detailRoot.Size = UDim2.fromScale(widthPx / visibleWidth, heightPx / visibleHeight)
	end
	object.Visible = true
	return true
end

local function setRow(
	row,
	topY: number,
	bottomY: number,
	centerXPx: number,
	roadHalfWidthPx: number,
	color,
	fog: number,
	lanes: number,
	junctionKind: string?
)
	local top = math.clamp(topY / HEIGHT, 0, 1)
	local bottom = math.clamp(bottomY / HEIGHT, 0, 1)
	local heightScale = math.max(1 / HEIGHT, bottom - top)
	local centerX = centerXPx / WIDTH
	local halfRoadWidth = roadHalfWidthPx / WIDTH
	local roadWidth = math.max(0, (roadHalfWidthPx * 2) / WIDTH)
	local rumbleWidth = halfRoadWidth / math.max(6, 2 * lanes)
	local laneWidth = halfRoadWidth / math.max(32, 8 * lanes)

	row.root.Visible = true
	row.root.Position = UDim2.new(0, 0, top, 0)
	row.root.Size = UDim2.new(1, 0, heightScale, 0)
	row.root.BackgroundColor3 = colorWithFog(color.Grass, fog)

	row.road.Position = UDim2.new(centerX - roadWidth / 2, 0, 0, 0)
	row.road.Size = UDim2.new(roadWidth, 0, 1, 0)
	row.road.BackgroundColor3 = colorWithFog(color.Road, fog)

	local branchHeight = math.min(1, roadWidth * 0.35)
	local branchY = 0.5 - branchHeight / 2
	local showLeft = junctionKind == "left" or junctionKind == "cross"
	local showRight = junctionKind == "right" or junctionKind == "cross"
	row.junctionLeft.Visible = showLeft
	row.junctionLeft.Position = UDim2.new(0, 0, branchY, 0)
	row.junctionLeft.Size = UDim2.new(math.max(0, centerX - roadWidth / 2), 0, branchHeight, 0)
	row.junctionLeft.BackgroundColor3 = colorWithFog(color.Road, fog)
	row.junctionRight.Visible = showRight
	row.junctionRight.Position = UDim2.new(centerX + roadWidth / 2, 0, branchY, 0)
	row.junctionRight.Size = UDim2.new(math.max(0, 1 - (centerX + roadWidth / 2)), 0, branchHeight, 0)
	row.junctionRight.BackgroundColor3 = colorWithFog(color.Road, fog)

	row.leftRumble.Position = UDim2.new(centerX - roadWidth / 2 - rumbleWidth, 0, 0, 0)
	row.leftRumble.Size = UDim2.new(rumbleWidth, 0, 1, 0)
	row.leftRumble.BackgroundColor3 = colorWithFog(color.Rumble, fog)

	row.rightRumble.Position = UDim2.new(centerX + roadWidth / 2, 0, 0, 0)
	row.rightRumble.Size = UDim2.new(rumbleWidth, 0, 1, 0)
	row.rightRumble.BackgroundColor3 = colorWithFog(color.Rumble, fog)

	for _, marker in row.laneMarkers do
		marker.Visible = false
	end
	if color.Lane then
		local markerCount = math.clamp(lanes - 1, 0, #row.laneMarkers)
		for index = 1, markerCount do
			local marker = row.laneMarkers[index]
			local fraction = index / lanes
			local laneX = centerX - roadWidth / 2 + roadWidth * fraction
			marker.Visible = true
			marker.Position = UDim2.new(laneX - laneWidth / 2, 0, 0, 0)
			marker.Size = UDim2.new(laneWidth, 0, 1, 0)
			marker.BackgroundColor3 = colorWithFog(color.Lane, fog)
		end
	end
end

local function render(renderer, state)
	local position = state.position.Value
	local playerX = state.playerX.Value
	local speed = state.speed.Value
	local trafficTime = state.trafficTime.Value
	local steer = state.steer.Value
	local mode = state.mode.Value
	local skyOffset = state.skyOffset.Value
	local hillOffset = state.hillOffset.Value
	local treeOffset = state.treeOffset.Value
	local roadWidthSetting = state.settingRoadWidth.Value
	local cameraHeight = state.settingCameraHeight.Value
	local drawDistance = math.floor(state.settingDrawDistance.Value)
	local fieldOfView = state.settingFieldOfView.Value
	local fogDensity = state.settingFogDensity.Value
	local lanes = math.floor(state.settingLanes.Value)
	local cameraDepth = 1 / math.tan(math.rad(fieldOfView / 2))
	local playerZ = cameraHeight * cameraDepth
	local baseSegmentIndex = math.floor(position / RacerConfig.SegmentLength)
	local basePercent = RacerMath.percentRemaining(position, RacerConfig.SegmentLength)
	local segmentCount = RacerConfig.segmentCount(mode)
	local trackLength = RacerConfig.trackLength(mode)
	local playerSegmentIndex = math.floor((position + playerZ) / RacerConfig.SegmentLength)
		% segmentCount
	local playerSegment = RacerConfig.segmentFor(mode, playerSegmentIndex)
	local playerPercent = RacerMath.percentRemaining(position + playerZ, RacerConfig.SegmentLength)
	local playerY = RacerMath.interpolate(playerSegment.y1, playerSegment.y2, playerPercent)
	local maxY = HEIGHT
	local rowCursor = 0
	local objectSegments = {}
	local projectedByIndex = {}
	local curveX = 0
	local curveDx = -RacerConfig.curveFor(mode, baseSegmentIndex) * basePercent
	local background = renderer.background
	local skyY = playerY * BACKGROUND_SPEEDS.Sky / 480
	local hillY = playerY * BACKGROUND_SPEEDS.Hill / 480
	local treeY = playerY * BACKGROUND_SPEEDS.Tree / 480

	background.cloudLayer.Position = UDim2.new(-(skyOffset % 1), 0, skyY, 0)
	background.hillLayer.Position = UDim2.new(-(hillOffset % 1), 0, hillY, 0)
	background.treeLayer.Position = UDim2.new(-(treeOffset % 1), 0, treeY, 0)

	for _, row in renderer.rows do
		row.root.Visible = false
	end

	local rowPoolExhausted = false
	for n = 0, drawDistance - 1 do
		local segmentIndex = (baseSegmentIndex + n) % segmentCount
		local looped = segmentIndex < baseSegmentIndex % segmentCount
		local cameraZ = position - if looped then trackLength else 0
		local worldZ1 = segmentIndex * RacerConfig.SegmentLength
		local worldZ2 = (segmentIndex + 1) * RacerConfig.SegmentLength
		local segment = RacerConfig.segmentFor(mode, segmentIndex)
		local currentCurveX = curveX
		local nextCurveX = curveX + curveDx
		local p1 = RacerMath.project(
			0,
			segment.y1,
			worldZ1,
			playerX * roadWidthSetting - currentCurveX,
			playerY + cameraHeight,
			cameraZ,
			cameraDepth,
			WIDTH,
			HEIGHT,
			roadWidthSetting
		)
		local p2 = RacerMath.project(
			0,
			segment.y2,
			worldZ2,
			playerX * roadWidthSetting - nextCurveX,
			playerY + cameraHeight,
			cameraZ,
			cameraDepth,
			WIDTH,
			HEIGHT,
			roadWidthSetting
		)

		curveX += curveDx
		curveDx += RacerConfig.curveFor(mode, segmentIndex)

		if p1 and p2 then
			local projected = {
				index = segmentIndex,
				p1 = p1,
				p2 = p2,
				clip = maxY,
			}
			if n > 0 then
				table.insert(objectSegments, projected)
			end
			projectedByIndex[segmentIndex] = projected

			local frontFacing = not RacerConfig.Modes[mode].hills or p2.y < p1.y
			if p1.cameraZ > cameraDepth and frontFacing and p2.y < maxY then
				local fog = RacerMath.exponentialFog(n / drawDistance, fogDensity)
				local color = RacerConfig.segmentColor(mode, segmentIndex, playerZ)
				local segmentTop = math.max(math.floor(p2.y), SCREEN_MIN_Y)
				local segmentBottom = math.min(math.ceil(p1.y), math.floor(maxY), SCREEN_MAX_Y)
				local segmentHeight = p1.y - p2.y
				local scanY = segmentTop
				local junctionKind = RacerConfig.junctionForSegment(mode, projected.index)
				while scanY < segmentBottom do
					rowCursor += 1
					if rowCursor > #renderer.rows then
						rowPoolExhausted = true
						break
					end
					local nextY = math.min(scanY + ROAD_SCANLINE_HEIGHT, segmentBottom)
					local sampleY = (scanY + nextY) * 0.5
					local percent = RacerMath.limit((sampleY - p2.y) / segmentHeight, 0, 1)
					setRow(
						renderer.rows[rowCursor],
						scanY,
						nextY,
						RacerMath.interpolate(p2.x, p1.x, percent),
						RacerMath.interpolate(p2.w, p1.w, percent),
						color,
						fog,
						lanes,
						junctionKind
					)
					scanY = nextY
				end
				maxY = if RacerConfig.isFinalLike(mode) then p1.y else p2.y
			end
		end
		if rowPoolExhausted then
			break
		end
	end

	local objectCursor = 0
	local drawLayer = 0
	local playerDrawZIndex = PLAYER_CAR_Z_INDEX
	if RacerConfig.isFinalLike(mode) then
		local orderedTrafficBySegment = state.trafficBySegment
		local trafficItems = nil
		if orderedTrafficBySegment == nil then
			if state.trafficState and state.trafficState.bySegment then
				trafficItems = state.trafficState.items
				orderedTrafficBySegment = state.trafficState.bySegment
			elseif state.trafficOffsets then
				local trafficState = RacerConfig.createTrafficState(
					trafficTime,
					trackLength,
					segmentCount,
					state.trafficOffsets,
					mode
				)
				trafficItems = trafficState.items
				orderedTrafficBySegment = trafficState.bySegment
			else
				local trafficState = RacerConfig.createTrafficState(
					trafficTime,
					trackLength,
					segmentCount,
					replicatedTrafficOffsets(state),
					mode
				)
				trafficItems = trafficState.items
				orderedTrafficBySegment = trafficState.bySegment
			end
		end
		local trafficBySegment = {}
		if orderedTrafficBySegment then
			for segmentIndex, orderedItems in orderedTrafficBySegment do
				for _, item in orderedItems do
					local projected = projectedByIndex[segmentIndex]
					if projected then
						local distance = RacerMath.increase(item.z - position, 0, trackLength)
						local list = trafficBySegment[segmentIndex]
						if not list then
							list = {}
							trafficBySegment[segmentIndex] = list
						end
						table.insert(list, {
							item = item,
							distance = distance,
							projected = projected,
						})
					end
				end
			end
		end
		if orderedTrafficBySegment == nil then
			for _, item in trafficItems or {} do
				local distance = RacerMath.increase(item.z - position, 0, trackLength)
				local projected = projectedByIndex[item.segmentIndex]
				if projected then
					local list = trafficBySegment[item.segmentIndex]
					if not list then
						list = {}
						trafficBySegment[item.segmentIndex] = list
					end
					table.insert(list, {
						item = item,
						distance = distance,
						projected = projected,
					})
				end
			end
		end

		for index = #objectSegments, 1, -1 do
			local projected = objectSegments[index]
			local trafficList = trafficBySegment[projected.index]
			if trafficList then
				for _, traffic in trafficList do
					if objectCursor >= #renderer.finalObjects then
						break
					end
					local nextCursor = objectCursor + 1
					local object = renderer.finalObjects[nextCursor]
					local item = traffic.item
					local carData = item.car
					local scale =
						RacerMath.interpolate(projected.p1.scale, projected.p2.scale, item.percent)
					local x = RacerMath.interpolate(projected.p1.x, projected.p2.x, item.percent)
						+ scale * item.offset * roadWidthSetting * WIDTH / 2
					local y = RacerMath.interpolate(projected.p1.y, projected.p2.y, item.percent)
					local width, height =
						spriteSizeScale(carData.width, carData.height, scale, roadWidthSetting)
					object.ZIndex = objectZIndex(drawLayer)
					setTrafficObject(object, carData)
					if placeClippedObject(object, x, y, width, height, projected.clip) then
						drawLayer += 1
						objectCursor = nextCursor
					end
				end
			end

			local spriteList = RacerConfig.spritesForSegment(mode, projected.index)
			for _, spriteData in spriteList do
				if objectCursor >= #renderer.finalObjects then
					break
				end
				local nextCursor = objectCursor + 1
				local object = renderer.finalObjects[nextCursor]
				local spriteDef = spriteData.definition
				local scale = projected.p1.scale
				local spriteX = projected.p1.x
					+ scale
						* RacerConfig.roadsideSpriteCenter(spriteData)
						* roadWidthSetting
						* WIDTH
						/ 2
				local spriteY = projected.p1.y
				local width, height =
					spriteSizeScale(spriteDef.width, spriteDef.height, scale, roadWidthSetting)
				object.ZIndex = objectZIndex(drawLayer)
				setSpriteObject(object, spriteData, mode)
				if placeClippedObject(object, spriteX, spriteY, width, height, projected.clip) then
					drawLayer += 1
					objectCursor = nextCursor
				end
			end

			if projected.index == playerSegmentIndex then
				playerDrawZIndex = objectZIndex(drawLayer)
				drawLayer += 1
			end
		end
	end
	objectCursor = math.min(objectCursor, #renderer.finalObjects)
	for index = objectCursor + 1, renderer.finalObjectVisibleCount do
		renderer.finalObjects[index].Visible = false
	end
	renderer.finalObjectVisibleCount = objectCursor
	renderer.lastRowCount = rowCursor
	renderer.lastObjectCount = objectCursor
	renderer.lastMode = mode

	local playerSprite = RacerConfig.playerSpriteDef(steer, playerSegment.y2 - playerSegment.y1)
	local playerWidth, playerHeight = spriteSizeScale(
		playerSprite.width,
		playerSprite.height,
		cameraDepth / playerZ,
		roadWidthSetting
	)
	local playerProjected = projectedByIndex[playerSegmentIndex]
	local playerBottomY = HEIGHT
	if RacerConfig.Modes[mode].hills and playerProjected then
		local cameraY = RacerMath.interpolate(
			playerProjected.p1.cameraY,
			playerProjected.p2.cameraY,
			playerPercent
		)
		playerBottomY = HEIGHT / 2 - (cameraDepth / playerZ * cameraY * HEIGHT / 2)
	end
	setPlayerCarZIndex(renderer.car, playerDrawZIndex)
	local playerBounce =
		RacerConfig.playerBounce(position, speed / RacerConfig.MaxSpeed, HEIGHT / 480)
	renderer.car.BackgroundColor3 = playerSprite.color
	renderer.car.BackgroundTransparency = 0
	renderer.car.Size = UDim2.fromScale(playerWidth, playerHeight)
	renderer.car.Rotation = 0
	renderer.car.Position = UDim2.new(0.5, 0, (playerBottomY + playerBounce) / HEIGHT, 0)
	local playerTexture = renderer.car:FindFirstChild("Texture")
	local playerHasTexture = textureArtEnabled()
		and applyTextureImage(playerTexture, playerSprite.name)
	for _, child in renderer.car:GetChildren() do
		if child:IsA("GuiObject") and child.Name ~= "Texture" then
			child.Visible = not playerHasTexture
		end
	end
	if playerHasTexture then
		renderer.car.BackgroundTransparency = 1
	elseif playerTexture and playerTexture:IsA("GuiObject") then
		playerTexture.Visible = false
	end
	local windshield = renderer.car:FindFirstChild("Windshield")
	if windshield and windshield:IsA("GuiObject") then
		windshield.Position = UDim2.new(0.26 + steer * 0.08, 0, 0.13, 0)
	end
	local showAvatarPeople = mode == "v5" and playerHasTexture
	local driverAvatar = renderer.car:FindFirstChild("DriverAvatar")
	if driverAvatar and driverAvatar:IsA("ImageLabel") then
		local image = thumbnailForUserId(state.activeUserId.Value)
		driverAvatar.Image = image or ""
		driverAvatar.Visible = showAvatarPeople and image ~= nil
		driverAvatar.Position = UDim2.new(0.34 + steer * 0.035, 0, 0.16, 0)
	end
	local passengerAvatar = renderer.car:FindFirstChild("PassengerAvatar")
	if passengerAvatar and passengerAvatar:IsA("ImageLabel") then
		local passengerImage = thumbnailForUserId(passengerUserIdFor(state.activeUserId.Value))
		passengerAvatar.Image = passengerImage or ""
		passengerAvatar.Visible = showAvatarPeople and passengerImage ~= nil
		passengerAvatar.Position = UDim2.new(0.52 + steer * 0.035, 0, 0.16, 0)
	end

	if RacerConfig.isFinalLike(mode) and renderer.statusEnabled ~= false then
		renderer.status.Visible = true
		renderer.status.Text = finalHudText(state, speed)
	else
		renderer.status.Text = ""
		renderer.status.Visible = false
	end
end

local function renderSignature(state): string
	return table.concat({
		state.mode.Value,
		tostring(state.activeUserId.Value),
		state.activePlayerName.Value,
		if state.trafficOffsetsBlob then state.trafficOffsetsBlob.Value else "",
		math.floor(state.position.Value * 10 + 0.5),
		math.floor(state.playerX.Value * 1000 + 0.5),
		math.floor(state.speed.Value + 0.5),
		math.floor(state.trafficTime.Value * 20 + 0.5),
		math.floor(state.steer.Value * 10 + 0.5),
		math.floor(state.skyOffset.Value * 1000 + 0.5),
		math.floor(state.hillOffset.Value * 1000 + 0.5),
		math.floor(state.treeOffset.Value * 1000 + 0.5),
		state.settingRoadWidth.Value,
		state.settingCameraHeight.Value,
		state.settingDrawDistance.Value,
		state.settingFieldOfView.Value,
		state.settingFogDensity.Value,
		state.settingLanes.Value,
		if textureArtEnabled() then "textures" else "placeholders",
		v5BillboardText.Value,
		math.floor(state.currentLapTime.Value * 10 + 0.5),
		math.floor(state.lastLapTime.Value * 10 + 0.5),
		math.floor(state.fastLapTime.Value * 10 + 0.5),
	}, "|")
end

local function renderIfChanged(renderer, state)
	local signature = renderSignature(state)
	if renderer.lastSignature == signature then
		return false
	end
	renderer.lastSignature = signature
	render(renderer, state)
	return true
end

local screenGui = Instance.new("ScreenGui")
screenGui.Name = "RacerHud"
screenGui.ResetOnSpawn = false
screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screenGui.Parent = player:WaitForChild("PlayerGui")

local title =
	createLabel(screenGui, "Title", UDim2.fromScale(0.5, 0.025), UDim2.fromOffset(420, 52), 22)
title.AnchorPoint = Vector2.new(0.5, 0)
title.Visible = false

local hint =
	createLabel(screenGui, "Hint", UDim2.new(0.5, -280, 1, -72), UDim2.fromOffset(560, 46), 15)
hint.BackgroundTransparency = 0.22
hint.Text = "Walk to a screen and press E."

local perfLabel =
	createLabel(screenGui, "PerfLog", UDim2.new(0, 14, 1, -170), UDim2.fromOffset(760, 122), 13)
perfLabel.BackgroundTransparency = 0.18
perfLabel.TextXAlignment = Enum.TextXAlignment.Left
perfLabel.TextYAlignment = Enum.TextYAlignment.Top
perfLabel.Visible = false
perfLabel.Text = "Perf log enabled. Press F6 to hide."

local labRejoinButton = Instance.new("TextButton")
labRejoinButton.Name = "LabRejoinButton"
labRejoinButton.AnchorPoint = Vector2.new(1, 0)
labRejoinButton.BackgroundColor3 = Color3.fromRGB(18, 22, 30)
labRejoinButton.BackgroundTransparency = 0.08
labRejoinButton.BorderSizePixel = 0
labRejoinButton.Font = Enum.Font.GothamBold
labRejoinButton.Position = UDim2.new(1, -18, 0, 18)
labRejoinButton.Size = UDim2.fromOffset(104, 42)
labRejoinButton.Text = "Rejoin"
labRejoinButton.TextColor3 = Color3.fromRGB(255, 255, 255)
labRejoinButton.TextSize = 16
labRejoinButton.ZIndex = 120
labRejoinButton.Parent = screenGui
labRejoinButton.MouseButton1Click:Connect(function()
	actionEvent:FireServer("Rejoin")
end)

UserInputService.InputBegan:Connect(function(inputObject, gameProcessed)
	if gameProcessed then
		return
	end
	if inputObject.KeyCode == Enum.KeyCode.F6 then
		perfLabel.Visible = not perfLabel.Visible
	end
end)

local fullScreen = Instance.new("Frame")
fullScreen.Name = "FullScreenRacer"
fullScreen.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
fullScreen.BorderSizePixel = 0
fullScreen.Size = UDim2.fromScale(1, 1)
fullScreen.Visible = false
fullScreen.ZIndex = 200
fullScreen.Parent = screenGui

local fullViewport = Instance.new("Frame")
fullViewport.Name = "RacerViewport"
fullViewport.AnchorPoint = Vector2.new(0.5, 0.5)
fullViewport.BackgroundColor3 = Color3.fromRGB(0, 0, 0)
fullViewport.BorderSizePixel = 0
fullViewport.Position = UDim2.fromScale(0.5, 0.5)
fullViewport.ZIndex = 201
fullViewport.Parent = fullScreen

local activeStatus = nil

local function updateFullViewportSize()
	local absoluteSize = fullScreen.AbsoluteSize
	if absoluteSize.X <= 0 or absoluteSize.Y <= 0 then
		return
	end
	local aspectRatio = RacerConfig.Width / RacerConfig.Height
	local width = absoluteSize.X
	local height = width / aspectRatio
	if height > absoluteSize.Y then
		height = absoluteSize.Y
		width = height * aspectRatio
	end
	local viewportTop = math.floor((absoluteSize.Y - height) / 2 + 0.5)
	fullViewport.Size = UDim2.fromOffset(math.floor(width + 0.5), math.floor(height + 0.5))
	if activeStatus then
		activeStatus.Position = UDim2.fromOffset(
			math.floor(absoluteSize.X / 2 + 0.5),
			viewportTop + ACTIVE_STATUS_MARGIN_TOP
		)
	end
end

fullScreen:GetPropertyChangedSignal("AbsoluteSize"):Connect(updateFullViewportSize)
task.defer(updateFullViewportSize)

local fullRenderer = createRenderer(fullViewport, "LocalScreen")
fullRenderer.root.ZIndex = 201
fullRenderer.root.Size = UDim2.new(1, 0, 1, 0)
fullRenderer.statusEnabled = false

activeStatus = Instance.new("Frame")
activeStatus.Name = "ActiveStatus"
activeStatus.AnchorPoint = Vector2.new(0.5, 0)
activeStatus.BackgroundColor3 = Color3.fromRGB(12, 16, 24)
activeStatus.BackgroundTransparency = 0.1
activeStatus.BorderSizePixel = 0
activeStatus.Size = UDim2.fromOffset(640, 42)
activeStatus.Visible = false
activeStatus.ZIndex = 255
activeStatus.Parent = fullScreen
updateFullViewportSize()

local function createActiveStatusField(name: string, position: UDim2, size: UDim2, alignment: Enum.TextXAlignment)
	local label = Instance.new("TextLabel")
	label.Name = name
	label.BackgroundTransparency = 1
	label.BorderSizePixel = 0
	label.Font = Enum.Font.GothamBold
	label.Position = position
	label.Size = size
	label.Text = ""
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.TextSize = 15
	label.TextXAlignment = alignment
	label.TextYAlignment = Enum.TextYAlignment.Center
	label.ZIndex = activeStatus.ZIndex + 1
	label.Parent = activeStatus
	return label
end

local activeStatusCurrent = createActiveStatusField(
	"CurrentLapTime",
	UDim2.new(0, 12, 0, 0),
	UDim2.new(0, 120, 1, 0),
	Enum.TextXAlignment.Left
)
local activeStatusLast = createActiveStatusField(
	"LastLapTime",
	UDim2.new(0, 140, 0, 0),
	UDim2.new(0, 135, 1, 0),
	Enum.TextXAlignment.Left
)
local activeStatusFast = createActiveStatusField(
	"FastLapTime",
	UDim2.new(0, 285, 0, 0),
	UDim2.new(0, 210, 1, 0),
	Enum.TextXAlignment.Center
)
local activeStatusSpeed = createActiveStatusField(
	"Speed",
	UDim2.new(1, -120, 0, 0),
	UDim2.new(0, 108, 1, 0),
	Enum.TextXAlignment.Right
)
local worldRenderers = {}

local function updateActiveStatus(state)
	if state and RacerConfig.isFinalLike(state.mode.Value) then
		activeStatusSpeed.Text = `{5 * math.round(state.speed.Value / 500)} mph`
		activeStatusCurrent.Text = `Time: {formatTime(state.currentLapTime.Value)}`
		activeStatusFast.Text = `Fastest Lap: {formatTime(state.fastLapTime.Value)}`
		if state.lastLapTime.Value > 0 then
			activeStatusLast.Text = `Last Lap: {formatTime(state.lastLapTime.Value)}`
			activeStatusLast.Visible = true
		else
			activeStatusLast.Text = ""
			activeStatusLast.Visible = false
		end
		activeStatus.Visible = true
	else
		activeStatusSpeed.Text = ""
		activeStatusCurrent.Text = ""
		activeStatusLast.Text = ""
		activeStatusFast.Text = ""
		activeStatusLast.Visible = false
		activeStatus.Visible = false
	end
end

local exitButton = Instance.new("TextButton")
exitButton.Name = "ExitButton"
exitButton.AnchorPoint = Vector2.new(1, 0)
exitButton.BackgroundColor3 = Color3.fromRGB(18, 22, 30)
exitButton.BackgroundTransparency = 0.08
exitButton.BorderSizePixel = 0
exitButton.Font = Enum.Font.GothamBold
exitButton.Position = UDim2.new(1, -18, 0, 18)
exitButton.Size = UDim2.fromOffset(104, 42)
exitButton.Text = "Exit"
exitButton.TextColor3 = Color3.fromRGB(255, 255, 255)
exitButton.TextSize = 16
exitButton.ZIndex = 260
exitButton.Parent = fullScreen
exitButton.MouseButton1Click:Connect(function()
	actionEvent:FireServer("Exit")
end)

local rejoinButton = Instance.new("TextButton")
rejoinButton.Name = "RejoinButton"
rejoinButton.AnchorPoint = Vector2.new(1, 0)
rejoinButton.BackgroundColor3 = Color3.fromRGB(18, 22, 30)
rejoinButton.BackgroundTransparency = 0.08
rejoinButton.BorderSizePixel = 0
rejoinButton.Font = Enum.Font.GothamBold
rejoinButton.Position = UDim2.new(1, -130, 0, 18)
rejoinButton.Size = UDim2.fromOffset(104, 42)
rejoinButton.Text = "Rejoin"
rejoinButton.TextColor3 = Color3.fromRGB(255, 255, 255)
rejoinButton.TextSize = 16
rejoinButton.ZIndex = 260
rejoinButton.Parent = fullScreen
rejoinButton.MouseButton1Click:Connect(function()
	actionEvent:FireServer("Rejoin")
end)

local settingsButton = Instance.new("TextButton")
settingsButton.Name = "SettingsButton"
settingsButton.AnchorPoint = Vector2.new(1, 0)
settingsButton.BackgroundColor3 = Color3.fromRGB(18, 22, 30)
settingsButton.BackgroundTransparency = 0.08
settingsButton.BorderSizePixel = 0
settingsButton.Font = Enum.Font.GothamBold
settingsButton.Position = UDim2.new(1, -18, 0, 66)
settingsButton.Size = UDim2.fromOffset(104, 42)
settingsButton.Text = "Settings"
settingsButton.TextColor3 = Color3.fromRGB(255, 255, 255)
settingsButton.TextSize = 16
settingsButton.ZIndex = 260
settingsButton.Parent = fullScreen

local settingsPanel = Instance.new("Frame")
settingsPanel.Name = "SettingsPanel"
settingsPanel.AnchorPoint = Vector2.new(1, 0)
settingsPanel.BackgroundColor3 = Color3.fromRGB(12, 16, 24)
settingsPanel.BackgroundTransparency = 0.08
settingsPanel.BorderSizePixel = 0
settingsPanel.Position = UDim2.new(1, -18, 0, 114)
settingsPanel.Size = UDim2.fromOffset(238, 350)
settingsPanel.Visible = false
settingsPanel.ZIndex = 260
settingsPanel.Parent = fullScreen
rounded(settingsPanel, 6)

settingsButton.MouseButton1Click:Connect(function()
	settingsPanel.Visible = not settingsPanel.Visible
	settingsButton.Text = if settingsPanel.Visible then "Hide" else "Settings"
end)

local settingsTitle = createLabel(
	settingsPanel,
	"SettingsTitle",
	UDim2.fromOffset(10, 8),
	UDim2.new(1, -20, 0, 32),
	15
)
settingsTitle.BackgroundTransparency = 1
settingsTitle.Text = "Renderer Settings"
settingsTitle.ZIndex = 261

local function makeButton(parent: Instance, text: string, position: UDim2, size: UDim2)
	local button = Instance.new("TextButton")
	button.BackgroundColor3 = Color3.fromRGB(35, 45, 58)
	button.BorderSizePixel = 0
	button.Font = Enum.Font.GothamBold
	button.Position = position
	button.Size = size
	button.Text = text
	button.TextColor3 = Color3.fromRGB(255, 255, 255)
	button.TextSize = 15
	button.ZIndex = 262
	button.Parent = parent
	rounded(button, 4)
	return button
end

local settingRows = {
	{ label = "Road", key = "RoadWidth", valueName = "settingRoadWidth" },
	{ label = "Height", key = "CameraHeight", valueName = "settingCameraHeight" },
	{ label = "Draw", key = "DrawDistance", valueName = "settingDrawDistance" },
	{ label = "FOV", key = "FieldOfView", valueName = "settingFieldOfView" },
	{ label = "Fog", key = "FogDensity", valueName = "settingFogDensity" },
	{ label = "Lanes", key = "Lanes", valueName = "settingLanes" },
}

local textureToggleLabel: TextButton? = nil

local function currentSettingText(row): string
	local state = activeState()
	if not state then
		return "-"
	end
	local valueObject = state[row.valueName]
	return if valueObject then tostring(math.floor(valueObject.Value)) else "-"
end

for index, row in settingRows do
	local y = 42 + (index - 1) * 34
	local nameLabel = createLabel(
		settingsPanel,
		`SettingName_{row.key}`,
		UDim2.fromOffset(12, y),
		UDim2.fromOffset(72, 28),
		13
	)
	nameLabel.BackgroundTransparency = 1
	nameLabel.Text = row.label
	nameLabel.TextXAlignment = Enum.TextXAlignment.Left
	nameLabel.ZIndex = 261

	local valueLabel = createLabel(
		settingsPanel,
		`SettingValue_{row.key}`,
		UDim2.fromOffset(136, y),
		UDim2.fromOffset(48, 28),
		13
	)
	valueLabel.BackgroundTransparency = 1
	valueLabel.Text = currentSettingText(row)
	valueLabel.ZIndex = 261
	row.valueLabel = valueLabel

	local minus = makeButton(settingsPanel, "-", UDim2.fromOffset(90, y), UDim2.fromOffset(32, 28))
	minus.MouseButton1Click:Connect(function()
		actionEvent:FireServer("Setting", row.key, -1)
	end)

	local plus = makeButton(settingsPanel, "+", UDim2.fromOffset(194, y), UDim2.fromOffset(32, 28))
	plus.MouseButton1Click:Connect(function()
		actionEvent:FireServer("Setting", row.key, 1)
	end)
end

local function updateSettingLabels()
	for _, row in settingRows do
		row.valueLabel.Text = currentSettingText(row)
	end
	if textureToggleLabel then
		local available = textureAtlasImage() ~= nil
		textureToggleLabel.Text = `{if useTextureArt and available then "[x]" else "[ ]"} Textures`
		textureToggleLabel.TextColor3 = if available
			then Color3.fromRGB(255, 255, 255)
			else Color3.fromRGB(150, 156, 164)
	end
end

textureToggleLabel = makeButton(
	settingsPanel,
	"[ ] Textures",
	UDim2.fromOffset(12, 248),
	UDim2.new(1, -24, 0, 32)
)
textureToggleLabel.TextXAlignment = Enum.TextXAlignment.Left
textureToggleLabel.MouseButton1Click:Connect(function()
	useTextureArt = not useTextureArt
	fullRenderer.lastSignature = nil
	for _, entry in worldRenderers do
		entry.renderer.lastSignature = nil
	end
	updateSettingLabels()
end)

local resetButton =
	makeButton(settingsPanel, "Reset", UDim2.fromOffset(12, 296), UDim2.new(1, -24, 0, 36))
resetButton.MouseButton1Click:Connect(function()
	actionEvent:FireServer("ResetSettings")
end)
updateSettingLabels()

task.spawn(function()
	local lab = Workspace:WaitForChild("RacerLab", 20)
	if not lab then
		return
	end
	for _, definition in RacerConfig.Screens do
		local cabinet = lab:WaitForChild(`ArcadeScreen_{definition.Id}`, 20)
		local screenPart = cabinet and cabinet:WaitForChild("ScreenPart", 20)
		if screenPart and screenPart:IsA("BasePart") then
			local surfaceGui = Instance.new("SurfaceGui")
			surfaceGui.Name = "RacerWorldScreen"
			surfaceGui.Adornee = screenPart
			surfaceGui.Face = Enum.NormalId.Back
			surfaceGui.LightInfluence = 0
			surfaceGui.MaxDistance = WORLD_SCREEN_MAX_DISTANCE
			surfaceGui.PixelsPerStud = 32
			surfaceGui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
			surfaceGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
			surfaceGui.Parent = screenPart

			worldRenderers[definition.Id] = {
				renderer = createRenderer(
					surfaceGui,
					`WorldScreen_{definition.Id}`,
					0.84,
					RacerConfig.isFinalLike(definition.Mode)
				),
				screenPart = screenPart,
				surfaceGui = surfaceGui,
			}
		end
	end
end)

local controlsBound = false
local savedCameraType: Enum.CameraType? = nil
local savedPlayerListEnabled = true
local savedChatEnabled = true

local function getCoreGuiEnabled(coreGuiType: Enum.CoreGuiType, fallback: boolean): boolean
	local ok, enabled = pcall(function()
		return StarterGui:GetCoreGuiEnabled(coreGuiType)
	end)
	return if ok then enabled else fallback
end

local function setCoreGuiEnabled(coreGuiType: Enum.CoreGuiType, enabled: boolean)
	pcall(function()
		StarterGui:SetCoreGuiEnabled(coreGuiType, enabled)
	end)
end

local function releaseFocusedTextBox()
	pcall(function()
		StarterGui:SetCore("ChatActive", false)
	end)
	pcall(function()
		GuiService.SelectedObject = nil
	end)
	local focusedTextBox = UserInputService:GetFocusedTextBox()
	if focusedTextBox then
		pcall(function()
			focusedTextBox:ReleaseFocus(false)
		end)
	end
end

local function inputIsDown(inputName: string): boolean
	return keyboardInputs[inputName] == true or pointerInputs[inputName] == true
end

local function publishInput(inputName: string)
	local isDown = inputIsDown(inputName)
	if (pressedInputs[inputName] == true) == isDown then
		return
	end
	pressedInputs[inputName] = isDown
	inputEvent:FireServer(inputName, isDown)
end

local function setKeyboardInput(inputName: string, isDown: boolean)
	if (keyboardInputs[inputName] == true) == isDown then
		return
	end
	keyboardInputs[inputName] = isDown
	publishInput(inputName)
end

local function setPointerInput(inputName: string, isDown: boolean)
	if (pointerInputs[inputName] == true) == isDown then
		return
	end
	pointerInputs[inputName] = isDown
	publishInput(inputName)
end

local function handleRacerKeyboardInput(inputObject: InputObject, isDown: boolean)
	if not controlsBound then
		return
	end
	releaseFocusedTextBox()
	local inputName = keyMap[inputObject.KeyCode]
	if inputName then
		setKeyboardInput(inputName, isDown)
	end
end

local function syncHeldKeyboardInputs()
	local heldInputs = {}
	for keyCode, inputName in keyMap do
		if UserInputService:IsKeyDown(keyCode) then
			heldInputs[inputName] = true
		end
	end
	for _, inputName in inputNames do
		setKeyboardInput(inputName, heldInputs[inputName] == true)
	end
end

UserInputService.InputBegan:Connect(function(inputObject)
	handleRacerKeyboardInput(inputObject, true)
end)

UserInputService.InputEnded:Connect(function(inputObject)
	handleRacerKeyboardInput(inputObject, false)
end)

local function releaseInputs()
	for _, inputName in inputNames do
		keyboardInputs[inputName] = false
		pointerInputs[inputName] = false
		publishInput(inputName)
	end
end

local mobileControlButtons = {}
local mobileButtonColor = Color3.fromRGB(18, 22, 30)
local mobileButtonPressedColor = Color3.fromRGB(54, 68, 84)

local mobileControls = Instance.new("Frame")
mobileControls.Name = "MobileControls"
mobileControls.BackgroundTransparency = 1
mobileControls.BorderSizePixel = 0
mobileControls.Size = UDim2.fromScale(1, 1)
mobileControls.Visible = UserInputService.TouchEnabled
mobileControls.ZIndex = 270
mobileControls.Parent = fullScreen

local function resetMobileControlButtons()
	for _, button in mobileControlButtons do
		button.BackgroundColor3 = mobileButtonColor
	end
end

local function bindMobileHoldButton(button: TextButton, inputName: string)
	local activePointers = {}

	button.InputBegan:Connect(function(inputObject)
		if
			inputObject.UserInputType ~= Enum.UserInputType.Touch
			and inputObject.UserInputType ~= Enum.UserInputType.MouseButton1
		then
			return
		end

		activePointers[inputObject] = true
		button.BackgroundColor3 = mobileButtonPressedColor
		setPointerInput(inputName, true)
	end)

	button.InputEnded:Connect(function(inputObject)
		if not activePointers[inputObject] then
			return
		end

		activePointers[inputObject] = nil
		for _ in activePointers do
			return
		end
		button.BackgroundColor3 = mobileButtonColor
		setPointerInput(inputName, false)
	end)
end

local function createMobileControlButton(name: string, text: string, position: UDim2, inputName: string)
	local button = Instance.new("TextButton")
	button.Name = name
	button.AnchorPoint = Vector2.new(0, 1)
	button.BackgroundColor3 = mobileButtonColor
	button.BackgroundTransparency = 0.12
	button.BorderSizePixel = 0
	button.Font = Enum.Font.GothamBold
	button.Position = position
	button.Size = UDim2.fromOffset(66, 56)
	button.Text = text
	button.TextColor3 = Color3.fromRGB(255, 255, 255)
	button.TextSize = 14
	button.ZIndex = 271
	button.Parent = mobileControls
	rounded(button, 8)
	table.insert(mobileControlButtons, button)
	bindMobileHoldButton(button, inputName)
	return button
end

createMobileControlButton("MobileLeftButton", "Left", UDim2.new(0, 16, 1, -24), "left")
createMobileControlButton("MobileRightButton", "Right", UDim2.new(0, 90, 1, -24), "right")
createMobileControlButton("MobileBrakeButton", "Brake", UDim2.new(1, -156, 1, -24), "slower")
createMobileControlButton("MobileGasButton", "Gas", UDim2.new(1, -82, 1, -24), "faster")

local function racerControlAction(_, inputState: Enum.UserInputState, inputObject: InputObject)
	if inputObject.KeyCode == Enum.KeyCode.Tab then
		if inputState == Enum.UserInputState.Begin then
			actionEvent:FireServer("Exit")
		end
		return Enum.ContextActionResult.Sink
	end

	local inputName = keyMap[inputObject.KeyCode]
	if inputName then
		setKeyboardInput(inputName, inputState == Enum.UserInputState.Begin)
		return Enum.ContextActionResult.Sink
	end
	return Enum.ContextActionResult.Pass
end

local function bindRacerControls()
	if controlsBound then
		return
	end
	controlsBound = true
	local camera = Workspace.CurrentCamera
	if camera then
		savedCameraType = camera.CameraType
		camera.CameraType = Enum.CameraType.Scriptable
	end
	savedPlayerListEnabled = getCoreGuiEnabled(Enum.CoreGuiType.PlayerList, true)
	savedChatEnabled = getCoreGuiEnabled(Enum.CoreGuiType.Chat, true)
	setCoreGuiEnabled(Enum.CoreGuiType.PlayerList, false)
	setCoreGuiEnabled(Enum.CoreGuiType.Chat, false)
	releaseFocusedTextBox()
	ContextActionService:BindActionAtPriority(
		CONTROL_ACTION,
		racerControlAction,
		false,
		10000,
		Enum.KeyCode.A,
		Enum.KeyCode.Left,
		Enum.KeyCode.D,
		Enum.KeyCode.Right,
		Enum.KeyCode.W,
		Enum.KeyCode.Up,
		Enum.KeyCode.S,
		Enum.KeyCode.Down,
		Enum.KeyCode.Tab
	)
	syncHeldKeyboardInputs()
end

local function unbindRacerControls()
	if not controlsBound then
		return
	end
	controlsBound = false
	ContextActionService:UnbindAction(CONTROL_ACTION)
	releaseInputs()
	resetMobileControlButtons()
	local camera = Workspace.CurrentCamera
	if camera then
		camera.CameraType = savedCameraType or Enum.CameraType.Custom
	end
	setCoreGuiEnabled(Enum.CoreGuiType.PlayerList, savedPlayerListEnabled)
	setCoreGuiEnabled(Enum.CoreGuiType.Chat, savedChatEnabled)
	savedCameraType = nil
end

actionEvent.OnClientEvent:Connect(function(actionName: string, detail: string?)
	if actionName == "Busy" then
		hint.Text = `Screen is busy: {detail}`
	elseif actionName == "Entered" then
		hint.Text = `{detail}: Tab exits the screen.`
	elseif actionName == "Exited" then
		unbindRacerControls()
		hint.Text = "Walk to a screen and press E."
	end
end)

local function updateHud()
	local state = activeState()
	local active = state ~= nil
	fullScreen.Visible = active
	labRejoinButton.Visible = not active
	title.Visible = false
	hint.Visible = not active
	if active then
		bindRacerControls()
		updateSettingLabels()
		updateActiveStatus(state)
		return
	end
	settingsPanel.Visible = false
	settingsButton.Text = "Settings"
	updateActiveStatus(nil)
	unbindRacerControls()
	hint.Text = anyBusyStatus() or "Walk to a screen and press E."
end

for _, state in states do
	state.activeUserId:GetPropertyChangedSignal("Value"):Connect(updateHud)
	state.status:GetPropertyChangedSignal("Value"):Connect(updateHud)
end

local worldRenderAccumulator = WORLD_RENDER_INTERVAL
local settingsLabelAccumulator = SETTINGS_LABEL_INTERVAL
local latestPerfSummary = "waiting for perf sample"
local perfStats = {
	elapsed = 0,
	frames = 0,
	stutters = 0,
	severeStutters = 0,
	maxFrame = 0,
	worldRenderTime = 0,
	worldRenderCount = 0,
	fullRenderTime = 0,
	fullRenderCount = 0,
	lastWorldObjects = 0,
	lastWorldRows = 0,
	lastFullObjects = 0,
	lastFullRows = 0,
}

local function resetPerfStats()
	perfStats.elapsed = 0
	perfStats.frames = 0
	perfStats.stutters = 0
	perfStats.severeStutters = 0
	perfStats.maxFrame = 0
	perfStats.worldRenderTime = 0
	perfStats.worldRenderCount = 0
	perfStats.fullRenderTime = 0
	perfStats.fullRenderCount = 0
end

local function averageMs(totalSeconds: number, count: number): number
	if count <= 0 then
		return 0
	end
	return totalSeconds * 1000 / count
end

local function inputDebugFlags(source): string
	return `{if source.left then "L" else "-"}{if source.right then "R" else "-"}{if source.faster then "F" else "-"}{if source.slower then "S" else "-"}`
end

local function racerStateDebugText(label: string, state): string
	if not state then
		return `{label}=none`
	end
	local mph = 5 * math.round(state.speed.Value / 500)
	return `{label}=mph:{mph} speed:{math.floor(state.speed.Value + 0.5)} time:{formatTime(state.currentLapTime.Value)} pos:{math.floor(state.position.Value + 0.5)}`
end

local function focusDebugText(): string
	local focusedTextBox = UserInputService:GetFocusedTextBox()
	local selectedObject = GuiService.SelectedObject
	return `focus:{if focusedTextBox then focusedTextBox.Name else "-"} selected:{if selectedObject then selectedObject.Name else "-"}`
end

local function activeDebugText(state): string
	return table.concat({
		`active={if state then state.id else "none"}`,
		`keys K:{inputDebugFlags(keyboardInputs)} P:{inputDebugFlags(pointerInputs)} I:{inputDebugFlags(pressedInputs)}`,
		racerStateDebugText("local", predictedState),
		racerStateDebugText("server", state),
		focusDebugText(),
	}, "\n")
end

local function refreshPerfLabel(state)
	perfLabel.Text = `Perf log (F6)\n{latestPerfSummary}\n{activeDebugText(state)}`
end

local function flushPerfStats(state)
	if perfStats.elapsed <= 0 or perfStats.frames <= 0 then
		return
	end

	local fps = perfStats.frames / perfStats.elapsed
	local mode = if state then state.mode.Value else "lab"
	local summary = string.format(
		"mode=%s fps=%.1f stutter=%d severe=%d max=%.0fms full=%.2fms/%d world=%.2fms/%d objs=%d/%d rows=%d/%d",
		mode,
		fps,
		perfStats.stutters,
		perfStats.severeStutters,
		perfStats.maxFrame * 1000,
		averageMs(perfStats.fullRenderTime, perfStats.fullRenderCount),
		perfStats.fullRenderCount,
		averageMs(perfStats.worldRenderTime, perfStats.worldRenderCount),
		perfStats.worldRenderCount,
		perfStats.lastFullObjects,
		perfStats.lastWorldObjects,
		perfStats.lastFullRows,
		perfStats.lastWorldRows
	)
	latestPerfSummary = summary
	refreshPerfLabel(state)
	warn(`[RacerPerf] {summary}`)
	perfLogEvent:FireServer(summary)
	resetPerfStats()
end

RunService.RenderStepped:Connect(function(deltaTime)
	local state = activeState()

	perfStats.elapsed += deltaTime
	perfStats.frames += 1
	perfStats.maxFrame = math.max(perfStats.maxFrame, deltaTime)
	if deltaTime >= STUTTER_FRAME_TIME then
		perfStats.stutters += 1
	end
	if deltaTime >= SEVERE_STUTTER_FRAME_TIME then
		perfStats.severeStutters += 1
	end

	worldRenderAccumulator += deltaTime
	if state then
		worldRenderAccumulator = WORLD_RENDER_INTERVAL
		perfStats.lastWorldObjects = 0
		perfStats.lastWorldRows = 0
	elseif worldRenderAccumulator >= WORLD_RENDER_INTERVAL then
		worldRenderAccumulator %= WORLD_RENDER_INTERVAL
		local worldRenderStart = os.clock()
		local renderedWorldScreens = 0
		local camera = Workspace.CurrentCamera
		local cameraPosition = if camera then camera.CFrame.Position else nil
		for screenId, entry in worldRenderers do
			local screenPart = entry.screenPart
			local enabled = true
			if cameraPosition and screenPart and screenPart:IsA("BasePart") then
				local toCamera = cameraPosition - screenPart.Position
				local distance = toCamera.Magnitude
				enabled = distance <= WORLD_SCREEN_MAX_DISTANCE
			end
			entry.surfaceGui.Enabled = enabled
			if enabled and renderIfChanged(entry.renderer, states[screenId]) then
				renderedWorldScreens += 1
			end
		end
		if renderedWorldScreens > 0 then
			perfStats.worldRenderTime += os.clock() - worldRenderStart
			perfStats.worldRenderCount += renderedWorldScreens
		end
		local worldObjects = 0
		local worldRows = 0
		for _, entry in worldRenderers do
			if entry.surfaceGui.Enabled then
				worldObjects += entry.renderer.lastObjectCount or 0
				worldRows += entry.renderer.lastRowCount or 0
			end
		end
		perfStats.lastWorldObjects = worldObjects
		perfStats.lastWorldRows = worldRows
	end

	if state then
		local fullRenderStart = os.clock()
		syncHeldKeyboardInputs()
		local renderState = updatePredictedState(state, deltaTime)
		render(fullRenderer, renderState)
		updateActiveStatus(renderState)
		perfStats.fullRenderTime += os.clock() - fullRenderStart
		perfStats.fullRenderCount += 1
		perfStats.lastFullObjects = fullRenderer.lastObjectCount or 0
		perfStats.lastFullRows = fullRenderer.lastRowCount or 0
		settingsLabelAccumulator += deltaTime
		if settingsLabelAccumulator >= SETTINGS_LABEL_INTERVAL then
			settingsLabelAccumulator = 0
			updateSettingLabels()
		end
		if perfLabel.Visible then
			refreshPerfLabel(state)
		end
	else
		updateActiveStatus(nil)
		predictedState = nil
		predictedSourceId = nil
		perfStats.lastFullObjects = 0
		perfStats.lastFullRows = 0
		settingsLabelAccumulator = SETTINGS_LABEL_INTERVAL
		if perfLabel.Visible then
			refreshPerfLabel(nil)
		end
	end

	if perfStats.elapsed >= PERF_LOG_INTERVAL then
		flushPerfStats(state)
	end
end)

updateHud()
