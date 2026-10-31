# CORBELscore on macOS: test report

Version 2.0.0-alpha.6, branch `feature/macos`, Electron 44.9.3.

## The Mac

| | |
|---|---|
| macOS | 27.0 (build 26A428) |
| Processor | arm64 (Apple Silicon); Intel build run under Rosetta |
| Display | one built-in Liquid Retina XDR display, 3024 × 1964 Retina |
| Tools | git 2.54.0, Node v26.10.0, shasum, ditto, codesign, iconutil, sips, hdiutil, PlistBuddy, xattr, lipo |
| Firewall | on (so the incoming-connections prompt was seen) |

Electron zips checked against `SHASUMS256.txt` of the v44.9.3 release: `electron-v44.9.3-darwin-arm64.zip` `4af51382278d00291dfcda265eddd9bab6e98cebb09f46aadc8438bf606de162` and `electron-v44.9.3-darwin-x64.zip` `451363b59bb7d2c1c9e0c4baa99106004eaabe724aa21a0c6b4c87469293531a`. Both match.

Interactive tests were driven with real key presses and mouse events (System Events and CGEvent), reading the page's state through Electron's debugging port, and checked against window screenshots. Screenshots were taken outside the repo; three that show no personal information are in `docs/img/macos/`.

## Automated (A)

| ID | Result | Notes |
|---|---|---|
| A-01 | PASS | `node --test`: 115 tests, 103 pass, 12 skipped (the Playwright browser tests; Playwright is not installed), 0 fail. 108 before the changes, plus 7 in `test/mac.test.js`. |
| A-02 | PASS | `./CORBELscore.command test`: the unit tests, then the desktop self-check with 32 checks, all PASS (27 original, 4 for opening from Finder, 1 for typing a project name). |
| A-03 | PASS | `test/mac.test.js`: ⌘S saves, ⌘Z is design undo, ⌃Space still matches a project's Ctrl+Space, ⌘Space matches nothing, ⌘Z / ⌘⇧Z also match the template's Ctrl+Z / Ctrl+Y, display strings show ⌘ ⌃ ⇧ ⌥, and Windows strings are unchanged. The tests pass the platform in (`mac` true or false), so they give the same result on every system; they were not run on a Windows machine. |
| A-04 | PASS | Unit test: a queued open-file wins over the command line and `-psn_…` is ignored. Desktop self-check (4 checks): an open from Finder with unsaved changes asks "Save changes?" and leaves the project alone until answered; Cancel keeps it; with nothing unsaved it opens. |
| A-05 | PASS | `scripts/mac/build.sh` for arm64 and x64. arm64: DMG 143 MB `23c0f9cad14531aab4b785a0f444d2dc2010c8a4d158e091a29a8a5d0d828589`, zip 128 MB `5a7607495ab107f2e3fca6ba076ff888a80fc18cf89195c9e1a68ffbbdb0ccd7`. x64: DMG 151 MB `42e852203f148fb7e3d02280dd5e764b7b37ebdcb0eb76a4aa2f34af79c9424a`, zip 135 MB `69a95d98b6f4eaa1477a3c54dc281f667f4b35f3c21dca61d9fe8ee3c4b984ea`. (Rebuilt later for the final commit; the numbers above are from the build tested.) |
| A-06 | PASS | Main and helper plists as specified (name, executable, identifier `io.github.rohzino.corbelscore[.helper…]`, version 2.0.0 / 2.0.0.6, `icon.icns`, copyright, category, `NSHighResolutionCapable`, document types for `corbel` (Editor) and `tsproj` (Viewer), exported type). `LSMinimumSystemVersion` 13.0 as Electron ships it. No `*UsageDescription` keys. No `default_app.asar`. `lipo`: arm64 for the arm64 build, x86_64 for the x64 build, no Intel code in the arm64 app (0 of 14 binaries). |
| A-07 | PASS | `codesign --verify --deep --strict` on both apps: "valid on disk" and "satisfies its Designated Requirement". |
| A-08 | PASS | `spctl --assess --type execute -vv`: "rejected" for both, as expected for ad-hoc signing. It does not say damaged. |
| A-09 | PASS | Packaged arm64 self-check: 32 PASS, 0 FAIL, exit 0. |
| A-10 | PASS | Packaged x64 self-check under Rosetta: 32 PASS, 0 FAIL, exit 0. macOS then warned that Rosetta apps will not open in macOS 28; that is about the Intel build only, and is why `docs/macos.md` tells Apple Silicon users to take the arm64 image. |
| A-11 | PASS / N/A | `CORBELscore.bat` is unchanged. In `scripts/exe` only a version comment and the release notes changed. The Linux build (`build.py --target linux`) is N/A: Go is not installed. |
| A-12 | PASS | Checked on every commit (see the PR): the only matches are the Electron SHA-256 values, the TeleScore credit and the attribution lines. Nothing from `settings.json`, `windows.json`, `runtime/` or `dist/` is staged. |

