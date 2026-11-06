#!/bin/bash
# Stable local demo launcher: starts the API if needed, waits for health,
# then opens a dedicated Chrome app window. No shell PATH assumptions.
set -u
ROOT="${WATCHTOWER_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="${WATCHTOWER_PORT:-8765}"
PY="$ROOT/.venv/bin/python"
LOG_DIR="$ROOT/data/logs"
SERVER_LOG="$LOG_DIR/server.log"
mkdir -p "$LOG_DIR"

show_error() {
  /usr/bin/osascript -e "display dialog \"$1\" buttons {\"好\"} default button \"好\" with title \"Watchtower\" with icon stop" >/dev/null 2>&1 || true
}

if [ ! -x "$PY" ]; then
  show_error "找不到 Python 环境。\\n\\n$PY\\n\\n请在项目目录重新创建 .venv。"
  exit 1
fi
if [ ! -f "$ROOT/web/dist/index.html" ]; then
  show_error "前端尚未构建。\\n\\n请在 web 目录运行 npm run build。"
  exit 1
fi

health_ok() {
  /usr/bin/curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1
}

open_browser() {
  if [ "${WATCHTOWER_BROWSER:-chrome}" = "safari" ]; then
    /usr/bin/open -a Safari "http://127.0.0.1:$PORT/" >/dev/null 2>&1
    return
  fi
  local chrome="/Applications/Google Chrome.app"
  if [ -d "$chrome" ]; then
    # A normal Chrome tab is more reliable than --app mode when Chrome is
    # already running; the server is the part that must be started first.
    /usr/bin/open -a "$chrome" "http://127.0.0.1:$PORT/" >/dev/null 2>&1
  else
    /usr/bin/open "http://127.0.0.1:$PORT/" >/dev/null 2>&1
  fi
}

if health_ok; then
  open_browser
  exit 0
fi

PID="$(/usr/sbin/lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | /usr/bin/head -1)"
if [ -n "$PID" ]; then
  CMD="$(/bin/ps -p "$PID" -o command= 2>/dev/null || true)"
  if printf '%s' "$CMD" | /usr/bin/grep -q "$ROOT"; then
    /bin/kill "$PID" 2>/dev/null || true
    /bin/sleep 1
  else
    show_error "端口 $PORT 被其他程序占用。\\n\\n$CMD"
    exit 1
  fi
fi

cd "$ROOT" || exit 1
: > "$SERVER_LOG"
/usr/bin/nohup "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >>"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(/usr/bin/seq 1 60); do
  if health_ok; then
    open_browser
    exit 0
  fi
  /bin/sleep 0.5
done

show_error "服务启动失败。\\n\\n日志：$SERVER_LOG\\n\\n$(/usr/bin/tail -n 6 "$SERVER_LOG" 2>/dev/null | /usr/bin/tr '\\n' ' ')"
exit 1
