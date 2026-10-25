// Templates for common sports: fields, a scorebug, a full-screen board, buttons
// and a ready-made control layout.

import { Clock } from "./clock.js";
import { makeBoard, makeElement } from "./board.js";
import { Engine } from "./engine.js";
import { ChoiceField, ClockField, CounterField, ImageField, PenaltyField, TextField, ToggleField } from "./fields.js";
import { autoLayout, makeLayout, makePage } from "./layout.js";
import { makeButton, Project } from "./project.js";

// On-air palette (Keystone Dark brand; always used on air whatever the UI scheme)
export const ONAIR = { ink: "#e8f1ec", panel: "#18211e", head: "#0a0f0d", head95: "#0a0f0df2", accent: "#3ddc84",
  hi: "#5ad1e6", user: "#ffb454", alert: "#ff6b6b", muted: "#a8b5ae", rule: "#34423c" };

function teams({ steps = [1] } = {}) {
  const out = [];
  for (const [side, name, short, color] of [["away", "Away", "AWY", "#5ad1e6"], ["home", "Home", "HOM", "#ffb454"]]) {
    const T = side[0].toUpperCase() + side.slice(1);
    out.push(new TextField(`${side}.name`, { label: `${T} name`, value: name }),
      new TextField(`${side}.short`, { label: `${T} abbreviation`, value: short, uppercase: true }),
      new CounterField(`${side}.score`, { label: `${T} score`, steps }),
      new TextField(`${side}.color`, { label: `${T} colour`, value: color }),
      new ImageField(`${side}.logo`, { label: `${T} logo` }));
  }
  return out;
}

function gameClock({ key = "clock.game", label = "Game clock", minutes = 12, tenths = true, countdown = true, fmt = "m:ss" } = {}) {
  const clock = new Clock({ countdown, initial_ms: countdown ? minutes * 60_000 : 0, fmt,
    tenths_under_ms: tenths && countdown ? 60_000 : 0, tenths_fmt: "s.t" });
  return new ClockField(key, { label, clock });
}

const t = (o) => makeElement({ kind: "text", font: "Archivo", weight: 900, color: ONAIR.ink, tabular: true, fit: true, ...o });
const box = (o) => makeElement({ kind: "box", ...o });

// A one-line scorebug, bottom left, 1920 x 1080 transparent.
function scorebug(extraRight = null, { chip = "{period}", clock = "{clock.game}" } = {}) {
  const x = 60, y = 950, h = 76;
  const els = [
    box({ name: "Panel", x, y, w: 100, h, fill: ONAIR.head95, stroke: ONAIR.rule, stroke_width: 1, radius: 3 }),
    box({ name: "Accent edge", x, y, w: 6, h, fill: ONAIR.accent }),
  ];
  let cx = x + 6;
  for (const side of ["away", "home"]) {
    const T = side[0].toUpperCase() + side.slice(1);
    els.push(box({ name: `${T} colour`, x: cx + 14, y: y + 14, w: 6, h: h - 28, fill: `{${side}.color}` }),
      t({ name: `${T} ID`, text: `{${side}.short}`, x: cx + 28, y, w: 118, h, size: 34, align: "left", uppercase: true, tracking: 0.02 }),
      box({ name: `${T} score box`, x: cx + 150, y: y + 8, w: 86, h: h - 16, fill: ONAIR.panel, radius: 3 }),
      t({ name: `${T} score`, text: `{${side}.score}`, x: cx + 150, y: y + 8, w: 86, h: h - 16, size: 46 }));
    cx += 246;
  }
  els.push(box({ name: "Period chip", x: cx + 12, y: y + 16, w: 84, h: h - 32, fill: ONAIR.accent, radius: 3 }),
    t({ name: "Period", text: chip, x: cx + 12, y: y + 16, w: 84, h: h - 32, size: 26, color: ONAIR.head, uppercase: true }),
    t({ name: "Clock", text: clock, x: cx + 104, y, w: 150, h, size: 44, weight: 800 }));
  if (!clock) { els.pop(); cx -= 154; }      // no clock (baseball): the extras move left
  if (extraRight) els.push(...extraRight(cx + 260, y));
  // The panel hugs its permanent contents; situational tags sit just outside it.
  const rest = els.slice(2);
  const right = Math.max(...rest.filter((e) => !e.show_when).map((e) => e.x + e.w));
  els[0].w = right + 14 - x;
  const tags = rest.filter((e) => e.show_when);
  if (tags.length) {
    const shift = right + 14 + 6 - Math.min(...tags.map((e) => e.x));
    for (const e of tags) e.x += shift;
  }
  return makeBoard({ name: "Scorebug", width: 1920, height: 1080, background: "", elements: els });
}

