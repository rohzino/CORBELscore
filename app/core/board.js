// Scoreboard graphics ("boards"): fixed canvases (1920 x 1080 by default) of
// elements in paint order: text built from field templates, boxes and pictures.
// Geometry is canvas pixels, so a board renders identically at any size.
// Templates: {home.score} is the field's display text; {{ and }} are braces.
// Boards and elements are plain JSON objects; these helpers work on them.

import { newId } from "./ids.js";

export const ELEMENT_KINDS = ["text", "box", "image"];

export const ELEMENT_DEFAULTS = {
  kind: "text", name: "", x: 0, y: 0, w: 200, h: 80, opacity: 1, visible: true, locked: false, show_when: "",
  fill: "", stroke: "", stroke_width: 0, radius: 0,
  text: "", font: "Archivo", size: 48, weight: 700, italic: false, color: "#ffffff", align: "center",
  valign: "middle", uppercase: false, tracking: 0, fit: true, tabular: true, padding: 0,
  src: "", contain: true, rules: "", anim_in: "", anim_out: "", anim_change: "",
};

const TPL = /\{\{|\}\}|\{([a-z0-9_.]+)\}/g;
const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;

export function renderTemplate(template, values) {
  return String(template ?? "").replace(TPL, (m, k) => (m === "{{" ? "{" : m === "}}" ? "}" : String(values[k] ?? "")));
}

export function templateKeys(template) {
  return [...String(template ?? "").matchAll(TPL)].map((m) => m[1]).filter(Boolean);
}

// A colour may be a literal (#rgb, #rrggbb, #rrggbbaa) or a template such as
// {home.color}. Returns lower-case #rrggbb / #rrggbbaa, or "" for nothing valid.
export function resolveColor(value, values = {}) {
  const raw = String(value ?? "");
  let v = (raw.includes("{") ? renderTemplate(raw, values) : raw).trim();
  if (!v) return "";
  if (!v.startsWith("#")) v = "#" + v;
  if (!HEX.test(v)) return "";
  if (v.length === 4) v = "#" + [...v.slice(1)].map((c) => c + c).join("");
  return v.toLowerCase();
}

// #rrggbbaa -> rgba() for CSS; #rrggbb unchanged.
export function cssColor(hex) {
  if (!hex) return "";
  if (hex.length === 9) {
    const n = (i) => parseInt(hex.slice(i, i + 2), 16);
    return `rgba(${n(1)},${n(3)},${n(5)},${(n(7) / 255).toFixed(3)})`;
  }
  return hex;
}

export function makeElement(o = {}) {
  const e = { ...structuredClone(ELEMENT_DEFAULTS), ...structuredClone(o) };
  e.id = o.id || newId();
  if (!ELEMENT_KINDS.includes(e.kind)) throw new Error(`Unknown element kind "${e.kind}".`);
  for (const k of ["x", "y", "w", "h", "opacity", "stroke_width", "radius", "size", "tracking", "padding"]) {
    e[k] = Number(e[k]);
    if (!Number.isFinite(e[k])) throw new Error(`Element "${e.name || e.id}": ${k} must be a number.`);
  }
  e.weight = Math.trunc(Number(e.weight) || 700);
  return e;
}

// Only what differs from the defaults, so files stay small and diffable.
export function compactElement(e) {
  const d = {};
  for (const [k, v] of Object.entries(e)) {
    if (["kind", "id", "x", "y", "w", "h"].includes(k) || !(k in ELEMENT_DEFAULTS) || JSON.stringify(v) !== JSON.stringify(ELEMENT_DEFAULTS[k])) d[k] = v;
  }
  return d;
}

export function elementKeys(e) {
  const out = [...templateKeys(e.text), ...templateKeys(e.src), ...templateKeys(e.fill), ...templateKeys(e.stroke),
    ...templateKeys(e.color)];
  if (e.show_when) out.push(e.show_when);
  return out;
}

export function elementShown(e, values) {
  if (e.visible === false) return false;
  if (!e.show_when) return true;
  const v = String(values[e.show_when] ?? "").trim();
  return !["", "0", "false", "False"].includes(v);
}

export function makeBoard(o = {}) {
  const b = { name: String(o.name ?? "Board"), id: String(o.id || newId()), width: Math.trunc(Number(o.width ?? 1920)),
    height: Math.trunc(Number(o.height ?? 1080)), background: String(o.background ?? ""), elements: [] };
  if (!(b.width >= 16 && b.width <= 8192 && b.height >= 16 && b.height <= 8192)) {
    throw new Error(`Board "${b.name}" is ${b.width} x ${b.height}; a board can be 16 to 8192 pixels each way.`);
  }
  b.elements = (o.elements || []).map(makeElement);
  return b;
}

export function compactBoard(b) {
  return { name: b.name, id: b.id, width: b.width, height: b.height, background: b.background,
    elements: b.elements.map(compactElement) };
}

export function boardKeys(b) {
  return [...new Set(b.elements.flatMap(elementKeys))];
}

export function bounds(b, ids) {
  const set = new Set(ids);
  const els = b.elements.filter((e) => set.has(e.id));
  if (!els.length) return null;
  return [Math.min(...els.map((e) => e.x)), Math.min(...els.map((e) => e.y)),
    Math.max(...els.map((e) => e.x + e.w)), Math.max(...els.map((e) => e.y + e.h))];
}

const r2 = (v) => Math.round(v * 100) / 100;

// Align to the selection's bounds, or to the canvas for one element.
export function align(b, ids, how) {
  const set = new Set(ids);
  const els = b.elements.filter((e) => set.has(e.id));
  if (!els.length) return;
  const [x1, y1, x2, y2] = els.length === 1 ? [0, 0, b.width, b.height] : bounds(b, ids);
  for (const e of els) {
    if (how === "left") e.x = x1;
    else if (how === "right") e.x = x2 - e.w;
    else if (how === "hcenter") e.x = r2((x1 + x2) / 2 - e.w / 2);
    else if (how === "top") e.y = y1;
    else if (how === "bottom") e.y = y2 - e.h;
    else if (how === "vcenter") e.y = r2((y1 + y2) / 2 - e.h / 2);
    else throw new Error(how);
  }
}

// Equal gaps between three or more elements. axis: h | v
export function distribute(b, ids, axis) {
  const set = new Set(ids);
  const els = b.elements.filter((e) => set.has(e.id));
  if (els.length < 3) return;
  const [p, s] = axis === "h" ? ["x", "w"] : ["y", "h"];
  els.sort((a, c) => a[p] - c[p]);
  const span = els.at(-1)[p] + els.at(-1)[s] - els[0][p];
  const gap = (span - els.reduce((n, e) => n + e[s], 0)) / (els.length - 1);
  let pos = els[0][p];
  for (const e of els) { e[p] = r2(pos); pos += e[s] + gap; }
}

// where: front | back | forward | backward
export function reorder(b, eid, where) {
  const i = b.elements.findIndex((e) => e.id === eid);
  if (i < 0) throw new Error(eid);
  const [e] = b.elements.splice(i, 1);
  if (where === "front") b.elements.push(e);
  else if (where === "back") b.elements.unshift(e);
  else if (where === "forward") b.elements.splice(Math.min(b.elements.length, i + 1), 0, e);
  else if (where === "backward") b.elements.splice(Math.max(0, i - 1), 0, e);
  else { b.elements.splice(i, 0, e); throw new Error(where); }
}

export function copyBoard(b) {
  const c = structuredClone(b);
  c.id = newId();
  for (const e of c.elements) e.id = newId();
  return c;
}
