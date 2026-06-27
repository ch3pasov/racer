#!/usr/bin/env bash
set -euo pipefail

: "${ROBLOX_API_KEY:?ROBLOX_API_KEY is required}"

IMAGE_FILE="${1:-assets/racer/textures/racer-sprites-v1.png}"
DISPLAY_NAME="${ROBLOX_TEXTURE_DISPLAY_NAME:-Racer Sprites v1}"
DESCRIPTION="${ROBLOX_TEXTURE_DESCRIPTION:-Original optional texture atlas for Racer Lab.}"

if [[ -n "${ROBLOX_CREATOR_GROUP_ID:-}" ]]; then
  CREATOR_JSON="{\"groupId\":\"${ROBLOX_CREATOR_GROUP_ID}\"}"
elif [[ -n "${ROBLOX_CREATOR_USER_ID:-}" ]]; then
  CREATOR_JSON="{\"userId\":\"${ROBLOX_CREATOR_USER_ID}\"}"
else
  echo "ROBLOX_CREATOR_USER_ID or ROBLOX_CREATOR_GROUP_ID is required" >&2
  exit 2
fi

if [[ ! -f "${IMAGE_FILE}" ]]; then
  echo "Texture atlas not found: ${IMAGE_FILE}" >&2
  exit 2
fi

REQUEST="$(
  DISPLAY_NAME="${DISPLAY_NAME}" \
    DESCRIPTION="${DESCRIPTION}" \
    CREATOR_JSON="${CREATOR_JSON}" \
    python3 -c 'import json, os
print(json.dumps({
  "assetType": "Image",
  "displayName": os.environ["DISPLAY_NAME"],
  "description": os.environ["DESCRIPTION"],
  "creationContext": {
    "creator": json.loads(os.environ["CREATOR_JSON"]),
    "expectedPrice": 0,
  },
}))' \
)"

curl --fail-with-body \
  --request POST \
  --header "x-api-key: ${ROBLOX_API_KEY}" \
  --form "request=${REQUEST};type=application/json" \
  --form "fileContent=@${IMAGE_FILE};type=image/png" \
  "https://apis.roblox.com/assets/v1/assets"
