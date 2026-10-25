// Data fields: the single source of truth for everything TeleScore shows.
// A scoreboard is a set of named fields (home.score, clock.game, period); every
// output, board, control and button reads or writes those names.
// A key is lower-case dotted words: [a-z0-9_]+(.[a-z0-9_]+)*

import { Clock, int } from "./clock.js";
import { formatMs, ordinal, parseTime } from "./timefmt.js";

const KEY_RE = /^[a-z0-9_]+(\.[a-z0-9_]+)*$/;

export const validKey = (key) => KEY_RE.test(key || "");

// 'Home Score' -> 'home_score'
export function normaliseKey(text) {
  let s = String(text || "").trim().toLowerCase().replace(/[^a-z0-9_.]+/g, "_");
  s = s.replace(/_+/g, "_").replace(/\.+/g, ".").replace(/^[._]+|[._]+$/g, "");
  return s || "field";
}

function wholeNumber(v) {
  const s = String(v).trim();
  if (!/^[-+]?\d+$/.test(s)) throw new Error(`"${v}" is not a whole number.`);
  return parseInt(s, 10);
}

export class Field {
  static type = "field";
  get type() { return this.constructor.type; }

  constructor(key, { label = "", source = "", rules = "", override = "", override_on = false } = {}) {
    if (!validKey(key)) {
      throw new Error(`"${key}" is not a valid field key. Use lower-case words joined by dots, for example home.score.`);
    }
    this.key = key;
    this.label = label || key;
    // The value pipeline (see logic.js), shared by every output:
    //   source   a live-data key (e.g. Sportzcast HomeScore) that replaces the field's own value
    //   rules    value replacements, "0:00=FINAL|2:00=Two-minute warning"
    //   override, override_on   fixed text that replaces everything while on
    this.source = String(source || "");
    this.rules = String(rules || "");
    this.override = String(override || "");
    this.override_on = !!override_on;
  }

  display() { throw new Error("not implemented"); }
  raw() { throw new Error("not implemented"); }
  extra() { return {}; }                // sub-keys published with this field (suffix -> text)
  state(t) { return this.raw(t); }      // opaque snapshot for undo
  restore() { throw new Error("not implemented"); }
  reset() { throw new Error("not implemented"); }

  toDict() {
    const d = { key: this.key, type: this.type, label: this.label };
    for (const k of ["source", "rules", "override"]) if (this[k]) d[k] = this[k];
    if (this.override_on) d.override_on = true;
    return d;
  }
}

export class CounterField extends Field {
  static type = "counter";
  constructor(key, o = {}) {
    super(key, o);
    this.default = int(o.default ?? 0);
    this.minimum = o.minimum === null ? null : int(o.minimum ?? 0);
    this.maximum = o.maximum === null || o.maximum === undefined ? null : int(o.maximum);
    const steps = (o.steps ?? [1]).map((s) => int(s));
    this.steps = steps.length ? steps : [1];
    this.ordinal = !!o.ordinal;
    this.blank_zero = !!o.blank_zero;
    this.pad = Math.max(0, int(o.pad ?? 0));
    this.value = this._clamp(int(o.value ?? 0));
  }
  _clamp(v) {
    if (this.minimum !== null) v = Math.max(this.minimum, v);
    if (this.maximum !== null) v = Math.min(this.maximum, v);
    return v;
  }
  set(v) { this.value = this._clamp(typeof v === "number" ? Math.trunc(v) : wholeNumber(v)); }
  add(amount = 1) { this.value = this._clamp(this.value + int(amount)); }
  display() {
    if (this.blank_zero && this.value === 0) return "";
    if (this.ordinal) return ordinal(this.value);
    if (this.pad) {
      const neg = this.value < 0;
      const s = String(Math.abs(this.value)).padStart(neg ? this.pad - 1 : this.pad, "0");
      return neg ? "-" + s : s;
    }
    return String(this.value);
  }
  raw() { return this.value; }
  restore(s) { this.value = int(s); }
  reset() { this.value = this._clamp(this.default); }
  toDict() {
    return { ...super.toDict(), value: this.value, default: this.default, minimum: this.minimum, maximum: this.maximum,
      steps: [...this.steps], ordinal: this.ordinal, blank_zero: this.blank_zero, pad: this.pad };
  }
}

