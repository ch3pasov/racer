local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TeleportService = game:GetService("TeleportService")

local world = Instance.new("Folder")
world.Name = "RacerLab"
world.Parent = workspace

local function createBootPart(
	name: string,
	size: Vector3,
	cframe: CFrame,
	color: Color3,
	parent: Instance,
	material: Enum.Material?
): Part
	local part = Instance.new("Part")
	part.Name = name
	part.Anchored = true
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.TopSurface = Enum.SurfaceType.Smooth
	part.Size = size
	part.CFrame = cframe
	part.Color = color
	part.Material = material or Enum.Material.SmoothPlastic
	part.Parent = parent
	return part
end

local function createBootBadge(message: string)
	local badge = createBootPart(
		"BootStatusBadge",
		Vector3.new(38, 5, 0.25),
		CFrame.new(0, 8, 12) * CFrame.Angles(0, math.rad(180), 0),
		Color3.fromRGB(90, 26, 26),
		world,
		Enum.Material.SmoothPlastic
	)
	badge.CanCollide = false

	local surfaceGui = Instance.new("SurfaceGui")
	surfaceGui.Name = "BootStatusGui"
	surfaceGui.Face = Enum.NormalId.Front
	surfaceGui.LightInfluence = 0
	surfaceGui.PixelsPerStud = 28
	surfaceGui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	surfaceGui.Parent = badge

	local label = Instance.new("TextLabel")
	label.BackgroundTransparency = 1
	label.Font = Enum.Font.GothamBold
	label.Size = UDim2.fromScale(1, 1)
	label.Text = message
	label.TextColor3 = Color3.fromRGB(255, 235, 235)
	label.TextScaled = true
	label.TextWrapped = true
	label.Parent = surfaceGui
end

local function createBootFallback()
	createBootPart(
		"BootFloor",
		Vector3.new(70, 1, 42),
		CFrame.new(0, -0.5, 0),
		Color3.fromRGB(34, 38, 48),
		world,
		Enum.Material.Concrete
	)

	local spawn = Instance.new("SpawnLocation")
	spawn.Name = "BootSpawn"
	spawn.Anchored = true
	spawn.Neutral = true
	spawn.Size = Vector3.new(7, 1, 7)
	spawn.CFrame = CFrame.new(0, 0.6, 14)
	spawn.Color = Color3.fromRGB(236, 240, 244)
	spawn.Material = Enum.Material.Neon
	spawn.Parent = world
end

createBootFallback()

local generatedOk, GeneratedPlaceIds = pcall(function()
	return require(ReplicatedStorage.Shared.GeneratedPlaceIds)
end)
local racerShared = ReplicatedStorage:WaitForChild("RacerShared", 15)
local configOk, RacerConfig = pcall(function()
	return require(racerShared.RacerConfig)
end)
local mathOk, RacerMath = pcall(function()
	return require(racerShared.RacerMath)
end)

if not generatedOk or not racerShared or not configOk or not mathOk then
	local message = "Racer Lab boot failed. Open Developer Console."
	createBootBadge(message)
	warn(
		`[RacerLab] boot failed generated={generatedOk} shared={racerShared ~= nil} config={configOk} math={mathOk}`
	)
	return
end

local actionEvent = Instance.new("RemoteEvent")
actionEvent.Name = "RacerAction"
actionEvent.Parent = ReplicatedStorage

local inputEvent = Instance.new("RemoteEvent")
inputEvent.Name = "RacerInput"
inputEvent.Parent = ReplicatedStorage

local perfLogEvent = Instance.new("RemoteEvent")
perfLogEvent.Name = "RacerPerfLog"
perfLogEvent.Parent = ReplicatedStorage

local statesFolder = Instance.new("Folder")
statesFolder.Name = "RacerStates"
statesFolder.Parent = ReplicatedStorage

local perfFolder = Instance.new("Folder")
perfFolder.Name = "RacerPerf"
perfFolder.Parent = ReplicatedStorage

