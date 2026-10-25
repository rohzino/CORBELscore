// Rules, overrides and conditions: the SportzSuite model, applied to every
// output (text files, XML, JSON, boards), not just graphics.
//
// Value pipeline for a field, in order (first match wins):
//   1. override      while override_on, the field shows override text
//   2. live source   a bound live-data key replaces the field's own value
//   3. rule          "bot value=display value" pairs joined by |
//   4. conditional   a rule that applies only while a condition holds
//   5. the value itself
//
// Rules: 0.0=Final|2:00=Two-minute warning. * matches any run of characters,
// ? one character; \| and \= are literal; NULL on the left matches an empty
// value; {value} on the right inserts the original value.
//
// Conditions: "If <principal> <op> <value> then <target> <action> <arg>",
// checked when the principal's value changes (and once at start).

import { parseTime, TimeParseError } from "./timefmt.js";
import { newId } from "./ids.js";

export const OPS = {
  equals: "has value", not_equals: "does not have value", greater: "is greater than", less: "is less than",
  changes_by: "changes by", changes: "changes", contains: "contains", empty: "is empty", not_empty: "is not empty",
};
export const NO_VALUE_OPS = ["empty", "not_empty", "changes"];
export const ELEMENT_ACTIONS = {
  show: "Show", show_once: "Show once", hide: "Hide", color: "Change colour", fill: "Change fill",
  font: "Change font", image: "Alternate picture", rule: "Conditional rule", animate: "Animate",
};
export const FIELD_ACTIONS = { rule: "Conditional rule", set: "Set value", pulse: "Pulse on", action: "Run action" };

// ----- rules -------------------------------------------------------------------

// Split on sep unless escaped. keep leaves escapes in place for a later split.
export function splitEsc(text, sep, keep = false) {
  const out = [];
  let cur = "", esc = false;
  for (const ch of text) {
    if (esc) {
      cur += keep ? "\\" + ch : ("|=\\".includes(ch) ? ch : "\\" + ch);
      esc = false;
    } else if (ch === "\\") esc = true;
    else if (ch === sep) { out.push(cur); cur = ""; }
    else cur += ch;
  }
  if (esc) cur += "\\";
  out.push(cur);
  return out;
}

// "a=b|c=d" -> [["a","b"],["c","d"]]; pieces without = are ignored.
export function parseRules(text) {
  const pairs = [];
  if (!text) return pairs;
  for (const piece of splitEsc(text, "|", true)) {
    if (!piece.trim()) continue;
    const parts = splitEsc(piece, "=");
    if (parts.length < 2) continue;
    pairs.push([parts[0].trim(), parts.slice(1).join("=").trim()]);
  }
  return pairs;
}

const ruleCache = new Map();
const globCache = new Map();
function globRe(p) {
  let re = globCache.get(p);
  if (!re) {
    re = new RegExp("^" + [...p].map((c) => (c === "*" ? "[\\s\\S]*" : c === "?" ? "[\\s\\S]" :
      c.replace(/[.+^${}()|[\]\\]/g, "\\$&"))).join("") + "$");
    if (globCache.size > 500) globCache.clear();
    globCache.set(p, re);
  }
  return re;
}

// The replacement for value, or null when no rule matches.
export function applyRules(rules, value) {
  if (!rules) return null;
  let pairs = ruleCache.get(rules);
  if (!pairs) {
    pairs = parseRules(rules);
    if (ruleCache.size > 500) ruleCache.clear();
    ruleCache.set(rules, pairs);
  }
  const v = String(value ?? "").trim();
  for (const [left, right] of pairs) {
    let hit;
    if (left === "NULL") hit = v === "";
    else if (left.includes("*") || left.includes("?")) hit = globRe(left).test(v);
    else hit = v === left;
    if (hit) return right.split("{value}").join(value ?? "");
  }
  return null;
}

// ----- comparisons -------------------------------------------------------------

const NUM = /^[+-]?\d+(\.\d+)?$/;
function number(text) {
  const s = String(text ?? "").trim();
  if (NUM.test(s)) return parseFloat(s);
  if (s.includes(":") || s.includes(".")) {
    try { return parseTime(s) / 1000; } catch (e) { if (e instanceof TimeParseError) return null; throw e; }
  }
  return null;
}