// A full-screen scoreboard for a projector, TV or LED wall.
function fullScreen({ title = "{period}", clock = "{clock.game}", extras = [] } = {}) {
  return makeBoard({ name: "Full screen", width: 1920, height: 1080, background: "#000000", elements: [
    box({ name: "Away colour", x: 80, y: 120, w: 760, h: 14, fill: "{away.color}", radius: 3 }),
    box({ name: "Home colour", x: 1080, y: 120, w: 760, h: 14, fill: "{home.color}", radius: 3 }),
    t({ name: "Away name", text: "{away.name}", x: 80, y: 150, w: 760, h: 110, size: 84, uppercase: true }),
    t({ name: "Home name", text: "{home.name}", x: 1080, y: 150, w: 760, h: 110, size: 84, uppercase: true }),
    t({ name: "Away score", text: "{away.score}", x: 80, y: 270, w: 760, h: 420, size: 380 }),
    t({ name: "Home score", text: "{home.score}", x: 1080, y: 270, w: 760, h: 420, size: 380 }),
    t({ name: "Clock", text: clock, x: 560, y: 720, w: 800, h: 220, size: 200, weight: 800, color: ONAIR.user }),
    t({ name: "Period", text: title, x: 760, y: 330, w: 400, h: 120, size: 90, color: ONAIR.accent, uppercase: true }),
    ...extras,
  ] });
}

const B = (label, action, o = {}) => makeButton({ label, action, ...o });

function commonButtons(game = "clock.game") {
  return [B("Start / stop clock", { do: "toggle", field: game }, { role: "accent", hotkey: "Space" }),
    B("Undo", { do: "undo" }, { hotkey: "Ctrl+Z" }), { ...B("Redo", { do: "redo" }, { hotkey: "Ctrl+Y" }), place: false }];
}

// Keyboard scoring. The score tiles already have these steps, so these buttons
// are shortcuts only and are not placed on the layout.
function scoreButtons(points = [1]) {
  const keys = { away: ["Q", "W", "E"], home: ["O", "P", "["] };
  const out = [];
  for (const side of ["away", "home"]) {
    const T = side[0].toUpperCase() + side.slice(1);
    points.forEach((p, i) => out.push({ ...B(`${T} +${p}`, { do: "add", field: `${side}.score`, amount: p }, { hotkey: keys[side][i] ?? "" }), place: false }));
    out.push({ ...B(`${T} -1`, { do: "add", field: `${side}.score`, amount: -1 }, { role: "alert" }), place: false });
  }
  return out;
}

function finish(name, sport, fields, boards, buttons) {
  const engine = new Engine(fields);
  const layout = autoLayout(engine.fieldsToList(), buttons);
  const preview = boards[0];
  if (preview) {
    // A live picture of the scorebug, where the Game column leaves room.
    const tiles = layout.pages[0].tiles;
    const colBottom = (a, b) => tiles.filter((x) => x.kind !== "button" && x.text !== "Shortcuts" && overlapsCols(x, a, b)).reduce((m, x) => Math.max(m, x.y + x.h), 1);
    const actions = tiles.find((x) => x.kind === "heading" && x.text === "Shortcuts");
    const y = colBottom(8, 16);
    if (!actions || actions.y - y >= 4) tiles.push({ id: `pv${preview.id}`, kind: "preview", board: preview.id, x: 8, y, w: 8, h: Math.min(5, (actions?.y ?? y + 5) - y) });
  }
  return new Project({ name, sport, engine, boards, buttons: buttons.map(({ place, ...b }) => b), layout });
}
const overlapsCols = (tile, a, b) => tile.x < b && a < tile.x + tile.w;

