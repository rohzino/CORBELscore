// Rules, overrides, conditions, live sources and animations (engine side).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { BUILTIN, Tracker, ease, elementText, library, makeAnimation, sample } from "../app/core/animation.js";
import { makeBoard, makeElement } from "../app/core/board.js";
import { Clock } from "../app/core/clock.js";
import { FX_KEY, Engine } from "../app/core/engine.js";
import { ChoiceField, ClockField, CounterField, TextField, ToggleField } from "../app/core/fields.js";
import { Condition, applyRules, compareValue, parseRules } from "../app/core/logic.js";
import { PRESETS } from "../app/core/presets.js";
import { xmlFields } from "../app/core/formats.js";
import { loadProject, saveProject } from "../app/service/files.js";

test("rules: SportzSuite examples", () => {
  const rules = "0.0=Final|2:00=Two-minute Warning!";
  assert.equal(applyRules(rules, "0.0"), "Final");
  assert.equal(applyRules(rules, "2:00"), "Two-minute Warning!");
  assert.equal(applyRules(rules, "1:59"), null);
  assert.equal(applyRules("1=Joe|2=John|3=Bob", "2"), "John");
});
test("rules: extras", () => {
  assert.equal(applyRules("NULL=—", ""), "—");
  assert.equal(applyRules("0:0*=UNDER 10", "0:07"), "UNDER 10");
  assert.equal(applyRules("1={value}st|2={value}nd", "2"), "2nd");
  assert.equal(applyRules("a\\=b=c\\|d", "a=b"), "c|d");
  assert.deepEqual(parseRules("x=|=y|bad|k=v=w"), [["x", ""], ["", "y"], ["k", "v=w"]]);
  assert.equal(applyRules("[1]=one", "[1]"), "one");
  assert.equal(applyRules("a?c=hit", "abc"), "hit");
  assert.equal(applyRules("a.c=hit", "abc"), null);    // a dot is literal, not "any character"
});
test("rules: compare", () => {
  assert.ok(compareValue("equals", "F", "F", null));
  assert.ok(compareValue("equals", "", "NULL", null));
  assert.ok(compareValue("less", "0:59", "1:00", null));
  assert.ok(compareValue("greater", "34.5", "30", null));
  assert.ok(compareValue("changes_by", "2", "-1", "3"));
  assert.ok(!compareValue("changes_by", "2", "-1", null));
  assert.ok(compareValue("changes", "a", "", "b"));
  assert.ok(!compareValue("greater", "2nd", "1", null));
});

const engine = () => new Engine([
  new ClockField("clock.game", { label: "Game", clock: new Clock({ initial_ms: 120_000, fmt: "m:ss" }) }),
  new CounterField("home.score"), new CounterField("home.timeouts", { value: 3 }), new TextField("flag", { value: "" }),
  new ChoiceField("half", { options: ["T", "B"] }), new TextField("atbat", { value: "1" }), new ToggleField("home.flash", { on_text: "1" }),
]);

test("pipeline: order reaches xml", () => {
  const e = engine();
  const f = e.field("clock.game");
  f.rules = "2:00=Two-minute warning";
  e.publish(undefined, true);
  assert.equal(e.snapshot().values["clock.game"], "Two-minute warning");
  assert.equal(e.snapshot().base["clock.game"], "2:00");
  f.override = "HALFTIME"; f.override_on = true;
  e.publish(undefined, true);
  assert.equal(e.snapshot().values["clock.game"], "HALFTIME");
  assert.ok(xmlFields(e.snapshot()).includes('key="clock.game"'));
  assert.ok(xmlFields(e.snapshot()).includes(">HALFTIME</field>"));
  f.override_on = false;
  e.publish(undefined, true);
  assert.equal(e.snapshot().values["clock.game"], "Two-minute warning");
});
test("pipeline: a live source wins over the field's own value", () => {
  const e = engine();
  e.field("home.score").source = "HomeScore";
  e.field("clock.game").source = "Clock";
  e.feed({ HomeScore: "21", Clock: "4:07", ClockStatus: "R" });
  e.tick(0);
  const s = e.snapshot();
  assert.equal(s.values["home.score"], "21");
  assert.equal(s.raw["home.score"], 21);
  assert.equal(s.values["clock.game"], "4:07");
  assert.equal(s.raw["clock.game"], 247_000);
  assert.equal(s.values["clock.game.running"], "1");
  assert.deepEqual(new Set(s.live), new Set(["home.score", "clock.game"]));
  e.perform({ do: "add", field: "home.score", amount: 3 }, 0);
  assert.equal(e.snapshot().values["home.score"], "21");
  e.field("home.score").override = "0"; e.field("home.score").override_on = true;
  e.publish(undefined, true);
  assert.equal(e.snapshot().values["home.score"], "0");
});
test("pipeline: settings are saved, secrets are not", () => {
  const p = PRESETS.Basketball();
  const f = p.engine.field("home.score");
  Object.assign(f, { source: "HomeScore", rules: "0=—", override: "TBD", override_on: true });
  p.engine.setConditions([new Condition({ principal: "home.score", op: "changes", target: "x", action: "animate", arg: "Pulse" })]);
  p.animations.push(makeAnimation({ name: "Mine", kind: "in", duration: 500, x: -40 }));
  p.source.kind = "mqtt"; p.source.bot = 175;
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "ts-"));
  const file = path.join(d, "a.tsproj");
  saveProject(p, file);
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  assert.ok(!JSON.stringify(data.source).includes("token"));
  const q = loadProject(file);
  const g = q.engine.field("home.score");
  assert.deepEqual([g.source, g.rules, g.override, g.override_on], ["HomeScore", "0=—", "TBD", true]);
  assert.equal(q.engine.logic.conditions[0].arg, "Pulse");
  assert.equal(q.animations[0].x, -40);
  assert.deepEqual([q.source.kind, q.source.bot], ["mqtt", 175]);
});