export class TextField extends Field {
  static type = "text";
  constructor(key, o = {}) {
    super(key, o);
    this.value = String(o.value ?? "");
    this.default = o.default === undefined || o.default === null ? this.value : String(o.default);
    this.uppercase = !!o.uppercase;
    this.trim_zeros = !!o.trim_zeros;   // "06" shows as "6" (scoreboards pad digits)
  }
  set(v) { this.value = v === null || v === undefined ? "" : String(v); }
  display() {
    let v = this.value;
    if (this.trim_zeros && /^\s*0+\d+\s*$/.test(v)) v = String(parseInt(v, 10));
    return this.uppercase ? v.toUpperCase() : v;
  }
  raw() { return this.value; }
  restore(s) { this.value = String(s); }
  reset() { this.value = this.default; }
  toDict() { return { ...super.toDict(), value: this.value, default: this.default, uppercase: this.uppercase, trim_zeros: this.trim_zeros }; }
}

export class ToggleField extends Field {
  static type = "toggle";
  constructor(key, o = {}) {
    super(key, o);
    this.value = !!o.value;
    this.default = !!o.default;
    this.on_text = String(o.on_text ?? "1");
    this.off_text = String(o.off_text ?? "");
  }
  set(v) {
    if (typeof v === "string") v = ["1", "true", "on", "yes", "y", "show"].includes(v.trim().toLowerCase());
    this.value = !!v;
  }
  toggle() { this.value = !this.value; }
  display() { return this.value ? this.on_text : this.off_text; }
  raw() { return this.value; }
  restore(s) { this.value = !!s; }
  reset() { this.value = this.default; }
  toDict() {
    return { ...super.toDict(), value: this.value, default: this.default, on_text: this.on_text, off_text: this.off_text };
  }
}

export class ChoiceField extends Field {
  static type = "choice";
  constructor(key, o = {}) {
    super(key, o);
    const opts = (o.options ?? [""]).map(String);
    this.options = opts.length ? opts : [""];
    this.default = this._clamp(int(o.default ?? 0));
    this.wrap = !!o.wrap;
    this.index = this._clamp(int(o.index ?? 0));
  }
  _clamp(i) { return Math.max(0, Math.min(this.options.length - 1, i)); }
  // An option's text or its 0-based index.
  set(v) {
    if (typeof v === "number") { this.index = this._clamp(Math.trunc(v)); return; }
    const s = String(v).trim();
    const i = this.options.findIndex((o) => o.toLowerCase() === s.toLowerCase());
    if (i >= 0) { this.index = i; return; }
    if (/^-?\d+$/.test(s)) { this.index = this._clamp(parseInt(s, 10)); return; }
    throw new Error(`"${v}" is not one of ${this.options.join(", ")}.`);
  }
  step(delta) {
    const n = this.options.length;
    const i = this.index + int(delta);
    this.index = this.wrap ? ((i % n) + n) % n : this._clamp(i);
  }
  display() { return this.options[this.index]; }
  raw() { return this.options[this.index]; }
  state() { return this.index; }
  restore(s) { this.index = this._clamp(int(s)); }
  reset() { this.index = this.default; }
  extra() { return { index: String(this.index + 1) }; }
  toDict() {
    return { ...super.toDict(), options: [...this.options], index: this.index, default: this.default, wrap: this.wrap };
  }
}

const CLOCK_KEYS = ["countdown", "initial_ms", "limit_ms", "fmt", "tenths_under_ms", "tenths_fmt", "blank_at_zero"];

