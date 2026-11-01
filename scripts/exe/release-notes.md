**CORBELscore 2.0.0-alpha.6**, a live broadcast scoring solution built on TeleScore.

## Download
**CORBELscore.exe** below is the whole program in one file for Windows 10 or 11 (64-bit). There is no installer and no administrator rights are needed.

1. Download `CORBELscore.exe` and double-click it.
2. The first run unpacks to `%LOCALAPPDATA%\CORBELscore`. A small "Setting up CORBELscore" window shows for a few seconds. After that it starts straight away.
3. The file isn't code-signed yet, so Windows SmartScreen may say it "protected your PC". Choose **More info → Run anyway**.

A newer `CORBELscore.exe` replaces the old unpacked copy by itself.

### Mac
**`CORBELscore-<version>-mac-arm64.dmg`** is for Apple Silicon (M1 and later) and **`CORBELscore-<version>-mac-x64.dmg`** for Intel Macs. It needs macOS 13 or later.

1. Open the disk image and drag **CORBELscore** onto **Applications**.
2. Open CORBELscore. macOS says **"CORBELscore" Not Opened**, because the app is not notarised yet. Click **Done**.
3. Open **System Settings → Privacy & Security**, scroll to **Security** ("CORBELscore" was blocked to protect your Mac) and click **Open Anyway**. Right-click → Open no longer works on macOS 15 and later.

See [docs/macos.md](https://github.com/rohzino/CORBELscore/blob/main/docs/macos.md) for what is different on a Mac.

## What's new
- **Pop-out windows.** Control and View can each move into a window of their own: any size, on any screen, with **Always on top**. Everything in the window scales with it (Fit), or choose 50% to 200% yourself.

See [CHANGELOG.md](https://github.com/rohzino/CORBELscore/blob/main/CHANGELOG.md) for everything since the first alpha.

## Known
- This is an alpha. It has passed the automated tests and the desktop self-check on Linux, but it hasn't been run on Windows yet. Please report anything odd as an issue.
