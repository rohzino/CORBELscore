<img src="img/logo.png" alt="TeleScore" width="320">

# TeleScore 2

Open-source scoreboard and live scoring for streams and broadcast. Keep score in one window. The scores go out as text files, XML, JSON, browser sources for OBS and vMix, PNG pictures and a full-screen projector window.

This is a community continuation of [TeleScore](https://github.com/JumpShot-Interactive/TeleScore) by the JumpShot team, rebuilt from the ground up. It is still licensed under the AGPL-3.0. See [AUDIT.md](AUDIT.md) for what was wrong in 1.0.3 and how 2.0 fixes it, and [CHANGELOG.md](CHANGELOG.md) for what is new.

## What it does

- **Operate tab.** Each field gets a card: clocks with Start/Stop, ±1 s and ±1 min, and typed times; score buttons; text, choices, on/off, penalties and pictures. Your own buttons sit beside them with their shortcuts, next to a live preview of any board. Every action can be undone.
- **Build tab.** This is the scoreboard designer. Boards are fixed canvases (1920 × 1080 by default). Drag and resize with eight handles, and elements snap to a grid and to other elements. You can align, distribute, reorder, copy and paste, and undo or redo. Drag a field onto the board to show it. Text shrinks to fit, colours can follow fields such as `{home.color}`, and an element can be shown only while a field is on.
- **Data tab.** Counters, text, on/off, choices, clocks, penalties and pictures. Renaming a field updates every board and button that uses it.
- **Buttons tab.** A button runs one or more actions as one undo step, for example "Next quarter: next period, reset game clock, reset shot clock". Any button can have a keyboard shortcut.
- **Outputs tab.**
  - Text files: one per value, for OBS Text sources.
  - XML for vMix, Ross XPression and Chyron.
  - JSON.
  - A local web server for browser sources, data feeds and remote control (Stream Deck, Bitfocus Companion, any HTTP request).
  - PNG pictures of boards.
- **Projector windows.** Show any board full screen on any display.
- **Templates.** Basketball, hockey, soccer, football, volleyball, baseball, a general scoreboard and a blank project.
- **1.x projects open directly.** They are converted, and the original file is never overwritten.

Clocks keep time in milliseconds from the system clock, so they never drift and a pause keeps the fraction already run. Penalties count down only while their game clock runs.

## Run it

You need Python 3.10 or newer.

```
python -m pip install -r requirements.txt
python -m telescore
```

`pynput` in `requirements.txt` is optional. It only lets shortcuts work while TeleScore is in the background (Settings menu).

## Outputs at a glance

| Output | Where | Use |
|---|---|---|
| Text | `<folder>/text/home.score.txt` … | OBS Text (GDI+/FreeType) "Read from file" |
| `telescore.xml` | file and `http://127.0.0.1:8130/telescore.xml` | XPression DataLinq, Chyron: `/telescore/home/score` |
| `vmix.xml` | file and URL | vMix Data Sources → XML, XPath `//row` |
| `fields.xml` | file and URL | look-ups by key: `//field[@key='home.score']` (schema: `docs/schema/fields.xsd`) |
| `state.json` | file and URL | anything |
| Browser source | `http://127.0.0.1:8130/board/<id>` | OBS / vMix browser input; add `?bg=green` for a chroma key |
| Remote control | `http://127.0.0.1:8130/api/action?do=add&field=home.score&amount=1` | Stream Deck, Companion |
| PNG | `<folder>/images/<board>.png` | systems that load pictures |

The default folder is `Documents/TeleScore Output/<project>`. The web server listens only on this computer unless you allow the network in Outputs. On a network you should set a control token.

### Actions

| `do` | Parameters | What it does |
|---|---|---|
| `add` | `field`, `amount` | Add to a counter (negative subtracts). On a clock, adds seconds. |
| `set` | `field`, `value` | Set any field. Clocks take `12:00`, `45` or `1:30.5`. |
| `reset` | `field` | Reset to the default; a clock goes back to its period length. |
| `toggle`, `start`, `stop` | `field` | Clocks start and stop; `toggle` also flips on/off fields. |
| `adjust` | `field`, `ms` | Add milliseconds to a clock without stopping it. |
| `next`, `prev` | `field` | Step a choice (1st → 2nd) or a counter. |
| `penalty.add` | `field`, `player`, `time` | Add a penalty. |
| `penalty.remove` | `field`, `index` | Remove a penalty. |
| `penalty.clear` | `field` | Remove every penalty. |
| `stop_all` | — | Stop every clock. |
| `undo`, `redo` | — | Undo or redo the last action. |
| `batch` | `actions: [...]` | Run several actions as one undo step. |

## Test

```
python -m unittest discover -s tests -v
```

- **Engine, feeds, XML schema, web server and 1.x import.** These need only the standard library; `lxml` adds the XSD check.
- **`tests/test_overlay_browser.py`.** This renders every template's boards in Chromium, if Playwright is installed.
- **`tests/test_ui_smoke.py`.** This drives the real desktop app offscreen and saves a screenshot of every tab. Set `TELESCORE_SHOTS` to choose the folder.

## Build a standalone app

```
python -m pip install pyinstaller
pyinstaller TeleScore.spec
```

The app is written to `dist/TeleScore/`. Build on each platform you want to ship.

## Project layout

```
telescore/core      engine: fields, clocks, actions + undo, boards, projects, templates, 1.x import  (no Qt)
telescore/outputs   text/XML/JSON writer, web server, browser-source page                            (stdlib only)
telescore/ui        PyQt6 desktop app
tests/              unit, browser and offscreen UI tests
docs/schema         XSD for fields.xml
```

The operator UI follows the Keystone Scorebook design fundamentals:
- a nine-colour scheme derived by recipe;
- flat panels with hairline borders;
- Archivo at heavy weight in capitals for labels;
- tabular figures;
- words on buttons;
- one accent kept for the main action.

It also borrows from Rally: every status is a colour plus a word (RUNNING, LIVE, FAILING). Choose Keystone Dark, Keystone Light or Rally under View → Colours. On-air graphics use their own fixed broadcast palette.

## Credits

TeleScore was created by the JumpShot team: riscyseven, TheLittleDoctor, Fisk31, controldelta, SPCcleveland9035 and Glenn. Version 2 is a community rebuild.

The Archivo font is © The Archivo Project Authors, under the SIL Open Font License 1.1 (`telescore/assets/fonts/OFL.txt`).

Licensed under the [GNU Affero General Public License v3](LICENSE).
