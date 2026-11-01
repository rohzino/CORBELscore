// Keyboard shortcuts written the way TeleScore 2 projects store them (Qt's
// portable text): modifiers Ctrl+Alt+Shift+Meta then the key, e.g. "Ctrl+Space",
// "Q", "[", "F5". Old and new files share the same strings.

const NAMES = { " ": "Space", Enter: "Return", Escape: "Esc", ArrowLeft: "Left", ArrowRight: "Right", ArrowUp: "Up", ArrowDown: "Down",
  PageUp: "PgUp", PageDown: "PgDown", Delete: "Del", Insert: "Ins", Backspace: "Backspace", Tab: "Tab", Home: "Home", End: "End" };
const MODS = ["Control", "Alt", "Shift", "Meta", "AltGraph", "CapsLock", "OS"];

export function fromEvent(e) {
  if (MODS.includes(e.key)) return "";
  let key = NAMES[e.key] ?? e.key;
  if (/^Key[A-Z]$/.test(e.code) && (e.ctrlKey || e.altKey || e.metaKey)) key = e.code.slice(3);   // Ctrl+A whatever the layout
  else if (/^Digit\d$/.test(e.code) && (e.ctrlKey || e.altKey || e.metaKey)) key = e.code.slice(5);
  if (key.length === 1) key = key.toUpperCase();
  const mods = [];
  if (e.ctrlKey) mods.push("Ctrl");
  if (e.altKey) mods.push("Alt");
  // Shift is part of a symbol (Shift+1 = "!"), so it only counts for named keys and letters.
  if (e.shiftKey && (key.length > 1 || /[A-Z0-9]/.test(key))) mods.push("Shift");
  if (e.metaKey) mods.push("Meta");
  return [...mods, key].join("+");
}

export function normalise(s) {
  if (!s) return "";
  const parts = String(s).split("+").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return "";
  let key = parts.pop();
  const lower = key.toLowerCase();
  const named = { space: "Space", enter: "Return", return: "Return", esc: "Esc", escape: "Esc", left: "Left", right: "Right", up: "Up", down: "Down",
    pgup: "PgUp", pgdown: "PgDown", del: "Del", delete: "Del", ins: "Ins", backspace: "Backspace", tab: "Tab", home: "Home", end: "End" };
  key = named[lower] ?? (/^f\d{1,2}$/.test(lower) ? lower.toUpperCase() : key.length === 1 ? key.toUpperCase() : key);
  const mods = new Set(parts.map((m) => ({ ctrl: "Ctrl", control: "Ctrl", alt: "Alt", shift: "Shift", meta: "Meta", cmd: "Meta", win: "Meta" })[m.toLowerCase()]).filter(Boolean));
  return [...["Ctrl", "Alt", "Shift", "Meta"].filter((m) => mods.has(m)), key].join("+");
}

// Safe while typing in a box, and for background (global) shortcuts.
export function isGlobalSafe(s) {
  const n = normalise(s);
  if (!n) return false;
  const parts = n.split("+");
  const key = parts.pop();
  return parts.some((m) => ["Ctrl", "Alt", "Meta"].includes(m)) || /^F\d{1,2}$/.test(key);
}

export const typing = (el) => !!el && (el.isContentEditable || (el.tagName === "INPUT" && !["checkbox", "radio", "button", "range", "color"].includes(el.type)) || el.tagName === "TEXTAREA" || el.tagName === "SELECT");

// ---- Mac ------------------------------------------------------------------------------------
// Stored shortcuts never change: "Ctrl" is the Control key (⌃) on every computer, as in
// TeleScore files. On a Mac the app's own commands (Save, Open, undo, Pop out…) answer to ⌘
// instead, and keys are shown with Mac symbols. `mac` can be forced, for tests.
const detectMac = () => typeof navigator !== "undefined" && /Mac/i.test(navigator.platform || navigator.userAgent || "");
export const isMac = (mac) => mac ?? detectMac();

// The key as an app command sees it: ⌘S is "Ctrl+S" (the Windows spelling the handlers know),
// ⌘1 / ⌘2 are F1 / F2. ⌃ combos stay as they are, so ⌃Z still undoes the design as well.
export function appCombo(combo, mac) {
  if (!isMac(mac) || !combo) return combo;
  const parts = combo.split("+");
  const key = parts.pop();
  if (!parts.includes("Meta") || parts.includes("Ctrl")) return combo;
  if (key === "1" || key === "2") return parts.length === 1 ? `F${key}` : combo;
  return normalise([...parts.map((m) => (m === "Meta" ? "Ctrl" : m)), key].join("+"));
}

// The key as a project shortcut sees it. Only undo and redo also answer to ⌘, so the Edit menu's
// ⌘Z works in Locked mode, where the template shortcuts Ctrl+Z / Ctrl+Y undo and redo the score.
export function hotkeyCombo(combo, mac) {
  if (!isMac(mac)) return combo;
  const n = normalise(combo);
  if (n === "Meta+Z") return "Ctrl+Z";
  if (n === "Shift+Meta+Z") return "Ctrl+Y";   // fromEvent writes modifiers Ctrl, Alt, Shift, Meta
  return combo;
}

// ⌘Z / ⌘⇧Z as the keyboard sends them: "undo", "redo", or "" for any other key.
export function undoKey(combo, mac) {
  if (!isMac(mac)) return "";
  const n = normalise(combo);
  return n === "Meta+Z" ? "undo" : n === "Shift+Meta+Z" ? "redo" : "";
}

// How a key is written for people. `app` is for the app's own commands, where Ctrl means ⌘ on a Mac.
const SYMBOLS = { Ctrl: "⌃", Alt: "⌥", Shift: "⇧", Meta: "⌘", Space: "Space", Return: "↩", Esc: "⎋", Left: "←", Right: "→", Up: "↑", Down: "↓", Backspace: "⌫", Del: "⌦", Tab: "⇥" };
export function display(s, { app = false, mac } = {}) {
  if (!s || !isMac(mac)) return s;
  const parts = String(s).split("+");
  const key = parts.pop();
  const mods = parts.map((m) => (app && m === "Ctrl" ? "Meta" : m));
  // Mac order: ⌃ ⌥ ⇧ ⌘.
  return [...["Ctrl", "Alt", "Shift", "Meta"].filter((m) => mods.includes(m)).map((m) => SYMBOLS[m]), SYMBOLS[key] ?? key].join("");
}