local latestPerfLog = Instance.new("StringValue")
latestPerfLog.Name = "Latest"
latestPerfLog.Value = ""
latestPerfLog.Parent = perfFolder

local perfHistory = Instance.new("StringValue")
perfHistory.Name = "History"
perfHistory.Value = ""
perfHistory.Parent = perfFolder

local SPAWN_CFRAME = CFrame.new(0, 4, 22)
local LOBBY_PLACE_ID = GeneratedPlaceIds.LobbyPlaceId or 0
local RACER_PLACE_ID = if GeneratedPlaceIds.RacerPlaceId and GeneratedPlaceIds.RacerPlaceId > 0
	then GeneratedPlaceIds.RacerPlaceId
	else game.PlaceId
local MAX_ACCUMULATED_TIME = 1
local MAX_STEPS_PER_HEARTBEAT = 8

local SETTING_DEFAULTS = {
	RoadWidth = { min = 500, max = 3000, step = 100, default = 2000 },
	CameraHeight = { min = 500, max = 5000, step = 100, default = 1000 },
	DrawDistance = { min = 100, max = RacerConfig.MaxDrawDistance, step = 20, default = 300 },
	FieldOfView = { min = 80, max = 140, step = 5, default = 100 },
	FogDensity = { min = 0, max = 50, step = 1, default = 5 },
	Lanes = { min = 1, max = 4, step = 1, default = 3 },
}

local BACKGROUND_SPEEDS = {
	Sky = 0.001,
	Hill = 0.002,
	Tree = 0.003,
}

local sessions = {}
local perfLines = {}

local function createValue(parent: Instance, className: string, name: string, initialValue)
	local item = Instance.new(className)
	item.Name = name
	item.Value = initialValue
	item.Parent = parent
	return item
end

local function createSession(definition)
	local folder = Instance.new("Folder")
	folder.Name = definition.Id
	folder.Parent = statesFolder

	local values = {
		ActiveUserId = createValue(folder, "IntValue", "ActiveUserId", 0),
		ActivePlayerName = createValue(folder, "StringValue", "ActivePlayerName", ""),
		Position = createValue(folder, "NumberValue", "Position", 0),
		Speed = createValue(folder, "NumberValue", "Speed", 0),
		TrafficTime = createValue(folder, "NumberValue", "TrafficTime", 0),
		TrafficOffsets = createValue(folder, "StringValue", "TrafficOffsets", ""),
		CurrentLapTime = createValue(folder, "NumberValue", "CurrentLapTime", 0),
		LastLapTime = createValue(folder, "NumberValue", "LastLapTime", 0),
		FastLapTime = createValue(folder, "NumberValue", "FastLapTime", 180),
		VisibleCars = createValue(folder, "IntValue", "VisibleCars", 0),
		VisibleSprites = createValue(folder, "IntValue", "VisibleSprites", 0),
		ClippedObjects = createValue(folder, "IntValue", "ClippedObjects", 0),
		PlayerX = createValue(folder, "NumberValue", "PlayerX", 0),
		Steer = createValue(folder, "NumberValue", "Steer", 0),
		SkyOffset = createValue(folder, "NumberValue", "SkyOffset", 0),
		HillOffset = createValue(folder, "NumberValue", "HillOffset", 0),
		TreeOffset = createValue(folder, "NumberValue", "TreeOffset", 0),
		Status = createValue(
			folder,
			"StringValue",
			"Status",
			`Approach {definition.Name} and press E.`
		),
		ScreenName = createValue(folder, "StringValue", "ScreenName", definition.Name),
		Mode = createValue(folder, "StringValue", "Mode", definition.Mode),
		SettingRoadWidth = createValue(
			folder,
			"NumberValue",
			"SettingRoadWidth",
			SETTING_DEFAULTS.RoadWidth.default
		),
		SettingCameraHeight = createValue(
			folder,
			"NumberValue",
			"SettingCameraHeight",
			SETTING_DEFAULTS.CameraHeight.default
		),
		SettingDrawDistance = createValue(
			folder,
			"NumberValue",
			"SettingDrawDistance",
			SETTING_DEFAULTS.DrawDistance.default
		),
		SettingFieldOfView = createValue(
			folder,
			"NumberValue",
			"SettingFieldOfView",
			SETTING_DEFAULTS.FieldOfView.default
		),
		SettingFogDensity = createValue(
			folder,
			"NumberValue",
			"SettingFogDensity",
			SETTING_DEFAULTS.FogDensity.default
		),
		SettingLanes = createValue(
			folder,
			"NumberValue",
			"SettingLanes",
			SETTING_DEFAULTS.Lanes.default
		),
	}

	local session = {
		definition = definition,
		folder = folder,
		values = values,
		activePlayer = nil :: Player?,
		position = 0,
		speed = 0,
		trafficTime = 0,
		currentLapTime = 0,
		lastLapTime = 0,
		fastLapTime = 180,
		lapStarted = false,
		playerX = 0,
		steer = 0,
		skyOffset = 0,
		hillOffset = 0,
		treeOffset = 0,
		trafficOffsets = {},
		trafficState = nil,
		input = {
			left = false,
			right = false,
			faster = false,
			slower = false,
		},
	}
	sessions[definition.Id] = session
	return session
