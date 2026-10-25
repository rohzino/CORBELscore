// The engine owns the fields, runs the clocks, carries out actions and
// publishes snapshots for every output. It runs on one event loop: anything
// arriving from outside (web requests, live data, global shortcuts) is queued
// with submit()/feed() and handled on the next tick().

import { now } from "./clock.js";
import { ChoiceField, ClockField, CounterField, ImageField, PenaltyField, TextField, ToggleField, validKey } from "./fields.js";
import { Logic, applyRules } from "./logic.js";
import { parseTime, TimeParseError } from "./timefmt.js";

// Lets whoever submitted an action withdraw it until it starts, so a remote
// caller that gave up waiting is never surprised by a late score.
export class Ticket {
  constructor() { this.stateName = "waiting"; }
  withdraw() {
    if (this.stateName === "waiting") { this.stateName = "withdrawn"; return true; }
    return false;
  }
  start() {
    if (this.stateName === "withdrawn") return false;
    this.stateName = "started";
    return true;
  }
}

// An action that cannot be carried out; the message is for the operator.
export class ActionError extends Error {}

// Every button, shortcut and web call is one of these.
export const ACTIONS = {
  set: "Set a field: {do, field, value}",
  add: "Add to a counter (negative to subtract): {do, field, amount}",
  reset: "Reset a field to its default; a clock to its period length: {do, field}",
  toggle: "Flip an on/off field, or start/stop a clock: {do, field}",
  start: "Start a clock: {do, field}",
  stop: "Stop a clock: {do, field}",
  adjust: "Add milliseconds to a clock (negative removes): {do, field, ms}",
  next: "Next option of a choice, or +1 on a counter: {do, field}",
  prev: "Previous option of a choice, or -1 on a counter: {do, field}",
  "penalty.add": "{do, field, player, time}",
  "penalty.remove": "{do, field, index (1-based)}",
  "penalty.clear": "{do, field}",
  stop_all: "Stop every running clock: {do}",
  batch: "Run several actions as one undo step: {do, actions: [...]}",
  undo: "Undo the last action: {do}",
  redo: "Redo: {do}",
};

const UNDO_LIMIT = 200;
export const FX_KEY = "#fx";      // in a change set: board element effects changed
export const BASE_KEY = "#live";  // in a change set: which fields follow a live source changed

function num(v, what = "value") {
  const n = typeof v === "number" ? v : Number(String(v ?? "").trim());
  if (v === null || v === undefined || String(v).trim() === "" || !Number.isFinite(n)) {
    throw new ActionError(`"${v}" is not a number (${what}).`);
  }
  return n;
}

// Machine value for a field fed from live text.
function rawFromText(f, text) {
  const s = String(text ?? "").trim();
  if (f instanceof CounterField) return /^[-+]?\d+$/.test(s) ? parseInt(s, 10) : s;
  if (f instanceof ClockField) {
    try { return parseTime(s); } catch (e) { if (e instanceof TimeParseError) return s; throw e; }
  }
  if (f instanceof ToggleField) return !["", "0", "false", "False", "N", "n"].includes(s);
  return text;
}

export class Engine {
  constructor(fields = []) {
    this.fields = new Map();
    this._undo = [];
    this._redo = [];
    this._snapshot = null;
    this._listeners = [];
    this._expiredListeners = [];
    this._inbox = [];
    this._feeds = [];
    this._seq = 0;
    this._marks = {};          // clock key -> [running, value_ms, t] at the last settle
    this.logic = new Logic();
    this.sources = {};         // live data: source key -> text
    this.lastFeed = 0;
    this.logicErrors = [];
    for (const f of fields) this.addField(f);
    this.publish(undefined, true);
  }

  // ----- fields --------------------------------------------------------------
  field(key) {
    const f = this.fields.get(key);
    if (!f) throw new ActionError(`There is no field called "${key}". Check its name under Fields.`);
    return f;
  }

  addField(f, index = null) {
    if (this.fields.has(f.key)) throw new Error(`A field called "${f.key}" already exists.`);
    const subbed = (x) => x instanceof ClockField || x instanceof PenaltyField || x instanceof ChoiceField;
    for (const [k, existing] of this.fields) {
      if (k.startsWith(f.key + ".") || f.key.startsWith(k + ".")) {
        // home.score vs home.score.x would make outputs ambiguous
        if (subbed(existing) || subbed(f)) throw new Error(`"${f.key}" collides with the published sub-keys of "${k}".`);
      }
    }
    if (index === null || index === undefined) this.fields.set(f.key, f);
    else {
      const items = [...this.fields.entries()];
      items.splice(index, 0, [f.key, f]);
      this.fields = new Map(items);
    }
    this._structureChanged();
  }

