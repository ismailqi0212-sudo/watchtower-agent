#!/bin/bash
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/demo_runner.sh"
