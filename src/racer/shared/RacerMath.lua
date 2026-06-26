local RacerMath = {}

function RacerMath.limit(value: number, minValue: number, maxValue: number): number
	return math.max(minValue, math.min(value, maxValue))
end

function RacerMath.accelerate(value: number, acceleration: number, dt: number): number
	return value + acceleration * dt
end

function RacerMath.easeIn(startValue: number, endValue: number, percent: number): number
	return startValue + (endValue - startValue) * percent ^ 2
end

function RacerMath.easeInOut(startValue: number, endValue: number, percent: number): number
	return startValue + (endValue - startValue) * ((-math.cos(percent * math.pi) / 2) + 0.5)
end

function RacerMath.interpolate(startValue: number, endValue: number, percent: number): number
	return startValue + (endValue - startValue) * percent
end

function RacerMath.increase(start: number, increment: number, maxValue: number): number
	local result = start + increment
	while result >= maxValue do
		result -= maxValue
	end
	while result < 0 do
		result += maxValue
	end
	return result
end

function RacerMath.percentRemaining(value: number, total: number): number
	return (value % total) / total
end

function RacerMath.exponentialFog(distance: number, density: number): number
	return 1 / math.exp(distance * distance * density)
end

function RacerMath.overlap(
	x1: number,
	w1: number,
	x2: number,
	w2: number,
	percent: number?
): boolean
	local half = (percent or 1) / 2
	local min1 = x1 - w1 * half
	local max1 = x1 + w1 * half
	local min2 = x2 - w2 * half
	local max2 = x2 + w2 * half
	return not (max1 < min2 or min1 > max2)
end

function RacerMath.project(
	worldX: number,
	worldY: number,
	worldZ: number,
	cameraX: number,
	cameraY: number,
	cameraZ: number,
	cameraDepth: number,
	width: number,
	height: number,
	roadWidth: number
)
	local cameraZDelta = worldZ - cameraZ
	if cameraZDelta <= 0 then
		return nil
	end

	local scale = cameraDepth / cameraZDelta
	return {
		scale = scale,
		x = math.floor(width / 2 + scale * (worldX - cameraX) * width / 2 + 0.5),
		y = math.floor(height / 2 - scale * (worldY - cameraY) * height / 2 + 0.5),
		w = math.floor(scale * roadWidth * width / 2 + 0.5),
		cameraY = worldY - cameraY,
		cameraZ = cameraZDelta,
	}
end

return RacerMath
