// Engine tests: node --test test/
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { makeBoard, makeElement, renderTemplate, resolveColor, align, distribute, reorder, compactElement, elementShown, boardKeys } from "../app/core/board.js";
import { Clock, MAX_MS } from "../app/core/clock.js";
import { ActionError, Engine, Ticket } from "../app/core/engine.js";
import { ChoiceField, ClockField, CounterField, PenaltyField, TextField, ToggleField, fieldFromDict, normaliseKey } from "../app/core/fields.js";
import { PRESETS } from "../app/core/presets.js";
import { Project, ProjectError } from "../app/core/project.js";
import { formatMs, ordinal, parseTime, TimeParseError } from "../app/core/timefmt.js";
import { atomicWriteText, loadProject, saveProject } from "../app/service/files.js";
import { fieldReferences, renameFieldEverywhere } from "../app/core/refactor.js";
import { overlaps } from "../app/core/layout.js";

const tmpdir = () => fs.mkdtempSync(path.join(os.tmpdir(), "ts-"));

test("time: countdown rounds up", () => {
  assert.equal(formatMs(4_999, "m:ss"), "0:05");
  assert.equal(formatMs(4_001, "m:ss"), "0:05");
  assert.equal(formatMs(4_000, "m:ss"), "0:04");
  assert.equal(formatMs(1, "m:ss"), "0:01");
  assert.equal(formatMs(0, "m:ss"), "0:00");
});
test("time: stopwatch rounds down", () => {
  assert.equal(formatMs(4_999, "m:ss", false), "0:04");
  assert.equal(formatMs(59_999, "mm:ss", false), "00:59");
});
test("time: total units", () => {
  assert.equal(formatMs(90 * 60_000, "mm:ss"), "90:00");
  assert.equal(formatMs(90 * 60_000, "h:mm:ss"), "1:30:00");
  assert.equal(formatMs(125_000, "ss"), "125");
});
test("time: tenths and hundredths", () => {
  assert.equal(formatMs(4_070, "s.t"), "4.0");
  assert.equal(formatMs(4_070, "s.t", false), "4.0");
  assert.equal(formatMs(4_071, "ss.tt"), "04.07");
  assert.equal(formatMs(247_300, "mm:ss.z"), "04:07.3");
});
test("time: literals survive", () => assert.equal(formatMs(65_000, "Clock m'ss"), "Clock 1'05"));
test("time: parse", () => {
  assert.equal(parseTime("12:00"), 720_000);
  assert.equal(parseTime("1:02:03"), 3_723_000);
  assert.equal(parseTime("45"), 45_000);
  assert.equal(parseTime("90"), 90_000);
  assert.equal(parseTime("4:07.3"), 247_300);
  assert.equal(parseTime("0:00.25"), 250);
  assert.equal(parseTime(".5"), 500);
  assert.equal(parseTime("8:"), 480_000);
  assert.equal(parseTime(" 2 : 00 "), 120_000);
  for (const bad of ["", "abc", "1:60", "1:61:00", "1:2:3:4", "-5"]) assert.throws(() => parseTime(bad), TimeParseError, bad);
});
test("time: ordinal", () => {
  const cases = { 1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 13: "13th", 21: "21st", 22: "22nd", 101: "101st", 111: "111th", 112: "112th", 0: "0th" };
  for (const [n, want] of Object.entries(cases)) assert.equal(ordinal(Number(n)), want);
});