## Install and first run (B)

| ID | Result | Notes |
|---|---|---|
| G-01 | PASS | The DMG mounts and holds `CORBELscore.app` and an Applications shortcut. The icon was not inspected in the mounted window. |
| G-02 | PASS (last step not run) | A zip downloaded with Safari from a local server is quarantined. Opening it shows **"CORBELscore" Not Opened** (Apple could not verify it is free of malware) with **Move to Trash** and **Done**. **Done**, then System Settings → Privacy & Security → Security shows **"CORBELscore" was blocked to protect your Mac** with **Open Anyway**. Those steps are in the README. Pressing Open Anyway needs the owner's password or Touch ID and was not done. A quarantine flag written by hand with `xattr` did not trigger Gatekeeper on this Mac, so the Safari download was used. |
| G-03 | PASS | First launch: window opens maximised, dark and branded with no white flash; Dock name and menu bar read CORBELscore (menu bar: CORBELscore, Edit, Window). `g03-launch.png` |
| G-04 | PASS | Processes are `CORBELscore` and `CORBELscore Helper (GPU / Renderer / …)`; none is called Electron. No crash reports. |
| G-05 | PASS | Menu bar → About CORBELscore opens the About box: version 2.0.0a6, TeleScore credit and licences. |

## Editing and keys (C)

| ID | Result | Notes |
|---|---|---|
| G-06 | PASS | In the project name box: typing, ⌘A, ⌘C, ⌘X, ⌘V all work. ⌘Z undoes the typing only and ⌘⇧Z redoes it; the score does not change. Re-run on the final build. |
| G-07 | PASS | Edit mode: a tile moved, resized from the edge and from the corner, each undone and redone one step at a time with ⌘Z and ⌘⇧Z; the score did not change. |
| G-08 | PASS | ⌘N opens New project; ⌘S opens the Save sheet suggesting `<name>.corbel` in Documents and the header then says "Saved"; ⌘⇧S and ⌘O open the Save as and Open sheets. |
| G-09 | PASS | Right-click and ⌃-click on a page tab both open Rename / Move left / Move right / Delete page. |
| G-10 | PASS | ⌘1 and ⌘2, and F1 and F2, switch Control and View. |
| G-11 | PASS | Key chips and menus show ⌘N ⌘O ⌘S ⇧⌘S; the project shortcut Ctrl+Space shows as ⌃Space and Ctrl+Z as ⌃Z; the help text reads "⌘Z undoes a layout change". |

## Running a game (D)