export function compareValue(op, current, target, previous) {
  const cur = String(current ?? "").trim();
  const t0 = String(target ?? "").trim();
  const tgt = t0 === "NULL" ? "" : t0;
  switch (op) {
    case "equals": return cur === tgt;
    case "not_equals": return cur !== tgt;
    case "empty": return cur === "";
    case "not_empty": return cur !== "";
    case "contains": return tgt ? cur.toLowerCase().includes(tgt.toLowerCase()) : false;
    case "changes": return previous !== null && previous !== undefined && previous !== current;
    case "greater": case "less": {
      const a = number(cur), b = number(tgt);
      if (a === null || b === null) return false;
      return op === "greater" ? a > b : a < b;
    }
    case "changes_by": {
      if (previous === null || previous === undefined) return false;
      const a = number(cur), b = number(previous), d = number(tgt);
      if (a === null || b === null || d === null) return false;
      return Math.abs((a - b) - d) < 1e-6;
    }
    default: throw new Error(`Unknown condition "${op}".`);
  }
}

// ----- conditions --------------------------------------------------------------

const COND_DEFAULTS = { principal: "", op: "equals", value: "", target_kind: "element", target: "", action: "show",
  arg: "*", run: {}, finish_ms: 0, finish: "", enabled: true, note: "" };
const ALWAYS = ["principal", "op", "target", "action", "id"];

export class Condition {
  constructor(o = {}) {
    Object.assign(this, structuredClone(COND_DEFAULTS));
    for (const k of Object.keys(COND_DEFAULTS)) if (o[k] !== undefined) this[k] = structuredClone(o[k]);
    this.id = o.id || newId();
    this.finish_ms = Math.trunc(Number(this.finish_ms) || 0);
  }
  toDict() {
    const d = {};
    for (const k of [...Object.keys(COND_DEFAULTS), "id"]) {
      const v = this[k];
      const empty = v === "" || v === 0 || (v && typeof v === "object" && !Object.keys(v).length);
      if (!empty || ALWAYS.includes(k)) d[k] = structuredClone(v);
    }
    if (this.enabled === true) delete d.enabled;
    else d.enabled = false;
    return d;
  }
  static fromDict(d) {
    const c = new Condition(d);
    if (!(c.op in OPS)) throw new Error(`Unknown condition "${c.op}".`);
    const acts = c.target_kind === "element" ? ELEMENT_ACTIONS : FIELD_ACTIONS;
    if (!(c.action in acts)) throw new Error(`"${c.action}" is not an action for a ${c.target_kind}.`);
    return c;
  }
  describe(labels = {}) {
    const v = NO_VALUE_OPS.includes(this.op) ? "" : ` ${this.value || "NULL"}`;
    const tgt = labels[this.target] ?? this.target;
    const arg = this.action === "action" ? "" : ` ${this.arg}`;
    const fin = this.finish_ms && this.finish ? `, then after ${this.finish_ms} ms ${this.finish}` : "";
    const act = ELEMENT_ACTIONS[this.action] || FIELD_ACTIONS[this.action] || this.action;
    return `If ${this.principal} ${OPS[this.op] ?? this.op}${v} then ${tgt} ${act}${arg}${fin}`;
  }
}

function msArg(arg) {
  const s = String(arg ?? "").trim();
  if (s === "" || s === "*") return null;
  const n = Number(s);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : null;
}

// Evaluates conditions and keeps their effects:
//   fx           per board element: visible, color, fill, font, src, rule, anim {name, id}
//   field_rules  conditional rules per field, applied by the engine before publishing
//   pending      actions (set, pulse, run) the engine performs next tick
export class Logic {
  constructor(conditions = []) {
    this.conditions = [...conditions];
    this.reset();
  }
  reset() {
    this.prev = {};
    this.truth = {};
    this.fx = {};
    this.fieldRules = {};
    this.timers = [];      // [due, kind, payload]
    this.pending = [];
    this.animId = 0;
    this.started = false;
  }
  setConditions(conds) { this.conditions = [...conds]; this.reset(); }
  principals() { return new Set(this.conditions.filter((c) => c.enabled).map((c) => c.principal)); }
  _fx(eid) { return (this.fx[eid] ??= {}); }