function basketball() {
  const shot = new Clock({ countdown: true, initial_ms: 24_000, fmt: "s", tenths_under_ms: 5_000, tenths_fmt: "s.t" });
  const fields = [...teams({ steps: [1, 2, 3] }), gameClock({ minutes: 10 }), new ClockField("clock.shot", { label: "Shot clock", clock: shot }),
    new ChoiceField("period", { label: "Quarter", options: ["1st", "2nd", "3rd", "4th", "OT"] }),
    new CounterField("away.fouls", { label: "Away fouls", maximum: 99 }), new CounterField("home.fouls", { label: "Home fouls", maximum: 99 }),
    new CounterField("away.timeouts", { label: "Away time-outs", value: 5, default: 5, maximum: 9 }),
    new CounterField("home.timeouts", { label: "Home time-outs", value: 5, default: 5, maximum: 9 }),
    new ToggleField("away.bonus", { label: "Away bonus", on_text: "BONUS" }), new ToggleField("home.bonus", { label: "Home bonus", on_text: "BONUS" }),
    new ToggleField("possession.home", { label: "Home possession", on_text: "◀" })];
  const bug = scorebug((x, y) => [box({ name: "Shot clock box", x, y: y + 8, w: 70, h: 60, fill: ONAIR.panel, radius: 3 }),
    t({ name: "Shot clock", text: "{clock.shot}", x, y: y + 8, w: 70, h: 60, size: 36, color: ONAIR.user })]);
  const buttons = [...commonButtons(),
    B("Start / stop both", { do: "batch", actions: [{ do: "toggle", field: "clock.game" }, { do: "toggle", field: "clock.shot" }] }, { role: "accent", hotkey: "Ctrl+Space" }),
    B("Shot clock 24", { do: "batch", actions: [{ do: "reset", field: "clock.shot" }] }, { role: "hi", hotkey: "R" }),
    B("Shot clock 14", { do: "set", field: "clock.shot", value: "14" }, { role: "hi", hotkey: "T" }),
    B("Next quarter", { do: "batch", actions: [{ do: "next", field: "period" }, { do: "reset", field: "clock.game" }, { do: "reset", field: "clock.shot" }] }, { role: "user" }),
    ...scoreButtons([1, 2, 3])];
  return finish("Basketball", "basketball", fields, [bug, fullScreen()], buttons);
}

function hockey() {
  const fields = [...teams(), gameClock({ minutes: 20 }),
    new ChoiceField("period", { label: "Period", options: ["1st", "2nd", "3rd", "OT", "SO"] }),
    new CounterField("away.shots", { label: "Away shots", maximum: 999 }), new CounterField("home.shots", { label: "Home shots", maximum: 999 }),
    new PenaltyField("away.penalties", { label: "Away penalties", master: "clock.game", slots: 2 }),
    new PenaltyField("home.penalties", { label: "Home penalties", master: "clock.game", slots: 2 }),
    new ToggleField("away.pp", { label: "Away power play", on_text: "PP" }), new ToggleField("home.pp", { label: "Home power play", on_text: "PP" })];
  const bug = scorebug((x, y) => [box({ name: "Power play", x, y: y + 16, w: 80, h: 44, fill: ONAIR.user, radius: 3, show_when: "home.pp" }),
    t({ name: "Power play text", text: "PP {home.penalties.1.time}", x, y: y + 16, w: 80, h: 44, size: 20, color: ONAIR.head, show_when: "home.pp" })]);
  const buttons = [...commonButtons(),
    B("Next period", { do: "batch", actions: [{ do: "next", field: "period" }, { do: "reset", field: "clock.game" }] }, { role: "user" }),
    B("Away minor", { do: "penalty.add", field: "away.penalties", player: "", time: "2:00" }, { role: "alert" }),
    B("Home minor", { do: "penalty.add", field: "home.penalties", player: "", time: "2:00" }, { role: "alert" }),
    ...scoreButtons([1])];
  return finish("Hockey", "hockey", fields, [bug, fullScreen()], buttons);
}