| ID | Result | Notes |
|---|---|---|
| G-12 | PASS | Basketball: each score button, ±1 s and ±1 min, quarters 1st to OT, fouls, time-outs, bonus and possession change their value once per click. Re-run on the final build. |
| G-13 | PASS | Space, ⌃Space, R and T each fire once per key press, also inside a pop-out; typing "r" and a space in a text box fires nothing. |
| G-14 | PASS | Locked mode: ⌘Z and ⌘⇧Z move the score one step each, ⌃Z and ⌃Y too, and the Undo button; the layout never changed. This test found that ⌘⇧Z did nothing (the key helper writes modifiers as `Shift+Meta+Z`); fixed, with a test, and re-run on the final build. |
| G-15 | PASS (wav, m4a) | The buzzer plays once when the clock reaches 0:00, for a wav and an m4a file. An mp3 was not tested: there is no mp3 encoder or file here. |
| G-16 | PASS | With "Shortcuts work while CORBELscore is in the background" on and TextEdit in front, Space started and stopped the clock once per press. With CORBELscore in front a key fires once. ⌃Space was not tried while another app was in front, as macOS can use it for input sources. |
| G-17 | PASS | Hockey, Soccer, Football, Volleyball, Baseball, General scoreboard, Blank project and Basketball each open with their controls and no page errors. |

## Windows, pop-outs and displays (E)

| ID | Result | Notes |
|---|---|---|
| G-18 | PASS | ⌘⇧P pops Control out into "CORBELscore · Control"; the main window marks Control ↗ and switches to View. |
| G-19 | PASS (display parts N/A) | The pop-out resized from 320 × 200 to the largest the screen allows: Fit rescales (50% to 99%), nothing is wider than the window and nothing scrolls. Dragging between displays and a non-Retina display are N/A (one display). |
| G-20 | PASS | −, +, ⌘−, ⌘=, ⌘0: the scale moves in 10% steps and Fit returns; the main window stays at 100%. |
| G-21 | PASS | Always on top (button and ⌘⇧T): the pop-out sits above normal windows (window level 3) and over Safari in full screen. Turning it off returns it to level 0. This test failed first: the window stayed behind full-screen Safari. The fix is `setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })` with the plain "floating" level (no higher level needed) and showing the Dock icon again. Re-run on the final build. |
| G-22 | PASS | View pops out and its font list has 192 computer fonts, including Helvetica Neue and Avenir. Adding text and changing its font was tested in the main window (G-29, G-30). |
| G-23 | PASS | Put back, and the red button, return the panel to the main window. |
| G-24 | PASS (display part N/A) | ⌘Q with a pop-out open, then relaunch: the pop-out reopens with Always on top. Its size is saved only once it has been moved or resized. A pop-out left on a disconnected display could not be tried (one display). |
| G-25 | PASS | ⌃⌘F enters and leaves full screen and the layout reflows (949 vs 917 px high). The green button enters full screen. |
| G-26 | PASS | View → Live view → Full screen goes full screen; Esc returns. |
| G-27 | N/A (one display) | With one display the projector opens as a normal 1280 × 720 window; ⌃⌘F makes it full screen and Esc leaves it; closing it leaves the main window alone. Native full screen on a second display could not be tried, so `simpleFullScreen` was not needed or used. |
| G-28 | PASS | Minimise and a click on the Dock icon restore the main window. |

## Graphics designer (F)

| ID | Result | Notes |
|---|---|---|
| G-29 | PASS | Text, Box, a board inside a board, and a picture through the macOS Open panel (a PNG and an SVG) are added; a 4000 × 3000 picture asks "Bigger than the board" and Fit to the board makes it 1440 × 1080. |
| G-30 | PASS (partly) | The font list has the bundled Red Hat fonts first, then the computer's fonts; weight, alignment, opacity slider and Auto / Fixed width are present; the colour control opens the macOS colour panel. Wrap, shrink and the look of every font were not checked one by one. |
| G-31 | PASS (pinch N/A) | Dragging and resizing with the mouse (G-07) and ⌘-scroll zoom in the designer (102% to 237% and back) work and do not zoom the page. A trackpad pinch cannot be sent from the test tools. |
| G-32 | PASS | A condition and an animation can be added; Play animates the canvas. |
| G-33 | PASS | Split view puts the live controls under the board; +2 there scores. |
| G-34 | PASS | The On air switch hides the nested board in the PNG output and shows it again. |

