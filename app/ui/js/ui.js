// Shared UI pieces: per-window state, menus, dialogs, toasts, form rows.

import { h, button, noteCommit } from "./dom.js";

// Window state, remembered between sessions where it helps.
const saved = (() => { try { return JSON.parse(localStorage.getItem("ts-ui") || "{}"); } catch { return {}; } })();
export const ui = {
  tab: saved.tab ?? "control",          // control | view
  mode: saved.mode ?? "locked",         // edit | locked
  page: saved.page ?? null,             // control page id
  side: saved.side ?? "fields",         // left panel in Edit
  viewSection: saved.viewSection ?? "graphics",
  gside: saved.gside ?? "elements",     // designer left panel
  board: saved.board ?? null,           // designer board id
  liveBoard: saved.liveBoard ?? null,
  liveBg: saved.liveBg ?? "checker",
  sel: null,                            // control selection: {kind: "tile"|"field"|"button"|"page", id}
  gsel: [],                             // designer selection (element ids)
  gpick: null,                          // designer: {kind: "condition"|"animation", id}
  split: saved.split ?? false,          // designer: live controls beside the canvas
  splitPage: saved.splitPage ?? null,   // the control page shown there
  splitH: saved.splitH ?? 300,          // its height in px
  safe: saved.safe ?? false,            // designer: title- and action-safe guides
};
// This page as a pop-out window: "control" or "view" (from ?panel=), else null.
export const PANEL = (() => { const p = new URLSearchParams(location.search).get("panel"); return p === "control" || p === "view" ? p : null; })();
if (PANEL) ui.tab = PANEL;

// Told whenever the page, mode or section changes (a pop-out refits its scale).
export const uiChanged = new Set();
export function remember() {
  const { sel, gsel, gpick, ...keep } = ui;
  try { localStorage.setItem("ts-ui", JSON.stringify(keep)); } catch { /* */ }
  for (const fn of uiChanged) { try { fn(); } catch (e) { console.error(e); } }
}

// Key handlers the Control and View tabs register while they want keys first.
export const editKeys = new Set();
export function claimKeys(handler) { editKeys.add(handler); return () => editKeys.delete(handler); }

// ---- toasts -------------------------------------------------------------------
export function toast(text, alert = false, ms = 3200) {
  const t = h(`div.toast${alert ? ".alert" : ""}`, { role: alert ? "alert" : "status" }, text);
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), alert ? Math.max(ms, 6000) : ms);
}

// Run a request and show what went wrong, in words, if it fails.
export async function attempt(fn, okText = "") {
  try { const r = await fn(); if (okText) toast(okText); return r; } catch (e) { toast(e.message, true); return undefined; }
}

// ---- menus --------------------------------------------------------------------
let openMenu = null;
export function closeMenu() { openMenu?.remove(); openMenu = null; }
document.addEventListener("pointerdown", (e) => { if (openMenu && !openMenu.contains(e.target)) closeMenu(); }, true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && openMenu) { closeMenu(); e.stopPropagation(); } }, true);

// items: [{label, run, kbd, disabled}] | "-" | {title}
export function menu(anchor, items) {
  closeMenu();
  const m = h("div.menu", { role: "menu" });
  for (const it of items) {
    if (it === "-") m.appendChild(h("hr"));
    else if (it.title) m.appendChild(h("div.mlabel.caps", it.title));
    else m.appendChild(h("button", { type: "button", role: "menuitem", disabled: !!it.disabled, onclick: () => { closeMenu(); it.run(); } },
      h("span", it.label), it.kbd ? h("span.kbd", it.kbd) : null));
  }
  document.body.appendChild(m);
  const r = anchor.getBoundingClientRect ? anchor.getBoundingClientRect() : { left: anchor.x, bottom: anchor.y, top: anchor.y, right: anchor.x };
  const mr = m.getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(innerWidth - mr.width - 4, r.left)) + "px";
  m.style.top = (r.bottom + mr.height + 4 > innerHeight ? Math.max(4, r.top - mr.height - 4) : r.bottom + 4) + "px";
  openMenu = m;
  m.querySelector("button:not(:disabled)")?.focus();
  m.addEventListener("keydown", (e) => {
    const bs = [...m.querySelectorAll("button:not(:disabled)")];
    const i = bs.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { bs[(i + 1) % bs.length]?.focus(); e.preventDefault(); }
    if (e.key === "ArrowUp") { bs[(i - 1 + bs.length) % bs.length]?.focus(); e.preventDefault(); }
  });
  return m;
}

// ---- dialogs ------------------------------------------------------------------
// Resolves with the clicked button's value (or null when dismissed).
export function dialog(title, body, buttons = [{ label: "OK", value: true, role: "accent" }]) {
  return new Promise((resolve) => {
    const d = h("dialog", { "aria-label": title });
    const done = (v) => { d.close(); d.remove(); resolve(v); };
    d.append(h("div.dlg-body", h("h2", title), body),
      h("div.dlg-foot", buttons.map((b) => button(b.label, () => done(typeof b.value === "function" ? b.value(d) : b.value), { role: b.role || "" }))));
    d.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
    document.body.appendChild(d);
    d.showModal();
    const first = d.querySelector("input, select, textarea") || d.querySelector(".btn-accent") || d.querySelector("button");
    first?.focus();
    d.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); d.querySelector(".dlg-foot .btn-accent")?.click(); }
    });
  });
}