end

for _, definition in RacerConfig.Screens do
	createSession(definition)
end

local function createPart(
	name: string,
	size: Vector3,
	cframe: CFrame,
	color: Color3,
	parent: Instance,
	material: Enum.Material?
): Part
	local part = Instance.new("Part")
	part.Name = name
	part.Anchored = true
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.TopSurface = Enum.SurfaceType.Smooth
	part.Size = size
	part.CFrame = cframe
	part.Color = color
	part.Material = material or Enum.Material.SmoothPlastic
	part.Parent = parent
	return part
end

local function addInvisibleWall(name: string, position: Vector3, size: Vector3)
	local wall = createPart(
		name,
		size,
		CFrame.new(position),
		Color3.fromRGB(255, 255, 255),
		world,
		Enum.Material.SmoothPlastic
	)
	wall.Transparency = 1
	wall.CanCollide = true
	wall.CanQuery = false
	wall.CanTouch = false
end

local function setCharacterLocked(player: Player, locked: boolean)
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if not humanoid then
		return
	end
	if locked then
		humanoid.WalkSpeed = 0
		humanoid.JumpPower = 0
		humanoid.AutoRotate = false
	else
		humanoid.WalkSpeed = 16
		humanoid.JumpPower = 50
		humanoid.AutoRotate = true
	end
end

local function publishState(session)
	session.values.ActiveUserId.Value = if session.activePlayer
		then session.activePlayer.UserId
		else 0
	session.values.ActivePlayerName.Value = if session.activePlayer
		then session.activePlayer.DisplayName
		else ""
	session.values.Position.Value = session.position
	session.values.Speed.Value = session.speed
	session.values.TrafficTime.Value = session.trafficTime
	session.values.TrafficOffsets.Value = if session.definition.Mode == "final"
		then RacerConfig.packTrafficOffsets(session.trafficOffsets)
		else ""
	session.values.CurrentLapTime.Value = session.currentLapTime
	session.values.LastLapTime.Value = session.lastLapTime
	session.values.FastLapTime.Value = session.fastLapTime
	session.values.PlayerX.Value = session.playerX
	session.values.Steer.Value = session.steer
	session.values.SkyOffset.Value = session.skyOffset
	session.values.HillOffset.Value = session.hillOffset
	session.values.TreeOffset.Value = session.treeOffset
end

