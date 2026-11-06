#!/bin/bash
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
export WATCHTOWER_BROWSER=safari
exec "$DIR/demo_runner.sh"
