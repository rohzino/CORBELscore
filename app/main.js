// TeleScore's desktop shell (Electron). Everything that matters runs in the
// service (app/service); this file only gives it a window and the few things a
// browser page cannot do: file dialogs, projector windows on other displays,
// PNG capture, background shortcuts and opening folders.

import { app, BrowserWindow, dialog, globalShortcut, screen, shell, Menu, nativeImage } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { App } from "./service/app.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ICON = path.join(HERE, "assets", "icon.ico");

// The self-check keeps its own settings, so it never touches the real ones.
if (process.env.TELESCORE_SMOKE) app.setPath("userData", path.join(process.env.TELESCORE_SMOKE, "data"));
else if (!app.requestSingleInstanceLock()) app.quit();

let win = null;
let service = null;
let quitting = false;

// ---- dialogs ----------------------------------------------------------------------------------
const FILTERS = {
  project: [{ name: "TeleScore projects", extensions: ["tsproj", "json", "tsp"] }, { name: "All files", extensions: ["*"] }],
  save: [{ name: "TeleScore project", extensions: ["tsproj"] }],
  image: [{ name: "Pictures", extensions: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"] }],
  sound: [{ name: "Sounds", extensions: ["wav", "mp3", "ogg", "m4a", "aac", "flac"] }],
  data: [{ name: "Score data", extensions: ["xml", "json", "txt"] }, { name: "All files", extensions: ["*"] }],
};

async function pick(kind, opts = {}) {
  const parent = BrowserWindow.getFocusedWindow() ?? win;
  if (kind === "save") {
    const r = await dialog.showSaveDialog(parent, { title: "Save project", defaultPath: path.join(app.getPath("documents"), opts.name || "Untitled.tsproj"), filters: FILTERS.save });
    return r.canceled ? "" : r.filePath;
  }
  const r = await dialog.showOpenDialog(parent, {
    title: { project: "Open a project", image: "Choose a picture", sound: "Choose a sound", data: "Choose a data file", folder: "Choose a folder" }[kind] ?? "Choose",
    properties: kind === "folder" ? ["openDirectory", "createDirectory"] : ["openFile"],
    filters: FILTERS[kind],
  });
  return r.canceled ? "" : r.filePaths[0] ?? "";
}

// ---- projector windows ------------------------------------------------------------------------
function displays() {
  const primary = screen.getPrimaryDisplay().id;
  return screen.getAllDisplays().map((d, i) => ({ id: d.id, index: i, name: d.label || `Display ${i + 1}`, primary: d.id === primary,
    width: d.size.width, height: d.size.height }));
}

function openProjector(url, opts = {}) {
  const all = screen.getAllDisplays();
  const primary = screen.getPrimaryDisplay();
  // The chosen display, else the first one that is not the operator's screen.
  const target = all.find((d) => d.id === Number(opts.display)) ?? all.find((d) => d.id !== primary.id) ?? null;
  const w = new BrowserWindow({
    title: "TeleScore projector", icon: ICON, backgroundColor: "#000000", autoHideMenuBar: true,
    ...(target ? { x: target.bounds.x, y: target.bounds.y, width: target.bounds.width, height: target.bounds.height, fullscreen: true }
      : { width: 1280, height: 720 }),
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  w.setMenu(null);
  // F11 toggles full screen, Esc leaves it.
  w.webContents.on("before-input-event", (e, input) => {
    if (input.type !== "keyDown") return;
    if (input.key === "F11") { w.setFullScreen(!w.isFullScreen()); e.preventDefault(); }
    if (input.key === "Escape" && w.isFullScreen()) { w.setFullScreen(false); e.preventDefault(); }
  });
  w.loadURL(url);
}

// ---- PNG capture --------------------------------------------------------------------------------
// One hidden window per board, kept open: the board page updates itself live,
// so each capture is just a snapshot of what is already drawn.
const capturers = new Map();
async function capturePng(url, width, height) {
  const id = `${url}|${width}x${height}`;
  let c = capturers.get(id);
  if (!c || c.win.isDestroyed()) {
    const w = new BrowserWindow({ show: false, width, height, transparent: true, frame: false, useContentSize: true, enableLargerThanScreen: true,
      webPreferences: { offscreen: true, contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false } });
    w.webContents.setFrameRate(10);
    w.setContentSize(width, height);   // boards are often bigger than the screen
    c = { win: w, ready: w.loadURL(url).then(() => new Promise((r) => setTimeout(r, 1200))) };   // fonts and intro animations
    capturers.set(id, c);
  }
  await c.ready;
  await new Promise((r) => setTimeout(r, 120));   // let the newest values paint
  let img = await c.win.webContents.capturePage({ x: 0, y: 0, width, height });
  const got = img.getSize();
  if (got.width !== width || got.height !== height) img = img.resize({ width, height, quality: "best" });   // HiDPI screens
  return img.toPNG();
}

// ---- background shortcuts --------------------------------------------------------------------
// Off while the TeleScore window has focus (the window handles its own keys,
// and typing a team name must not fire Space), on while it does not.
let wanted = [];
const lastFired = new Map();

function accelerator(qt) {
  const parts = String(qt).split("+").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return "";
  const key = parts.pop();
  const mods = parts.map((m) => ({ ctrl: "Control", control: "Control", alt: "Alt", shift: "Shift", meta: "Super", cmd: "Super", win: "Super" })[m.toLowerCase()]).filter(Boolean);
  const named = { space: "Space", return: "Return", enter: "Return", esc: "Escape", escape: "Escape", left: "Left", right: "Right", up: "Up", down: "Down",
    pgup: "PageUp", pgdown: "PageDown", del: "Delete", delete: "Delete", ins: "Insert", backspace: "Backspace", tab: "Tab", home: "Home", end: "End" };
  const k = named[key.toLowerCase()] ?? (/^f\d{1,2}$/i.test(key) ? key.toUpperCase() : key.length === 1 ? key.toUpperCase() : "");
  return k ? [...mods, k].join("+") : "";
}

function applyShortcuts() {
  globalShortcut.unregisterAll();
  if (!win || win.isDestroyed() || win.isFocused()) return;
  for (const { key, run } of wanted) {
    const acc = accelerator(key);
    if (!acc) continue;
    try {
      globalShortcut.register(acc, () => {
        // Held keys repeat; one press is one action.
        const now = Date.now();
        if (now - (lastFired.get(acc) ?? 0) < 250) return;
        lastFired.set(acc, now);
        run();
      });
    } catch { /* taken by another program, or not a key Electron knows */ }
  }
}

// ---- the window ------------------------------------------------------------------------------
async function createWindow() {
  win = new BrowserWindow({
    title: "TeleScore", icon: nativeImage.createFromPath(ICON), width: 1440, height: 900, minWidth: 960, minHeight: 600,
    backgroundColor: "#0e1311", show: false, autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  win.setMenu(null);
  win.once("ready-to-show", () => { win.maximize(); win.show(); });
  win.on("focus", applyShortcuts);
  win.on("blur", applyShortcuts);
  // Links to other sites (help pages, the feeds page) open in the normal browser.
  win.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(service.studio.url("/"))) { e.preventDefault(); if (/^https?:/.test(url)) shell.openExternal(url); } });
  win.webContents.on("before-input-event", (e, input) => {
    if (input.type === "keyDown" && input.key === "F12" && input.control && input.shift) win.webContents.toggleDevTools();
  });
  win.on("close", async (e) => {
    if (quitting || !service?.dirty) return;
    e.preventDefault();
    const r = await dialog.showMessageBox(win, { type: "warning", title: "TeleScore", message: `Save changes to ${service.project?.name ?? "this project"}?`,
      detail: "If you don't save, your design changes since the last save are lost.", buttons: ["Save", "Don't save", "Cancel"], defaultId: 0, cancelId: 2, noLink: true });
    if (r.response === 2) return;
    if (r.response === 0) {
      try {
        let file = service.project.path;
        if (!file) file = await pick("save", { name: `${service.project.name}.tsproj` });
        if (!file) return;
        service.save(file);
      } catch (err) { await dialog.showMessageBox(win, { type: "error", message: "Could not save.", detail: err.message }); return; }
    } else service.clearRecovery?.();
    quitting = true;
    win.close();
  });
  win.on("closed", () => { win = null; app.quit(); });
  await win.loadURL(service.studioUrl());
}

app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  service = new App({
    dataDir: app.getPath("userData"),
    host: {
      dialog: pick,
      openProjector,
      capturePng,
      displays,
      setGlobalShortcuts: (list) => { wanted = list; applyShortcuts(); },
      openPath: async (p) => { if (!p) throw new Error("Nothing to open."); const err = await shell.openPath(p); if (err) throw new Error(err); },
    },
  });
  try {
    await service.start();
  } catch (err) {
    dialog.showErrorBox("TeleScore could not start", err.message);
    app.quit();
    return;
  }
  const file = process.argv.slice(app.isPackaged ? 1 : 2).find((a) => /\.(tsproj|json|tsp)$/i.test(a));
  if (file) await service.openFile(path.resolve(file)).catch((err) => dialog.showErrorBox("Could not open the project", err.message));
  await createWindow();
  if (process.env.TELESCORE_SMOKE) smokeTest(process.env.TELESCORE_SMOKE);
});

// A self-check of the desktop parts (TeleScore.bat test): the window draws, a
// board renders to PNG, shortcuts convert. Writes pictures and a report, then quits.
async function smokeTest(dir) {
  const fs = await import("node:fs");
  const report = [];
  const ok = (name, pass, detail = "") => report.push(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  " + detail : ""}`);
  try {
    fs.mkdirSync(dir, { recursive: true });
    await service.newProject("Basketball");
    await new Promise((r) => setTimeout(r, 2000));
    const shot = await win.webContents.capturePage();
    fs.writeFileSync(path.join(dir, "window.png"), shot.toPNG());
    const text = await win.webContents.executeJavaScript("document.body.innerText");
    ok("window shows the Basketball controls", /AWAY SCORE/i.test(text) && /10:00/.test(text));
    const b = service.project.boards[0];
    const png = await capturePng(service.studio.url(`/board/${encodeURIComponent(b.id)}`), b.width, b.height);
    fs.writeFileSync(path.join(dir, "board.png"), png);
    const size = nativeImage.createFromBuffer(png).getSize();
    ok("board renders to PNG", png.length > 1000 && size.width === b.width, `${size.width}x${size.height}, ${png.length} bytes`);
    const pairs = [["Ctrl+Space", "Control+Space"], ["Q", "Q"], ["[", "["], ["F5", "F5"], ["Ctrl+Shift+PgUp", "Control+Shift+PageUp"], ["Del", "Delete"]];
    ok("shortcuts convert", pairs.every(([q, a]) => accelerator(q) === a), pairs.map(([q]) => `${q}→${accelerator(q)}`).join(" "));
    ok("displays listed", displays().length >= 1, JSON.stringify(displays()));
  } catch (err) { ok("smoke test ran", false, err.stack); }
  fs.writeFileSync(path.join(dir, "report.txt"), report.join("\n") + "\n");
  console.log(report.join("\n"));
  service.dirty = false;
  app.exit(report.some((l) => l.startsWith("FAIL")) ? 1 : 0);
}

app.on("will-quit", () => globalShortcut.unregisterAll());
app.on("window-all-closed", () => app.quit());
let stopping = false;
app.on("before-quit", async (e) => {
  if (stopping || !service) return;
  e.preventDefault();
  stopping = true;
  quitting = true;
  for (const c of capturers.values()) if (!c.win.isDestroyed()) c.win.destroy();
  try { await service.stop(); } catch { /* closing anyway */ }
  app.quit();
});