local function resetRun(session)
	session.position = 0
	session.speed = 0
	session.trafficTime = 0
	session.currentLapTime = 0
	session.lastLapTime = 0
	session.lapStarted = false
	session.playerX = 0
	session.steer = 0
	session.skyOffset = 0
	session.hillOffset = 0
	session.treeOffset = 0
	if session.definition.Mode == "final" then
		session.trafficOffsets = RacerConfig.baseTrafficOffsets()
		session.trafficState = RacerConfig.createTrafficState(
			0,
			RacerConfig.trackLength(session.definition.Mode),
			RacerConfig.segmentCount(session.definition.Mode),
			session.trafficOffsets
		)
	else
		session.trafficOffsets = {}
		session.trafficState = nil
	end
	session.input.left = false
	session.input.right = false
	session.input.faster = false
	session.input.slower = false
	publishState(session)
end

local function findPlayerSession(player: Player)
	for _, session in sessions do
		if session.activePlayer == player then
			return session
		end
	end
	return nil
end

local function exitScreen(player: Player, message: string?)
	local session = findPlayerSession(player)
	if not session then
		return
	end

	setCharacterLocked(player, false)
	player:SetAttribute("Activity", "RacerLab")
	player:SetAttribute("RacerMode", "Spectating")
	player:SetAttribute("RacerScreenId", "")
	session.activePlayer = nil
	resetRun(session)
	session.values.Status.Value = message or `{session.definition.Name} ready.`
	actionEvent:FireClient(player, "Exited")
end

local function rejoinPlace(player: Player)
	if RACER_PLACE_ID <= 0 then
		actionEvent:FireClient(player, "Busy", "Rejoin is unavailable in this place.")
		return
	end

	local reservedOk, reservedErr = pcall(function()
		local accessCode = TeleportService:ReserveServer(RACER_PLACE_ID)
		exitScreen(player, "Screen ready.")
		TeleportService:TeleportToPrivateServer(RACER_PLACE_ID, accessCode, { player })
	end)
	if reservedOk then
		return
	end

	warn(`[RacerLab] reserved rejoin failed for {player.Name}: {reservedErr}`)
	local fallbackOk, fallbackErr = pcall(function()
		exitScreen(player, "Screen ready.")
		TeleportService:Teleport(RACER_PLACE_ID, player)
	end)
	if not fallbackOk then
		warn(`[RacerLab] fallback rejoin failed for {player.Name}: {fallbackErr}`)
		actionEvent:FireClient(player, "Busy", "Rejoin failed. Try again.")
	end
end

local function enterScreen(player: Player, screenId: string)
	if findPlayerSession(player) then
		actionEvent:FireClient(player, "Busy", "Exit the current screen first.")
		return
	end

	local session = sessions[screenId]
	if not session then
		return
	end
	if session.activePlayer and session.activePlayer ~= player then
		actionEvent:FireClient(player, "Busy", session.values.ActivePlayerName.Value)
		return
	end

	session.activePlayer = player
	resetRun(session)
	setCharacterLocked(player, true)
	player:SetAttribute("Activity", "RacerScreen")
	player:SetAttribute("RacerMode", session.definition.Name)
	player:SetAttribute("RacerScreenId", session.definition.Id)
	session.values.Status.Value = `{player.DisplayName} is playing {session.definition.Name}.`
	publishState(session)
	actionEvent:FireClient(player, "Entered", session.definition.Name)
end

