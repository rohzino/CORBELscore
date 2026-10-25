// The TeleScore window: header, the two tabs, the start page, file commands,
// notices and the keyboard.

import { act, call, connect, edit, on, store } from "./api.js";
import { applyScheme, DEFAULT_SCHEME, SCHEMES } from "./colors.js";
import { button, chip, clear, h, kbd } from "./dom.js";
import { fromEvent, isGlobalSafe, normalise, typing } from "./keys.js";
import { attempt, closeMenu, confirmDialog, dialog, editKeys, menu, remember, toast, ui } from "./ui.js";
import { mountControl } from "./control.js";
import { mountView } from "./view.js";

const head = document.getElementById("head");
const main = document.getElementById("main");
const noticeEl = document.getElementById("notice");
let mounted = null;      // { name, unmount }
let scheme = DEFAULT_SCHEME;

applyScheme(scheme);

// ---- header ---------------------------------------------------------------------
function renderHead() {
  const p = store.project;
  const st = store.status || {};
  clear(head);
  head.append(h("span.brand", "TeleScore"));
  if (p) {
    const name = h("input.proj", { value: p.name, "aria-label": "Project name", title: "Project name. Click to rename.", spellcheck: false, size: Math.max(4, p.name.length + 1) });
    name.addEventListener("change", () => edit({ op: "meta", name: name.value }, "Rename project").catch((e) => toast(e.message, true)));
    name.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === "Escape") { if (e.key === "Escape") name.value = p.name; name.blur(); } });
    head.append(name, h("span.saved", !p.path ? "Not saved yet" : st.dirty ? "Unsaved changes" : "Saved"));
    const tabs = h("nav.tabs", { role: "tablist" },
      [["control", "Control"], ["view", "View"]].map(([id, label]) => h("button", { role: "tab", "aria-selected": String(ui.tab === id), onclick: () => setTab(id),
        title: id === "control" ? "Design your controls and run the game (F1)" : "Design the on-air graphics and watch them live (F2)" }, label)));
    head.append(tabs);
  }
  head.append(h("span.spacer"));
  if (p) head.append(lights(st));
  head.append(button("File", (e) => fileMenu(e.currentTarget), { title: "New, open, save" }),
    button("Settings", (e) => settingsMenu(e.currentTarget), { title: "Colours and shortcuts" }));
}

function light(word, state, title) {
  const cls = { live: "ok", ok: "ok", connecting: "busy", busy: "busy", stale: "busy", error: "error" }[state] || "";
  return h("span.light", { title }, h(`span.dot${cls ? ".dot-" + cls : ""}`), word);
}

function lights(st) {
  const files = Object.values(st.files || {});
  const fstate = files.some((f) => f.state === "error") ? "error" : files.some((f) => f.state === "ok") ? "ok" : "off";
  const live = st.live?.state ?? "off";
  const web = st.web?.running ? "ok" : st.web?.error ? "error" : "off";
  return h("div.lights",
    light("Live", live, { off: "No live data", live: "Live data arriving", connecting: "Connecting to live data", stale: "Live data has gone quiet", error: st.live?.detail }[live] || ""),
    light("Files", fstate, fstate === "error" ? files.find((f) => f.state === "error")?.detail : fstate === "ok" ? `Writing to ${st.folder}` : "File outputs are off"),
    light("Web", web, web === "ok" ? `Browser sources at ${st.web.url} · ${st.web.clients} connected` : st.web?.error || "The web server is off"));
}

// A new or opened project starts fresh: its first page, the right mode, Control.
// The window may already have drawn it (the service announces it before the
// request returns), so draw it again with these settings.
function freshView(mode) {
  Object.assign(ui, { page: null, sel: null, board: null, mode, tab: "control" });
  remember();
  mounted?.unmount?.();
  mounted = null;
  clear(main);
  renderHead();
  renderMain();
}

function setTab(id) {
  ui.tab = id;
  remember();
  renderHead();
  renderMain();
}

// ---- main area ---------------------------------------------------------------------
function renderMain() {
  const want = store.project ? ui.tab : "start";
  if (mounted?.name === want) return;
  mounted?.unmount?.();
  clear(main);
  if (want === "start") mounted = { name: "start", unmount: startPage(main) };
  else if (want === "control") mounted = { name: "control", unmount: mountControl(main) };
  else mounted = { name: "view", unmount: mountView(main) };
}

function templateCards(onPick) {
  const st = store.state;
  return h("div.templates", st.presets.map((name) => h(`button.tcard${name === "General scoreboard" ? ".primary" : ""}`, { type: "button", onclick: () => onPick(name) },
    h("span.t", name), h("span.hint", st.blurbs[name] || ""))));
}