export class ClockField extends Field {
  static type = "clock";
  constructor(key, o = {}) {
    super(key, o);
    this.buzzer = String(o.buzzer || "");   // sound played when it reaches zero
    if (o.clock instanceof Clock) {
      this.clock = o.clock;
    } else {
      const cfg = {};
      for (const k of CLOCK_KEYS) if (o[k] !== undefined) cfg[k] = o[k];
      if (o.value_ms !== undefined) cfg.value_ms = o.value_ms;
      this.clock = Clock.fromDict(cfg);
    }
  }
  display(t) { return this.clock.display(t); }
  raw(t) { return this.clock.value(t); }
  extra(t) {
    const c = this.clock, v = c.value(t);
    return { running: c.running ? "1" : "0", tenths: c.countdown && c.tenths_under_ms && v > 0 && v < c.tenths_under_ms ? "1" : "0" };
  }
  state(t) { return this.clock.state(t); }
  restore(s, t) { this.clock.restore(s, t); }
  reset() { this.clock.reset(); }
  toDict(t) {
    const d = { ...super.toDict(), ...this.clock.toDict(t), running: false };
    if (this.buzzer) d.buzzer = this.buzzer;
    return d;
  }
}

// Timed penalties that run only while their master clock runs: the engine
// advances them by exactly the time the master ran, so they stop in stoppages.
// Sub-keys for slots 1..slots: <key>.<n>.player, <key>.<n>.time, <key>.count.
export class PenaltyField extends Field {
  static type = "penalties";
  constructor(key, o = {}) {
    super(key, o);
    this.master = o.master ?? "clock.game";
    this.slots = Math.max(1, int(o.slots ?? 2));
    this.fmt = o.fmt ?? "m:ss";
    this.entries = (o.entries || []).map((e) => ({ player: String(e.player ?? ""), ms: int(e.ms ?? 0) }));
  }
  add(player, time) {
    const ms = typeof time === "string" ? parseTime(time) : int(time);
    if (ms <= 0) throw new Error("A penalty needs a time above zero.");
    this.entries.push({ player: String(player ?? ""), ms });
  }
  remove(i) {
    if (!(i >= 0 && i < this.entries.length)) throw new Error(`There is no penalty ${i + 1}.`);
    this.entries.splice(i, 1);
  }
  clear() { this.entries = []; }
  // Run the penalties on the board by elapsed ms; returns those that expired.
  advance(elapsed) {
    if (elapsed <= 0) return [];
    for (const e of this.entries.slice(0, this.slots)) e.ms -= elapsed;
    const expired = this.entries.filter((e) => e.ms <= 0);
    this.entries = this.entries.filter((e) => e.ms > 0);
    return expired;
  }
  display() { return String(this.entries.length); }
  raw() { return this.entries.length; }
  extra() {
    const out = { count: String(this.entries.length) };
    for (let n = 1; n <= this.slots; n++) {
      const e = this.entries[n - 1];
      out[`${n}.player`] = e ? e.player : "";
      out[`${n}.time`] = e ? formatMs(e.ms, this.fmt, true) : "";
    }
    return out;
  }
  state() { return this.entries.map((e) => ({ ...e })); }
  restore(s) { this.entries = s.map((e) => ({ ...e })); }
  reset() { this.entries = []; }
  toDict() { return { ...super.toDict(), master: this.master, slots: this.slots, fmt: this.fmt, entries: this.state() }; }
}

export class ImageField extends Field {
  static type = "image";
  constructor(key, o = {}) {
    super(key, o);
    this.value = String(o.value ?? "");
    this.default = o.default === undefined || o.default === null ? this.value : String(o.default);
  }
  set(v) { this.value = v === null || v === undefined ? "" : String(v); }
  display() { return this.value; }
  raw() { return this.value; }
  restore(s) { this.value = String(s); }
  reset() { this.value = this.default; }
  toDict() { return { ...super.toDict(), value: this.value, default: this.default }; }
}

export const FIELD_TYPES = Object.fromEntries(
  [CounterField, TextField, ToggleField, ChoiceField, ClockField, PenaltyField, ImageField].map((c) => [c.type, c]));

export const TYPE_NAMES = { counter: "Counter", text: "Text", toggle: "On / off", choice: "Choice", clock: "Clock",
  penalties: "Penalties", image: "Picture" };

export function fieldFromDict(d) {
  const cls = FIELD_TYPES[d?.type];
  if (!cls) throw new Error(`Unknown field type "${d?.type}".`);
  const { key, type, ...rest } = d;
  return new cls(key, rest);
}
