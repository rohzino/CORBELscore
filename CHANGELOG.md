# Changelog

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
- **Logic tab and Live data tab.**
- **Plan for an OBS plugin:** [docs/obs-plugin.md](docs/obs-plugin.md).

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
