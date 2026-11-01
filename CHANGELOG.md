# Changelog

## CORBELscore 2.0.0a6 (unreleased)

### macOS
CORBELscore now runs on macOS 13 or later, on Apple Silicon and Intel. The Windows and Linux builds are unchanged.
- **Downloads.** `CORBELscore-2.0.0-alpha.6-mac-arm64.dmg` (Apple Silicon) and `…-mac-x64.dmg` (Intel): open the disk image and drag CORBELscore to Applications. The app is signed ad hoc, not notarised, so macOS asks you to allow it once ([docs/macos.md](docs/macos.md)).
- **`CORBELscore.command`** runs, tests and updates CORBELscore from a checkout, like `CORBELscore.bat`. `scripts/mac/build.sh` builds the app and the disk image with the tools that come with macOS.
- **⌘ for app commands.** Save, Save as, Open, New, undo and redo, Pop out, Always on top and the pop-out scale keys use ⌘; keys are shown the Mac way (⌘S, ⌃Space, ⇧, ⌥). Shortcuts stored in a project keep their meaning: Ctrl is the Control key (⌃), so a project moves between Windows and Mac unchanged. **⌘Z / ⌘⇧Z** do what Ctrl+Z / Ctrl+Y do on Windows in the same place: score undo and redo in Locked mode, design undo and redo in Edit mode and Graphics, and the typing in a text box. ⌘1 and ⌘2 switch Control and View, as F1 and F2 do.
- **A menu bar** (CORBELscore, Edit, Window), so ⌘C, ⌘V, ⌘A and ⌘Q work. **About CORBELscore** opens the usual About box.
- **⌘Q and Quit from the Dock** ask "Save changes?" like closing the window, and Cancel keeps CORBELscore open. Pop-outs that were open come back next time.
- **Finder.** Double-clicking a `.corbel` file, or dropping it on the Dock icon, opens it, and asks first if there are unsaved changes. A second launch brings the running window forward.
- **Always on top** floats over another program in full screen (OBS, Safari), and the Dock icon stays. **⌃⌘F** toggles full screen in any window.
- **A Mac icon** on Apple's icon grid (`icon.icns`, rebuilt by `scripts/mac/icon.sh`).

### Fixes
- A project name you are typing no longer loses focus, text or cursor when live data, the files or the web server change the header.

## CORBELscore 2.0.0a5 (28 October 2026)

### Pop-out windows
- **Pop out** (Ctrl + Shift + P) moves Control or View into a window of its own. Resize it to any size, down to 320 × 200, and put it on any screen. The main window marks the tab with ↗ and shows where it went, with **Show the window** and **Put it back**; it switches to the other panel if that one is still here.
- **Always on top** (Ctrl + Shift + T) keeps a pop-out in front of other programs, such as OBS or vMix.
- **Fit** scales everything in a pop-out with its window, text and buttons included: a locked control page fits the window without scrolling (50% to 150%), and Edit mode and View shrink to fit (down to 50%). **−** and **+** (Ctrl + − and Ctrl + =) choose a size yourself, from 50% to 200%; Ctrl + 0 goes back to Fit. Each window keeps its own scale; the main window is never affected.
- Each pop-out remembers its size, place, scale and Always on top. One that was open when CORBELscore closed opens again next time, back on the main screen if its display has gone.
- **Put back**, or closing the window, returns the panel to the main window.
- Background shortcuts stay off while any CORBELscore window has focus, so a key pressed in a pop-out scores once.
- Shortcut buttons on short tiles keep their label and key apart: the key moves beside the label, or the label keeps to one line.

## CORBELscore 2.0.0a4 (26 October 2026)

TeleScore is now **CORBELscore**, built on TeleScore's engine, outputs and project format.

### Sharing
- **`CORBELscore.exe`**: the whole program in one file. The first run unpacks it to `%LOCALAPPDATA%\CORBELscore` behind a small "Setting up" window; later runs start at once, and a newer file replaces the old copy. The file and the program inside it carry CORBELscore's icon and version. Built by `scripts/exe/build.py` with Go and Python only.
- The computer's fonts are loaded as CORBELscore starts, so the designer's font list is complete straight away.

### Brand
- New name, wordmark (**CORBEL**score at 91% opacity), tagline lockup and app icon (a corbel: three courses stepping out), as outline SVGs in `app/assets/brand/`, rebuilt by `scripts/brand/build.py`.
- New design system ([docs/design-system.md](docs/design-system.md)): Basalt, Limestone (Pantone P 179-1 U), Patina, Brass and Terracotta. Two schemes, Basalt (dark) and Limestone (light), replace the old ones; a saved old scheme falls back to Basalt.
- Red Hat Text, Display and Mono ship with the app and replace Archivo in the window and the templates (Archivo stays for older graphics).
- Projects save as `.corbel`; TeleScore `.tsproj` files open and keep their name. The nested XML feed is `corbelscore.xml` with a `<corbelscore>` root. The remote-control header is `X-CORBELscore-Token` (`X-TeleScore-Token` still works). The launcher is `CORBELscore.bat`. Settings, including the Sportzcast token, are copied from TeleScore on the first run.