test("clock: countdown runs and pauses exactly", () => {
  const c = new Clock({ countdown: true, initial_ms: 10_000 });
  c.start(100);
  assert.equal(c.value(104.9), 5_100);
  c.stop(104.9);
  assert.equal(c.value(500), 5_100);
  c.start(600);
  assert.equal(c.value(601), 4_100);
  assert.equal(c.display(601), "0:05");
});
test("clock: expiry fires once and stops", () => {
  const c = new Clock({ countdown: true, initial_ms: 1_000 });
  c.start(0);
  assert.equal(c.tick(0.5), false);
  assert.equal(c.tick(1.2), true);
  assert.equal(c.running, false);
  assert.equal(c.value(9), 0);
  assert.equal(c.tick(9), false);
  assert.equal(c.start(10), false);
});
test("clock: toggle is not inverted", () => {
  const c = new Clock({ initial_ms: 5_000 });
  assert.equal(c.toggle(0), true);
  assert.equal(c.toggle(1), false);
  assert.equal(c.value(), 4_000);
});
test("clock: set while running keeps running", () => {
  const c = new Clock({ initial_ms: 60_000 });
  c.start(0);
  c.set(30_000, 5);
  assert.equal(c.running, true);
  assert.equal(c.value(6), 29_000);
});
test("clock: adjust and bounds", () => {
  const c = new Clock({ initial_ms: 5_000 });
  c.adjust(-10_000, 0);
  assert.equal(c.value(0), 0);
  c.adjust(MAX_MS * 2, 0);
  assert.equal(c.value(0), MAX_MS);
});
test("clock: stopwatch limit", () => {
  const c = new Clock({ countdown: false, initial_ms: 0, limit_ms: 3_000 });
  c.start(0);
  assert.equal(c.value(5), 3_000);
  assert.equal(c.tick(5), true);
  assert.equal(c.running, false);
});
test("clock: tenths threshold and blank", () => {
  const c = new Clock({ initial_ms: 65_000, tenths_under_ms: 60_000, tenths_fmt: "s.t", blank_at_zero: true });
  assert.equal(c.display(0), "1:05");
  c.set(60_000, 0); assert.equal(c.display(0), "1:00");
  c.set(59_999, 0); assert.equal(c.display(0), "59.9");
  c.set(4_321, 0); assert.equal(c.display(0), "4.3");
  c.set(0, 0); assert.equal(c.display(0), "");
});
test("clock: round trip opens stopped", () => {
  const c = new Clock({ initial_ms: 20 * 60_000, fmt: "mm:ss" });
  c.start(0);
  const c2 = Clock.fromDict(JSON.parse(JSON.stringify(c.toDict(65))));
  assert.equal(c2.running, false);
  assert.equal(c2.value(), 20 * 60_000 - 65_000);
  assert.equal(c2.fmt, "mm:ss");
});

test("fields: keys", () => {
  assert.throws(() => new TextField("Home Score"));
  assert.equal(normaliseKey("Home Score!"), "home_score");
  assert.equal(normaliseKey("..a..b.."), "a.b");
});
test("fields: counter", () => {
  const f = new CounterField("x", { minimum: 0, maximum: 3, pad: 2 });
  f.add(5); assert.equal(f.display(), "03");
  f.add(-9); assert.equal(f.value, 0);
  assert.throws(() => f.set("two"));
  assert.equal(new CounterField("p", { value: 2, ordinal: true }).display(), "2nd");
  assert.equal(new CounterField("z", { blank_zero: true }).display(), "");
});
test("fields: choice", () => {
  const f = new ChoiceField("period", { options: ["1st", "2nd", "OT"] });
  f.step(5); assert.equal(f.display(), "OT");
  f.set("2ND"); assert.equal(f.index, 1);
  assert.deepEqual(f.extra(), { index: "2" });
  const w = new ChoiceField("half", { options: ["▲", "▼"], wrap: true });
  w.step(1); w.step(1); assert.equal(w.display(), "▲");
  w.step(-1); assert.equal(w.display(), "▼");    // wraps backwards too
  assert.throws(() => f.set("4th"));
});
test("fields: toggle strings", () => {
  const f = new ToggleField("pp", { on_text: "PP" });
  f.set("on"); assert.equal(f.display(), "PP");
  f.set("0"); assert.equal(f.display(), "");
});
test("fields: round trip every type", () => {
  const proj = PRESETS.Hockey();
  for (const f of proj.engine.fields.values()) {
    const g = fieldFromDict(JSON.parse(JSON.stringify(f.toDict())));
    assert.equal(g.constructor, f.constructor, f.key);
    assert.equal(g.display(), f.display(), f.key);
  }
});

const makeEngine = () => new Engine([
  new CounterField("home.score", { label: "Home score" }), new CounterField("away.score", { label: "Away score" }),
  new TextField("home.name", { value: "Hawks" }), new ClockField("clock.game", { label: "Game clock", clock: new Clock({ initial_ms: 20 * 60_000 }) }),
  new PenaltyField("home.penalties", { master: "clock.game", slots: 2 }), new ToggleField("home.pp", { on_text: "PP" }),
  new ChoiceField("period", { options: ["1st", "2nd", "3rd"] }),
]);