local function createCabinet(definition)
	local position = definition.Position
	local cabinet = Instance.new("Model")
	cabinet.Name = `ArcadeScreen_{definition.Id}`
	cabinet:SetAttribute("RacerScreenId", definition.Id)
	cabinet.Parent = world

	createPart(
		"CabinetBase",
		Vector3.new(24, 3, 6),
		CFrame.new(position.X, 1.2, position.Z + 3),
		Color3.fromRGB(12, 16, 24),
		cabinet,
		Enum.Material.Metal
	)
	local screenPart = createPart(
		"ScreenPart",
		Vector3.new(24, 18, 0.5),
		CFrame.new(position.X, 9, position.Z),
		Color3.fromRGB(4, 7, 12),
		cabinet,
		Enum.Material.SmoothPlastic
	)
	screenPart:SetAttribute("RacerScreen", true)
	screenPart:SetAttribute("RacerScreenId", definition.Id)

	local frameParts = {
		{
			name = "ScreenFrameTop",
			size = Vector3.new(25.5, 0.6, 0.25),
			cframe = CFrame.new(position.X, 18.3, position.Z + 0.18),
		},
		{
			name = "ScreenFrameBottom",
			size = Vector3.new(25.5, 0.6, 0.25),
			cframe = CFrame.new(position.X, -0.3, position.Z + 0.18),
		},
		{
			name = "ScreenFrameLeft",
			size = Vector3.new(0.6, 19.2, 0.25),
			cframe = CFrame.new(position.X - 12.45, 9, position.Z + 0.18),
		},
		{
			name = "ScreenFrameRight",
			size = Vector3.new(0.6, 19.2, 0.25),
			cframe = CFrame.new(position.X + 12.45, 9, position.Z + 0.18),
		},
	}
	for _, framePart in frameParts do
		local glow = createPart(
			framePart.name,
			framePart.size,
			framePart.cframe,
			definition.Color,
			cabinet,
			Enum.Material.Neon
		)
		glow.Transparency = 0.18
		glow.CanCollide = false
	end

	local promptPart = createPart(
		"PlayConsole",
		Vector3.new(10, 1.1, 4),
		CFrame.new(position.X, 1.0, position.Z + 12),
		definition.Color,
		cabinet,
		Enum.Material.Neon
	)

	local prompt = Instance.new("ProximityPrompt")
	prompt.Name = "RacerPrompt"
	prompt.ActionText = "Enter Screen"
	prompt.ObjectText = definition.Name
	prompt.HoldDuration = 0.15
	prompt.KeyboardKeyCode = Enum.KeyCode.E
	prompt.MaxActivationDistance = 12
	prompt.RequiresLineOfSight = false
	prompt.Parent = promptPart
	prompt.Triggered:Connect(function(player)
		enterScreen(player, definition.Id)
	end)
end

local function createLobbyPortal()
	if LOBBY_PLACE_ID <= 0 then
		return
	end

	local portal = createPart(
		"LobbyPortal",
		Vector3.new(9, 1.1, 9),
		CFrame.new(SPAWN_CFRAME.Position.X, 0.9, SPAWN_CFRAME.Position.Z),
		Color3.fromRGB(236, 240, 244),
		world,
		Enum.Material.Neon
	)

	local prompt = Instance.new("ProximityPrompt")
	prompt.Name = "LobbyPrompt"
	prompt.ActionText = "Go to Lobby"
	prompt.ObjectText = "Roblox Game Lab"
	prompt.HoldDuration = 0.15
	prompt.KeyboardKeyCode = Enum.KeyCode.E
	prompt.MaxActivationDistance = 12
	prompt.RequiresLineOfSight = false
	prompt.Parent = portal
	prompt.Triggered:Connect(function(player)
		exitScreen(player, "Screen ready.")
		TeleportService:Teleport(LOBBY_PLACE_ID, player)
	end)
end