function soccer() {
  const fields = [...teams(), new ClockField("clock.game", { label: "Match clock", clock: new Clock({ countdown: false, initial_ms: 0, fmt: "mm:ss" }) }),
    new TextField("clock.added", { label: "Added time", value: "" }),
    new ChoiceField("period", { label: "Half", options: ["1H", "2H", "ET1", "ET2", "PENS"] })];
  const bug = scorebug((x, y) => [box({ name: "Added time box", x, y: y + 16, w: 64, h: 44, fill: ONAIR.user, radius: 3, show_when: "clock.added" }),
    t({ name: "Added time", text: "{clock.added}", x, y: y + 16, w: 64, h: 44, size: 24, color: ONAIR.head, show_when: "clock.added" })]);
  const buttons = [...commonButtons(),
    B("Second half (45:00)", { do: "batch", actions: [{ do: "set", field: "period", value: "2H" }, { do: "set", field: "clock.game", value: "45:00" }, { do: "set", field: "clock.added", value: "" }] }, { role: "user" }),
    B("+1 added", { do: "set", field: "clock.added", value: "+1" }), B("+3 added", { do: "set", field: "clock.added", value: "+3" }),
    B("Clear added", { do: "set", field: "clock.added", value: "" }), ...scoreButtons([1])];
  return finish("Soccer", "soccer", fields, [bug, fullScreen()], buttons);
}

function football() {
  const fields = [...teams({ steps: [1, 2, 3, 6] }), gameClock({ minutes: 15, tenths: false }),
    new ClockField("clock.play", { label: "Play clock", clock: new Clock({ countdown: true, initial_ms: 40_000, fmt: "s" }) }),
    new ChoiceField("period", { label: "Quarter", options: ["1st", "2nd", "3rd", "4th", "OT"] }),
    new ChoiceField("down", { label: "Down", options: ["1st", "2nd", "3rd", "4th"] }),
    new TextField("distance", { label: "Distance", value: "10" }),
    new CounterField("away.timeouts", { label: "Away time-outs", value: 3, default: 3, maximum: 3 }),
    new CounterField("home.timeouts", { label: "Home time-outs", value: 3, default: 3, maximum: 3 }),
    new ToggleField("possession.home", { label: "Home ball", on_text: "●" }), new ToggleField("possession.away", { label: "Away ball", on_text: "●" })];
  const bug = scorebug((x, y) => [t({ name: "Down and distance", text: "{down} & {distance}", x, y, w: 150, h: 76, size: 30, color: ONAIR.user, uppercase: true }),
    t({ name: "Play clock", text: ":{clock.play}", x: x + 150, y, w: 70, h: 76, size: 30, color: ONAIR.muted })]);
  const buttons = [...commonButtons(),
    B("Play clock 40", { do: "batch", actions: [{ do: "reset", field: "clock.play" }, { do: "start", field: "clock.play" }] }, { role: "hi", hotkey: "R" }),
    B("Play clock 25", { do: "batch", actions: [{ do: "set", field: "clock.play", value: "25" }] }, { role: "hi", hotkey: "T" }),
    B("Next down", { do: "next", field: "down" }, { hotkey: "D" }),
    B("1st & 10", { do: "batch", actions: [{ do: "set", field: "down", value: "1st" }, { do: "set", field: "distance", value: "10" }] }, { hotkey: "F" }),
    B("Change possession", { do: "batch", actions: [{ do: "toggle", field: "possession.home" }, { do: "toggle", field: "possession.away" }] }),
    ...scoreButtons([1, 3, 6])];
  return finish("Football", "football", fields, [bug, fullScreen()], buttons);
}

function volleyball() {
  const fields = [...teams(), new CounterField("away.sets", { label: "Away sets", maximum: 5 }), new CounterField("home.sets", { label: "Home sets", maximum: 5 }),
    new CounterField("set", { label: "Set", value: 1, default: 1, minimum: 1, maximum: 5, ordinal: true }),
    new ToggleField("serve.home", { label: "Home serving", on_text: "●" }),
    gameClock({ minutes: 0, countdown: false, fmt: "h:mm:ss", tenths: false })];
  const buttons = [B("Undo", { do: "undo" }, { hotkey: "Ctrl+Z" }),
    B("Next set", { do: "batch", actions: [{ do: "next", field: "set" }, { do: "reset", field: "away.score" }, { do: "reset", field: "home.score" }] }, { role: "user" }),
    B("Away wins set", { do: "add", field: "away.sets", amount: 1 }), B("Home wins set", { do: "add", field: "home.sets", amount: 1 }),
    B("Switch serve", { do: "toggle", field: "serve.home" }, { hotkey: "S" }), ...scoreButtons([1])];
  return finish("Volleyball", "volleyball", fields,
    [scorebug(null, { chip: "SET {set}", clock: "{away.sets}-{home.sets}" }), fullScreen({ title: "SET {set}", clock: "{away.sets} – {home.sets}" })], buttons);
}

