# Sportzcast live data

Sportzcast reads a venue's scoreboard controller through a ScoreLink, ScoreConnect III or Scorelink+ (a "bot") and republishes the data. TeleScore can take that data and drive any field from it. Rules, overrides and conditions then apply as usual.

In Control → Edit, open **Live data**, pick a source, fill in its settings, and click **Connect**. Nothing connects until you do, and changing a setting later never drops or restarts the connection by itself: TeleScore says the settings changed, and **Reconnect** applies them. **Disconnect** stops live data, and bound fields show their own values again. Opening a project does not connect either. When keys start arriving, click **Suggest bindings**, or bind keys by hand.

## Connections

| Source | What TeleScore does | You need |
|---|---|---|
| Sportzcast cloud (MQTT, recommended) | Connects to `score.sportzcast.net:8883` over TLS and subscribes to `bot/<bot>/json`. | The account e-mail, the access token from your sportzcast.net account, and the bot number. The account needs an active licence and the bot assigned to it. |
| ScoreConnect III / Scorelink+ (local MQTT) | Connects to the device on port 1883 and subscribes to `bot/<bot>/json`. No login. | The device's address. Its local MQTT server must be on, on the same network. |
| Sportzcast socket (legacy) | Port 1402: `GT <email> <token>`, then `FB<bot>`, then an XML (`XB`) or JSON (`JB`) stream in STX/ETX frames. | The e-mail, user token and bot number. Sportzcast recommends MQTT instead. |
| LiveXML file or URL | Reads the XML that Sportzcast LiveXML writes, or any XML file or web address, whenever it changes. | The file path or URL. |
| JSON file or URL | The same, for JSON. | The file path or URL. |

TeleScore implements these connections itself in plain JavaScript on Node's built-in TLS and sockets; nothing extra needs installing. Details follow Sportzcast's public docs at docs.sportzcast.net: the MQTT integration, the base contract and TCP sockets (legacy).

**The token is kept out of the project file.** It is stored in this computer's TeleScore settings, so sharing a `.tsproj` never shares your credentials.

## Keys

Every key that arrives is listed with its current value. Nested JSON and XML are flattened with dots, for example `info.Hscore` becomes `Hscore`, and repeated tags become `tag.1` and `tag.2`.

**Suggest bindings** knows these names:
- from Sportzcast's base contract: `HomeScore`, `GuestScore`, `HomeTeamName`, `GuestTeamName`, `Clock` and `ClockStatus`;
- common per-sport names: `Period`, `ShotClock`, `HomeFouls` and others;
- football names: `Quarter`, `Down`, `ToGo`, `YardsToGo`, `Distance`, `PlayClock`, `HomePossession` and `GuestPossession`;
- LiveXML names: `Hscore`, `Vscore`, `Htimeouts`, `Vtimeouts` and `down`.

**Copy all keys** puts every key and its current value on the clipboard, which is the quickest way to see exactly what a bot sends.

Anything else can be matched by name, bound by hand, or turned into a new field with **Make a field**.

A choice field (quarter, half, down) follows live data whether the scoreboard sends a number or a name: `1` shows as `1st`, `5` as the fifth option (`OT`), and `OT`, `ot` or `Q2` match by name or by the number inside. Its buttons light up the live option. Text that matches no option is shown as it came. A counter shown as an ordinal (`2nd`) or padded (`07`) keeps that look when live.

A live clock shows the scoreboard's time in the field's own format, using the scoreboard's whole seconds exactly (`Clock`, e.g. `4:28`) and `FullClock` (`04:28.0`) for tenths.

- **Tenths** show whenever the scoreboard is in tenths mode (`Clock` reads `28.4`, or `ClockMode` is `.`), and also when the field's **Tenths under** setting asks for them near the end. `clock.game.tenths` is `1` while tenths are showing, for graphics that change style in the last minute.
- **Running** follows the clock's own status key when the bot sends one (`PlayClock` follows `PlayClockStatus`), otherwise `ClockStatus` (`R` means running).
- Text that is not a time (`--:--`) is shown as it came.

On/off fields show their own words when live (possession `>` becomes `●`). Text fields keep their capitals setting, and **Drop leading zeros** turns the bot's padded `06` into `6` (on for Distance in the Football template). A blank team name from the bot (it sends spaces) never wipes the name you typed.

## While live

- A bound field shows **LIVE** on its control. Its buttons still change the field's own value, which shows again if the bot stops sending that key.
- To put up something else, use **Override** on the field. Click the OVERRIDE chip on the card to return to live.
- The **Live** light in the header turns amber after the silence you set (30 s by default) with no update, and red on errors.
- Once connected, a lost connection is retried automatically, with back-off up to 30 s. MQTT delivery is QoS 0, so an occasional dropped update is normal; the next one corrects it.