## Outputs (G)

| ID | Result | Notes |
|---|---|---|
| G-35 | PASS | Default folder `~/Documents/CORBELscore Output/Basketball`: text, XML (corbelscore, vMix, fields) and JSON files update within a second of scoring; "Open folder" opens a Finder window on it. |
| G-36 | PASS | The PNG is exactly 1920 × 1080 (not Retina double size) and changes with the score. |
| G-37 | PASS | The browser-source URL follows the score in Safari on a transparent background. |
| G-38 | PASS | Turning on LAN access shows macOS's "accept incoming network connections?" prompt. After the owner pressed Allow, the Mac's own LAN address answered (HTTP 200). No second device was used. |
| G-39 | N/A | OBS is not installed. |

## Files, recovery and data (H)

| ID | Result | Notes |
|---|---|---|
| G-40 | PASS | Opening a `.corbel` from Finder (`open file`): with CORBELscore closed it starts and opens the project; with it open and unsaved changes it asks "Save changes?", Cancel keeps the project. Finder lists the file as a "CORBELscore project" handled by CORBELscore; the icon was not inspected. Run on the final build. |
| G-41 | PASS (by equivalence) | Dropping on the Dock icon sends the same open-file event as `open file`. A drag onto the Dock was not performed. |
| G-42 | PASS | A TeleScore `.tsproj` written from the structure in `test/legacy.test.js` opens, shows "Converted" with its notes, and the original file's SHA-256 is unchanged. |
| G-43 | PASS | Closing the window with unsaved changes: Cancel keeps CORBELscore open; Save saves and quits. Don't save is the same code path as in G-44. |
| G-44 | PASS | ⌘Q asks Save / Don't save / Cancel; Cancel keeps CORBELscore open; Don't save quits. Re-run on the final build. Quit from the Dock menu uses the same quit path and was not clicked separately. |
| G-45 | PASS | After `kill -9`, the start page says "Unsaved work was found" and Restore brings back the project and its score. |
| G-46 | PASS | A second launch (`open -n`) starts no second copy. The running window did not come forward at first; fixed (`app.focus({ steal: true })`) and re-run on the final build. |
| G-47 | PASS | Basalt and Limestone apply to the main window and a pop-out. |
| G-48 | PASS | A JSON file feeds bound fields; nothing connects until Connect; editing the file updates the fields. This test found that a project name being typed lost focus on every status change; fixed (shared fix, with a self-check) and re-run on the final build. |
| G-49 | N/A | Sportzcast needs the owner's account, which was not asked for. |

## Final (I)

| ID | Result | Notes |
|---|---|---|
| F-01 | PASS | A-01, A-02, A-05 to A-09 were re-run on the final code. |
| F-02 | PASS | G-03, G-06, G-12, G-18, G-21, G-40 and G-44 were re-run on the final alpha.6 build installed in Applications. |
| F-03 | PASS | README and `docs/macos.md` read in plain Markdown; the three images are in `docs/img/macos/`. |

## Found and fixed during testing

1. ⌘⇧Z did not redo the score in Locked mode (modifier order). Fixed, with a test.
2. Always on top did not show over a full-screen app. Fixed.
3. A second launch did not bring the running window forward. Fixed.
4. A project name being typed lost focus when live data or outputs changed the header (not Mac-specific). Fixed, with a self-check.

## Not covered

A second display (G-27, the display parts of G-19 and G-24), OBS (G-39), Sportzcast (G-49), an mp3 buzzer, a trackpad pinch, the final Open Anyway confirmation (G-02), logout or shutdown with unsaved changes, the CI workflow (it cannot run before the branch is pushed), and the Linux build.
