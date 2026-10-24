# OBS plugin: plan

TeleScore's main outputs are `.txt` and `.xml`, and OBS already reads those, along with the browser source. A dedicated plugin is still worth building later, for four reasons:

1. OBS hotkeys and Stream Deck buttons could trigger TeleScore actions without a browser or HTTP tool.
2. A native "TeleScore Text" source would follow a field key directly, so you no longer pick a file per value.
3. A board could appear as a native source, with no browser source and no Chromium cost.
4. The plugin could show TeleScore's status, LIVE or SILENT, in an OBS dock.

## What TeleScore already provides

Nothing in TeleScore needs to change for a first version. The local web server is the contract:

| Need | Endpoint |
|---|---|
| Current values | `GET /state.json` (values, raw values, types, labels and board effects) |
| Push updates | `GET /events` (Server-Sent Events): `full` on connect, then `diff` with changed keys, and `fx` for effects |
| Field list for a picker | `GET /api/fields` |
| Run an action | `GET /api/action?do=…&field=…` or `POST /api/action` with JSON |
| Board as a picture | `GET /board/<id>` (HTML); PNG output is also written to `images/<board>.png` |
| Authentication | `?token=` or the `X-TeleScore-Token` header, when a control token is set |

## Stage 1: OBS Python script (about a day)

This is a script loaded through Tools → Scripts, with no compiling.

- Settings: TeleScore address (default `127.0.0.1:8130`), token, and a list of `text source ⇐ field key` pairs.
- A timer reads `/state.json` four times a second, or better, a thread reads `/events`. The script sets each text source's `text` setting with `obs_data_set_string` and `obs_source_update`.
- It registers OBS hotkeys named after the project's buttons, from a new `/api/buttons` endpoint (a small addition). Each hotkey POSTs the button's action.
- Limits: it uses OBS's embedded Python, its text sources only, and it can't do custom rendering.

## Stage 2: native C++ plugin (`obs-telescore`)

- **Source "TeleScore Field".** Renders one field's value with OBS's text renderer (FreeType), with font and colour settings. Its value comes from an SSE client on a worker thread, guarded by a mutex.
- **Source "TeleScore Board".** Renders a board natively: the same element model, rules and animations as `core.animation`. The board JSON comes from `/board/<id>.json`, and the animation recipes would need a new `/animations.json` endpoint. It draws with `gs_*` calls.
- **Dock.** Connection status, the LIVE / SILENT / FAILING state from a new `/api/status` endpoint, and the project's buttons.
- **Hotkeys.** One OBS hotkey per TeleScore button, saved per scene collection.
- **Build.** CMake against `obs-studio` libobs; CI for Windows (MSVC), macOS (universal) and Linux.

Endpoints to add when stage 1 starts:
- `/api/buttons` (panels and buttons, with ids and actions);
- `/api/status` (live source state, output lights);
- `/animations.json`.

## Why not now

The text and XML outputs, together with the browser source, already cover OBS. A plugin is convenience on top of them. Building it first would tie TeleScore to one program, while vMix, XPression and Chyron users rely on the XML.
