// CORBELscore's desktop shell (Electron). Everything that matters runs in the
// service (app/service); this file only gives it a window and the few things a
// browser page cannot do: file dialogs, projector windows on other displays,
// pop-out windows for Control and View, PNG capture, background shortcuts and
// opening folders.

import { app, BrowserWindow, dialog, globalShortcut, screen, session, shell, Menu, nativeImage } from "electron";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { App } from "./service/app.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ICON = path.join(HERE, "assets", "icon.ico");

// The self-check keeps its own settings, so it never touches the real ones.
if (process.env.CORBEL_SMOKE) app.setPath("userData", path.join(process.env.CORBEL_SMOKE, "data"));
else if (!app.requestSingleInstanceLock()) app.quit();
else migrateFromTeleScore();

// Settings (the Sportzcast token, recent projects, colours) used to live in
// TeleScore's folder. Copy them across once so nothing has to be typed again.
function migrateFromTeleScore() {
  try {
    const now = app.getPath("userData");
    const old = path.join(path.dirname(now), "TeleScore");
    const file = path.join(now, "settings.json");
    if (!fs.existsSync(file) && fs.existsSync(path.join(old, "settings.json"))) {
      fs.mkdirSync(now, { recursive: true });
      fs.copyFileSync(path.join(old, "settings.json"), file);
    }
  } catch { /* a fresh start is fine */ }
}

let win = null;
let service = null;
let quitting = false;
let closingApp = false;   // the main window is closing: pop-outs close too, and reopen next time

