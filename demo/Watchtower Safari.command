#!/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export WATCHTOWER_ROOT="$ROOT"
export WATCHTOWER_BROWSER=safari
exec "$ROOT/scripts/demo_runner.sh"
