# Changelog

## 2.0.0a3 (unreleased)

### Changed
- **Rebuilt on Electron and JavaScript.** One runtime for the engine, outputs, live data and window; no Python, PyQt or Node to install. `TeleScore.bat` downloads Electron 44.9.3 from GitHub on first run, checks its SHA-256 and runs it from a `runtime` folder. `TeleScore.bat build` makes a portable `TeleScore.exe` folder.
- **Two tabs instead of three.**
  - **Control**, with an Edit / Locked switch. Locked runs the game with the controls full width. Edit adds the Library (Fields, Shortcuts, Live data, Outputs) on the left and Properties on the right, around a layout you arrange.
  - **View**: Graphics (the designer, with Logic and Animations beside the canvas) and Live view.
- **Your own control layout.** Controls sit on a 24-column grid, on pages you name (Game, Teams, …). Drag from the Library, move, resize, use the keyboard; other controls move aside. Templates and older projects get a sensible layout to start from.
- **Buttons are now Shortcuts** and belong to the project, not to panels. Place one on any page as a button, give it a key, or both.
- A blank project opens straight into Edit mode with the Library showing.
- **Live data connects only when you press Connect**, never on its own when a project opens or a setting changes. While connected, a changed setting shows "Reconnect to use them"; Disconnect stops it.
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
