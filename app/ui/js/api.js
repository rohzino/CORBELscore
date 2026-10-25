// The window's connection to the TeleScore service: requests and a live
// stream of state (project, status, values, notices).

export const KEY = new URLSearchParams(location.search).get("key") || sessionStorage.getItem("ts-key") || "";
try { sessionStorage.setItem("ts-key", KEY); } catch { /* */ }

export async function call(path, body = {}) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-TeleScore-Key": KEY }, body: JSON.stringify(body) });
  let d;
  try { d = await r.json(); } catch { throw new Error(`TeleScore answered ${r.status}.`); }
  if (!d.ok) throw new Error(d.error || "That did not work.");
  return d;
}

export const fileUrl = (p) => `/file?key=${encodeURIComponent(KEY)}&path=${encodeURIComponent(p)}`;

// The store: the latest of everything, and who to tell when it changes.
export const store = { state: null, project: null, status: {}, snapshot: null, settings: {}, connected: false };
const listeners = {};
export function on(ev, fn) { (listeners[ev] ??= new Set()).add(fn); return () => listeners[ev].delete(fn); }
export function emit(ev, data) { for (const fn of listeners[ev] ?? []) { try { fn(data); } catch (e) { console.error(ev, e); } } }

export function connect() {
  const es = new EventSource(`/api/events?key=${encodeURIComponent(KEY)}`);
  const handle = (name, fn) => es.addEventListener(name, (ev) => fn(JSON.parse(ev.data)));
  handle("state", (s) => {
    store.state = s; store.project = s.project; store.status = s.status; store.snapshot = s.snapshot; store.settings = s.settings;
    store.connected = true;
    emit("state", s); emit("project", s.project); emit("status", s.status); if (s.snapshot) emit("snap", s.snapshot);
  });
  handle("project", (p) => { store.project = p; emit("project", p); });
  handle("status", (s) => { store.status = s; emit("status", s); });
  handle("snap", (s) => { store.snapshot = s; emit("snap", s); });
  handle("settings", (s) => { store.settings = s; emit("settings", s); });
  handle("notice", (n) => emit("notice", n));
  handle("expired", (x) => emit("expired", x));
  es.onerror = () => { if (store.connected) { store.connected = false; emit("disconnected"); } };
  es.onopen = () => { if (!store.connected && store.state) emit("reconnected"); };
}

// Design edits: one or more ops as a single undo step.
export const edit = (ops, label = "") => call("/api/edit", { ops: Array.isArray(ops) ? ops : [ops], label });
// Scoring actions.
export const act = (action) => call("/api/action", { action });
