# TeleScore 1.0.3 audit

The audit covers JumpShot-Interactive/TeleScore at commit `7a83b91` (9 February 2025): 70 source files and about 5,700 lines. Each finding gives what was wrong, its effect, and how 2.0 handles it. Severity runs from **Air**, which is visible on a broadcast, through **Data**, which loses or corrupts work, and **Ops**, which breaks setup or install, down to **Code**, which affects maintainability.

## Clocks and timing

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 1 | Air | Changing any clock property re-ran `_reconfProperty`, which stopped the clock and reset it to its default time. This happened mid-game. | Settings and the running clock are separate. Editing a clock in Data never touches its value. |
| 2 | Air | The clock used `int(time())` with an unaligned 1000 ms QTimer, so the display could skip or repeat a second. | The value is computed in milliseconds from a monotonic clock whenever it is read. The timer only refreshes the display. |
| 3 | Air | Pausing threw away the fraction already run: stopping at 4.9 s resumed from 4 s. | Stop keeps exact milliseconds (tested). |
| 4 | Air | `startStopClock()` was inverted: it stopped stopped clocks and "started" running ones. | `toggle()` is tested in both directions. |
| 5 | Air | Every penalty had its own free-running timer. Penalties drifted from the game clock and ran through stoppages. | Penalties advance by exactly the time their master clock ran. Clock adjustments do not move them, and extra penalties wait their turn. |
| 6 | Air | Penalty slots were renumbered by re-pointing text files, which cleared and rewrote them, so they flickered. | Slots are values (`home.penalties.1.time`). Outputs change only when a value changes. |
| 7 | Air | The tenths clock cleared the text file at zero but not the label, so the two disagreed. | One formatter feeds every output. |
| 8 | Air | The penalty format list contained a typo, `hh::mm:ss`. | The format engine accepts any pattern. Legacy formats are kept. |
| 9 | Ops | The buzzer re-created a `QMediaPlayer` on every property change and was never released. The reload code also wrote a stray `Buzzer Audio` property. | There is one player per sound file. The buzzer is a saved clock setting. |

## Outputs

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 10 | Air | Text files were truncated and rewritten in place, so OBS could read an empty or partial file and flicker. | Every file is written to a temp file and then replaced. On Windows a held file is retried, then written directly. |
| 11 | Air | Before a folder was chosen, team and penalty outputs wrote to literal `./Output/{}-name-0.txt`. | File names come from field keys. The default folder is `Documents/TeleScore Output/<project>`. |
| 12 | Ops | Output paths were relative to whatever directory TeleScore was started from. | Paths are absolute, with a clear default and an Open folder button. |
| 13 | Ops | All writes ran on the GUI thread, so a slow disk or an antivirus scan stalled the clock display. | A writer thread keeps only the newest snapshot. Bursts collapse to one write. |
| 14 | Data | There was no XML or JSON output. Browser source and remote control were roadmap items. | Three XML profiles (nested, vMix row, key/value with XSD), JSON, a browser source with SSE, an HTTP control API, and PNG per board. |
| 15 | Ops | Renaming a component left its old text file behind and silently changed OBS's path. | Renaming a key updates every reference in the project. |

## Files, settings and start-up

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 16 | Data | Settings and recent projects saved to `required/`, which only the frozen build created. Run from source, the error was swallowed and nothing persisted. | `QSettings` and the platform's app-data folder are used. |
| 17 | Data | The recent list called `popitem()`, which evicted the project just opened rather than the oldest. | The list is newest first and the oldest falls off (12 kept). |
| 18 | Data | `Project.setProperty` read `prop["DIR"]`, which was never written, leaving the output directory `None`. | Removed. Project format 2 has explicit `outputs`. |
| 19 | Data | Project saves wrote in place, so a crash mid-save destroyed the project. | Saves are atomic. A recovery copy is written 3 s after changes and offered at next launch. |
| 20 | Ops | The start screen's "General Template" pointed at `src/resources/premade.json`, which is not in the repository. Opening it reported a corrupted file. | Eight built-in templates are generated in code and tested. |
| 21 | Ops | `os.getlogin()` raises without a controlling terminal, crashing new projects in services and some desktop launches. | `getpass.getuser()` with a fallback. |
| 22 | Ops | Resource names differed in case (`blank.png` against `blank.PNG`), which breaks on case-sensitive file systems. | Assets are referenced by exact name. |
| 23 | Ops | An unhandled exception showed a dialog and then quit the app mid-game. | Errors are logged to `errors.log` and shown, and the app keeps running. |
| 24 | Ops | `QT_DEBUG_PLUGINS=1` was set in release builds, which is noisy and slow. | Removed. |

## Hotkeys

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 25 | Ops | Hotkeys were Windows-only through global pynput hooks, with one listener thread per button. | In-app shortcuts work on every platform. Optional background shortcuts use one listener. |
| 26 | Air | Single-key global hotkeys fired while typing in any other program. | Background shortcuts must use Ctrl, Alt or an F-key. In-app plain keys pause while you type in a box. |
| 27 | Air | Holding a key auto-repeated the hotkey. | Auto-repeat is ignored. |
| 28 | Ops | An invalid hotkey showed a warning, then crashed passing the raw string to `HotKey()`. | Shortcuts are recorded with a key-sequence editor, and clashes are reported. |

## Layout and editor

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 29 | Air | Positions were stored as ratios of the live window size, so layouts drifted with resizing and rounding. | A board is a fixed pixel canvas (1920 × 1080 by default) scaled as a whole. |
| 30 | Ops | State lived inside widgets, so nothing could be exported, previewed or driven remotely without the widget. | A UI-free engine (fields and actions, `app/core`) sits beneath every view and is shared by the service and the window. |
| 31 | Ops | The connection system (`Connection`, handshake packets, A2B and B2A lists) was hard to follow. `emitSignal` raised on unknown types. | Buttons hold plain actions with batches, undo and validation. Errors become operator-readable notices. |
| 32 | Ops | The board background image was reloaded from disk on every paint. | An image cache keyed on file modification time. |
| 33 | Ops | The background colour was read back by parsing the widget's style sheet string. | It is a model property. |
| 34 | Air | The ordinal suffix was wrong for 111–113 and similar numbers. | `ordinal()` is tested, including 11–13 and 111–113. |
| 35 | Ops | The editor had no copy, paste, align, distribute, snapping or reliable undo. | All of these are in the Build tab. |
| 36 | Ops | "Transparent Background" set a widget attribute that was never unset. | Transparency is a fill value. |

## Build and project hygiene

| # | Sev | Finding | 2.0 |
|---|-----|---------|-----|
| 37 | Ops | Python versions disagreed: CI used 3.10, the README asked for 3.11.1 and `setup.py` targeted 3.12. | Python 3.10+; CI matrix covers 3.10, 3.12 and 3.13 on Windows, macOS and Linux. |
| 38 | Ops | `setup.py` crashed on non-Windows systems because `build_exe_options` was undefined. | A PyInstaller spec builds on all three. |
| 39 | Ops | The README's "build" step just ran the app. | The README covers run, test and build separately. |
| 40 | Code | Leftover "GameMaster" naming, `print()` debugging, a bare `except:` in the start menu and a dead `extra/OCR.py`. | Removed. |
| 41 | Code | Tests barely covered behaviour, and one test body was commented out. | 92 tests: engine, logic, live data, files, web server, layout, 1.x import, and the studio window in a real browser. |
| 42 | Ops | `requests` was used without timeouts (update check). | Removed; there is no network dependency. |
