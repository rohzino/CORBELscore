#!/bin/bash
# Builds CORBELscore.app for one processor type and packages it as a .dmg and a .zip.
# Only tools that come with macOS: ditto, PlistBuddy, codesign, iconutil, hdiutil, shasum, lipo.
#
#   scripts/mac/build.sh --electron electron-v44.9.3-darwin-arm64.zip [--out dist]
#
# The Electron zip comes from https://github.com/electron/electron/releases (the
# version in CORBELscore.bat); its SHA-256 is checked. The app is signed ad hoc, which
# Apple Silicon needs to run it at all; it is not notarised (that needs an Apple
# Developer account), so macOS asks you to allow it once. See docs/macos.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PB=/usr/libexec/PlistBuddy
BUNDLE_ID="io.github.rohzino.corbelscore"
ZIP="" ; OUT="$ROOT/dist"
while [ $# -gt 0 ]; do
  case "$1" in
    --electron) ZIP="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "Usage: $0 --electron electron-vX-darwin-<arm64|x64>.zip [--out dist]"; exit 2 ;;
  esac
done
[ -f "$ZIP" ] || { echo "Missing Electron zip. Usage: $0 --electron electron-vX-darwin-<arm64|x64>.zip [--out dist]"; exit 2; }
ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"

EV=$(sed -n 's/^set "EV=\([^"]*\)".*/\1/p' "$ROOT/CORBELscore.bat")
case "$(basename "$ZIP")" in
  "electron-v$EV-darwin-arm64.zip") ARCH=arm64; WANT=4af51382278d00291dfcda265eddd9bab6e98cebb09f46aadc8438bf606de162 ;;
  "electron-v$EV-darwin-x64.zip")   ARCH=x64;   WANT=451363b59bb7d2c1c9e0c4baa99106004eaabe724aa21a0c6b4c87469293531a ;;
  *) echo "Expected electron-v$EV-darwin-arm64.zip or electron-v$EV-darwin-x64.zip, got $(basename "$ZIP")"; exit 2 ;;
esac

# 1. Check the zip.
GOT=$(shasum -a 256 "$ZIP" | cut -d' ' -f1)
if [ "$GOT" != "$WANT" ]; then
  echo "$(basename "$ZIP") does not match the expected SHA-256."; echo "  expected $WANT"; echo "  got      $GOT"; exit 1
fi

# Versions, built the same way as scripts/exe/build.py: 2.0.0-alpha.5 -> 2.0.0 and 2.0.0.5.
VER=$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$ROOT/package.json" | head -1)
SHORT="${VER%%-*}"
NUMS="$SHORT.${VER##*.}"
[ "$VER" = "$SHORT" ] && NUMS="$SHORT.0"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/CORBELscore.app"

# 2. Unpack with ditto (it keeps the symlinks the Electron framework needs) and rename.
echo "Unpacking $(basename "$ZIP")..."
ditto -x -k "$ZIP" "$STAGE/unzip"
mv "$STAGE/unzip/Electron.app" "$APP"
C="$APP/Contents"

# 3. Rename the executable and the helpers, as electron-packager does: Electron finds its
#    helpers by the main executable's name.
mv "$C/MacOS/Electron" "$C/MacOS/CORBELscore"
for suffix in "" " (GPU)" " (Renderer)" " (Plugin)"; do
  old="Electron Helper$suffix"; new="CORBELscore Helper$suffix"
  mv "$C/Frameworks/$old.app" "$C/Frameworks/$new.app"
  mv "$C/Frameworks/$new.app/Contents/MacOS/$old" "$C/Frameworks/$new.app/Contents/MacOS/$new"
  id="$BUNDLE_ID.helper"; case "$suffix" in " (GPU)") id="$id.GPU" ;; " (Renderer)") id="$id.Renderer" ;; " (Plugin)") id="$id.Plugin" ;; esac
  hp="$C/Frameworks/$new.app/Contents/Info.plist"
  for kv in "CFBundleExecutable:$new" "CFBundleName:$new" "CFBundleDisplayName:$new" "CFBundleIdentifier:$id"; do
    k="${kv%%:*}"; v="${kv#*:}"
    $PB -c "Set :$k $v" "$hp" 2>/dev/null || $PB -c "Add :$k string $v" "$hp"
  done
done

# 4. The main Info.plist.
IP="$C/Info.plist"
setp() { $PB -c "Set :$1 $2" "$IP" 2>/dev/null || $PB -c "Add :$1 ${3:-string} $2" "$IP"; }
setp CFBundleName CORBELscore
setp CFBundleDisplayName CORBELscore
setp CFBundleExecutable CORBELscore
setp CFBundleIdentifier "$BUNDLE_ID"
setp CFBundleShortVersionString "$SHORT"
setp CFBundleVersion "$NUMS"
setp CFBundleIconFile icon.icns
setp NSHumanReadableCopyright "AGPL-3.0. Built on TeleScore by the JumpShot team."
setp LSApplicationCategoryType public.app-category.video
setp NSHighResolutionCapable true bool
# LSMinimumSystemVersion stays as Electron ships it.
# CORBELscore uses no camera, microphone, Bluetooth or location: drop Electron's placeholder strings.
for k in $(plutil -p "$IP" | sed -n 's/^ *"\(NS[A-Za-z]*UsageDescription\)".*/\1/p'); do $PB -c "Delete :$k" "$IP"; done
$PB -c "Delete :ElectronAsarIntegrity" "$IP" 2>/dev/null || true   # default_app.asar is removed below

