# Sportzcast live data

Sportzcast reads a venue's scoreboard controller through a ScoreLink, ScoreConnect III or Scorelink+ (a "bot") and republishes the data. TeleScore can take that data and drive any field from it. Rules, overrides and conditions then apply as usual.

Open the **Live data** tab, pick a source, and click **Connect**. When keys start arriving, click **Suggest bindings**, or bind keys by hand.

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
- LiveXML names: `Hscore`, `Vscore`, `Htimeouts`, `Vtimeouts` and `down`.

Anything else can be matched by name, bound by hand, or turned into a new field with **Make a field**.

When a period number is bound to a choice field (1st, 2nd …), the suggestion also adds a rule such as `1=1st|2=2nd|…`, so the outputs show your period names.

A clock bound to `Clock` shows the bot's clock text exactly. `clock.game.running` follows `ClockStatus` (`R` means running).

## While live

- A bound field shows **LIVE** on its control. Its buttons still change the field's own value, which shows again if the bot stops sending that key.
- To put up something else, use **Override** on the field. Click the OVERRIDE chip on the card to return to live.
- The **Live** light in the header turns amber after the silence you set (30 s by default) with no update, and red on errors.
- Reconnection is automatic, with back-off up to 30 s. MQTT delivery is QoS 0, so an occasional dropped update is normal; the next one corrects it.