// ---- dialogs ----------------------------------------------------------------------------------
const FILTERS = {
  project: [{ name: "CORBELscore and TeleScore projects", extensions: ["corbel", "tsproj", "json", "tsp"] }, { name: "All files", extensions: ["*"] }],
  save: [{ name: "CORBELscore project", extensions: ["corbel"] }],
  image: [{ name: "Pictures", extensions: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"] }],
  sound: [{ name: "Sounds", extensions: ["wav", "mp3", "ogg", "m4a", "aac", "flac"] }],
  data: [{ name: "Score data", extensions: ["xml", "json", "txt"] }, { name: "All files", extensions: ["*"] }],
};

async function pick(kind, opts = {}) {
  const parent = BrowserWindow.getFocusedWindow() ?? win;
  if (kind === "save") {
    const r = await dialog.showSaveDialog(parent, { title: "Save project", defaultPath: path.join(app.getPath("documents"), opts.name || "Untitled.corbel"), filters: FILTERS.save });
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
    title: "CORBELscore projector", icon: ICON, backgroundColor: "#000000", autoHideMenuBar: true,
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

// ---- pop-out windows ---------------------------------------------------------------------------
// Control and View can each move into a window of their own: any size, on any
// display, optionally always on top. Each has its own session partition, because
// Chromium keeps one zoom per site per session and each window needs its own scale.
// Size, place, scale and always-on-top are kept in windows.json; a pop-out that
// was open when CORBELscore closed opens again next time.
const PANELS = { control: { title: "Control", width: 960, height: 600 }, view: { title: "View", width: 1280, height: 800 } };
const SCALE_MIN = 0.5, SCALE_MAX = 2;
const pops = {};            // panel -> { win, need: {w, h, max} }
let popState = {};          // panel -> { open, bounds, top, scale: "fit" | number }
const popFile = () => path.join(app.getPath("userData"), "windows.json");

function loadPops() {
  try { popState = JSON.parse(fs.readFileSync(popFile(), "utf8")) || {}; } catch { popState = {}; }
  for (const k of Object.keys(PANELS)) popState[k] = { open: false, bounds: null, top: false, scale: "fit", ...(popState[k] ?? {}) };
}
let popSaveT = 0;
function savePops() {
  clearTimeout(popSaveT);
  popSaveT = setTimeout(() => { try { fs.writeFileSync(popFile(), JSON.stringify(popState, null, 2)); } catch { /* not worth stopping for */ } }, 300);
}

function popInfo() {
  const out = {};
  for (const [k, p] of Object.entries(pops)) out[k] = { top: !!popState[k].top, scale: popState[k].scale, zoom: Math.round(p.win.webContents.getZoomFactor() * 100) / 100 };
  return out;
}
const popsChanged = () => service?.windowsChanged(popInfo());

// A saved place is used only if most of it is still on a connected display.
function onScreen(b) {
  if (!b || !(b.width > 0 && b.height > 0)) return false;
  return screen.getAllDisplays().some((d) => {
    const a = d.workArea;
    const w = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
    const h = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
    return w >= Math.min(160, b.width) && h >= Math.min(120, b.height);
  });
}

// The zoom that fits the panel's natural size into the window, or the operator's own.
const clampZoom = (z, max = SCALE_MAX) => Math.round(Math.max(SCALE_MIN, Math.min(max, z)) * 100) / 100;
function fitZoom(panel) {
  const p = pops[panel];
  const st = popState[panel];
  if (!p || p.win.isDestroyed()) return;
  let z;
  if (st.scale === "fit") {
    const { width, height } = p.win.getContentBounds();
    const n = p.need ?? { w: PANELS[panel].width, h: PANELS[panel].height, max: 1 };
    z = clampZoom(Math.min(width / Math.max(1, n.w), n.h > 0 ? height / n.h : Infinity), n.max ?? 1);
  } else z = clampZoom(Number(st.scale) || 1);
  if (Math.abs(p.win.webContents.getZoomFactor() - z) >= 0.005) { p.win.webContents.setZoomFactor(z); popsChanged(); }
}

function openPop(panel) {
  if (pops[panel] && !pops[panel].win.isDestroyed()) { const w = pops[panel].win; if (w.isMinimized()) w.restore(); w.show(); w.focus(); return; }
  const st = popState[panel];
  const def = PANELS[panel];
  let bounds = onScreen(st.bounds) ? st.bounds : null;
  if (!bounds) {   // centred on the display the main window is on
    const a = screen.getDisplayMatching(win?.getBounds() ?? { x: 0, y: 0, width: 1, height: 1 }).workArea;
    const width = Math.min(def.width, a.width - 40), height = Math.min(def.height, a.height - 40);
    bounds = { x: Math.round(a.x + (a.width - width) / 2), y: Math.round(a.y + (a.height - height) / 2), width, height };
  }
  const w = new BrowserWindow({
    title: `CORBELscore · ${def.title}`, icon: nativeImage.createFromPath(ICON), ...bounds, minWidth: 320, minHeight: 200,
    backgroundColor: "#0c0d0d", show: false, autoHideMenuBar: true,
    webPreferences: { partition: `persist:corbel-${panel}`, contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  w.setMenu(null);
  pops[panel] = { win: w, need: null };
  st.open = true;
  if (st.top) w.setAlwaysOnTop(true, "floating");
  w.once("ready-to-show", () => w.show());
  guardWindow(w);
  const keep = () => { if (!w.isDestroyed() && !w.isMinimized() && !w.isFullScreen() && !w.isMaximized()) { st.bounds = w.getNormalBounds(); savePops(); } };
  w.on("resize", () => { keep(); fitZoom(panel); });
  w.on("move", keep);
  w.on("closed", () => {
    delete pops[panel];
    if (!closingApp) { st.open = false; savePops(); }   // closed by the operator: the panel goes back to the main window
    popsChanged();
    applyShortcutsSoon();
  });
  savePops();
  w.webContents.setZoomFactor(1);   // the partition remembers the last zoom; start clean and fit once the page says what it needs
  w.webContents.on("did-finish-load", () => {
    fitZoom(panel);
    if (panel === "view") w.webContents.executeJavaScript("window.__corbelLoadFonts ? window.__corbelLoadFonts() : 0", true).catch(() => {});
  });
  w.loadURL(`${service.studioUrl()}&panel=${panel}`);
  popsChanged();
}

// Requests from a page (via the service): open, show, close, scale, always on top.
async function popRequest(b) {
  const panel = b.panel;
  const st = popState[panel];
  const p = pops[panel];
  switch (b.op) {
    case "open": openPop(panel); break;
    case "show": if (p) { if (p.win.isMinimized()) p.win.restore(); p.win.show(); p.win.focus(); } else openPop(panel); break;
    case "close": if (p) p.win.close(); win?.show(); win?.focus(); break;
    case "top":
      st.top = b.on === undefined ? !st.top : !!b.on;
      p?.win.setAlwaysOnTop(st.top, "floating");
      savePops(); popsChanged(); break;
    case "scale": {
      const cur = p ? p.win.webContents.getZoomFactor() : 1;
      if (b.scale === "fit") st.scale = "fit";
      else if (b.scale === "in" || b.scale === "out") st.scale = clampZoom(Math.round((cur + (b.scale === "in" ? 0.1 : -0.1)) * 10) / 10);
      else st.scale = clampZoom(Number(b.scale) || 1);
      savePops(); fitZoom(panel); popsChanged(); break;
    }
    case "need":   // the page's natural size in CSS pixels at 100%, and the largest scale that suits it
      if (p) { p.need = { w: Math.max(200, Number(b.w) || 0), h: Math.max(0, Number(b.h) || 0), max: Math.max(SCALE_MIN, Math.min(SCALE_MAX, Number(b.max) || 1)) }; fitZoom(panel); }
      break;
    default: throw new Error("Unknown window request.");
  }
  return { windows: popInfo() };
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
// Off while the CORBELscore window has focus (the window handles its own keys,
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

// Our own windows: the main one and the pop-outs. Projector windows do not count:
// they handle no keys, so background shortcuts must keep working while one has focus.
const ownWindows = () => [win, ...Object.values(pops).map((p) => p.win)].filter((w) => w && !w.isDestroyed());

function applyShortcuts() {
  globalShortcut.unregisterAll();
  if (!win || win.isDestroyed() || ownWindows().some((w) => w.isFocused())) return;
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

// Moving focus between two CORBELscore windows blurs one before focusing the
// other; wait a moment so the shortcuts are not switched on in between.
let shortcutsT = 0;
function applyShortcutsSoon() { clearTimeout(shortcutsT); shortcutsT = setTimeout(applyShortcuts, 60); }

// What every CORBELscore window shares: other sites open in the browser, nothing
// navigates away, Ctrl+Shift+F12 opens the developer tools, focus switches shortcuts.
function guardWindow(w) {
  w.on("focus", applyShortcutsSoon);
  w.on("blur", applyShortcutsSoon);
  w.webContents.setWindowOpenHandler(({ url }) => { if (/^https?:/.test(url)) shell.openExternal(url); return { action: "deny" }; });
  w.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(service.studio.url("/"))) { e.preventDefault(); if (/^https?:/.test(url)) shell.openExternal(url); } });
  w.webContents.on("before-input-event", (e, input) => {
    if (input.type === "keyDown" && input.key === "F12" && input.control && input.shift) w.webContents.toggleDevTools();
  });
}

// ---- the window ------------------------------------------------------------------------------
async function createWindow() {
  win = new BrowserWindow({
    title: "CORBELscore", icon: nativeImage.createFromPath(ICON), width: 1440, height: 900, minWidth: 960, minHeight: 600,
    backgroundColor: "#0e1311", show: false, autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, spellcheck: false },
  });
  win.setMenu(null);
  win.once("ready-to-show", () => { win.maximize(); win.show(); });
  // Links to other sites (help pages, the feeds page) open in the normal browser.
  guardWindow(win);
  win.on("close", async (e) => {
    if (quitting || !service?.dirty) return;
    e.preventDefault();
    const r = await dialog.showMessageBox(win, { type: "warning", title: "CORBELscore", message: `Save changes to ${service.project?.name ?? "this project"}?`,
      detail: "If you don't save, your design changes since the last save are lost.", buttons: ["Save", "Don't save", "Cancel"], defaultId: 0, cancelId: 2, noLink: true });
    if (r.response === 2) return;
    if (r.response === 0) {
      try {
        let file = service.project.path;
        if (!file) file = await pick("save", { name: `${service.project.name}.corbel` });
        if (!file) return;
        service.save(file);
      } catch (err) { await dialog.showMessageBox(win, { type: "error", message: "Could not save.", detail: err.message }); return; }
    } else service.clearRecovery?.();
    quitting = true;
    win.close();
  });
  win.on("closed", () => {
    win = null;
    closingApp = true;   // pop-outs close with it, and remember they were open
    for (const p of Object.values(pops)) if (!p.win.isDestroyed()) p.win.close();
    app.quit();
  });
  await win.loadURL(service.studioUrl());
  // The computer's fonts, for the designer's font list, as the program starts.
  win.webContents.executeJavaScript("window.__corbelLoadFonts ? window.__corbelLoadFonts() : 0", true).catch(() => {});
}

app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  if (process.platform === "win32") app.setAppUserModelId("CORBELscore");   // one taskbar group, with CORBELscore's icon
  // The window may list the computer's fonts (for the font picker), copy to the
  // clipboard and go full screen; nothing else (camera, location…) is granted.
  const ALLOWED = new Set(["local-fonts", "clipboard-sanitized-write", "clipboard-read", "fullscreen"]);
  for (const ses of [session.defaultSession, ...Object.keys(PANELS).map((k) => session.fromPartition(`persist:corbel-${k}`))]) {
    ses.setPermissionRequestHandler((_wc, permission, done) => done(ALLOWED.has(permission)));
    ses.setPermissionCheckHandler((_wc, permission) => ALLOWED.has(permission));
  }
  loadPops();
  service = new App({
    dataDir: app.getPath("userData"),
    host: {
      dialog: pick,
      openProjector,
      capturePng,
      displays,
      window: popRequest,
      setGlobalShortcuts: (list) => { wanted = list; applyShortcuts(); },
      openPath: async (p) => { if (!p) throw new Error("Nothing to open."); const err = await shell.openPath(p); if (err) throw new Error(err); },
    },
  });
  try {
    await service.start();
  } catch (err) {
    dialog.showErrorBox("CORBELscore could not start", err.message);
    app.quit();
    return;
  }
  const file = process.argv.slice(app.isPackaged ? 1 : 2).find((a) => /\.(corbel|tsproj|json|tsp)$/i.test(a));
  if (file) await service.openFile(path.resolve(file)).catch((err) => dialog.showErrorBox("Could not open the project", err.message));
  await createWindow();
  // Pop-outs that were open when CORBELscore last closed.
  if (!process.env.CORBEL_SMOKE) for (const k of Object.keys(PANELS)) if (popState[k].open) openPop(k);
  if (process.env.CORBEL_SMOKE) smokeTest(process.env.CORBEL_SMOKE);
});

// A self-check of the desktop parts (CORBELscore.bat test): the window draws, a
// board renders to PNG, shortcuts convert. Writes pictures and a report, then quits.
async function smokeTest(dir) {
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
    const font = await win.webContents.executeJavaScript('document.fonts.check(\'16px "Red Hat Text"\') && document.fonts.check(\'700 16px "Red Hat Display"\')');
    ok("Red Hat fonts loaded", font === true);
    // Loaded on its own as the window opened, no click needed.
    const fonts = await win.webContents.executeJavaScript("import('/ui/js/fonts.js').then((m) => m.localFonts()?.length ?? 'not loaded')");
    ok("computer's fonts loaded at start", typeof fonts === "number" && fonts > 0, String(fonts));
    await popTest(dir, ok);
  } catch (err) { ok("smoke test ran", false, err.stack); }
  fs.writeFileSync(path.join(dir, "report.txt"), report.join("\n") + "\n");
  console.log(report.join("\n"));
  service.dirty = false;
  app.exit(report.some((l) => l.startsWith("FAIL")) ? 1 : 0);
}

// Pop-out windows: open from the button, Always on top, Fit at several sizes
// (without touching the main window's scale), nothing wider than the window, put back.
async function popTest(dir, ok) {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const js = (w, code) => w.webContents.executeJavaScript(code, true);
  const until = async (fn, ms = 6000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await fn()) return true; await wait(100); } return false; };
  const clickText = (w, text) => js(w, `(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === ${JSON.stringify(text)}); if (!b) return false; b.click(); return true; })()`);
  ok("main window has a Pop out button", await clickText(win, "Pop out"));
  ok("Control opens in its own window", await until(() => !!pops.control?.win && !pops.control.win.webContents.isLoading()));
  const pw = pops.control.win;
  await until(() => js(pw, "document.body.innerText.includes('Always on top')"));
  const ptext = await js(pw, "document.body.innerText");
  ok("pop-out shows Control with its bar", /AWAY SCORE/i.test(ptext) && /Always on top/.test(ptext) && /Put back/.test(ptext), pw.getTitle());
  ok("main window moves to View", await until(() => js(win, "document.querySelector('.tabs [aria-selected=true]')?.textContent.startsWith('View') && document.body.innerText.includes('Graphics')")));
  ok("main window marks Control as popped out", await until(() => js(win, "document.querySelector('.tabs .popped') !== null")));
  // Always on top, from the page's own toggle.
  await js(pw, "document.querySelector('.pop-top').click()");
  ok("Always on top turns on", await until(() => pw.isAlwaysOnTop()));
  ok("Always on top shows as on", await until(() => js(pw, "document.querySelector('.pop-top').getAttribute('aria-pressed') === 'true'")));
  // Fit at several sizes: the scale follows the window, the main window keeps 100%.
  const need = () => pops.control.need;
  await until(() => !!need());
  const sizes = [[480, 300], [900, 560], [1600, 340], [1500, 1000], [320, 200]];
  const fits = [];
  for (const [w, h] of sizes) {
    pw.setContentSize(w, h);
    await wait(500);
    const cb = pw.getContentBounds();
    const n = need();
    const want = Math.round(Math.max(0.5, Math.min(n.max, Math.min(cb.width / n.w, cb.height / n.h))) * 100) / 100;
    const z = pw.webContents.getZoomFactor();
    const over = await js(pw, "document.documentElement.scrollWidth - innerWidth");
    const headOver = await js(pw, "(() => { const h = document.getElementById('head'); return h.scrollWidth - h.clientWidth; })()");
    fits.push({ size: `${cb.width}x${cb.height}`, zoom: z, want, over, headOver });
    fs.writeFileSync(path.join(dir, `popout-${cb.width}x${cb.height}.png`), (await pw.webContents.capturePage()).toPNG());
  }
  ok("Fit scales to each window size", fits.every((f) => Math.abs(f.zoom - f.want) < 0.011), JSON.stringify(fits));
  ok("nothing is wider than the window", fits.every((f) => f.over <= 0 && f.headOver <= 0));
  ok("main window keeps its own scale", win.webContents.getZoomFactor() === 1, String(win.webContents.getZoomFactor()));
  // A size of the operator's own, then Fit again.
  pw.setContentSize(900, 560); await wait(400);
  const before = pw.webContents.getZoomFactor();
  await clickText(pw, "+");
  await until(() => pw.webContents.getZoomFactor() > before + 0.05);
  const bigger = pw.webContents.getZoomFactor();
  ok("+ makes it bigger and Fit lets go", bigger > before && popState.control.scale !== "fit", `${before} → ${bigger}`);
  pw.setContentSize(700, 400); await wait(400);
  ok("a chosen size stays when the window changes", pw.webContents.getZoomFactor() === bigger);
  await js(pw, "document.querySelector('.pop-fit').click()");
  ok("Fit comes back", await until(() => popState.control.scale === "fit" && pw.webContents.getZoomFactor() !== bigger));
  // The pop-out runs the game too.
  const score = () => service.project.engine.snapshot().values["away.score"];
  const s0 = Number(score());
  await js(pw, "(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === '+1'); b.click(); })()");
  ok("a control in the pop-out scores", await until(() => Number(score()) === s0 + 1), `${s0} → ${score()}`);
  ok("its place and settings are kept", await until(() => { try { const j = JSON.parse(fs.readFileSync(popFile(), "utf8")); return j.control.open && j.control.top && j.control.bounds?.width > 0; } catch { return false; } }));
  // Put back.
  await clickText(pw, "Put back");
  ok("Put back closes the window", await until(() => !pops.control));
  ok("main window no longer marks Control", await until(() => js(win, "document.querySelector('.tabs .popped') === null")));
  // View pops out too, with the designer.
  await popRequest({ op: "open", panel: "view" });
  await until(() => pops.view && !pops.view.win.webContents.isLoading());
  ok("View opens in its own window", await until(() => js(pops.view.win, "document.body.innerText.includes('Graphics') && document.body.innerText.includes('Always on top')")));
  pops.view.win.setContentSize(800, 500); await wait(500);
  fs.writeFileSync(path.join(dir, "popout-view-800x500.png"), (await pops.view.win.webContents.capturePage()).toPNG());
  ok("View fits a small window", pops.view.win.webContents.getZoomFactor() < 1, String(pops.view.win.webContents.getZoomFactor()));
  await js(win, "(() => { const t = [...document.querySelectorAll('.tabs button')].find((x) => x.textContent.startsWith('View')); t.click(); })()");
  await wait(300);
  ok("main window says where View went", await until(() => js(win, "document.body.textContent.includes('View is in its own window')")));
  fs.writeFileSync(path.join(dir, "main-away.png"), (await win.webContents.capturePage()).toPNG());
  pops.view.win.close();
  ok("closing the window puts View back", await until(() => !pops.view && popState.view.open === false));
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
