#!/bin/bash
set -u
PORT="${WATCHTOWER_PORT:-8765}"
PID="$(/usr/sbin/lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | /usr/bin/head -1)"
if [ -n "$PID" ]; then
  /bin/kill "$PID"
  echo "Stopped Watchtower on port $PORT"
else
  echo "Watchtower is not running on port $PORT"
fi