# Project files: .corbel is CORBELscore's, TeleScore's .tsproj opens too (Viewer).
$PB -c "Delete :CFBundleDocumentTypes" "$IP" 2>/dev/null || true
$PB -c "Delete :UTExportedTypeDeclarations" "$IP" 2>/dev/null || true
$PB -c "Add :CFBundleDocumentTypes array" "$IP"
$PB -c "Add :CFBundleDocumentTypes:0 dict" \
    -c "Add :CFBundleDocumentTypes:0:CFBundleTypeName string CORBELscore project" \
    -c "Add :CFBundleDocumentTypes:0:CFBundleTypeRole string Editor" \
    -c "Add :CFBundleDocumentTypes:0:CFBundleTypeIconFile string icon.icns" \
    -c "Add :CFBundleDocumentTypes:0:LSHandlerRank string Owner" \
    -c "Add :CFBundleDocumentTypes:0:CFBundleTypeExtensions array" \
    -c "Add :CFBundleDocumentTypes:0:CFBundleTypeExtensions:0 string corbel" \
    -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes array" \
    -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes:0 string $BUNDLE_ID.project" "$IP"
$PB -c "Add :CFBundleDocumentTypes:1 dict" \
    -c "Add :CFBundleDocumentTypes:1:CFBundleTypeName string TeleScore project" \
    -c "Add :CFBundleDocumentTypes:1:CFBundleTypeRole string Viewer" \
    -c "Add :CFBundleDocumentTypes:1:CFBundleTypeIconFile string icon.icns" \
    -c "Add :CFBundleDocumentTypes:1:LSHandlerRank string Alternate" \
    -c "Add :CFBundleDocumentTypes:1:CFBundleTypeExtensions array" \
    -c "Add :CFBundleDocumentTypes:1:CFBundleTypeExtensions:0 string tsproj" "$IP"
$PB -c "Add :UTExportedTypeDeclarations array" \
    -c "Add :UTExportedTypeDeclarations:0 dict" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeIdentifier string $BUNDLE_ID.project" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeDescription string CORBELscore project" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeIconFile string icon.icns" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeConformsTo array" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeConformsTo:0 string public.json" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeConformsTo:1 string public.data" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification dict" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification:public.filename-extension array" \
    -c "Add :UTExportedTypeDeclarations:0:UTTypeTagSpecification:public.filename-extension:0 string corbel" "$IP"

# 5. The app, the icon.
R="$C/Resources"
cp "$ROOT/app/assets/icon.icns" "$R/icon.icns"
rm -f "$R/default_app.asar" "$R/electron.icns"
mkdir -p "$R/app"
cp "$ROOT/package.json" "$R/app/"
cp "$ROOT/LICENSE" "$R/app/" 2>/dev/null || true
ditto "$ROOT/app" "$R/app/app"
find "$R/app" -name '*.map' -delete
find "$R/app" -name '.DS_Store' -delete

# 6. Sign ad hoc, from the inside out: Apple Silicon kills an unsigned binary.
sign() { codesign --force --sign - --timestamp=none "$@"; }
echo "Signing..."
FW="$C/Frameworks"
find "$FW" -type f -name '*.dylib' -print0 | while IFS= read -r -d '' f; do sign "$f"; done
find "$FW"/*.framework -path '*/Helpers/*' -type f -perm +111 -print0 | while IFS= read -r -d '' f; do sign "$f"; done
for f in "$FW"/*.framework; do sign "$f"; done
for h in "$FW"/*Helper*.app; do sign "$h"; done
sign "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

# 7. Package: a zip of the app, and a disk image with an Applications shortcut.
BASE="CORBELscore-$VER-mac-$ARCH"
rm -f "$OUT/$BASE.zip" "$OUT/$BASE.dmg"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/$BASE.zip"
mkdir "$STAGE/dmg"
ditto "$APP" "$STAGE/dmg/CORBELscore.app"
ln -s /Applications "$STAGE/dmg/Applications"
hdiutil create -quiet -volname "CORBELscore" -srcfolder "$STAGE/dmg" -ov -format UDZO "$OUT/$BASE.dmg"

echo
echo "Architecture: $(lipo -archs "$APP/Contents/MacOS/CORBELscore")"
for f in "$OUT/$BASE.dmg" "$OUT/$BASE.zip"; do
  printf '%s  %s MB  %s\n' "$(basename "$f")" "$(( $(stat -f %z "$f") / 1000000 ))" "$(shasum -a 256 "$f" | cut -d' ' -f1)"
done