local function createVersionBadge()
	local badge = createPart(
		"VersionBadge",
		Vector3.new(9, 1.8, 0.25),
		CFrame.new(-12, 2.2, 29.2) * CFrame.Angles(0, math.rad(180), 0),
		Color3.fromRGB(14, 18, 24),
		world,
		Enum.Material.SmoothPlastic
	)
	badge.CanCollide = false

	local surfaceGui = Instance.new("SurfaceGui")
	surfaceGui.Name = "VersionBadgeGui"
	surfaceGui.Face = Enum.NormalId.Front
	surfaceGui.LightInfluence = 0
	surfaceGui.PixelsPerStud = 36
	surfaceGui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	surfaceGui.Parent = badge

	local label = Instance.new("TextLabel")
	label.BackgroundColor3 = Color3.fromRGB(14, 18, 24)
	label.BackgroundTransparency = 0
	label.BorderSizePixel = 0
	label.Font = Enum.Font.GothamBold
	label.Size = UDim2.fromScale(1, 1)
	local version = if game.PlaceVersion > 0 then tostring(game.PlaceVersion) else RacerConfig.VersionBuild
	label.Text = `build {version}`
	label.TextColor3 = Color3.fromRGB(236, 240, 244)
	label.TextScaled = true
	label.Parent = surfaceGui

	local padding = Instance.new("UIPadding")
	padding.PaddingBottom = UDim.new(0, 8)
	padding.PaddingLeft = UDim.new(0, 14)
	padding.PaddingRight = UDim.new(0, 14)
	padding.PaddingTop = UDim.new(0, 8)
	padding.Parent = label
end

local function buildLab()
	world:ClearAllChildren()

	Lighting.ClockTime = 18.2
	Lighting.Brightness = 2.1
	Lighting.Ambient = Color3.fromRGB(72, 76, 90)
	Lighting.OutdoorAmbient = Color3.fromRGB(32, 36, 48)

	createPart(
		"LabFloor",
		Vector3.new(150, 1, 70),
		CFrame.new(0, -0.5, 0),
		Color3.fromRGB(34, 38, 48),
		world,
		Enum.Material.Concrete
	)
	addInvisibleWall("BackWall", Vector3.new(0, 40, -34.5), Vector3.new(152, 82, 1.2))
	addInvisibleWall("FrontWall", Vector3.new(0, 40, 34.5), Vector3.new(152, 82, 1.2))
	addInvisibleWall("LeftWall", Vector3.new(-74.5, 40, 0), Vector3.new(1.2, 82, 72))
	addInvisibleWall("RightWall", Vector3.new(74.5, 40, 0), Vector3.new(1.2, 82, 72))

	local spawn = Instance.new("SpawnLocation")
	spawn.Name = "RacerLabSpawn"
	spawn.Anchored = true
	spawn.Neutral = true
	spawn.Size = Vector3.new(7, 1, 7)
	spawn.CFrame = CFrame.new(0, 0.6, 22)
	spawn.Color = Color3.fromRGB(236, 240, 244)
	spawn.Material = Enum.Material.Neon
	spawn.Parent = world

	for _, definition in RacerConfig.Screens do
		createCabinet(definition)
	end
	createLobbyPortal()
	createVersionBadge()
end

