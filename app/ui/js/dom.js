// Small DOM helpers. h("div.card#id", {props}, children...) builds elements;
// props starting with "on" become listeners; "style" may be an object;
// data-* and aria-* are attributes.

export function h(tag, props, ...kids) {
  const m = /^([a-z0-9-]+)?((?:[.#][\w-]+)*)$/i.exec(tag);
  const el = document.createElement(m?.[1] || "div");
  for (const part of (m?.[2] || "").match(/[.#][\w-]+/g) || []) {
    if (part[0] === ".") el.classList.add(part.slice(1)); else el.id = part.slice(1);
  }
  if (props && (typeof props !== "object" || props instanceof Node || Array.isArray(props))) { kids.unshift(props); props = null; }
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "class") el.className += " " + v;
    else if (k.startsWith("data-") || k.startsWith("aria-") || k === "role" || k === "for" || k === "list") el.setAttribute(k, v === true ? "" : v);
    else if (k in el) el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  append(el, kids);
  return el;
}

export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false || k === true) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

export const clear = (el) => { el.textContent = ""; return el; };

// Re-render a container but keep keyboard focus, caret and scroll where they
// were (by data-k), so an update from the service never steals typing.
export function rerender(el, build) {
  const active = document.activeElement;
  const k = active && el.contains(active) ? active.dataset.k : null;
  const sel = k && "selectionStart" in active ? [active.selectionStart, active.selectionEnd] : null;
  const scrolls = [...el.querySelectorAll("[data-scroll]")].map((s) => [s.dataset.scroll, s.scrollTop]);
  const top = el.scrollTop;
  clear(el);
  append(el, [build()]);
  el.scrollTop = top;
  for (const [id, y] of scrolls) { const s = el.querySelector(`[data-scroll="${id}"]`); if (s) s.scrollTop = y; }
  if (k) {
    const again = el.querySelector(`[data-k="${CSS.escape(k)}"]`);
    if (again) { again.focus({ preventScroll: true }); if (sel && "setSelectionRange" in again) { try { again.setSelectionRange(...sel); } catch { /* */ } } }
  }
}

export const caps = (text, extra = {}) => h("span.caps", extra, text);

export function button(text, onClick, { role = "", big = false, title = "", k = undefined, disabled = false, cls = "" } = {}) {
  return h(`button.btn${role ? ".btn-" + role : ""}${big ? ".btn-big" : ""}${cls ? "." + cls : ""}`, { type: "button", onclick: onClick, title, "data-k": k, disabled }, text);
}

// A chip is always a colour and a word (Rally): LIVE, RUNNING, OFF.
export const chip = (word, kind = "muted", title = "") => h(`span.chip.chip-${kind}`, { title }, word);

export function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

export function kbd(keys) { return h("span.kbd", keys); }
