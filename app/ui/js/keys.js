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
