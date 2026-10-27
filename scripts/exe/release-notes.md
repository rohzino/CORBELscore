**CORBELscore 2.0.0-alpha.4**, a live broadcast scoring solution built on TeleScore.

## Download
**CORBELscore.exe** below is the whole program in one file for Windows 10 or 11 (64-bit). There is no installer and no administrator rights are needed.

1. Download `CORBELscore.exe` and double-click it.
2. The first run unpacks to `%LOCALAPPDATA%\CORBELscore`. A small "Setting up CORBELscore" window shows for a few seconds. After that it starts straight away.
3. The file isn't code-signed yet, so Windows SmartScreen may say it "protected your PC". Choose **More info → Run anyway**.

A newer `CORBELscore.exe` replaces the old unpacked copy by itself. Settings from TeleScore, including a saved Sportzcast token, are carried over on first run.


## What's new
See [CHANGELOG.md](https://github.com/rohzino/CORBELscore/blob/rebuild/v2/CHANGELOG.md) and pull request #1:
- A new Control tab with Edit / Locked modes
- A new graphics designer: boards inside boards, text boxes, a font list, opacity and split view
- Sportzcast live data, including choice fields and tenth-second clocks
- The CORBELscore brand and design system

## Known
- This is an alpha. It has passed 107 automated tests and the desktop self-check on Linux, but it hasn't been run on Windows yet. Please report anything odd as an issue.