function startPage(el) {
  const st = store.state;
  const recent = st.settings.recent || [];
  const rec = st.recovery;
  el.append(h("div.start",
    h("section",
      rec ? h("div.panel", { style: { marginBottom: "18px", borderColor: "var(--user)" } },
        h("h3", "Unsaved work was found"),
        h("p.hint", `TeleScore closed without saving “${rec.name}” (${rec.at?.replace("T", " ") ?? "recently"}).`),
        h("div.row", button("Restore it", () => attempt(() => call("/api/recovery", { restore: true })), { role: "accent" }),
          button("Discard", () => attempt(async () => { await call("/api/recovery", { restore: false }); store.state.recovery = null; renderStart(); }))))
        : null,
      h("div.section-title", "New project"),
      h("p.hint", "Start from a sport. Every field, control, shortcut and graphic can be changed afterwards."),
      templateCards((name) => newProject(name))),
    h("section",
      h("div.section-title", "Open"),
      h("div.col", button("Open a project…", () => openProject(), { big: true }),
        h("p.hint", "TeleScore 1.x projects and earlier 2.0 files open too. They are converted, and the original file is left as it is.")),
      h("div.section-title", { style: { marginTop: "18px" } }, "Recent"),
      recent.length ? h("div.list", recent.map((r) => h("div.item", { tabindex: 0, title: r.path, onclick: () => openProject(r.path), onkeydown: (e) => e.key === "Enter" && openProject(r.path) },
        h("div.grow", h("div.name", r.name), h("div.sub", `${new Date(r.mtime).toLocaleString()} · ${r.folder}`)))))
        : h("p.hint", "Projects you open appear here."))));
  return () => {};
}
function renderStart() { if (mounted?.name === "start") { mounted = null; renderMain(); } }

// ---- files ---------------------------------------------------------------------------
async function guarded(op, body) {
  let r = await attempt(() => call("/api/file", { op, ...body }));
  if (r?.needsConfirm) {
    const choice = await dialog("Save changes?", h("p", { style: { margin: 0 } }, `Save the changes to ${store.project?.name ?? "this project"} first?`),
      [{ label: "Cancel", value: null }, { label: "Don't save", value: "discard", role: "alert" }, { label: "Save", value: "save", role: "accent" }]);
    if (!choice) return null;
    if (choice === "save" && !(await save())) return null;
    r = await attempt(() => call("/api/file", { op, ...body, force: true }));
  }
  return r;
}

async function newProject(preset) {
  const r = await guarded("new", { preset });
  if (r) freshView(preset === "Blank project" ? "edit" : "locked");
}

function newDialog() {
  let pick = null;
  const d = dialog("New project", h("div.col", h("p.hint", "Start from a sport."), templateCards((name) => { pick = name; document.querySelector("dialog .dlg-foot .btn")?.click(); })),
    [{ label: "Cancel", value: null }]);
  d.then(() => { if (pick) newProject(pick); });
}

async function openProject(path) {
  const r = await guarded("open", { path });
  if (r && !r.cancelled) {
    freshView("locked");
    if (r.imported && r.notes?.length) {
      dialog("Converted", h("div.col", h("p.hint", "This project came from an older TeleScore. Save it as a new .tsproj file; the original stays as it was."),
        h("ul", { style: { margin: 0, paddingLeft: "18px" } }, r.notes.map((n) => h("li.small", n)))));
    }
  }
}

async function save(as = false) {
  if (!store.project) return false;
  let path;
  if ((as || !store.project.path) && !store.state.host.dialogs) {
    const { ask } = await import("./ui.js");
    path = await ask("Save project", "Full path of the .tsproj file", store.project.path || `${store.project.name}.tsproj`);
    if (!path) return false;
  }
  const r = await attempt(() => call("/api/file", { op: as ? "saveAs" : "save", path }));
  if (r?.path) { toast(`Saved ${r.path.split(/[\\/]/).pop()}.`); return true; }
  return false;
}

function fileMenu(anchor) {
  const p = store.project;
  menu(anchor, [
    { label: "New project…", run: newDialog, kbd: "Ctrl+N" },
    { label: "Open…", run: () => openProject(), kbd: "Ctrl+O" },
    "-",
    { label: "Save", run: () => save(), kbd: "Ctrl+S", disabled: !p },
    { label: "Save as…", run: () => save(true), kbd: "Ctrl+Shift+S", disabled: !p },
    "-",
    ...(store.state.settings.recent || []).slice(0, 6).map((r) => ({ label: `Open ${r.name}`, run: () => openProject(r.path) })),
    ...(store.state.settings.recent?.length ? ["-"] : []),
    { label: "Close project", run: () => guarded("close"), disabled: !p },
  ]);
}