test("engine: actions and snapshot", () => {
  const e = makeEngine();
  e.perform({ do: "add", field: "home.score", amount: 3 }, 0);
  e.perform({ do: "next", field: "period" }, 0);
  const s = e.snapshot();
  assert.equal(s.values["home.score"], "3");
  assert.equal(s.values.period, "2nd");
  assert.equal(s.values["period.index"], "2");
  assert.equal(s.values["clock.game.running"], "0");
  assert.equal(s.raw["clock.game"], 1_200_000);
});
test("engine: errors are operator readable", () => {
  const e = makeEngine();
  assert.throws(() => e.perform({ do: "add", field: "nope" }), (x) => x instanceof ActionError && /no field called/.test(x.message));
  assert.throws(() => e.perform({ do: "explode", field: "home.score" }), /Unknown action/);
  assert.throws(() => e.perform({ do: "toggle", field: "home.score" }), /does not apply/);
  assert.throws(() => e.perform({ do: "set", field: "clock.game", value: "soon" }), /not a time/);
  assert.throws(() => e.perform({ do: "add", field: "home.score", amount: "lots" }), (x) => x instanceof ActionError && /not a number/.test(x.message));
});
test("engine: batch is all or nothing", () => {
  const e = makeEngine();
  assert.throws(() => e.perform({ do: "batch", actions: [{ do: "add", field: "home.score", amount: 2 }, { do: "add", field: "missing" }] }, 0), ActionError);
  assert.equal(e.snapshot().values["home.score"], "0");
  assert.equal(e.canUndo(), false);
});
test("engine: undo and redo", () => {
  const e = makeEngine();
  e.perform({ do: "add", field: "home.score", amount: 2 }, 0);
  e.perform({ do: "batch", actions: [{ do: "add", field: "home.score", amount: 1 }, { do: "set", field: "home.name", value: "Owls" }] }, 0);
  e.perform({ do: "undo" }, 0);
  let s = e.snapshot();
  assert.deepEqual([s.values["home.score"], s.values["home.name"]], ["2", "Hawks"]);
  e.perform({ do: "redo" }, 0);
  assert.equal(e.snapshot().values["home.name"], "Owls");
  e.perform({ do: "undo" }, 0);
  e.perform({ do: "undo" }, 0);
  assert.equal(e.snapshot().values["home.score"], "0");
  e.perform({ do: "undo" }, 0);
});
test("engine: undoing a clock set keeps time that ran", () => {
  const e = makeEngine();
  e.perform({ do: "start", field: "clock.game" }, 0);
  e.perform({ do: "set", field: "clock.game", value: "5:00" }, 10);
  e.perform({ do: "undo" }, 13);
  assert.equal(e.field("clock.game").clock.value(13), 20 * 60_000 - 13_000);
  assert.equal(e.field("clock.game").clock.running, true);
});
test("engine: score undo does not rewind a running clock", () => {
  const e = makeEngine();
  e.perform({ do: "start", field: "clock.game" }, 0);
  e.perform({ do: "add", field: "home.score" }, 5);
  e.perform({ do: "undo" }, 9);
  assert.equal(e.field("clock.game").clock.value(9), 20 * 60_000 - 9_000);
});
test("engine: cannot start a clock at zero", () => {
  const e = makeEngine();
  e.perform({ do: "set", field: "clock.game", value: "0" }, 0);
  assert.throws(() => e.perform({ do: "toggle", field: "clock.game" }, 0), /at zero/);
});
test("engine: penalties follow the game clock", () => {
  const e = makeEngine();
  for (const p of ["#12", "#7", "#3"]) e.perform({ do: "penalty.add", field: "home.penalties", player: p, time: "2:00" }, 0);
  e.tick(30);
  assert.equal(e.snapshot().values["home.penalties.1.time"], "2:00");
  e.perform({ do: "start", field: "clock.game" }, 30);
  for (let i = 1; i <= 60; i++) e.tick(30 + i);
  e.perform({ do: "stop", field: "clock.game" }, 90);
  e.tick(200);
  let s = e.snapshot();
  assert.equal(s.values["home.penalties.1.time"], "1:00");
  assert.equal(s.values["home.penalties.2.time"], "1:00");
  assert.equal(s.values["home.penalties.count"], "3");
  e.perform({ do: "start", field: "clock.game" }, 200);
  e.tick(260.5);
  s = e.snapshot();
  assert.equal(s.values["home.penalties.count"], "1");
  assert.equal(s.values["home.penalties.1.player"], "#3");
  assert.equal(s.values["home.penalties.1.time"], "2:00");
});
test("engine: adjusting the master does not move penalties", () => {
  const e = makeEngine();
  e.perform({ do: "penalty.add", field: "home.penalties", player: "", time: "2:00" }, 0);
  e.perform({ do: "start", field: "clock.game" }, 0);
  e.perform({ do: "adjust", field: "clock.game", ms: -5000 }, 10);
  e.tick(10);
  assert.equal(e.field("home.penalties").entries[0].ms, 110_000);
});
test("engine: a ticket withdraws only before start", () => {
  const e = PRESETS.Basketball().engine;
  const t = new Ticket();
  e.submit({ do: "add", field: "home.score", amount: 2 }, null, t);
  assert.equal(t.withdraw(), true);
  e.tick();
  assert.equal(e.snapshot().values["home.score"], "0");
  const t2 = new Ticket();
  e.submit({ do: "add", field: "home.score", amount: 2 }, null, t2);
  e.tick();
  assert.equal(t2.withdraw(), false);
  assert.equal(e.snapshot().values["home.score"], "2");
});
test("engine: expiry listener and queue", () => {
  const e = new Engine([new ClockField("shot", { clock: new Clock({ initial_ms: 1000 }) })]);
  const hits = [];
  e.onExpired((k) => hits.push(k));
  e.perform({ do: "start", field: "shot" }, 0);
  e.tick(0.5); e.tick(1.5); e.tick(2.5);
  assert.deepEqual(hits, ["shot"]);
  const results = [];
  e.submit({ do: "reset", field: "shot" }, (r) => results.push(r));
  e.submit({ do: "add", field: "nope" }, (r) => results.push(r));
  e.tick(3);
  assert.equal(results[0], null);
  assert.match(results[1], /no field/);
});
test("engine: listeners get only changes", () => {
  const e = makeEngine();
  const seen = [];
  e.onChange((snap, changed) => seen.push(changed));
  e.perform({ do: "add", field: "away.score" }, 0);
  assert.deepEqual([...seen.at(-1)], ["away.score"]);
  const n = seen.length;
  e.tick(0);
  assert.equal(seen.length, n);
});
test("engine: collisions rejected", () => {
  const e = makeEngine();
  assert.throws(() => e.addField(new TextField("home.score")));
  assert.throws(() => e.addField(new TextField("clock.game.running")));
});
test("engine: rename keeps position", () => {
  const e = makeEngine();
  e.renameField("home.name", "home.title");
  assert.ok(e.fields.has("home.title"));
  assert.equal([...e.fields.keys()].indexOf("home.title"), 2);
});

