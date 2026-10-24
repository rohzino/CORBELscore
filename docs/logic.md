# Rules, overrides and conditions

TeleScore uses the same three tools as Sportzcast's SportzSuite designer. The difference is where they apply. In SportzSuite they change a graphic. In TeleScore they also change what goes into the **text files, XML and JSON**, because those outputs are what most productions read.

## The value pipeline

Every field's published value is worked out in this order. The first step that applies wins.

| Step | Where you set it | Example |
|---|---|---|
| 1. **Override** | Setup → Fields → Override, or click the OVERRIDE chip on an Operate card to turn it off | `HALFTIME` |
| 2. **Live key** | Setup → Fields → Live key, or Setup → Live data → bind | the bot's `HomeScore` |
| 3. **Rules** | Setup → Fields → Rules | `0:00=FINAL\|2:00=Two-minute warning` |
| 4. **Conditional rules** | Design → Logic, a condition whose action is "Conditional rule" | `1=Joe\|2=John` while `half` is `T` |
| 5. The field's own value | Operate, buttons, remote control | `3` |

All outputs get the result: text files, the XML profiles, `state.json`, browser sources, projector windows and PNGs. The **Now** column in Setup → Fields shows the published result, and `state.json` carries both.

A rule beats a conditional rule, as it does in SportzSuite. An override beats everything; SportzSuite's docs don't say how its overrides rank, so this ordering is TeleScore's choice.

## Rules

Write a rule as `bot value=shown value`, and join several rules with `|`:

```
0.0=Final|2:00=Two-minute Warning!
```

TeleScore adds a few things SportzSuite doesn't document:

| Write | Means |
|---|---|
| `NULL=—` | an empty value shows an em dash |
| `0:0*=UNDER 10` | `*` matches any characters and `?` matches one |
| `1={value}st` | `{value}` puts the original value back in |
| `a\=b=c\|d` | `\=` and `\|` are a literal `=` and `\|` |

Board elements can have their own rules too (Design → Boards → inspector → Rules and motion). Element rules change only that graphic, never the files.

## Conditions

> If **field** **test** **value** then **target** **action** **argument**

### Tests

| Test | Meaning |
|---|---|
| has value | Equals the value (SportzSuite "has value"). `NULL` means empty. |
| does not have value | The converse of has value. |
| is greater than / is less than | Compares numbers. Times such as `2:00` or `34.5` compare as seconds. |
| changes by | The new value minus the old one equals this amount; `-1` catches a time-out being used. |
| changes | Any change at all. |
| contains, is empty, is not empty | Text tests. |

A condition is checked when its field's value changes, and once when the project opens. SportzSuite evaluates new bot data the same way. A field can be any published key, sub-keys included, such as `clock.game.running` or `home.penalties.1.time`.

### Element actions (graphics)

| Action | Argument |
|---|---|
| Show, Hide | Milliseconds, or `*` for "until another condition changes it". |
| Show once | Like Show, but it fires only when the condition becomes true. |
| Change colour | Text colour for text, fill for a box. Takes a colour or a field such as `{home.color}`. |
| Change fill, Change font | A colour; a font family. |
| Alternate picture | A file, or a field. |
| Conditional rule | Rules for that element while the condition holds. |
| Animate | Any animation, built in or your own. |

### Field actions (reach .txt and .xml)

| Action | What it does |
|---|---|
| Conditional rule | The rules apply to the field while the condition holds. |
| Set value | Sets the field. This is not an undo step. |
| Pulse on | Switches an on/off field on for a time, then off. Use it for "flash the goal graphic" flags that a CG system reads from XML. |
| Run action | Runs a button's action, e.g. "Next period" when the clock reaches 0:00. |

Every condition can also have a **finish**: N ms later, run another action. Examples are `hide`, `show`, `animate:<name>`, or `set:<value>` for fields. SportzSuite's timeout swap is built this way: tween out, then 4000 ms later tween back in.

### Patterns

- **Show and hide a flag.** Use a converse pair: `flag has value F → show *` and `flag does not have value F → hide *`.
- **Batter names per team.** Use two conditional rules on `atbat`, switched by `half` = `T` or `B`.
- **FINAL at the end.** Use `clock.game has value 0:00 → field clock.game, conditional rule 0:00=FINAL`. A plain rule on the field (`0:00=FINAL`) does the same with less work.
- **Goal flash for a CG system.** Use `home.score changes → field home.flash pulse 3000`. The CG system reads `home.flash` from `fields.xml`.

Conditions work on the values that come out of the pipeline. A conditional rule switched on by one condition can therefore trigger another condition. TeleScore lets a single update go three steps deep, so loops stop.
