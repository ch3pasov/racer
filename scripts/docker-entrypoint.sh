#!/bin/bash
set +x
set +a
set -euo pipefail

/usr/bin/env -u ROBLOX_API_KEY -u RACER_PUBLISH_API_KEY /usr/local/bin/aftman install --no-trust-check
exec "$@"