test("boards: templates and colours", () => {
  const v = { "home.score": "3", a: "x" };
  assert.equal(renderTemplate("{home.score}-{missing}", v), "3-");
  assert.equal(renderTemplate("{{literal}} {a}", v), "{literal} x");
  assert.equal(resolveColor("{c}", { c: "ABC" }), "#aabbcc");
  assert.equal(resolveColor("#0a0f0df2", {}), "#0a0f0df2");
  assert.equal(resolveColor("{c}", { c: "red" }), "");
  assert.equal(resolveColor("", {}), "");
});
test("boards: align, distribute, reorder", () => {
  const b = makeBoard({ width: 1000, height: 500 });
  const a = makeElement({ x: 10, y: 0, w: 100 }), c = makeElement({ x: 500, y: 20, w: 50 }), d = makeElement({ x: 200, y: 40, w: 100 });
  b.elements = [a, c, d];
  align(b, [a.id, c.id], "left"); assert.equal(c.x, 10);
  align(b, [a.id], "hcenter"); assert.equal(a.x, 450);
  b.elements = [makeElement({ x: 0, w: 100 }), makeElement({ x: 150, w: 100 }), makeElement({ x: 900, w: 100 })];
  const ids = b.elements.map((e) => e.id);
  distribute(b, ids, "h");
  assert.deepEqual(b.elements.map((e) => e.x), [0, 450, 900]);
  reorder(b, ids[0], "front"); assert.equal(b.elements.at(-1).id, ids[0]);
  reorder(b, ids[0], "backward"); assert.equal(b.elements.at(-2).id, ids[0]);
});
test("boards: show when", () => {
  const e = makeElement({ show_when: "home.pp" });
  assert.equal(elementShown(e, { "home.pp": "" }), false);
  assert.equal(elementShown(e, { "home.pp": "0" }), false);
  assert.equal(elementShown(e, { "home.pp": "PP" }), true);
});
test("boards: compact round trip", () => {
  const e = makeElement({ kind: "text", text: "{a}", size: 60 });
  const d = compactElement(e);
  assert.ok(!("font" in d));
  assert.deepEqual(makeElement(d), e);
  assert.throws(() => makeBoard({ width: 99999, height: 10 }));
});

