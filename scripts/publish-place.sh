#!/usr/bin/env bash
set -euo pipefail

: "${ROBLOX_API_KEY:?ROBLOX_API_KEY is required}"
: "${ROBLOX_UNIVERSE_ID:?ROBLOX_UNIVERSE_ID is required}"

PROJECT_FILE="racer.project.json"
OUTPUT_FILE="build/racer.rbxlx"
PLACE_ID="${ROBLOX_RACER_PLACE_ID:-${ROBLOX_PLACE_ID:-}}"

if [[ "${1:-}" != "" ]]; then
  echo "Racer Lab is the only publish target in this repository; run scripts/publish-place.sh without arguments." >&2
  exit 2
fi

: "${PLACE_ID:?ROBLOX_RACER_PLACE_ID or ROBLOX_PLACE_ID is required}"

mkdir -p build
cat > src/shared/GeneratedPlaceIds.lua <<EOF
return {
	LobbyPlaceId = ${ROBLOX_LOBBY_PLACE_ID:-0},
	RacerPlaceId = ${PLACE_ID},
}
EOF

rojo build "${PROJECT_FILE}" --output "${OUTPUT_FILE}"

curl --fail-with-body \
  --request POST \
  --header "x-api-key: ${ROBLOX_API_KEY}" \
  --header "Content-Type: application/xml" \
  --data-binary @"${OUTPUT_FILE}" \
  "https://apis.roblox.com/universes/v1/${ROBLOX_UNIVERSE_ID}/places/${PLACE_ID}/versions?versionType=Published"

echo "Published Racer Lab place ${PLACE_ID} in universe ${ROBLOX_UNIVERSE_ID}"