  removeField(key) {
    this.fields.delete(key);
    this._structureChanged();
  }

  moveField(key, index) {
    const items = [...this.fields.entries()];
    const i = items.findIndex(([k]) => k === key);
    if (i < 0) return;
    const [it] = items.splice(i, 1);
    items.splice(Math.max(0, Math.min(items.length, index)), 0, it);
    this.fields = new Map(items);
    this._structureChanged();
  }

  // Replace a field with a reconfigured copy (same position).
  replaceField(key, f) {
    if (!this.fields.has(key)) throw new Error(`There is no field called "${key}".`);
    if (f.key !== key && this.fields.has(f.key)) throw new Error(`A field called "${f.key}" already exists.`);
    this.fields = new Map([...this.fields.entries()].map(([k, v]) => (k === key ? [f.key, f] : [k, v])));
    this._structureChanged();
  }

  // Replace every field at once (design undo), keeping order as given.
  setFields(fields) {
    this.fields = new Map(fields.map((f) => [f.key, f]));
    this._structureChanged();
  }

  // Undo history refers to fields by key; after a structural change it is
  // cleared, and the snapshot is rebuilt so outputs match at once.
  _structureChanged() {
    this._undo = [];
    this._redo = [];
    if (this._snapshot) this.publish(undefined, true);
  }

  renameField(oldKey, newKey) {
    const f = this.field(oldKey);
    if (this.fields.has(newKey)) throw new Error(`A field called "${newKey}" already exists.`);
    if (!validKey(newKey)) throw new Error(`"${newKey}" is not a valid field key.`);
    const items = [...this.fields.entries()].map(([k, v]) => [k === oldKey ? newKey : k, v]);
    f.key = newKey;
    this.fields = new Map(items);
    this._structureChanged();
  }

  // ----- live data and conditions -----------------------------------------------
  feed(values) {
    const out = {};
    for (const [k, v] of Object.entries(values)) out[String(k)] = v === null || v === undefined ? "" : String(v);
    this._feeds.push(out);
  }
  clearSources() { this.sources = {}; }
  setConditions(conds) {
    this.logic.setConditions(conds);
    if (this._snapshot) this.publish(undefined, true);
  }

  onChange(fn) { this._listeners.push(fn); return () => { this._listeners = this._listeners.filter((x) => x !== fn); }; }
  onExpired(fn) { this._expiredListeners.push(fn); }

  // ----- actions ----------------------------------------------------------------
  submit(action, done = null, ticket = null) { this._inbox.push([action, done, ticket]); }

  // Run one action now and publish. Throws ActionError for the operator.
  perform(action, t = now()) {
    this._settle(t);
    const doName = action?.do;
    if (doName === "undo") this._step(this._undo, this._redo, t);
    else if (doName === "redo") this._step(this._redo, this._undo, t);
    else {
      const record = [];
      try {
        this._run(action, t, record, 0);
      } catch (e) {
        for (const [key, state] of record.reverse()) this.fields.get(key)?.restore(state, t); // all or nothing
        this._mark(t);
        throw e;
      }
      if (record.length) {
        this._undo.push(record);
        if (this._undo.length > UNDO_LIMIT) this._undo.splice(0, this._undo.length - UNDO_LIMIT);
        this._redo = [];
      }
    }
    this._mark(t);
    this.publish(t);
  }

  canUndo() { return this._undo.length > 0; }
  canRedo() { return this._redo.length > 0; }

  _remember(record, key, t) {
    if (record.some(([k]) => k === key)) return;
    record.push([key, structuredClone(this.fields.get(key).state(t)), t]);
  }

  _step(src, dst, t) {
    if (!src.length) return;
    const record = src.pop();
    const back = [];
    for (const [key, state, tThen] of record) {
      const f = this.fields.get(key);
      if (!f) continue;
      back.push([key, structuredClone(f.state(t)), t]);
      if (f instanceof ClockField) {
        let [value, running] = state;
        if (running && f.clock.running) {
          const run = Math.round((t - tThen) * 1000); // it kept running since; keep that time
          value = f.clock.countdown ? value - run : value + run;
        }
        f.restore([value, running], t);
      } else f.restore(structuredClone(state), t);
    }
    dst.push(back);
  }