  _elementAction(eid, action, arg, t) {
    const fx = this._fx(eid);
    if (action === "show" || action === "show_once" || action === "hide") {
      const vis = action !== "hide";
      fx.visible = vis;
      const ms = msArg(arg);
      this.timers = this.timers.filter((x) => !(x[1] === "vis" && x[2][0] === eid));
      if (ms !== null) this.timers.push([t + ms / 1000, "vis", [eid, !vis]]);
    } else if (["color", "fill", "font", "image", "rule"].includes(action)) {
      const key = action === "image" ? "src" : action;
      const a = String(arg ?? "").trim();
      if (a === "" || a === "*" || a === "NULL") delete fx[key];
      else fx[key] = a;
    } else if (action === "animate") {
      this.animId += 1;
      fx.anim = { name: String(arg ?? "").trim(), id: this.animId };
    }
  }
  _finish(c, t) {
    if (!c.finish_ms || !c.finish) return;
    this.timers.push([t + c.finish_ms / 1000, "finish", [c.target_kind, c.target, c.finish]]);
  }
  _runFinish(kind, target, finish, t) {
    const i = finish.indexOf(":");
    const verb = i < 0 ? finish : finish.slice(0, i);
    const arg = i < 0 ? "" : finish.slice(i + 1);
    if (kind === "element") {
      if (verb in ELEMENT_ACTIONS) this._elementAction(target, verb, arg || "*", t);
    } else if (verb === "set") this.pending.push({ do: "set", field: target, value: arg });
  }
  _fire(c, t) {
    if (c.target_kind === "element") this._elementAction(c.target, c.action, c.arg, t);
    else if (c.action === "set") this.pending.push({ do: "set", field: c.target, value: c.arg });
    else if (c.action === "pulse") {
      this.pending.push({ do: "set", field: c.target, value: true });
      const ms = msArg(c.arg) || 1000;
      this.timers.push([t + ms / 1000, "pending", { do: "set", field: c.target, value: false }]);
    } else if (c.action === "action" && c.run && Object.keys(c.run).length) this.pending.push(structuredClone(c.run));
    this._finish(c, t);
  }

  // Check conditions whose principal changed and run due timers. True when the
  // conditional field rules changed (the engine then re-applies them).
  evaluate(values, t) {
    const before = JSON.stringify(this.fieldRules);
    if (this.timers.length) {
      const due = this.timers.filter((x) => x[0] <= t);
      if (due.length) {
        this.timers = this.timers.filter((x) => x[0] > t);
        due.sort((a, b) => a[0] - b[0]);
        for (const [, kind, payload] of due) {
          if (kind === "vis") this._fx(payload[0]).visible = payload[1];
          else if (kind === "finish") this._runFinish(payload[0], payload[1], payload[2], t);
          else if (kind === "pending") this.pending.push(payload);
        }
      }
    }
    const changed = new Set([...this.principals()].filter((k) => !this.started || (values[k] ?? "") !== (this.prev[k] ?? "")));
    for (const c of this.conditions) {
      if (!c.enabled || !changed.has(c.principal)) continue;
      const cur = values[c.principal] ?? "";
      const prev = this.started ? (this.prev[c.principal] ?? null) : null;
      let ok;
      try { ok = compareValue(c.op, cur, c.value, prev); } catch { ok = false; }
      const was = this.truth[c.id] ?? false;
      this.truth[c.id] = ok;
      if (c.action === "rule") {
        if (c.target_kind === "field") {
          const slot = (this.fieldRules[c.target] ??= {});
          if (ok) slot[c.id] = c.arg; else delete slot[c.id];
        } else if (ok) this._fx(c.target).rule = c.arg;
        else if (this._fx(c.target).rule === c.arg) delete this._fx(c.target).rule;
        continue;
      }
      if (!ok) continue;
      if (c.action === "show_once" && was) continue;
      this._fire(c, t);
    }
    for (const k of changed) this.prev[k] = values[k] ?? "";
    this.started = true;
    for (const k of Object.keys(this.fieldRules)) if (!Object.keys(this.fieldRules[k]).length) delete this.fieldRules[k];
    return JSON.stringify(this.fieldRules) !== before;
  }
  takePending() { const out = this.pending; this.pending = []; return out; }
  conditionalRules(key) { return Object.values(this.fieldRules[key] ?? {}); }
  nextDue() { return this.timers.length ? Math.min(...this.timers.map((x) => x[0])) : null; }
  fxSnapshot() {
    const out = {};
    for (const [k, v] of Object.entries(this.fx)) if (Object.keys(v).length) out[k] = structuredClone(v);
    return out;
  }
}
