// Animations for board elements: small recipes for what an element looks like
// at the start of an "in" (end of an "out", peak of an "emphasis"), the move's
// length and its easing. One implementation serves the browser source, the
// designer preview and the live view.
//   kind in|out|emphasis  opacity 0..1  x,y px offset  scale  wipe ""|left|right|up|down
//   duration ms  delay ms  easing  repeat (emphasis)
// Triggers per element: anim_in (becomes visible), anim_out (becomes hidden;
// hidden at the end), anim_change (text or picture changes); a condition's
// Animate action plays any animation by name.

import { renderTemplate, elementShown } from "./board.js";
import { applyRules } from "./logic.js";

export const IDENTITY = Object.freeze({ opacity: 1, x: 0, y: 0, scale: 1, clip: [0, 0, 1, 1] });

export const EASINGS = {
  linear: [0, 0, 1, 1], ease: [0.25, 0.1, 0.25, 1], "ease-in": [0.42, 0, 1, 1], "ease-out": [0, 0, 0.58, 1],
  "ease-in-out": [0.42, 0, 0.58, 1], broadcast: [0.2, 0.8, 0.2, 1], "back-out": [0.34, 1.56, 0.64, 1],
  "bounce-out": "bounce",
};

function bezier(x1, y1, x2, y2, x) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const bx = (t) => 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t ** 2 * x2 + t ** 3;
  const by = (t) => 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t ** 2 * y2 + t ** 3;
  const dbx = (t) => 3 * (1 - t) ** 2 * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t ** 2 * (1 - x2);
  let t = x;
  for (let i = 0; i < 8; i++) {
    const err = bx(t) - x;
    if (Math.abs(err) < 1e-7) return by(t);
    const d = dbx(t);
    if (Math.abs(d) < 1e-6) break;
    t -= err / d;
  }
  let lo = 0, hi = 1;
  t = x;
  for (let i = 0; i < 40; i++) {
    const v = bx(t);
    if (Math.abs(v - x) < 1e-7) break;
    if (v < x) lo = t; else hi = t;
    t = (lo + hi) / 2;
  }
  return by(t);
}

function bounce(x) {
  const n = 7.5625, d = 2.75;
  if (x < 1 / d) return n * x * x;
  if (x < 2 / d) { x -= 1.5 / d; return n * x * x + 0.75; }
  if (x < 2.5 / d) { x -= 2.25 / d; return n * x * x + 0.9375; }
  x -= 2.625 / d;
  return n * x * x + 0.984375;
}

export function ease(name, x) {
  x = Math.max(0, Math.min(1, x));
  const e = EASINGS[name] ?? EASINGS.broadcast;
  return e === "bounce" ? bounce(x) : bezier(e[0], e[1], e[2], e[3], x);
}

const ANIM_DEFAULTS = { name: "Fade in", kind: "in", duration: 350, delay: 0, easing: "broadcast", opacity: 0, x: 0, y: 0,
  scale: 1, wipe: "", repeat: 1 };

export function makeAnimation(o = {}) {
  const a = { ...ANIM_DEFAULTS };
  for (const k of Object.keys(ANIM_DEFAULTS)) if (o[k] !== undefined) a[k] = o[k];
  if (!["in", "out", "emphasis"].includes(a.kind)) throw new Error(`Animation "${a.name}": kind must be in, out or emphasis.`);
  if (!["", "left", "right", "up", "down"].includes(a.wipe)) throw new Error(`Animation "${a.name}": wipe must be left, right, up or down.`);
  a.name = String(a.name);
  a.duration = Math.max(1, Math.trunc(Number(a.duration) || 1));
  a.delay = Math.max(0, Math.trunc(Number(a.delay) || 0));
  a.repeat = Math.max(1, Math.trunc(Number(a.repeat) || 1));
  for (const k of ["opacity", "x", "y", "scale"]) a[k] = Number(a[k]) || 0;
  if (o.builtin) a.builtin = true;
  return a;
}

export const total = (a) => a.delay + a.duration * (a.kind === "emphasis" ? a.repeat : 1);

