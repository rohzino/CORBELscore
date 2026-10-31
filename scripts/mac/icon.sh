#!/bin/bash
# Builds app/assets/icon.icns from app/assets/brand/icon-mac.svg using only macOS tools
# and the Electron runtime (to draw the SVG). Run ./CORBELscore.command once first.
#   scripts/mac/icon.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BRAND="$ROOT/app/assets/brand"
ELECTRON="$ROOT/runtime/Electron.app/Contents/MacOS/Electron"
[ -x "$ELECTRON" ] || { echo "Run ./CORBELscore.command first, to download the runtime."; exit 1; }

"$ELECTRON" "$ROOT/scripts/mac/render-svg.js" "$BRAND/icon-mac.svg" "$BRAND/icon-mac-1024.png" 1024
[ "$(sips -g pixelWidth "$BRAND/icon-mac-1024.png" | awk '/pixelWidth/{print $2}')" = 1024 ] || { echo "The render is not 1024 px wide."; exit 1; }

SET="$(mktemp -d)/icon.iconset"
mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$BRAND/icon-mac-1024.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$BRAND/icon-mac-1024.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o "$ROOT/app/assets/icon.icns"
rm -rf "$(dirname "$SET")"
echo "wrote app/assets/icon.icns ($(wc -c < "$ROOT/app/assets/icon.icns" | tr -d ' ') bytes)"
