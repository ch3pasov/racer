#!/bin/bash
set +x
set +a
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Racer container refuses to bootstrap tools as root." >&2
  exit 1
fi

if [[ -z "${HOME:-}" || "${HOME}" != /* ]]; then
  echo "Racer container requires an absolute non-root HOME." >&2
  exit 1
fi

AFTMAN_HOME="${HOME}/.aftman"
if [[ -L "${AFTMAN_HOME}" || ! -d "${AFTMAN_HOME}" || ! -O "${AFTMAN_HOME}" || ! -w "${AFTMAN_HOME}" ]]; then
  echo "Racer tool volume is not owned and writable by the container user; follow the README migration." >&2
  exit 1
fi

/usr/bin/env -u ROBLOX_API_KEY -u RACER_PUBLISH_API_KEY /usr/local/bin/aftman install --no-trust-check
exec "$@"