  _run(action, t, record, depth) {
    if (!action || typeof action !== "object" || Array.isArray(action)) {
      throw new ActionError('An action must be a set of named values, such as {"do": "add"}.');
    }
    const doName = action.do;
    if (!(doName in ACTIONS)) throw new ActionError(`Unknown action "${doName}". Known actions: ${Object.keys(ACTIONS).join(", ")}.`);
    if (doName === "batch") {
      if (depth > 4) throw new ActionError("Batches can be nested at most 4 deep.");
      for (const sub of action.actions || []) this._run(sub, t, record, depth + 1);
      return;
    }
    if (doName === "stop_all") {
      for (const [k, f] of this.fields) {
        if (f instanceof ClockField && f.clock.running) { this._remember(record, k, t); f.clock.stop(t); }
      }
      return;
    }
    if (doName === "undo" || doName === "redo") throw new ActionError("Undo and redo cannot go inside a batch.");
    const f = this.field(action.field);
    this._remember(record, action.field, t);
    try {
      this._apply(f, doName, action, t);
    } catch (e) {
      if (e instanceof ActionError) throw e;
      throw new ActionError(e.message);
    }
  }

  _apply(f, doName, a, t) {
    if (doName === "reset") { f.reset(t); return; }
    const not = (kind) => new ActionError(`"${doName}" does not apply to ${kind}.`);
    if (f instanceof ClockField) {
      const c = f.clock;
      if (doName === "start") {
        if (!c.start(t) && c.countdown && c.value(t) <= 0) throw new ActionError(`${f.label} is at zero. Reset it or set a time first.`);
      } else if (doName === "stop") c.stop(t);
      else if (doName === "toggle") {
        if (!c.running && c.countdown && c.value(t) <= 0) throw new ActionError(`${f.label} is at zero. Reset it or set a time first.`);
        c.toggle(t);
      } else if (doName === "set") {
        const v = a.value;
        c.set(typeof v === "string" ? parseTime(v) : Math.trunc(num(v)), t);
      } else if (doName === "adjust") c.adjust(Math.trunc(num(a.ms ?? 0, "ms")), t);
      else if (doName === "add") c.adjust(Math.round(num(a.amount ?? 1, "amount") * 1000), t); // seconds
      else throw not("a clock");
      return;
    }
    if (f instanceof CounterField) {
      if (doName === "add") f.add(Math.trunc(num(a.amount ?? 1, "amount")));
      else if (doName === "set") f.set(a.value);
      else if (doName === "next") f.add(1);
      else if (doName === "prev") f.add(-1);
      else throw not("a counter");
      return;
    }
    if (f instanceof ChoiceField) {
      if (doName === "next" || doName === "add") f.step(doName === "add" ? Math.trunc(num(a.amount ?? 1, "amount")) : 1);
      else if (doName === "prev") f.step(-1);
      else if (doName === "set") f.set(a.value);
      else throw not("a choice");
      return;
    }
    if (f instanceof ToggleField) {
      if (doName === "toggle") f.toggle();
      else if (doName === "set") f.set(a.value);
      else throw not("an on/off field");
      return;
    }
    if (f instanceof PenaltyField) {
      if (doName === "penalty.add") f.add(String(a.player ?? ""), a.time ?? "2:00");
      else if (doName === "penalty.remove") f.remove(Math.trunc(num(a.index ?? 1, "index")) - 1);
      else if (doName === "penalty.clear") f.clear();
      else throw not("penalties");
      return;
    }
    if (f instanceof TextField || f instanceof ImageField) {
      if (doName === "set") f.set(a.value ?? "");
      else throw not(`${f.type} fields`);
      return;
    }
    throw not(f.label);
  }

  // ----- time --------------------------------------------------------------------
  // Advance penalties by exactly what their master clocks ran since the last
  // settle, then fire expiries. Every action settles first, so a master's
  // running state is constant between two settles.
  _settle(t) {
    const expired = [];
    for (const f of this.fields.values()) {
      if (f instanceof PenaltyField) {
        const mark = this._marks[f.master];
        const master = this.fields.get(f.master);
        if (mark && mark[0] && master instanceof ClockField) {
          let ran = Math.round((t - mark[2]) * 1000);
          if (master.clock.countdown) ran = Math.min(ran, mark[1]); // the master stopped at zero
          f.advance(ran);
        }
      }
    }
    for (const [k, f] of this.fields) if (f instanceof ClockField && f.clock.tick(t)) expired.push(k);
    this._mark(t);
    for (const k of expired) for (const fn of this._expiredListeners) { try { fn(k); } catch { /* never stop the clock */ } }
  }

  _mark(t) {
    this._marks = {};
    for (const [k, f] of this.fields) if (f instanceof ClockField) this._marks[k] = [f.clock.running, f.clock.value(t), t];
  }