local function updateRacer(session, dt: number)
	if not session.activePlayer then
		return
	end

	local trackLength = RacerConfig.trackLength(session.definition.Mode)
	local speedPercent = session.speed / RacerConfig.MaxSpeed
	local dx = dt * 2 * speedPercent
	local startPosition = session.position
	local fieldOfView = session.values.SettingFieldOfView.Value
	local cameraHeight = session.values.SettingCameraHeight.Value
	local cameraDepth = 1 / math.tan(math.rad(fieldOfView / 2))
	local playerZ = cameraHeight * cameraDepth
	local segmentCount = RacerConfig.segmentCount(session.definition.Mode)
	local segmentIndex = math.floor((session.position + playerZ) / RacerConfig.SegmentLength)
		% segmentCount
	local curve = RacerConfig.curveFor(session.definition.Mode, segmentIndex)
	local trafficItems = nil
	local trafficBySegment = nil

	if session.definition.Mode == "final" then
		trafficItems, trafficBySegment = RacerConfig.advanceTraffic(
			session.trafficOffsets,
			session.trafficTime,
			dt,
			trackLength,
			segmentCount,
			segmentIndex,
			session.playerX,
			session.speed,
			session.values.SettingDrawDistance.Value,
			session.trafficState
		)
	end

	if session.definition.Mode == "final" then
		session.trafficTime += dt
	end
	session.position = RacerMath.increase(session.position, dt * session.speed, trackLength)
	if session.definition.Mode ~= "final" then
		session.skyOffset =
			RacerMath.increase(session.skyOffset, BACKGROUND_SPEEDS.Sky * curve * speedPercent, 1)
		session.hillOffset =
			RacerMath.increase(session.hillOffset, BACKGROUND_SPEEDS.Hill * curve * speedPercent, 1)
		session.treeOffset =
			RacerMath.increase(session.treeOffset, BACKGROUND_SPEEDS.Tree * curve * speedPercent, 1)
	end

	session.steer = 0
	if session.input.left then
		session.steer = -1
		session.playerX -= dx
	elseif session.input.right then
		session.steer = 1
		session.playerX += dx
	end
	session.playerX -= dx * speedPercent * curve * 0.3

	if session.input.faster then
		session.speed = RacerMath.accelerate(session.speed, RacerConfig.Accel, dt)
	elseif session.input.slower then
		session.speed = RacerMath.accelerate(session.speed, RacerConfig.Braking, dt)
	else
		session.speed = RacerMath.accelerate(session.speed, RacerConfig.Decel, dt)
	end

	if
		(session.playerX < -1 or session.playerX > 1)
		and session.speed > RacerConfig.OffRoadLimit
	then
		session.speed = RacerMath.accelerate(session.speed, RacerConfig.OffRoadDecel, dt)
	end

	if session.definition.Mode == "final" and (session.playerX < -1 or session.playerX > 1) then
		local roadsideSprite = RacerConfig.roadsideCollisionSprite(
			session.definition.Mode,
			segmentIndex,
			session.playerX
		)
		if roadsideSprite then
			session.speed = RacerConfig.RoadsideCollisionSpeed
			session.position =
				RacerConfig.roadsideCollisionPosition(segmentIndex, playerZ, trackLength)
		end
	end

	if session.definition.Mode == "final" then
		local collisionItem = RacerConfig.trafficCollisionCar(
			trafficItems,
			segmentIndex,
			session.playerX,
			session.speed,
			segmentCount,
			trafficBySegment
		)
		if collisionItem then
			local car = collisionItem.car
			session.speed = car.speed * (car.speed / math.max(session.speed, 1))
			session.position =
				RacerConfig.trafficCollisionPosition(collisionItem.z, playerZ, trackLength)
		end
	end

	local playerXLimit = if session.definition.Mode == "final" then 3 else 2
	session.playerX = RacerMath.limit(session.playerX, -playerXLimit, playerXLimit)
	session.speed = RacerMath.limit(session.speed, 0, RacerConfig.MaxSpeed)

	if session.definition.Mode == "final" then
		local positionDelta = (session.position - startPosition) / RacerConfig.SegmentLength
		session.skyOffset =
			RacerMath.increase(session.skyOffset, BACKGROUND_SPEEDS.Sky * curve * positionDelta, 1)
		session.hillOffset = RacerMath.increase(
			session.hillOffset,
			BACKGROUND_SPEEDS.Hill * curve * positionDelta,
			1
		)
		session.treeOffset = RacerMath.increase(
			session.treeOffset,
			BACKGROUND_SPEEDS.Tree * curve * positionDelta,
			1
		)
	end

	if session.definition.Mode == "final" and session.position > playerZ then
		if session.lapStarted and startPosition < playerZ then
			session.lastLapTime = session.currentLapTime
			session.currentLapTime = 0
			if session.lastLapTime <= session.fastLapTime then
				session.fastLapTime = session.lastLapTime
			end
		else
			session.lapStarted = true
			session.currentLapTime += dt
		end
	end
	publishState(session)
end

local function settingValue(session, settingName: string)
	return session.values[`Setting{settingName}`]
end

local function adjustSetting(player: Player, settingName: string, direction: number)
	local session = findPlayerSession(player)
	if not session then
		return
	end
	local setting = SETTING_DEFAULTS[settingName]
	local valueObject = settingValue(session, settingName)
	if not setting or not valueObject then
		return
	end
	valueObject.Value = math.clamp(
		valueObject.Value + setting.step * math.clamp(direction, -1, 1),
		setting.min,
		setting.max
	)