export async function ask(title, label, value = "", { placeholder = "", ok = "OK" } = {}) {
  const input = h("input.input", { value, placeholder, "aria-label": label });
  const r = await dialog(title, h("label.col", h("span.caps", label), input), [{ label: "Cancel", value: null }, { label: ok, role: "accent", value: () => input.value }]);
  return r === null ? null : String(r).trim();
}

export const confirmDialog = (title, text, ok = "OK", role = "accent") =>
  dialog(title, h("p", { style: { margin: 0 } }, text), [{ label: "Cancel", value: false }, { label: ok, value: true, role }]);

// ---- form rows ------------------------------------------------------------------
// Commit on Enter or leaving the box (never on every key), so live updates
// from the service never fight the typing.
export function textInput(value, commit, { k, placeholder = "", type = "text", title = "", list = undefined, cls = "" } = {}) {
  const el = h(`input.input${cls ? "." + cls : ""}`, { value: value ?? "", placeholder, type, title, "data-k": k, list, spellcheck: false });
  let last = el.value;
  const go = () => { if (el.value !== last) { last = el.value; noteCommit(el); commit(el.value, el); } };
  el.addEventListener("change", go);
  el.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); if (e.key === "Escape") { el.value = last; el.blur(); } });
  return el;
}

export function numberInput(value, commit, { k, min, max, step = 1, suffix = "", title = "" } = {}) {
  const el = h("input.input", { type: "number", value, min, max, step, "data-k": k, title });
  el.addEventListener("change", () => {
    let v = Number(el.value);
    if (!Number.isFinite(v)) { el.value = value; return; }
    if (min !== undefined) v = Math.max(min, v);
    if (max !== undefined) v = Math.min(max, v);
    el.value = v;
    noteCommit(el);
    commit(v);
  });
  return suffix ? h("div.row", el, h("span.muted.small", suffix)) : el;
}

export function select(options, value, commit, { k, title = "" } = {}) {
  const el = h("select.input", { "data-k": k, title }, options.map((o) => {
    const [v, label] = Array.isArray(o) ? o : [o, o];
    return h("option", { value: v, selected: String(v) === String(value) }, label);
  }));
  el.addEventListener("change", () => { noteCommit(el); commit(el.value); });
  return el;
}

export function check(label, value, commit, { k, title = "" } = {}) {
  const box = h("input", { type: "checkbox", checked: !!value, "data-k": k });
  box.addEventListener("change", () => { noteCommit(box); commit(box.checked); });
  return h("label.check", { title }, box, label);
}

// Colour: a swatch (picker) plus a text box that also takes templates like {home.color}.
export function colorInput(value, commit, { k, placeholder = "none" } = {}) {
  const swatchFill = h("i");
  const paint = (v) => { swatchFill.style.background = /^#[0-9a-f]{3,8}$/i.test(v) ? v : "transparent"; };
  paint(value);
  const picker = h("input", { type: "color", value: /^#[0-9a-f]{6}/i.test(value) ? value.slice(0, 7) : "#ffffff", title: "Pick a colour" });
  const text = textInput(value, (v) => { paint(v); commit(v); }, { k, placeholder });
  picker.addEventListener("change", () => { const keepAlpha = /^#[0-9a-f]{8}$/i.test(text.value) ? text.value.slice(7) : ""; text.value = picker.value + keepAlpha; paint(text.value); commit(text.value); });
  return h("div.row", h("label.swatch", swatchFill, picker), text);
}

// 0..1 shown as 0..100 %: a slider for feel, a box for exact numbers. preview(v)
// runs while dragging; commit(v) once on release or Enter.
export function percentInput(value, commit, { k, preview = null, title = "" } = {}) {
  const pct = Math.round((Number(value) || 0) * 100);
  const range = h("input.range", { type: "range", min: 0, max: 100, step: 1, value: pct, "data-k": k ? `${k}-r` : undefined, title, "aria-label": title || "Opacity" });
  const box = h("input.input", { type: "number", min: 0, max: 100, step: 1, value: pct, "data-k": k, style: { width: "64px", flex: "none" } });
  const clamp = (v) => Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
  range.addEventListener("input", () => { box.value = range.value; preview?.(clamp(range.value) / 100); });
  range.addEventListener("change", () => { noteCommit(range); commit(clamp(range.value) / 100); });
  box.addEventListener("change", () => { const v = clamp(box.value); box.value = v; range.value = v; noteCommit(box); commit(v / 100); });
  return h("div.row", range, box, h("span.muted.small", "%"));
}

export const formRow = (label, control, hint = "") => [h("label", label), control, hint ? h("div.hint", hint) : null];