  // Drain queued live data and actions, settle clocks and publish. Call 20-50
  // times a second. Returns [action, error] for queued actions.
  tick(t = now()) {
    const results = [];
    if (this._feeds.length) {
      for (const d of this._feeds) Object.assign(this.sources, d);
      this._feeds = [];
      this.lastFeed = t;
    }
    for (const action of this.logic.takePending()) {
      // Condition-driven actions change state but are not undo steps.
      try { this._run(action, t, [], 0); } catch (e) {
        this.logicErrors.push(`A condition could not run ${action.do}: ${e.message}`);
        this.logicErrors = this.logicErrors.slice(-20);
      }
    }
    const inbox = this._inbox;
    this._inbox = [];
    for (const [action, done, ticket] of inbox) {
      if (ticket && !ticket.start()) continue; // withdrawn: the caller was told it did not run
      let err = null;
      try { this.perform(action, t); } catch (e) {
        err = e instanceof ActionError ? e.message : `That action failed: ${e.message}`;
      }
      results.push([action, err]);
      if (done) { try { done(err); } catch { /* ignore */ } }
    }
    this._settle(t);
    this.publish(t);
    return results;
  }

  // ----- publishing ------------------------------------------------------------------
  _sourceText(f) {
    return f.source && Object.hasOwn(this.sources, f.source) ? this.sources[f.source] : null;
  }

  // override > rule > conditional rule > value
  _pipeline(f, base) {
    if (f.override_on) return f.override;
    let r = applyRules(f.rules, base);
    if (r !== null) return r;
    for (const cr of this.logic.conditionalRules(f.key)) {
      r = applyRules(cr, base);
      if (r !== null) return r;
    }
    return base;
  }

  buildSnapshot(t = now()) {
    const values = {}, base = {}, raw = {}, types = {}, labels = {};
    const live = new Set();
    for (const [k, f] of this.fields) {
      const src = this._sourceText(f);
      let b;
      if (src !== null) { live.add(k); b = src; raw[k] = rawFromText(f, src); }
      else { b = f.display(t); raw[k] = f.raw(t); }
      base[k] = b;
      values[k] = this._pipeline(f, b);
      let extra = f.extra(t);
      if (src !== null && f instanceof ClockField) {
        const status = this.sources[f.source_status || "ClockStatus"];
        if (status !== undefined) extra = { ...extra, running: status.trim().toUpperCase() === "R" ? "1" : "0" };
      }
      for (const [sub, text] of Object.entries(extra)) values[`${k}.${sub}`] = text;
      types[k] = f.type;
      labels[k] = f.label;
    }
    // Conditions see published values; the conditional rules they switch on can
    // trigger other conditions, at most three steps deep.
    for (let i = 0; i < 3; i++) {
      if (!this.logic.evaluate(values, t)) break;
      for (const [k, f] of this.fields) values[k] = this._pipeline(f, base[k]);
    }
    return { values, raw, types, labels, seq: this._seq, wall: Date.now() / 1000, fx: this.logic.fxSnapshot(), base,
      live: [...live] };
  }

  // Rebuild the snapshot; notify listeners with the set of changed keys.
  publish(t = now(), force = false) {
    const snap = this.buildSnapshot(t);
    const prev = this._snapshot;
    let changed;
    if (!prev || force) changed = new Set([...Object.keys(snap.values), FX_KEY, BASE_KEY]);
    else {
      changed = new Set(Object.keys(snap.values).filter((k) => prev.values[k] !== snap.values[k]));
      for (const k of Object.keys(prev.values)) if (!(k in snap.values)) changed.add(k);
      if (JSON.stringify(snap.fx) !== JSON.stringify(prev.fx)) changed.add(FX_KEY);
      if (JSON.stringify(snap.live) !== JSON.stringify(prev.live)) changed.add(BASE_KEY);
      if (JSON.stringify(snap.labels) !== JSON.stringify(prev.labels) || JSON.stringify(snap.types) !== JSON.stringify(prev.types)) {
        for (const k of Object.keys(snap.labels)) changed.add(k);
      }
    }
    if (!changed.size && prev) return null;
    this._seq += 1;
    snap.seq = this._seq;
    this._snapshot = snap;
    for (const fn of [...this._listeners]) { try { fn(snap, changed); } catch (e) { console.error(e); } }
    return changed;
  }

  snapshot() { return this._snapshot; }

  fieldsToList(t = now()) { return [...this.fields.values()].map((f) => f.toDict(t)); }
}
