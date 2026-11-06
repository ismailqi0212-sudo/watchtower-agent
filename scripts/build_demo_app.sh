#!/bin/bash
# Build a native double-clickable macOS app bundle in demo/Watchtower.app.
# A tiny C launcher avoids AppleScript/automation permissions; the bundle
# stores the absolute project root so Dock launches do not depend on cwd.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/demo/Watchtower.app"
CONTENTS="$APP/Contents"
RES="$CONTENTS/Resources"
MACOS="$CONTENTS/MacOS"
SCRIPT="$ROOT/scripts/demo_runner.sh"

rm -rf "$APP"
mkdir -p "$MACOS" "$RES"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Watchtower</string>
  <key>CFBundleDisplayName</key><string>Watchtower</string>
  <key>CFBundleIdentifier</key><string>local.watchtower.demo</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleSignature</key><string>????</string>
  <key>CFBundleExecutable</key><string>Watchtower</string>
  <key>CFBundleIconFile</key><string>Watchtower</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
printf 'APPL????' > "$CONTENTS/PkgInfo"

cat > /tmp/watchtower_launcher.c <<CLANG
#include <unistd.h>
int main(void) {
  execl("/usr/bin/open", "open", "-a", "Terminal",
        "$ROOT/demo/Watchtower.command", (char *)0);
  return 1;
}
CLANG
/usr/bin/clang -O2 -o "$MACOS/Watchtower" /tmp/watchtower_launcher.c
chmod +x "$MACOS/Watchtower"
rm -f /tmp/watchtower_launcher.c

ICON="$ROOT/docs/assets/app-icon.png"
if [ -f "$ICON" ]; then
  ICONSET="$RES/Watchtower.iconset"
  mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    /usr/bin/sips -z "$size" "$size" "$ICON" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    /usr/bin/sips -z "$double" "$double" "$ICON" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  /usr/bin/iconutil -c icns "$ICONSET" -o "$RES/Watchtower.icns" >/dev/null
  rm -rf "$ICONSET"
fi

/usr/bin/codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "Built $APP"
