# CORBELscore design system

A corbel is the stone bracket that steps out of a wall to carry a load. CORBELscore carries the score: quietly, solidly, always in the same place. The names in this system come from the same building trade: Basalt, Limestone, Patina, Brass and Terracotta.

The code is the source of truth. Colours live in `app/ui/js/colors.js` (`PALETTE`, `SCHEMES`, `derive`), type and layout in `app/ui/styles.css`, bundled fonts in `app/core/fonts.js`, brand files in `app/assets/brand/` (rebuilt by `scripts/brand/build.py`). The reasoning behind the layout is in [ui-principles.md](ui-principles.md).

## Brand

### Wordmark

**CORBEL**score: the architectural word in capitals, the product word in lower case, one weight (Red Hat Display 800), no space. Case does the work; never add a second colour, a bold/light split or a space.

- The wordmark always sits at **91% opacity** of its ink. The tagline sits at 100%.
- Ink: Limestone on Basalt (`wordmark.svg`, `lockup.svg`), or Basalt on Limestone (`wordmark-basalt.svg`, `lockup-basalt.svg`). Never on Patina, never on a photo without a Basalt panel behind it.
- Clear space: the height of the capital C on every side. Smallest size: 96 px wide on screen, 20 mm in print.
- The files are outlines (no font needed). Do not retype it.

### Lockup and tagline

The lockup stacks the wordmark over **LIVE BROADCAST SCORING SOLUTION**: Red Hat Text 500, capitals, tracked +0.06 em, sized so the tagline spans exactly the wordmark's width. The gap is 30% of the wordmark's cap height. Use the lockup on the start page, splash screens and anything printed; use the wordmark alone in tight spaces such as the app header.

### Icon

A corbel seen from the side: three courses of stone, each stepping further out than the one below. The top course is Patina, the score the bracket holds up; the others are Limestone, on a Basalt tile with 22% corner radius (`icon.svg`, `icon.ico`, `icon-256.png`, `icon-512.png`).

**On macOS** the same artwork sits on Apple's icon grid instead of filling the canvas: an 824-unit tile centred in a 1024 canvas (100 units of margin), a 185-unit corner radius and a soft drop shadow, so it is not bigger than every other Dock icon. The source is `app/assets/brand/icon-mac.svg`, with `icon-mac-1024.png` rendered from it by `scripts/brand/build.py` (or by `scripts/mac/icon.sh` with the Electron runtime). `scripts/mac/icon.sh` makes `app/assets/icon.icns` from the 1024 px master with `sips` (16, 32, 128, 256 and 512 px, each with an @2x) and `iconutil`. `icon.icns` is committed, so building the app needs no Chromium.

### Credit

CORBELscore is built on TeleScore, the open-source scoring utility by the JumpShot team. Say so in About, the README and anything describing where the software comes from: "Built on TeleScore."

## Colour

Five named colours. Everything else is derived from them by `derive()` and checked for contrast.

| Name | Hex | Use |
|---|---|---|
| Basalt | `#0c0d0d` | The ground: app background, on-air panels, ink on light fills |
| Limestone | `#f5f5f1` | Pantone P 179-1 U. Type and marks on Basalt; the ground of the light scheme |
| Patina | `#4cc9d6` | The one main action, "selected", "you are here", LIVE and RUNNING. Deep: `#0b7380` on Limestone |
| Brass | `#e4b363` | Edit mode, warnings, WAITING and SILENT. Deep: `#9a6512` on Limestone |
| Terracotta | `#ef6a5e` | Errors and destructive actions only. Deep: `#b3261e` on Limestone |

Slate surfaces sit between Basalt and Limestone: `#151717` (panels), `#1e2121` (raised), `#2e3232` (joints and hairlines).

### Schemes

| Token | Basalt (dark, default) | Limestone (light) | Use |
|---|---|---|---|
| `bg` | `#0c0d0d` | `#f5f5f1` | Window ground |
| `panel` | `#151717` | `#fbfbf8` | Sidebars, tiles, cards, dialogs |
| `head` | `#080909` | `#0c0d0d` | Header bar (always dark) |
| `ink` | `#f5f5f1` | `#0c0d0d` | Body text on `bg` and `panel` |
| `muted` | `#b6b7b4` | `#4f504f` | Labels, hints, secondary text |
| `rule` | `#3b3d3c` | `#d2d3d0` | Hairlines between areas |
| `rule-strong` | `#636563` | `#8f908e` | Control borders (3:1 on `panel`) |
| `field` | `#121414` | `#f9f9f6` | Inputs, wells |
| `accent` | `#4cc9d6` | `#0b7380` | Main action fill, LIVE chip, selection bar |
| `accent-ink` | `#0c0d0d` | `#f5f5f1` | Text on `accent` |
| `user` | `#e4b363` | `#9a6512` | Edit band, warnings |
| `alert` | `#ef6a5e` | `#b3261e` | Errors, delete |