test("conditions: show/hide converse pair", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "flag", op: "equals", value: "F", target: "rect2", action: "show", arg: "*" }),
    new Condition({ principal: "flag", op: "not_equals", value: "F", target: "rect2", action: "hide", arg: "*" })]);
  assert.equal(e.snapshot().fx.rect2.visible, false);
  const seen = [];
  e.onChange((s, c) => seen.push(c));
  e.perform({ do: "set", field: "flag", value: "F" }, 1);
  assert.equal(e.snapshot().fx.rect2.visible, true);
  assert.ok(seen.at(-1).has(FX_KEY));
  e.perform({ do: "set", field: "flag", value: "" }, 2);
  assert.equal(e.snapshot().fx.rect2.visible, false);
});
test("conditions: timed show and show once", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "home.score", op: "changes", target: "goal", action: "show", arg: "5000" }),
    new Condition({ principal: "home.score", op: "greater", value: "0", target: "first", action: "show_once", arg: "2000" })]);
  e.perform({ do: "add", field: "home.score" }, 10);
  const fx = e.snapshot().fx;
  assert.equal(fx.goal.visible, true);
  assert.equal(fx.first.visible, true);
  e.tick(13);
  assert.equal(e.snapshot().fx.first.visible, false);
  assert.equal(e.snapshot().fx.goal.visible, true);
  e.perform({ do: "add", field: "home.score" }, 14);
  e.tick(14.5);
  assert.equal(e.snapshot().fx.first.visible, false);
  e.tick(19.1);
  assert.equal(e.snapshot().fx.goal.visible, false);
});
test("conditions: conditional rule (batter names)", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "half", op: "equals", value: "T", target_kind: "field", target: "atbat", action: "rule", arg: "1=Joe|2=John" }),
    new Condition({ principal: "half", op: "equals", value: "B", target_kind: "field", target: "atbat", action: "rule", arg: "1=Dirk|2=Luca" })]);
  assert.equal(e.snapshot().values.atbat, "Joe");
  e.perform({ do: "set", field: "half", value: "B" }, 1);
  assert.equal(e.snapshot().values.atbat, "Dirk");
  e.perform({ do: "set", field: "atbat", value: "2" }, 2);
  assert.equal(e.snapshot().values.atbat, "Luca");
  e.field("atbat").rules = "2=Plain rule wins";
  e.publish(undefined, true);
  assert.equal(e.snapshot().values.atbat, "Plain rule wins");
});
test("conditions: changes by, with a finish", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "home.timeouts", op: "changes_by", value: "-1", target: "g1", action: "animate",
    arg: "Wipe out downward", finish_ms: 4000, finish: "animate:Wipe in downward" })]);
  e.perform({ do: "add", field: "home.timeouts", amount: -1 }, 5);
  const a1 = e.snapshot().fx.g1.anim;
  assert.equal(a1.name, "Wipe out downward");
  e.tick(9.1);
  const a2 = e.snapshot().fx.g1.anim;
  assert.equal(a2.name, "Wipe in downward");
  assert.ok(a2.id > a1.id);
  e.perform({ do: "add", field: "home.timeouts", amount: 1 }, 10);
  assert.equal(e.snapshot().fx.g1.anim.id, a2.id);
});
test("conditions: field actions reach outputs", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "home.score", op: "changes", target_kind: "field", target: "home.flash", action: "pulse", arg: "3000" }),
    new Condition({ principal: "clock.game", op: "equals", value: "0:00", target_kind: "field", target: "flag", action: "set", arg: "FINAL" }),
    new Condition({ principal: "flag", op: "equals", value: "FINAL", target_kind: "field", target: "", action: "action", run: { do: "next", field: "half" } })]);
  e.perform({ do: "add", field: "home.score" }, 0);
  e.tick(0.1);
  assert.equal(e.snapshot().values["home.flash"], "1");
  e.tick(3.2); e.tick(3.3);
  assert.equal(e.snapshot().values["home.flash"], "");
  e.perform({ do: "set", field: "clock.game", value: "0" }, 4);
  e.tick(4.1); e.tick(4.2); e.tick(4.3);
  const s = e.snapshot();
  assert.equal(s.values.flag, "FINAL");
  assert.equal(s.values.half, "B");
  assert.ok(!(e.canUndo() && e._undo.at(-1)[0][0] === "flag"));
});
test("conditions: a bad action is reported, not raised", () => {
  const e = engine();
  e.setConditions([new Condition({ principal: "home.score", op: "changes", target_kind: "field", target: "nope", action: "set", arg: "x" })]);
  e.perform({ do: "add", field: "home.score" }, 0);
  e.tick(0.1);
  assert.ok(e.logicErrors.length);
});
test("conditions: validation", () => {
  assert.throws(() => Condition.fromDict({ principal: "a", op: "bigger", target: "x", action: "show" }));
  assert.throws(() => Condition.fromDict({ principal: "a", op: "equals", target_kind: "field", target: "x", action: "font" }));
  const c = Condition.fromDict({ principal: "a", op: "equals", value: "1", target: "x", action: "show" });
  assert.deepEqual(Condition.fromDict(c.toDict()), c);
});