const b = (o) => makeAnimation({ ...o, builtin: true });
export const BUILTIN = [
  b({ name: "Fade in", kind: "in", duration: 350, opacity: 0 }),
  b({ name: "Fade out", kind: "out", duration: 350, opacity: 0 }),
  b({ name: "Fly in from left", kind: "in", duration: 450, x: -260, opacity: 1 }),
  b({ name: "Fly in from right", kind: "in", duration: 450, x: 260, opacity: 1 }),
  b({ name: "Fly in from top", kind: "in", duration: 450, y: -160, opacity: 1 }),
  b({ name: "Fly in from bottom", kind: "in", duration: 450, y: 160, opacity: 1 }),
  b({ name: "Fly out to left", kind: "out", duration: 450, x: -260, opacity: 1, easing: "ease-in" }),
  b({ name: "Fly out to right", kind: "out", duration: 450, x: 260, opacity: 1, easing: "ease-in" }),
  b({ name: "Fly out to top", kind: "out", duration: 450, y: -160, opacity: 1, easing: "ease-in" }),
  b({ name: "Fly out to bottom", kind: "out", duration: 450, y: 160, opacity: 1, easing: "ease-in" }),
  b({ name: "Wipe in from left", kind: "in", duration: 400, opacity: 1, wipe: "left" }),
  b({ name: "Wipe in from right", kind: "in", duration: 400, opacity: 1, wipe: "right" }),
  b({ name: "Wipe in upward", kind: "in", duration: 400, opacity: 1, wipe: "up" }),
  b({ name: "Wipe in downward", kind: "in", duration: 400, opacity: 1, wipe: "down" }),
  b({ name: "Wipe out to left", kind: "out", duration: 400, opacity: 1, wipe: "left" }),
  b({ name: "Wipe out to right", kind: "out", duration: 400, opacity: 1, wipe: "right" }),
  b({ name: "Wipe out upward", kind: "out", duration: 400, opacity: 1, wipe: "up" }),
  b({ name: "Wipe out downward", kind: "out", duration: 400, opacity: 1, wipe: "down" }),
  b({ name: "Slide in from left", kind: "in", duration: 450, x: -90, opacity: 0 }),
  b({ name: "Slide in from right", kind: "in", duration: 450, x: 90, opacity: 0 }),
  b({ name: "Slide in from below", kind: "in", duration: 450, y: 60, opacity: 0 }),
  b({ name: "Slide out to left", kind: "out", duration: 450, x: -90, opacity: 0, easing: "ease-in" }),
  b({ name: "Slide out to right", kind: "out", duration: 450, x: 90, opacity: 0, easing: "ease-in" }),
  b({ name: "Slide out downward", kind: "out", duration: 450, y: 60, opacity: 0, easing: "ease-in" }),
  b({ name: "Pop in", kind: "in", duration: 380, scale: 0.6, opacity: 0, easing: "back-out" }),
  b({ name: "Pop out", kind: "out", duration: 300, scale: 0.6, opacity: 0, easing: "ease-in" }),
  b({ name: "Drop in", kind: "in", duration: 700, y: -120, opacity: 1, easing: "bounce-out" }),
  b({ name: "Flash", kind: "emphasis", duration: 300, opacity: 0.15, easing: "ease-in-out", repeat: 3 }),
  b({ name: "Pulse", kind: "emphasis", duration: 450, scale: 1.18, opacity: 1, easing: "ease-in-out" }),
  b({ name: "Shake", kind: "emphasis", duration: 90, x: 10, opacity: 1, easing: "linear", repeat: 4 }),
  b({ name: "Bump up", kind: "emphasis", duration: 350, y: -14, opacity: 1, easing: "ease-out" }),
];

// Built-ins, then project animations (a custom one may replace a built-in name).
export function library(custom = []) {
  const lib = {};
  for (const a of BUILTIN) lib[a.name] = a;
  for (const a of custom) lib[a.name] = a;
  return lib;
}

const lerp = (a, c, p) => a + (c - a) * p;

// An element's look elapsed ms after a started: opacity, x, y, scale (about the
// centre) and clip [x0, y0, x1, y1] as fractions of the element box.
export function sample(a, elapsed) {
  const t = elapsed - a.delay;
  if (a.kind === "emphasis") {
    if (t <= 0 || t >= a.duration * a.repeat) return { ...IDENTITY, clip: [0, 0, 1, 1] };
    const phase = (t % a.duration) / a.duration;
    const tri = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
    const p = ease(a.easing, tri);
    return { opacity: lerp(1, a.opacity, p), x: lerp(0, a.x, p), y: lerp(0, a.y, p), scale: lerp(1, a.scale, p), clip: [0, 0, 1, 1] };
  }
  const raw = t <= 0 ? 0 : Math.min(1, t / a.duration);
  const p = ease(a.easing, raw);
  const k = a.kind === "in" ? 1 - p : p;
  const shown = Math.max(0, Math.min(1, a.kind === "in" ? p : 1 - p));
  let clip = [0, 0, 1, 1];
  if (a.wipe === "left") clip = [0, 0, shown, 1];
  else if (a.wipe === "right") clip = [1 - shown, 0, 1, 1];
  else if (a.wipe === "up") clip = [0, 1 - shown, 1, 1];
  else if (a.wipe === "down") clip = [0, 0, 1, shown];
  return { opacity: Math.max(0, Math.min(1, lerp(1, a.opacity, k))), x: a.x * k + 0, y: a.y * k + 0, scale: lerp(1, a.scale, k), clip };
}

