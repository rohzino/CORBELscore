# CORBELscore on macOS

CORBELscore runs on macOS 13 (Ventura) or later, on Apple Silicon and Intel. It is the same program as on Windows: the engine, the files and the window are shared, and the few Mac differences are listed below.

## Install

Download the disk image for your Mac from [Releases](https://github.com/rohzino/CORBELscore/releases): `CORBELscore-<version>-mac-arm64.dmg` for Apple Silicon, `CORBELscore-<version>-mac-x64.dmg` for Intel. On an Apple Silicon Mac use the arm64 image: the Intel one only runs there through Rosetta, and macOS warns that Rosetta apps will not open in macOS 28.

1. Open the disk image and drag **CORBELscore** onto **Applications**.
2. Open CORBELscore. macOS says **"CORBELscore" Not Opened** (Apple could not verify it is free of malware). Click **Done**.
3. Open **System Settings → Privacy & Security**, scroll to **Security**: **"CORBELscore" was blocked to protect your Mac**. Click **Open Anyway** and confirm with your password or Touch ID.

On macOS 15 and later, right-clicking the app and choosing Open no longer gets past the block; Open Anyway is the way. You do this once per download.

## Signing status

The app is signed **ad hoc** (`codesign --sign -`). That is enough for Apple Silicon to run it, but it is not a Developer ID signature and it is **not notarised**, which is why Gatekeeper asks. Notarising needs an Apple Developer account (US$99 a year). Until then the steps above stay. `spctl --assess` reports "rejected" for the same reason; it does not mean the app is damaged.

What was checked on macOS 27.0 (Apple Silicon): the Gatekeeper dialog and the Open Anyway entry in Privacy & Security are exactly as described above, using a zip downloaded with Safari. The last step, pressing Open Anyway and confirming, needs the owner's password and was not exercised by the tests.

## Differences from Windows

- **⌘ for the app's commands.** Save, Save as, Open, New, undo and redo, Pop out, Always on top and the pop-out scale keys use ⌘; keys are shown the Mac way (⌘S, ⌃Space, ⇧, ⌥). ⌘1 and ⌘2 switch Control and View, as F1 and F2 do (F keys need fn on most Mac keyboards).
- **Project shortcuts keep their meaning.** A shortcut stored in a project as `Ctrl+Space` is the Control key (⌃Space) on a Mac too, so a project moves between Windows and Mac unchanged. ⌘Space is left to Spotlight.
- **Undo.** ⌘Z and ⌘⇧Z do what Ctrl+Z and Ctrl+Y do on Windows in the same place: score undo and redo in Locked mode, design undo and redo in Edit mode and Graphics, and the typing in a text box. A design undo never changes a score, and a score undo never changes the layout. ⌃Z works too, because the template shortcut means Control.
- **Menu bar.** CORBELscore (About, Hide, Quit), Edit (undo, cut, copy, paste, select all) and Window. About CORBELscore opens the same About box as Settings → About.
- **Closing the window quits CORBELscore**, after asking to save. This is deliberate: a closed window should mean nothing is still writing files. ⌘Q and Quit from the Dock ask the same question and Cancel keeps CORBELscore open. Pop-outs that were open come back next time. On logout or shutdown a pending "Save changes?" question holds the logout until it is answered; unsaved work is also kept for recovery.
- **Finder.** Double-clicking a `.corbel` file, or dropping it on the Dock icon, opens it; with unsaved changes it asks first. Starting CORBELscore a second time brings the running window forward.
- **Full screen.** The green button and ⌃⌘F toggle full screen in any window, and Esc leaves a projector window's full screen. Live view → Full screen works as on Windows.
- **Always on top** floats a pop-out over other programs, including over another program in full screen (OBS, Safari). To do that macOS has to treat CORBELscore as a helper app for a moment; CORBELscore shows its Dock icon again straight away.
- **Network.** The first time you allow other computers on the network (Control → Edit → Outputs), macOS asks "Do you want the application CORBELscore to accept incoming network connections?" Choose Allow. Until you do, other devices cannot connect.
- **Where things are.** Settings and pop-out windows live in `~/Library/Application Support/CORBELscore/` (`settings.json`, `windows.json`); settings are copied once from a `TeleScore` folder beside it. The output folder defaults to `~/Documents/CORBELscore Output/<project>`.

## Build

You need only what comes with macOS (and Node 22 or later to run the tests with `node --test`; `./CORBELscore.command test` runs them inside Electron instead).

```
./CORBELscore.command            run from a checkout (downloads the Electron runtime the first time)
./CORBELscore.command test       unit tests, then the desktop self-check (32 checks)
scripts/mac/build.sh --electron electron-v44.9.3-darwin-arm64.zip [--out dist]
```

`build.sh` takes the official Electron zip from <https://github.com/electron/electron/releases> (its SHA-256 is checked), unpacks it with `ditto` (which keeps the framework's symlinks), renames the app and its four helpers to CORBELscore, edits `Info.plist` with PlistBuddy, adds the app and `icon.icns`, signs from the inside out, and writes `dist/CORBELscore-<version>-mac-<arch>.dmg` and `.zip`. It prints each file's size and SHA-256 and the architecture. Build each architecture separately; there is no universal build.

The bundle identifier is `io.github.rohzino.corbelscore`. `.corbel` files are declared as CORBELscore projects (Editor) and TeleScore `.tsproj` files open too (Viewer). No camera, microphone, Bluetooth or location usage strings are declared; CORBELscore uses none of them.

## Icon

`app/assets/icon.icns` is committed. To rebuild it after changing `app/assets/brand/icon-mac.svg`, run `scripts/mac/icon.sh` (it needs the runtime from `./CORBELscore.command`). The grid and sizes are in [design-system.md](design-system.md#icon).

## Tests

[macos-test-report.md](macos-test-report.md) lists every check run on a Mac, with the result of each.