Every text pair meets WCAG 4.5:1 in both schemes (Limestone on Basalt is 17.8:1; Patina on `panel` 9.1:1; Deep Patina on Limestone 5.1:1). Status is never colour alone: it is always a colour **and** a word.

### On air

Graphics use their own fixed palette whatever the window's scheme (`ONAIR` in `app/core/presets.js`): Limestone type on Basalt panels at 95%, Patina for the period chip and the accent edge, Brass for the shot clock and the full-screen clock. Team colours default to Patina (away) and Brass (home) and are the operator's to change.

## Type

| Family | Role |
|---|---|
| Red Hat Display (300–900) | The wordmark, numbers (scores, clocks), titles, on-air graphics |
| Red Hat Text (300–700) | Everything you read in the window |
| Red Hat Mono (300–700) | Keys, shortcuts, field keys such as `home.score` |
| Archivo | Kept so TeleScore graphics open unchanged |

All four ship with the app (`app/assets/fonts/`, SIL Open Font License), so a graphic looks the same on every computer and in every browser source. The designer's font list puts them first, then the computer's own fonts.

| Style | Spec | Use |
|---|---|---|
| Score | Red Hat Display 800, 30–132 px, tabular | Values on control tiles |
| Title | Red Hat Display 700, 18 px | Dialog titles, template names (16 px) |
| Project name | Red Hat Display 600, 16 px | Header |
| Body | Red Hat Text 400, 14/20 px | Default |
| Button | Red Hat Text 600, 14 px; 700 for the main action | Buttons |
| Label | Red Hat Text 700, 10.5–12 px, capitals, +0.1 em | Form labels, tile labels, section titles, chips |
| Hint | Red Hat Text 400, 12.5/18 px, `muted` | Explanations under controls |
| Key | Red Hat Mono 500, 11 px | Keyboard shortcuts |

Numbers are always tabular, so digits do not jump while a clock runs.

## Space and shape

- Spacing steps: 4, 6, 8, 12, 16, 24, 32 px. Controls sit 8 px apart; panels pad 12 px; page gutters are 16 px.
- Radius: inputs 4 px, buttons 6 px, panels and tiles 8 px, mode switch 999 px.
- Surfaces are flat with 1 px hairlines. Shadows only on things that float: menus, dialogs, toasts.
- Control layout: a 24-column grid, 40 px rows and 8 px gaps while editing; rows stretch from 30 to 60 px when locked.

## Components

- **Button.** Words, sentence case, verb first ("Open a project…", "Put a board inside"). Plain is the default; **accent** (Patina fill) at most once per view, for what the view is for; **alert** (Terracotta outline) for delete; **ghost** for quiet row actions. 30 px tall (24 px small, 40 px big). Pressed toggles use `aria-pressed` and the accent fill.
- **Chip.** A status word in tracked capitals on its colour: LIVE and RUNNING (Patina), WAITING, SILENT and EDITING (Brass), FAILING (Terracotta), OFF and STOPPED (outline).
- **Mode switch.** Edit | Locked, a pill at the top right of Control. Edit fills Brass and adds the EDITING band and dotted grid; Locked fills Patina.
- **Control tile.** Label in tracked capitals top left, state chip top right, the value in Red Hat Display, then the actions. Sized by the grid; adapts to its own size.
- **Panel.** `panel` ground, `rule` hairline, 8 px radius, 12 px padding, a tracked-capital title.
- **Toast.** Bottom right, Limestone on Basalt (inverted), says what happened in one sentence.
- **Dialog.** A Red Hat Display title that names the decision, one paragraph, and buttons that say what they do ("Fit to the board" / "Keep full size"), never OK/Cancel when a verb fits.

## Writing

- Name things the way an operator does: score, clock, period, on air. Not "field binding" or "payload".
- Buttons are verbs. Labels are nouns. Hints are one plain sentence.
- Say what will happen before it happens, and what happened after ("Copied. In OBS add a Browser source with this address.").
- Errors say what went wrong and how to fix it, without apologising.
- British spelling in the interface: colour, centre.
