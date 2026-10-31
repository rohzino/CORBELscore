#!/bin/bash
# ---------------------------------------------------------------------------
#  CORBELscore launcher for macOS (Apple Silicon and Intel)
#
#    ./CORBELscore.command               run CORBELscore (sets itself up the first time)
#    ./CORBELscore.command game.corbel   run and open a project
#    ./CORBELscore.command test          run the test suite and a check of the app window
#    ./CORBELscore.command update        download the runtime again
#
#  CORBELscore runs on Electron. The first run downloads it (about 100 MB) from
#  GitHub into the runtime folder and checks its SHA-256 before using it.
#  Nothing is installed on the computer; delete the folder to remove it.
# ---------------------------------------------------------------------------
set -u
cd "$(dirname "$0")" || exit 1
HERE="$PWD"
RT="$HERE/runtime"

# One version for every launcher: read it from CORBELscore.bat.
EV=$(sed -n 's/^set "EV=\([^"]*\)".*/\1/p' CORBELscore.bat)
[ -n "$EV" ] || { echo "Could not read the Electron version from CORBELscore.bat"; exit 1; }

case "$(uname -m)" in
  arm64)  ARCH=arm64; ESHA=4af51382278d00291dfcda265eddd9bab6e98cebb09f46aadc8438bf606de162 ;;
  x86_64) ARCH=x64;   ESHA=451363b59bb7d2c1c9e0c4baa99106004eaabe724aa21a0c6b4c87469293531a ;;
  *) echo "Unsupported processor: $(uname -m)"; exit 1 ;;
esac
EZIP="electron-v$EV-darwin-$ARCH.zip"
EURL="https://github.com/electron/electron/releases/download/v$EV/$EZIP"

setup() {
  echo "Setting up CORBELscore for the first time."
  echo "Downloading Electron $EV ($ARCH) from GitHub (about 100 MB)..."
  local tmp zip got
  tmp=$(mktemp -d) || return 1
  zip="$tmp/$EZIP"
  if ! curl -L --fail --progress-bar -o "$zip" "$EURL"; then
    echo; echo "Could not download $EURL"; echo "Check the internet connection and run this again."
    rm -rf "$tmp"; return 1
  fi
  echo "Checking the download..."
  got=$(shasum -a 256 "$zip" | cut -d' ' -f1)
  if [ "$got" != "$ESHA" ]; then
    echo; echo "The download does not match the expected SHA-256 and was not used."
    echo "  expected $ESHA"; echo "  got      $got"
    rm -rf "$tmp"; return 1
  fi
  echo "Unpacking..."
  rm -rf "$RT"; mkdir -p "$RT"
  # ditto keeps the symlinks the Electron framework depends on.
  ditto -x -k "$zip" "$RT" || { rm -rf "$tmp" "$RT"; return 1; }
  rm -rf "$tmp"
  xattr -dr com.apple.quarantine "$RT" 2>/dev/null
  echo "$EV" > "$RT/version"
  echo "Ready."
}

[ "${1:-}" = "update" ] && rm -rf "$RT"
if [ ! -x "$RT/Electron.app/Contents/MacOS/Electron" ] || [ "$(cat "$RT/version" 2>/dev/null)" != "$EV" ]; then
  setup || { echo; echo "CORBELscore could not start. See the message above."; exit 1; }
fi
ELECTRON="$RT/Electron.app/Contents/MacOS/Electron"

case "${1:-}" in
  test)
    echo "Running the test suite..."
    ELECTRON_RUN_AS_NODE=1 "$ELECTRON" --test
    UNIT=$?
    echo; echo "Checking the app window, pictures and shortcuts..."
    export CORBEL_SMOKE="${TMPDIR:-/tmp}/corbelscore-check"
    rm -rf "$CORBEL_SMOKE"
    "$ELECTRON" .
    SMOKE=$?
    echo "Pictures from the check are in $CORBEL_SMOKE"; echo
    if [ $UNIT -eq 0 ] && [ $SMOKE -eq 0 ] && ! grep -q '^FAIL' "$CORBEL_SMOKE/report.txt" 2>/dev/null; then
      echo "All checks passed."; exit 0
    fi
    echo "Some checks FAILED - see above."; exit 1 ;;
  update) shift ;;
esac

exec "$ELECTRON" . "$@"