test("animation: easing endpoints and shape", () => {
  for (const n of ["linear", "ease", "ease-in", "ease-out", "ease-in-out", "broadcast", "back-out", "bounce-out"]) {
    assert.ok(Math.abs(ease(n, 0)) < 1e-6 && Math.abs(ease(n, 1) - 1) < 1e-6, n);
  }
  assert.ok(Math.abs(ease("linear", 0.37) - 0.37) < 1e-5);
  assert.ok(Math.max(...Array.from({ length: 51 }, (_, x) => ease("back-out", x / 50))) > 1);
});
test("animation: sample", () => {
  const lib = library();
  const a = lib["Fly in from left"];
  assert.equal(sample(a, 0).x, -260);
  assert.equal(sample(a, a.duration).x, 0);
  const w = lib["Wipe in from left"];
  assert.deepEqual(sample(w, 0).clip, [0, 0, 0, 1]);
  assert.deepEqual(sample(w, w.duration).clip, [0, 0, 1, 1]);
  const o = lib["Fade out"];
  assert.equal(sample(o, o.duration).opacity, 0);
  const f = lib.Flash;
  assert.ok(Math.abs(sample(f, f.duration / 2).opacity - f.opacity) < 1e-6);
  assert.equal(sample(f, f.duration * f.repeat + 1).opacity, 1);
  assert.equal(sample(makeAnimation({ name: "d", kind: "in", duration: 100, delay: 200, x: 50 }), 150).x, 50);
});
test("animation: built-ins valid and named uniquely", () => {
  const names = BUILTIN.map((a) => a.name);
  assert.equal(names.length, new Set(names).size);
  for (const a of BUILTIN) makeAnimation(a);
});
test("animation: tracker triggers", () => {
  const el = makeElement({ id: "pp", kind: "text", text: "{home.pp}", show_when: "home.pp", anim_in: "Slide in from left",
    anim_out: "Slide out to left", anim_change: "Pulse" });
  const tr = new Tracker(makeBoard({ elements: [el] }));
  const look = (t) => tr.look(tr.board.elements[0], t);
  tr.update({ "home.pp": "" }, {}, 0);
  assert.equal(look(0), null);
  tr.update({ "home.pp": "PP" }, {}, 1);
  assert.ok(look(1.1).x < 0);
  assert.equal(look(2).x, 0);
  tr.update({ "home.pp": "PP 1:59" }, {}, 3);
  assert.ok(look(3.2).scale > 1);
  tr.update({ "home.pp": "" }, {}, 4);
  assert.notEqual(look(4.1), null);
  assert.equal(look(5), null);
  assert.equal(tr.active(5), false);
  tr.update({ "home.pp": "" }, { pp: { anim: { name: "Pop in", id: 7 } } }, 6);
  assert.notEqual(look(6.1), null);
});
test("animation: element text rules", () => {
  const e = makeElement({ text: "{c}", rules: "0:00=FINAL" });
  assert.equal(elementText(e, { c: "0:00" }), "FINAL");
  assert.equal(elementText(e, { c: "1:00" }, { rule: "1:00=ONE" }), "ONE");
  assert.equal(elementText(e, { c: "0:00" }, { rule: "0:00=LOSES" }), "FINAL");
});