// Displayed text: template, then the element's own rules, then a conditional
// rule from a condition (a plain rule wins, as in SportzSuite).
export function elementText(e, values, fx) {
  const text = renderTemplate(e.text, values);
  let r = applyRules(e.rules, text);
  if (r !== null) return r;
  if (fx?.rule) {
    r = applyRules(fx.rule, text);
    if (r !== null) return r;
  }
  return text;
}

// Turns visibility and content changes into running animations. update() with
// new values and effects; look() per element while painting. t in seconds.
export class Tracker {
  constructor(board = null, custom = []) {
    this.board = board;
    this.lib = library(custom);
    this.state = {};
    this.fxIds = {};
  }
  setBoard(board, custom = []) {
    if (board !== this.board) { this.state = {}; this.fxIds = {}; }
    this.board = board;
    this.lib = library(custom);
  }
  static targetVisible(e, values, fx) {
    if (e.visible === false) return false;
    if (fx && "visible" in fx) return !!fx.visible;
    return elementShown(e, values);
  }
  static content(e, values, fx) {
    if (e.kind === "text") return elementText(e, values, fx);
    if (e.kind === "image") return fx?.src || renderTemplate(e.src, values);
    return "";
  }
  _start(st, name, t, hideAfter = false) {
    const a = this.lib[name];
    if (!a) return false;
    st.anim = a; st.start = t; st.hideAfter = hideAfter || a.kind === "out";
    return true;
  }
  update(values, fxAll, t, animate = true) {
    if (!this.board) return;
    for (const e of this.board.elements) {
      const fx = fxAll[e.id] ?? {};
      const st = (this.state[e.id] ??= { visible: null, content: null, anim: null, start: 0, hideAfter: false });
      let vis = Tracker.targetVisible(e, values, fx);
      const cont = Tracker.content(e, values, fx);
      const first = st.visible === null;
      if (!first && animate) {
        if (vis && !st.visible) { if (!(e.anim_in && this._start(st, e.anim_in, t))) st.anim = null; }
        else if (!vis && st.visible) { if (!(e.anim_out && this._start(st, e.anim_out, t, true))) st.anim = null; }
        else if (vis && cont !== st.content && e.anim_change) this._start(st, e.anim_change, t);
      }
      const anim = fx.anim;
      if (anim && animate && this.fxIds[e.id] !== anim.id) {
        this.fxIds[e.id] = anim.id;
        if (!first) {
          const a = this.lib[anim.name ?? ""];
          if (a) { this._start(st, a.name, t, a.kind === "out"); if (a.kind === "in") vis = true; }
        }
      } else if (anim) this.fxIds[e.id] = anim.id;
      st.visible = vis;
      st.content = cont;
    }
  }
  // null = do not draw; otherwise the look to draw with.
  look(e, t) {
    const st = this.state[e.id];
    if (!st) return e.visible !== false ? { ...IDENTITY } : null;
    if (st.anim) {
      const elapsed = (t - st.start) * 1000;
      if (elapsed >= total(st.anim)) {
        const hide = st.hideAfter;
        st.anim = null;
        if (hide) return null;
      } else {
        if (elapsed < st.anim.delay && st.anim.kind === "in") return st.visible ? sample(st.anim, elapsed) : null;
        return sample(st.anim, elapsed);
      }
    }
    return st.visible ? { ...IDENTITY } : null;
  }
  active(t) {
    return Object.values(this.state).some((s) => s.anim && (t - s.start) * 1000 < total(s.anim) + 20);
  }
  // Preview an animation now (the designer's Play button).
  play(eid, name, t) {
    const st = (this.state[eid] ??= { visible: null, content: null, anim: null, start: 0, hideAfter: false });
    if (st.visible === null) st.visible = true;
    const a = this.lib[name];
    if (!a) return false;
    st.anim = a; st.start = t; st.hideAfter = false;
    return true;
  }
}