### Graphics editor
- The board is framed like a document in a photo editor: its name and size above it, the pasteboard around it dimmed, optional title- and action-safe guides.
- Easier resizing: whole edges resize, handles have a 24 px target, edges snap to other elements and the board, the size shows while dragging, and a click never nudges. Corners keep the shape of pictures and boards (Shift for the other way).
- Text boxes: **Auto width** (hugs the words and grows from its alignment, like OBS) or **Fixed width** with **Wrap** and **Shrink to fit**. Dragging an edge of Auto text fixes its width. New text starts Auto; a field dropped on a board starts Fixed.
- A **font list** replaces typing: the bundled fonts first, each shown in its own face, then the computer's own fonts on request, or any name typed.
- **Opacity** for every element as a percentage slider, previewed while dragging.
- **Pictures** arrive at their own size; one bigger than the board asks whether to fit it. Picture opens the file picker straight away.
- **Boards inside boards.** Board puts another board inside this one, sized and centred, with an **On air** switch added to the control page. The browser source, projector, previews and PNGs all draw it; a board can never end up inside itself.
- **Split view** shows the live controls under the board, on any page, with a draggable divider.
- One **Arrange** menu (align, distribute, order, duplicate) and one **Show** menu (live values, snapping, safe areas) instead of seven toolbar controls.
- A new board opens straight away when made from the + menu.

### Control
- Tiles resize from their right and bottom edges as well as the corner, following the pointer by half a cell.
- On/off switches show their own words ("On air" / "Off air"); `<key>.on` is published for every on/off field, so "show while" works whatever the words.

## TeleScore 2.0.0a3

### Changed
- **Rebuilt on Electron and JavaScript.** One runtime for the engine, outputs, live data and window; no Python, PyQt or Node to install. `TeleScore.bat` downloads Electron 44.9.3 from GitHub on first run, checks its SHA-256 and runs it from a `runtime` folder. `TeleScore.bat build` makes a portable `TeleScore.exe` folder.
- **Two tabs instead of three.**
  - **Control**, with an Edit / Locked switch. Locked runs the game with the controls full width. Edit adds the Library (Fields, Shortcuts, Live data, Outputs) on the left and Properties on the right, around a layout you arrange.
  - **View**: Graphics (the designer, with Logic and Animations beside the canvas) and Live view.
- **Your own control layout.** Controls sit on a 24-column grid, on pages you name (Game, Teams, …). Drag from the Library, move, resize, use the keyboard; other controls move aside. Templates and older projects get a sensible layout to start from.
- **Buttons are now Shortcuts** and belong to the project, not to panels. Place one on any page as a button, give it a key, or both.
- A blank project opens straight into Edit mode with the Library showing.
- **Live data connects only when you press Connect**, never on its own when a project opens or a setting changes. While connected, a changed setting shows "Reconnect to use them"; Disconnect stops it.
- **Choice fields follow live data.** Quarter, half and down now update from a scoreboard that sends numbers (`1` → `1st`, `5` → `OT`) as well as names, and their buttons light up the live option. Before, a number picked the wrong option or showed as a bare number. Ordinal and padded counters keep their look when live.
- **Tenth-second mode from live data.** Live clocks show tenths whenever the scoreboard does (`28.4`, or `ClockMode` `.`), and when the field's Tenths under setting asks, using `FullClock` for the tenths. Whole seconds always match the scoreboard. New `<clock>.tenths` value for graphics.
- Live clocks use the field's own format; the play clock follows `PlayClockStatus`.
- Live on/off fields show their own words (possession `>` → `●`); live text keeps capitals; new **Drop leading zeros** option for text (`06` → `6`), on for Distance in the Football template. Blank team names from the bot keep the typed names.
- Checked against a real football frame from a Sportzcast bot.
- Suggest bindings knows more football names (`YardsToGo`, `YardsToGain`, `DownNumber`, `Qtr`). **Copy all keys** copies what a source sends.
- Status updates and arriving data no longer close a drop-down or interrupt typing in a box. Panels refresh once you leave the box.
- Design undo restores layout and design only; it never rewinds the game.
- Project format 3. Version 2 and 1.x files are converted and saved under a new name.

### New
- Projector windows open full screen on the first display that is not the operator's.
- Background shortcuts switch off while TeleScore has focus, so typing a team name never fires Space.
- A recovery file keeps unsaved work and is offered back after a crash.
- `TeleScore.bat test` runs the full suite plus a check of the app window, PNG output and shortcuts.
- [docs/ui-principles.md](docs/ui-principles.md): the reasoning behind the layout.

### Removed
- The PyQt6 app, its launcher logic, `requirements.txt`, `pyproject.toml` and `TeleScore.spec`.

## 2.0.0a2 (unreleased)