function settingsMenu(anchor) {
  const s = store.settings;
  const host = store.state.host;
  menu(anchor, [
    { title: "Colours" },
    ...Object.keys(SCHEMES).map((name) => ({ label: (name === scheme ? "● " : "○ ") + name, run: () => setScheme(name) })),
    "-",
    { label: `${s.global_keys ? "☑" : "☐"} Shortcuts work while TeleScore is in the background`, disabled: !host.globalKeys,
      run: () => attempt(() => call("/api/settings", { global_keys: !s.global_keys })) },
    "-",
    { label: "Browser sources and feeds", disabled: !store.status.web?.running, run: () => window.open(store.status.web.url, "_blank") },
    { label: "About TeleScore", run: about },
  ]);
}

function setScheme(name) {
  scheme = name;
  applyScheme(name);
  attempt(() => call("/api/settings", { scheme: name }));
}

function about() {
  dialog("About TeleScore", h("div.col",
    h("p", { style: { margin: 0 } }, h("b", `TeleScore ${store.state.version}`), " · open-source scoreboard and live scoring for streams and broadcast."),
    h("p.hint", "Community continuation of TeleScore by the JumpShot team (riscyseven, TheLittleDoctor, Fisk31, controldelta, SPCcleveland9035, Glenn). Licensed under the GNU Affero General Public License v3. Archivo font © The Archivo Project Authors, SIL Open Font License 1.1.")));
}

// ---- notices ---------------------------------------------------------------------------
let noticeT = 0;
function notice(text, alert = false, ms = 0) {
  clearTimeout(noticeT);
  clear(noticeEl);
  noticeEl.className = "notice" + (alert ? " alert" : "");
  noticeEl.append(h("span.grow", text), button("Dismiss", () => clear(noticeEl), { role: "ghost", cls: "btn-sm" }));
  if (ms) noticeT = setTimeout(() => clear(noticeEl), ms);
}

// ---- keyboard --------------------------------------------------------------------------
// Shortcuts run anywhere in the window. While typing in a box only Ctrl, Alt
// and F-key shortcuts fire, so typing a name never scores a point.

document.addEventListener("keydown", (e) => {
  if (document.querySelector("dialog[open]")) return;
  const combo = fromEvent(e);
  if (!combo) return;
  if (combo === "Ctrl+S") { e.preventDefault(); save(); return; }
  if (combo === "Ctrl+Shift+S") { e.preventDefault(); save(true); return; }
  if (combo === "Ctrl+O") { e.preventDefault(); openProject(); return; }
  if (combo === "Ctrl+N") { e.preventDefault(); newDialog(); return; }
  if (combo === "F1" && store.project) { e.preventDefault(); setTab("control"); return; }
  if (combo === "F2" && store.project) { e.preventDefault(); setTab("view"); return; }
  for (const handler of editKeys) if (handler(e, combo)) { e.preventDefault(); return; }
  if (!store.project) return;
  if (typing(document.activeElement) && !isGlobalSafe(combo)) return;
  // Background (system-wide) shortcuts are switched off while this window has focus, so the window always handles its own keys.
  const b = store.project.buttons.find((x) => x.hotkey && normalise(x.hotkey) === combo);
  if (b) {
    e.preventDefault();
    if (e.repeat) return;
    act(b.action).catch((err) => toast(err.message, true));
    document.querySelectorAll(`[data-button="${CSS.escape(b.id)}"]`).forEach((x) => { x.classList.remove("flash"); void x.offsetWidth; x.classList.add("flash"); });
  }
});

// ---- buzzer -------------------------------------------------------------------------------
on("expired", async (x) => {
  if (!x.buzzer) return;
  try { const { fileUrl } = await import("./api.js"); await new Audio(fileUrl(x.buzzer)).play(); } catch { toast(`Could not play the buzzer for ${x.label}.`, true); }
});

// ---- wiring -------------------------------------------------------------------------------
let lastHad = null;
on("state", (s) => {
  if (s.settings?.scheme && s.settings.scheme !== scheme) { scheme = s.settings.scheme; applyScheme(scheme); }
  lastHad = !!s.project;
  renderHead();
  mounted?.unmount?.();
  mounted = null;
  clear(main);
  renderMain();
});
on("project", (p) => {
  const has = !!p;
  if (has !== lastHad) { lastHad = has; mounted?.unmount?.(); mounted = null; clear(main); renderMain(); }
  renderHead();
  if (!has && mounted?.name === "start") renderStart();
});
on("status", () => renderHead());
on("settings", (s) => { if (s.scheme && s.scheme !== scheme) { scheme = s.scheme; applyScheme(scheme); } });
on("notice", (n) => notice(n.text, n.alert, n.alert ? 0 : 5000));
on("disconnected", () => notice("Lost contact with the TeleScore service. Reconnecting…", true));
on("reconnected", () => notice("Reconnected.", false, 2000));
window.addEventListener("blur", closeMenu);
connect();