end

local function resetSettings(player: Player)
	local session = findPlayerSession(player)
	if not session then
		return
	end
	for settingName, setting in SETTING_DEFAULTS do
		local valueObject = settingValue(session, settingName)
		if valueObject then
			valueObject.Value = setting.default
		end
	end
end

local function runLoop()
	local step = RacerConfig.Step
	local accumulator = 0

	RunService.Heartbeat:Connect(function(deltaTime)
		accumulator += math.min(deltaTime, MAX_ACCUMULATED_TIME)

		local steps = 0
		while accumulator >= step and steps < MAX_STEPS_PER_HEARTBEAT do
			for _, session in sessions do
				updateRacer(session, step)
			end
			accumulator -= step
			steps += 1
		end
	end)
end

inputEvent.OnServerEvent:Connect(function(player: Player, inputName: string, isDown: boolean)
	local session = findPlayerSession(player)
	if not session then
		return
	end
	if
		inputName == "left"
		or inputName == "right"
		or inputName == "faster"
		or inputName == "slower"
	then
		session.input[inputName] = isDown
	end
end)

perfLogEvent.OnServerEvent:Connect(function(player: Player, message: string)
	if typeof(message) ~= "string" then
		return
	end

	local safeMessage = string.sub(message, 1, 500)
	local line = `{os.date("!%H:%M:%S")} {player.Name}: {safeMessage}`
	table.insert(perfLines, line)
	while #perfLines > 80 do
		table.remove(perfLines, 1)
	end
	latestPerfLog.Value = line
	perfHistory.Value = table.concat(perfLines, "\n")
	print(`[RacerPerf] {line}`)
end)

actionEvent.OnServerEvent:Connect(
	function(player: Player, actionName: string, settingName: string?, direction: number?)
		if actionName == "Exit" then
			exitScreen(player, "Screen ready.")
		elseif actionName == "Rejoin" then
			rejoinPlace(player)
		elseif actionName == "Setting" and settingName and direction then
			adjustSetting(player, settingName, direction)
		elseif actionName == "ResetSettings" then
			resetSettings(player)
		end
	end
)

local function setupPlayer(player: Player)
	local leaderstats = Instance.new("Folder")
	leaderstats.Name = "leaderstats"
	leaderstats.Parent = player

	local speed = Instance.new("IntValue")
	speed.Name = "Speed"
	speed.Value = 0
	speed.Parent = leaderstats

	player:SetAttribute("Activity", "RacerLab")
	player:SetAttribute("RacerMode", "Spectating")
	player:SetAttribute("RacerScreenId", "")
	player.CharacterAdded:Connect(function(character)
		task.wait(0.1)
		character:PivotTo(SPAWN_CFRAME)
		if findPlayerSession(player) then
			exitScreen(player, "Run reset after respawn.")
		end
	end)
end

Players.PlayerRemoving:Connect(function(player)
	local session = findPlayerSession(player)
	if session then
		session.activePlayer = nil
		resetRun(session)
		session.values.Status.Value = `{session.definition.Name} ready.`
	end
end)

task.spawn(function()
	while true do
		for _, player in Players:GetPlayers() do
			local session = findPlayerSession(player)
			local leaderstats = player:FindFirstChild("leaderstats")
			local speed = leaderstats and leaderstats:FindFirstChild("Speed")
			if speed and speed:IsA("IntValue") then
				speed.Value = if session then 5 * math.round(session.speed / 500) else 0
			end
		end
		task.wait(0.2)
	end
end)

buildLab()
for _, session in sessions do
	publishState(session)
end
Players.PlayerAdded:Connect(setupPlayer)
for _, player in Players:GetPlayers() do
	setupPlayer(player)
end
runLoop()