test("projects: templates are consistent", () => {
  for (const [name, make] of Object.entries(PRESETS)) {
    const p = make();
    const keys = new Set(Object.keys(p.engine.snapshot().values));
    for (const b of p.boards) assert.deepEqual(boardKeys(b).filter((k) => !keys.has(k)), [], `${name}/${b.name}`);
    for (const btn of p.buttons) {
      for (const a of btn.action.actions ?? [btn.action]) if (!["undo", "redo", "stop_all"].includes(a.do)) assert.ok(p.engine.fields.has(a.field), `${name}: ${btn.label}`);
      p.engine.perform(btn.action, 0);   // every button must actually run
    }
    for (const page of p.layout.pages) {
      const tiles = page.tiles;
      for (const t of tiles) {
        if (t.kind === "field") assert.ok(p.engine.fields.has(t.field), `${name}: tile ${t.field}`);
        if (t.kind === "button") assert.ok(p.button(t.button), `${name}: tile button`);
        if (t.kind === "preview") assert.ok(p.board(t.board), `${name}: preview`);
        assert.ok(t.x >= 0 && t.x + t.w <= 24, `${name}: tile inside the grid`);
      }
      for (let i = 0; i < tiles.length; i++) for (let j = i + 1; j < tiles.length; j++) {
        assert.ok(!overlaps(tiles[i], tiles[j]), `${name}: tiles overlap ${JSON.stringify(tiles[i])} ${JSON.stringify(tiles[j])}`);
      }
    }
  }
});
test("projects: save and load round trip", () => {
  const p = PRESETS.Basketball();
  p.engine.perform({ do: "add", field: "home.score", amount: 7 }, 0);
  const d = tmpdir();
  const file = path.join(d, "game.tsproj");
  saveProject(p, file);
  const q = loadProject(file);
  assert.equal(q.engine.snapshot().values["home.score"], "7");
  assert.deepEqual(q.toDict().boards, p.toDict().boards);
  assert.deepEqual(q.buttons, p.buttons);
  assert.deepEqual(q.layout, p.layout);
  assert.equal(q.path, file);
  assert.deepEqual(fs.readdirSync(d).filter((f) => f.endsWith(".tmp")), []);
});
test("projects: bad files", () => {
  const d = tmpdir();
  for (const [name, content] of [["a.tsproj", "{oops"], ["b.tsproj", '{"hello": 1}'], ["c.tsproj", '{"format":"telescore-project","version":99}']]) {
    const file = path.join(d, name);
    fs.writeFileSync(file, content);
    assert.throws(() => loadProject(file), ProjectError, name);
  }
  assert.throws(() => loadProject(path.join(d, "missing.tsproj")), ProjectError);
});
test("projects: a 2.0 alpha file is converted with a layout", () => {
  const d = tmpdir();
  const file = path.join(d, "old.tsproj");
  fs.writeFileSync(file, JSON.stringify({ format: "telescore-project", version: 2, name: "Old",
    fields: [{ key: "home.score", type: "counter", label: "Home score", value: 4 }],
    boards: [], panels: [{ name: "Game", columns: 4, buttons: [{ label: "Home +1", action: { do: "add", field: "home.score", amount: 1 }, hotkey: "O" }] }] }));
  const p = loadProject(file);
  assert.equal(p.path, "");                 // Save asks for a name: the original stays as it was
  assert.equal(p.importedFrom, file);
  assert.equal(p.buttons[0].hotkey, "O");
  assert.ok(p.layout.pages[0].tiles.some((t) => t.kind === "field" && t.field === "home.score"));
});
test("files: atomic write replaces", () => {
  const d = tmpdir();
  const file = path.join(d, "sub", "x.txt");
  atomicWriteText(file, "one");
  atomicWriteText(file, "two");
  assert.equal(fs.readFileSync(file, "utf8"), "two");
  assert.deepEqual(fs.readdirSync(path.dirname(file)), ["x.txt"]);
});
test("refactor: rename everywhere", () => {
  const p = PRESETS.Hockey();
  assert.ok(fieldReferences(p, "home.penalties").includes("Button “Home minor”"));
  assert.ok(renameFieldEverywhere(p, "home.penalties", "home.pen") > 0);
  const keys = new Set(Object.keys(p.engine.snapshot().values));
  for (const b of p.boards) assert.deepEqual(boardKeys(b).filter((k) => !keys.has(k)), []);
  assert.ok(p.boards[0].elements.find((e) => e.name === "Power play text").text.includes("{home.pen.1.time}"));
  renameFieldEverywhere(p, "clock.game", "clock.main");
  assert.equal(p.engine.field("home.pen").master, "clock.main");
  for (const btn of p.buttons) p.engine.perform(btn.action, 0);
  assert.deepEqual(fieldReferences(p, "clock.game"), []);
  assert.ok(p.layout.pages[0].tiles.some((t) => t.field === "clock.main"));
});