### New
- **Rules, overrides and conditions.** These follow the SportzSuite model and apply to text, XML and JSON as well as graphics:
  - The value pipeline runs override, then live key, then rules, then conditional rules.
  - Condition tests: has value, not equals, greater, less, changes by, changes, contains, empty.
  - Element actions: show (for ms or `*`), show once, hide, colour, fill, font, alternate picture, conditional rule, animate.
  - Field actions: conditional rule, set, pulse, run a button's action.
  - Any action can have a finish action after a delay.
- **Sportzcast live data.** MQTT to the cloud (TLS) or a local ScoreConnect III / Scorelink+, the legacy socket (XML or JSON stream), and LiveXML or JSON files and URLs.
  - Binding suggestions for base-contract and LiveXML names.
  - LIVE, OVERRIDE and WAITING states on Operate cards.
  - A header light that turns amber when the bot goes silent.
  - Tokens kept out of project files.
- **Animations in the builder.** Thirty-one built-ins plus custom recipes. They trigger when an element appears, disappears or changes, or from a condition, and preview on the canvas. Browser sources use a JavaScript copy of the same maths, and tests check that both agree.
- **Three tabs instead of seven.**
  - Operate.
  - Design: Boards, Logic and Animations, switched across the top so the canvas keeps its width.
  - Setup: Fields, Live data, Buttons and Outputs, in a list down the left.

  The Animations editor is a section now, not a pop-up. Button panels are picked from a drop-down above their buttons.
- **Plan for an OBS plugin:** [docs/obs-plugin.md](docs/obs-plugin.md).
- **Windows launcher** (`TeleScore.bat`). It sets up its own Python environment, and picks a 64-bit Python that PyQt6 supports.

### Fixed
Found on the first real Windows run:
- Green buttons inside panels had lost their fill and showed dark text on dark. This affected Connect, Suggest bindings, Try it, a template's Start and the clock Start/Stop on Operate cards.
- A disabled green button now looks disabled.
- The header said "Saved" for a project that had never been saved.
- The board was drawn thumbnail-sized when Design first opened. It now fits the canvas and keeps fitting until you zoom.
- The inspector no longer runs off the right edge with a sideways scroll bar.
- Operate's button grid spilled sideways and clipped labels such as "Start / stop both". The grid now drops columns when narrow, and a button's shortcut sits in its corner.
- Basketball scores step +1/+2/+3 and football +1/+2/+3/+6 on their cards.
- A remote action the app was too busy to run within two seconds is withdrawn. The 504 then means "not run, safe to retry", so a Stream Deck retry can never score twice.
- Smaller fixes:
  - no stray line above the tabs, and no empty band under the header;
  - the selected table row is no longer striped cell by cell;
  - the Logic "Value" label hides along with its box;
  - list tick-boxes are visible;
  - the canvas hides its scroll bars while fitted.
- `TeleScore.bat test` reported success after a failure when Python exited abnormally. It now reports any non-zero exit code.

## 2.0.0a1

This is a complete rebuild. Version 1.x projects open directly and are converted on the way in.

### New
- **XML output.** Three profiles:
  - nested `telescore.xml`, for XPression and Chyron;
  - flat `vmix.xml`, for vMix data sources;
  - key/value `fields.xml`, which comes with an XSD.

  All three are served over HTTP as well as written to files.
- **JSON output** (`state.json`).
- **Browser source** for every board, with live updates. It works offline using the bundled Archivo font.
- **HTTP remote control** (`/api/action`) for Stream Deck, Companion or any other device, with an optional token.
- **PNG output** for any board.
- **Build tab.** A new scoreboard designer:
  - fixed-size boards;
  - snapping and guides;
  - align, distribute and paint order;
  - copy, paste and duplicate;
  - undo and redo;
  - drag a field onto the board;
  - colours that follow fields;
  - elements that show only while a field is on.
- **Data tab.** Typed fields: counter, text, on/off, choice, clock, penalties and picture. Renaming a field updates every reference.
- **Buttons tab.** Buttons with multi-step actions and shortcuts. They replace the 1.x connection wiring.
- **Undo and redo** for every scoring action.
- **Templates.** Basketball, hockey, soccer, football, volleyball, baseball, a general scoreboard and a blank project.
- **Projector windows** on any display.
- **Recovery** of unsaved work after a crash.
- **Cross-platform shortcuts.** Background shortcuts are optional.
- **Colour schemes.** Keystone Dark, Keystone Light and Rally.

### Fixed
There are 42 findings in all; see [AUDIT.md](AUDIT.md). The most important:
- Clock edits no longer reset or stop a running game clock.
- Clocks no longer skip or repeat seconds, and a pause keeps the fraction already run.
- Penalties follow the game clock and stop during stoppages.
- Output files are replaced atomically, so OBS never shows a blank or half-written value.
- Settings and recent projects are now saved.

### Removed
- The update check over HTTP.
- The unused OCR experiment.
- cx_Freeze. PyInstaller replaces it.
