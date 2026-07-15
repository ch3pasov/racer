#!/usr/bin/env bash
set -euo pipefail

aftman install --no-trust-check
exec "$@"
