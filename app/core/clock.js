// A drift-free game clock. The value is kept in milliseconds and derived from a
// monotonic time source whenever it is read; the refresh timer only decides how
// often the display updates, never how fast time passes. `t` is always seconds
// from a monotonic source and is passed in, which keeps every behaviour testable.

import { formatMs } from "./timefmt.js";

const perf = globalThis.performance;
export const now = () => perf.now() / 1000;

export const MAX_MS = 100 * 3_600_000; // 100 hours; anything above is a typo

export class Clock {
  constructor({ countdown = true, initial_ms = 12 * 60_000, limit_ms = 0, fmt = "m:ss", tenths_under_ms = 0,
    tenths_fmt = "s.t", blank_at_zero = false } = {}) {
    this.countdown = countdown;
    this.initial_ms = initial_ms;
    this.limit_ms = limit_ms;
    this.fmt = fmt;
    this.tenths_under_ms = tenths_under_ms;
    this.tenths_fmt = tenths_fmt;
    this.blank_at_zero = blank_at_zero;
    this._base = countdown ? initial_ms : 0;
    this._started = null;
  }

  get running() { return this._started !== null; }

  value(t = now()) {
    if (this._started === null) return this._base;
    const elapsed = Math.round((t - this._started) * 1000);
    if (this.countdown) return Math.max(0, this._base - elapsed);
    const v = this._base + elapsed;
    if (this.limit_ms && v > this.limit_ms) return this.limit_ms;
    return Math.min(v, MAX_MS);
  }

  display(t = now()) {
    const v = this.value(t);
    if (this.countdown && this.blank_at_zero && v <= 0) return "";
    if (this.countdown && this.tenths_under_ms && v > 0 && v < this.tenths_under_ms) {
      return formatMs(v, this.tenths_fmt, true);
    }
    return formatMs(v, this.fmt, this.countdown);
  }

  // False if already running or there is nothing to run.
  start(t = now()) {
    if (this.running) return false;
    if (this.countdown && this._base <= 0) return false;
    if (!this.countdown && this.limit_ms && this._base >= this.limit_ms) return false;
    this._started = t;
    return true;
  }

  // Stop, keeping the exact milliseconds already run.
  stop(t = now()) {
    if (!this.running) return false;
    this._base = this.value(t);
    this._started = null;
    return true;
  }

  toggle(t = now()) {
    if (this.running) this.stop(t); else this.start(t);
    return this.running;
  }

  // Set the value; a running clock keeps running from the new value.
  set(ms, t = now()) {
    ms = Math.trunc(Math.max(0, Math.min(Math.trunc(ms), MAX_MS)));
    if (this.limit_ms && !this.countdown) ms = Math.min(ms, this.limit_ms);
    const was = this.running;
    this._base = ms;
    this._started = was ? t : null;
    if (was && this.countdown && ms === 0) this._started = null;
  }

  adjust(delta, t = now()) { this.set(this.value(t) + Math.trunc(delta), t); }

  reset() {
    this._started = null;
    this._base = this.countdown ? this.initial_ms : 0;
  }

  // Settle at t. True exactly once when a countdown reaches zero or a
  // stopwatch reaches its limit; the clock stops.
  tick(t = now()) {
    if (!this.running) return false;
    const v = this.value(t);
    if ((this.countdown && v <= 0) || (!this.countdown && this.limit_ms && v >= this.limit_ms)) {
      this._base = v;
      this._started = null;
      return true;
    }
    return false;
  }

  config() {
    return { countdown: this.countdown, initial_ms: this.initial_ms, limit_ms: this.limit_ms, fmt: this.fmt,
      tenths_under_ms: this.tenths_under_ms, tenths_fmt: this.tenths_fmt, blank_at_zero: this.blank_at_zero };
  }

  toDict(t = now()) { return { ...this.config(), value_ms: this.value(t), running: this.running }; }

  static fromDict(d = {}) {
    const c = new Clock({
      countdown: d.countdown ?? true, initial_ms: int(d.initial_ms, 12 * 60_000), limit_ms: int(d.limit_ms, 0),
      fmt: String(d.fmt ?? "m:ss"), tenths_under_ms: int(d.tenths_under_ms, 0), tenths_fmt: String(d.tenths_fmt ?? "s.t"),
      blank_at_zero: !!d.blank_at_zero,
    });
    c.countdown = !!c.countdown;
    if (d.value_ms !== undefined) c._base = Math.max(0, int(d.value_ms, 0));
    return c; // a saved project always opens with its clocks stopped
  }

  state(t = now()) { return [this.value(t), this.running]; }

  restore([value, running], t = now()) {
    this._base = Math.max(0, Math.trunc(value));
    this._started = running ? t : null;
  }
}

export function int(v, dflt) {
  const n = Number(v);
  if (v === null || v === undefined || v === "" || !Number.isFinite(n)) {
    if (dflt === undefined) throw new TypeError(`not a number: ${v}`);
    return dflt;
  }
  return Math.trunc(n);
}