test("boards: a board can go inside another, never inside itself", async () => {
  const { canNest, boardsInside, makeBoard, makeElement } = await import("../app/core/board.js");
  const a = makeBoard({ name: "A", id: "a" }), b = makeBoard({ name: "B", id: "b" }), c = makeBoard({ name: "C", id: "c" });
  b.elements.push(makeElement({ kind: "board", board: "c" }));
  const all = [a, b, c];
  assert.ok(canNest(all, "a", "b"), "B (holding C) can go in A");
  assert.ok(!canNest(all, "a", "a"), "not in itself");
  assert.ok(!canNest(all, "c", "b"), "not C inside B inside C");
  assert.deepEqual([...boardsInside(all, "b")], ["c"]);
});

test("boards: text extents and show-while for on/off fields", async () => {
  const { makeElement, elementShown } = await import("../app/core/board.js");
  assert.equal(makeElement({ kind: "text", extent: "auto" }).extent, "auto");
  assert.equal(makeElement({ kind: "text", extent: "sideways" }).extent, "fixed");
  const e = makeElement({ kind: "board", show_when: "onair.sponsor" });
  // An on/off field whose words are "On air"/"Off air" still hides when off.
  assert.equal(elementShown(e, { "onair.sponsor": "Off air", "onair.sponsor.on": "0" }), false);
  assert.equal(elementShown(e, { "onair.sponsor": "On air", "onair.sponsor.on": "1" }), true);
  // Any other field: shown while it has a value.
  const t = makeElement({ kind: "text", show_when: "home.name" });
  assert.equal(elementShown(t, { "home.name": "" }), false);
  assert.equal(elementShown(t, { "home.name": "Hawks" }), true);
});

test("fonts: every bundled face is on disk and in the CSS", async () => {
  const { BUNDLED_FONTS, fontFaceCss, fontStack } = await import("../app/core/fonts.js");
  const css = fontFaceCss("/fonts/");
  for (const f of BUNDLED_FONTS) {
    assert.ok(fs.existsSync(path.join("app/assets/fonts", f.file)), f.file);
    if (f.italic) assert.ok(fs.existsSync(path.join("app/assets/fonts", f.italic)), f.italic);
    assert.ok(css.includes(`font-family:"${f.family}"`), f.family);
  }
  assert.match(fontStack("Futura PT"), /^"Futura PT", "Red Hat Display"/);
});

test("toggles publish .on whatever their words, live or not", () => {
  const e = new Engine([new ToggleField("onair.x", { value: true, on_text: "On air", off_text: "Off air" })]);
  e.perform({ do: "set", field: "onair.x", value: false });
  assert.deepEqual([e.snapshot().values["onair.x"], e.snapshot().values["onair.x.on"]], ["Off air", "0"]);
  e.field("onair.x").source = "Flag";
  e.feed({ Flag: ">" });
  e.tick();
  assert.deepEqual([e.snapshot().values["onair.x"], e.snapshot().values["onair.x.on"]], ["On air", "1"]);
});