function baseball() {
  const fields = [...teams(), new CounterField("inning", { label: "Inning", value: 1, default: 1, minimum: 1, maximum: 99, ordinal: true }),
    new ChoiceField("half", { label: "Half", options: ["▲", "▼"], wrap: true }),
    new CounterField("balls", { label: "Balls", maximum: 3 }), new CounterField("strikes", { label: "Strikes", maximum: 2 }),
    new CounterField("outs", { label: "Outs", maximum: 2 }),
    new ToggleField("base.first", { label: "Runner on first" }), new ToggleField("base.second", { label: "Runner on second" }),
    new ToggleField("base.third", { label: "Runner on third" })];
  const bug = scorebug((x, y) => [t({ name: "Count", text: "{balls}-{strikes}", x, y, w: 90, h: 76, size: 34 }),
    t({ name: "Outs", text: "{outs} OUT", x: x + 90, y, w: 110, h: 76, size: 26, color: ONAIR.user })], { chip: "{half}{inning}", clock: "" });
  const buttons = [B("Undo", { do: "undo" }, { hotkey: "Ctrl+Z" }),
    B("Ball", { do: "add", field: "balls", amount: 1 }, { hotkey: "B" }), B("Strike", { do: "add", field: "strikes", amount: 1 }, { hotkey: "K" }),
    B("Out", { do: "batch", actions: [{ do: "add", field: "outs", amount: 1 }, { do: "reset", field: "balls" }, { do: "reset", field: "strikes" }] }, { role: "alert", hotkey: "X" }),
    B("New batter", { do: "batch", actions: [{ do: "reset", field: "balls" }, { do: "reset", field: "strikes" }] }, { hotkey: "N" }),
    B("Next half inning", { do: "batch", actions: [{ do: "next", field: "half" }, { do: "reset", field: "outs" }, { do: "reset", field: "balls" }, { do: "reset", field: "strikes" },
      { do: "set", field: "base.first", value: false }, { do: "set", field: "base.second", value: false }, { do: "set", field: "base.third", value: false }] }, { role: "user" }),
    B("Next inning", { do: "next", field: "inning" }), ...scoreButtons([1])];
  return finish("Baseball", "baseball", fields, [bug, fullScreen({ title: "{half} {inning}", clock: "{balls}-{strikes}  {outs} OUT" })], buttons);
}

function generic() {
  const fields = [...teams(), gameClock({ minutes: 10, tenths: false }),
    new CounterField("period", { label: "Period", value: 1, default: 1, minimum: 1, maximum: 9, ordinal: true })];
  const buttons = [...commonButtons(),
    B("Next period", { do: "batch", actions: [{ do: "next", field: "period" }, { do: "reset", field: "clock.game" }] }, { role: "user" }),
    ...scoreButtons([1])];
  return finish("Scoreboard", "generic", fields, [scorebug(), fullScreen()], buttons);
}

function blank() {
  return new Project({ name: "Untitled", sport: "blank", engine: new Engine([]), boards: [makeBoard({ name: "Board 1" })],
    buttons: [], layout: makeLayout({ pages: [makePage({ name: "Controls" })] }) });
}

export const PRESETS = {
  "Blank project": blank, "General scoreboard": generic, Basketball: basketball, Hockey: hockey, Soccer: soccer,
  Football: football, Volleyball: volleyball, Baseball: baseball,
};

export const BLURBS = {
  "Blank project": "Nothing yet. Add your own fields, controls and graphics.",
  "General scoreboard": "Two teams, a clock and a period.",
  Basketball: "Game and shot clocks, quarters, fouls, time-outs, bonus.",
  Hockey: "20-minute periods, shots, penalties that follow the clock.",
  Soccer: "Running match clock, halves, added time.",
  Football: "Game and play clocks, down and distance, time-outs.",
  Volleyball: "Points, sets and serve.",
  Baseball: "Inning, count, outs and runners.",
};

export function makeProject(name) {
  const fn = PRESETS[name];
  if (!fn) throw new Error(`No template called "${name}".`);
  return fn();
}
