// The CORBELscore service: one open project, its engine loop, file outputs,
// both web servers, live data, design undo, recovery and the studio API that
// the window uses. Everything that touches the operating system goes through
// `host` (dialogs, projector windows, global shortcuts, PNG capture), which the
// Electron shell provides; without it (tests, headless) those features say so.

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { makeAnimation, library } from "../core/animation.js";
import { boardKeys, copyBoard, makeBoard } from "../core/board.js";
import { now } from "../core/clock.js";
import { BASE_KEY, FX_KEY } from "../core/engine.js";
import { ClockField, FIELD_TYPES, fieldFromDict, PenaltyField } from "../core/fields.js";
import { makeLayout } from "../core/layout.js";
import { Condition } from "../core/logic.js";
import { BLURBS, PRESETS, makeProject } from "../core/presets.js";
import { APP_VERSION, makeButton, makeOutputs, Project, ProjectError } from "../core/project.js";
import { renameFieldEverywhere, fieldReferences } from "../core/refactor.js";
import { makeSource } from "../core/source.js";
import { atomicWriteText, loadProject, saveProject } from "./files.js";
import { OutputWriter, defaultOutputFolder } from "./outputs.js";
import { EventHub, IMAGE_TYPES, SOUND_TYPES, WebServer, json, publicRoutes, readBody, runAction, send, serveFile, serveStaticUi } from "./server.js";
import { Settings } from "./settings.js";
import { SportzcastSource } from "./sportzcast.js";
import { suggest } from "./feeds.js";

const VALUE_KEYS = new Set(["value", "index", "value_ms", "running", "entries"]);
const PARTS = ["meta", "fields", "boards", "buttons", "layout", "conditions", "animations", "outputs", "source"];
const HISTORY = 100;

export class App {
  constructor({ dataDir, host = null, studioPort = 0 } = {}) {
    this.dataDir = dataDir;
    this.host = host;
    this.settings = new Settings(dataDir);
    this.key = crypto.randomBytes(18).toString("base64url");
    this.project = null;
    this.rev = 0;
    this.dirty = false;
    this.undoStack = [];
    this.redoStack = [];
    this.notices = [];
    this.uiHub = new EventHub();
    this.publicHub = new EventHub();
    this.studio = new WebServer("studio", (req, res, url) => this._studio(req, res, url));
    this.public = new WebServer("public", (req, res, url) => this._public(req, res, url));
    this.writer = null;
    this.source = null;
    this.timer = null;
    this.recoveryFile = path.join(dataDir, "recovery.corbel");
    this.studioPort = studioPort;
    this._assets = new Set();
    this._snapPending = false;
    this._valuesChanged = false;
  }

  // ----- lifecycle --------------------------------------------------------------------
  async start() {
    const ok = await this.studio.start(this.studioPort, "127.0.0.1");
    if (!ok) throw new Error(this.studio.error);
    this._staleTimer = setInterval(() => this._everySecond(), 1000);
    return this.studioUrl();
  }

  studioUrl() { return this.studio.url(`/ui/index.html?key=${this.key}`); }

  async stop() {
    this._closeProject();
    clearInterval(this._staleTimer);
    this.uiHub.closeAll();
    await this.writer?.close();
    await this.public.stop();
    await this.studio.stop();
  }

  // ----- project ------------------------------------------------------------------------
  async load(project) {
    this._closeProject();
    this.project = project;
    this.rev += 1;
    this.dirty = false;
    this.undoStack = [];
    this.redoStack = [];
    const e = project.engine;
    e.onChange((snap, changed) => this._changed(snap, changed));
    e.onExpired((key) => this._expired(key));
    this.writer = new OutputWriter(project.outputs, project.name, { onStatus: () => this._status() });
    this.writer.submit(e.snapshot());
    this._refreshAssets();
    await this._applyServer();
    this._sourceChanged = false;   // live data waits for Connect
    this.timer = setInterval(() => { try { e.tick(); } catch (err) { console.error("tick", err); } }, 20);
    this._bindGlobalKeys();
    this._sendProject();
    this._status();
    return project;
  }

  _closeProject() {
    if (!this.project) return;
    clearInterval(this.timer);
    this.timer = null;
    this.source?.stop();
    this.source = null;
    this.writer?.close();
    this.writer = null;
    this.publicHub.closeAll();
    this.public.stop();
    this.host?.setGlobalShortcuts?.([]);
    this.project = null;
    this.rev += 1;
    this.dirty = false;
    this._sendProject();
  }

  _markDirty() {
    this.dirty = true;
    clearTimeout(this._recoveryT);
    this._recoveryT = setTimeout(() => this._writeRecovery(), 1500);
  }

  // ----- engine events ---------------------------------------------------------------------
  _changed(snap) {
    this.writer?.submit(snap);
    this.publicHub.snapshot(snap);
    this._valuesChanged = true;
    if (!this._snapPending) {
      this._snapPending = true;
      setTimeout(() => {
        this._snapPending = false;
        const s = this.project?.engine.snapshot();
        if (s) this.uiHub.broadcast("snap", s);
      }, 16);
    }
    if (this.project?.outputs.image_boards.length) this._schedulePng();
  }

  _expired(key) {
    const f = this.project?.engine.fields.get(key);
    this.uiHub.broadcast("expired", { key, label: f?.label ?? key, buzzer: f instanceof ClockField ? f.buzzer : "" });
  }

  _everySecond() {
    this.source?.checkStale();
    if (this.project && this._valuesChanged) {
      this._valuesChanged = false;
      // Values change all game long: a recovery copy every few seconds means a
      // crash mid-game brings back the score and the clocks.
      if (!this._lastRecovery || Date.now() - this._lastRecovery > 5000) this._writeRecovery();
    }
    const errs = this.project?.engine.logicErrors;
    if (errs?.length) {
      for (const msg of errs.splice(0)) this.notice(msg, true);
    }
  }

  notice(text, alert = false) { this.uiHub.broadcast("notice", { text, alert }); }

  _writeRecovery() {
    if (!this.project) return;
    try {
      const d = this.project.toDict();
      d._recovery = { path: this.project.path, at: new Date().toISOString().slice(0, 19), dirty: this.dirty };
      atomicWriteText(this.recoveryFile, JSON.stringify(d));
      this._lastRecovery = Date.now();
    } catch { /* recovery is best effort */ }
  }

  clearRecovery() { try { fs.unlinkSync(this.recoveryFile); } catch { /* */ } }

  recoveryInfo() {
    try {
      const d = JSON.parse(fs.readFileSync(this.recoveryFile, "utf8"));
      return { name: d.name, at: d._recovery?.at, path: d._recovery?.path || "" };
    } catch { return null; }
  }

  // ----- outputs and servers ------------------------------------------------------------------
  async _applyServer() {
    const o = this.project.outputs;
    if (!o.http_enabled) { await this.public.stop(); this._status(); return; }
    if (this.public.running && this.public.port === o.http_port && this.public.host === (o.http_lan ? "0.0.0.0" : "127.0.0.1")) return;
    this.publicHub.closeAll();
    await this.public.start(o.http_port, o.http_lan ? "0.0.0.0" : "127.0.0.1");
    if (this.public.error) this.notice(this.public.error, true);
    this._status();
  }

  _public(req, res, url) {
    return publicRoutes(this, this.publicHub, req, res, url, { token: this.project?.outputs.http_token || "" }).then((handled) => {
      if (!handled) send(res, 404, "Not found. Open / for the list of pages.");
    });
  }

  submit(action, done, ticket) { this.project ? this.project.engine.submit(action, done, ticket) : done?.("No project is open."); }

  _refreshAssets() {
    const p = this.project;
    const set = new Set();
    if (p) {
      const snap = p.engine.snapshot();
      for (const f of p.engine.fields.values()) {
        if (f.type === "image") { set.add(path.resolve(f.value)); set.add(path.resolve(f.default)); }
        if (f instanceof ClockField && f.buzzer) set.add(path.resolve(f.buzzer));
      }
      for (const b of p.boards) for (const e of b.elements) if (e.kind === "image" && e.src && !e.src.includes("{")) set.add(path.resolve(e.src));
      for (const c of p.engine.logic.conditions) if (c.action === "image" && c.arg) set.add(path.resolve(c.arg));
      for (const [k, v] of Object.entries(snap.values)) if (snap.types[k] === "image" && v) set.add(path.resolve(v));
    }
    this._assets = set;
  }

  assetAllowed(full) {
    if (this._assets.has(full)) return true;
    // A picture field may be set to any file by the operator: allow current values.
    const snap = this.project?.engine.snapshot();
    if (snap) for (const [k, v] of Object.entries(snap.values)) if (v && (snap.types[k] === "image" || k.endsWith(".logo")) && path.resolve(v) === full) return true;
    return false;
  }

  _schedulePng() {
    if (this._pngT || !this.host?.capturePng) return;
    this._pngT = setTimeout(async () => {
      this._pngT = null;
      const p = this.project;
      if (!p) return;
      const folder = path.join(this.writer.folder, "images");
      for (const id of p.outputs.image_boards) {
        const b = p.board(id);
        if (!b) continue;
        try {
          const png = await this.host.capturePng(this.studio.url(`/board/${encodeURIComponent(id)}`), b.width, b.height);
          if (png) { fs.mkdirSync(folder, { recursive: true }); atomicWriteText(path.join(folder, `${b.name.replace(/[^A-Za-z0-9 _-]/g, "_") || b.id}.png`), png); }
          this._png = { state: "ok", detail: folder };
        } catch (e) { this._png = { state: "error", detail: `PNG for ${b.name}: ${e.message}` }; }
      }
      this._status();
    }, 500);
  }

  // ----- live data --------------------------------------------------------------------------
  // Nothing connects until the operator presses Connect: changing the settings
  // never starts, restarts or drops a connection by itself.
  _connect() {
    this.source?.stop();
    const s = this.project.source;
    this.project.engine.clearSources();
    this.source = null;
    this._sourceChanged = false;
    if (s.kind) {
      this.source = new SportzcastSource(s, this.settings.get("sportzcast_token"), (v) => this.project?.engine.feed(v), () => this._status());
      this.source.start();
    }
    this._status();
  }

  _disconnect() {
    this.source?.stop();
    this.source = null;
    this._sourceChanged = false;
    this.project?.engine.clearSources();   // bound fields show their own values again
    this._status();
  }

  // ----- status ------------------------------------------------------------------------------
  statusInfo() {
    const p = this.project;
    const out = { open: !!p, dirty: this.dirty, path: p?.path ?? "", canUndo: this.undoStack.length > 0, canRedo: this.redoStack.length > 0,
      undoLabel: this.undoStack.at(-1)?.label ?? "", redoLabel: this.redoStack.at(-1)?.label ?? "" };
    if (!p) return out;
    out.files = this.writer ? structuredClone(this.writer.status) : {};
    out.folder = this.writer?.folder ?? "";
    out.png = this._png ?? { state: p.outputs.image_boards.length ? (this.host?.capturePng ? "busy" : "off") : "off", detail: this.host?.capturePng ? "" : "Pictures need the CORBELscore app window." };
    out.web = { running: this.public.running, port: this.public.port, lan: p.outputs.http_lan, error: this.public.error, clients: this.publicHub.clients.size,
      url: this.public.running ? this.public.url("/") : "" };
    out.live = this.source ? { ...this.source.status, keys: this.source.status.keys, connected: true, changed: !!this._sourceChanged } : { state: "off", connected: false };
    out.scoreUndo = { can: p.engine.canUndo(), canRedo: p.engine.canRedo() };
    return out;
  }

  _status() {
    clearTimeout(this._statusT);
    this._statusT = setTimeout(() => this.uiHub.broadcast("status", this.statusInfo()), 30);
  }

  projectInfo() {
    const p = this.project;
    if (!p) return null;
    const d = p.toDict();
    d.path = p.path;
    d.importedFrom = p.importedFrom;
    d.importNotes = p.importNotes;
    d.rev = this.rev;
    d.outputFolder = this.writer?.folder ?? defaultOutputFolder(p.name);
    d.library = Object.values(library(p.animations)).map((a) => ({ ...a, builtin: !!a.builtin }));
    return d;
  }

  _sendProject() {
    this.uiHub.broadcast("project", this.projectInfo());
    // A freshly loaded project has values the window has never seen.
    const snap = this.project?.engine.snapshot();
    if (snap) this.uiHub.broadcast("snap", snap);
    this.publicHub.broadcast("boards", this.rev);
    this._status();
  }

  // ----- design edits ----------------------------------------------------------------------------
  // One structural picture of the project per part, values left out, so undo
  // restores only what an edit changed and never rewinds the game.
  _structure() {
    const p = this.project;
    const fieldsFull = p.engine.fieldsToList();
    return {
      meta: { name: p.name, author: p.author },
      fields: fieldsFull.map((d) => Object.fromEntries(Object.entries(d).filter(([k]) => !VALUE_KEYS.has(k)))),
      fieldsFull,
      boards: structuredClone(p.boards), buttons: structuredClone(p.buttons), layout: structuredClone(p.layout),
      conditions: p.engine.logic.conditions.map((c) => c.toDict()), animations: structuredClone(p.animations),
      outputs: structuredClone(p.outputs), source: structuredClone(p.source),
    };
  }

  async _restore(st, parts) {
    const p = this.project;
    const cur = this._structure();
    for (const part of parts) {
      if (JSON.stringify(cur[part]) === JSON.stringify(st[part])) continue;
      if (part === "meta") Object.assign(p, st.meta);
      else if (part === "fields") {
        // Rebuild from the stored settings; fields that still exist keep their live values.
        const t = now();
        const fields = st.fieldsFull.map((d) => {
          const f = fieldFromDict(d);
          const live = p.engine.fields.get(f.key);
          if (live && live.type === f.type) { try { f.restore(structuredClone(live.state(t)), t); } catch { /* keep stored */ } }
          return f;
        });
        p.engine.setFields(fields);
      } else if (part === "conditions") p.engine.setConditions(st.conditions.map((c) => Condition.fromDict(c)));
      else p[part] = structuredClone(st[part]);
    }
    await this._afterEdit(parts, cur);
  }

  async _afterEdit(parts, before) {
    const p = this.project;
    if (parts.includes("outputs") || parts.includes("meta")) {
      this.writer.reconfigure(p.outputs, p.name);
      if (JSON.stringify(before.outputs) !== JSON.stringify(p.outputs) || parts.includes("outputs")) await this._applyServer();
    }
    if (parts.includes("source") && JSON.stringify(before.source) !== JSON.stringify(p.source) && this.source) { this._sourceChanged = true; this._status(); }
    if (parts.includes("fields")) this.writer.reconfigure(p.outputs, p.name);
    this._refreshAssets();
    this._bindGlobalKeys();
    p.engine.publish(undefined, true);
    this.rev += 1;
    this._markDirty();
    this._sendProject();
  }

  // Apply ops atomically as one design step.
  async edit(ops, label = "") {
    const p = this.project;
    if (!p) throw new ProjectError("Open or start a project first.");
    if (!Array.isArray(ops)) ops = [ops];
    const before = this._structure();
    try {
      for (const op of ops) this._apply(op);
    } catch (e) {
      await this._restore(before, PARTS);   // all or nothing
      this.rev += 1;
      this._sendProject();
      throw e;
    }
    this.undoStack.push({ st: before, label: label || ops[0]?.op || "edit" });
    if (this.undoStack.length > HISTORY) this.undoStack.shift();
    this.redoStack = [];
    await this._afterEdit(PARTS, before);
    return this.rev;
  }

  async undoEdit() {
    const e = this.undoStack.pop();
    if (!e) return false;
    this.redoStack.push({ st: this._structure(), label: e.label });
    await this._restore(e.st, PARTS);
    return e.label;
  }

  async redoEdit() {
    const e = this.redoStack.pop();
    if (!e) return false;
    this.undoStack.push({ st: this._structure(), label: e.label });
    await this._restore(e.st, PARTS);
    return e.label;
  }

  _apply(op) {
    const p = this.project;
    const e = p.engine;
    const t = now();
    switch (op.op) {
      case "meta": {
        if (op.name !== undefined) p.name = String(op.name).trim() || "Untitled";
        if (op.author !== undefined) p.author = String(op.author);
        return;
      }
      case "field.add": {
        e.addField(fieldFromDict(op.field), op.index ?? null);
        return;
      }
      case "field.update": {
        const old = e.field(op.key);
        const d = { ...old.toDict(t), ...op.changes, key: op.key };
        if (op.changes.type && op.changes.type !== old.type) {
          for (const k of VALUE_KEYS) delete d[k];
          delete d.default; delete d.steps; delete d.options;
        }
        const f = fieldFromDict(d);
        if (f.type === old.type) {
          if (f instanceof ClockField) {
            const [v, running] = old.clock.state(t);
            // A stopped clock still at its old period length follows the new one.
            const atStart = !running && v === (old.clock.countdown ? old.clock.initial_ms : 0);
            if ("value_ms" in op.changes) f.clock.set(f.clock.value(t), t);
            else if (atStart && !("value_ms" in op.changes)) f.clock.reset();
            else f.restore([v, running], t);
          } else if (!VALUE_CHANGE(op.changes)) {
            try { f.restore(structuredClone(old.state(t)), t); } catch { /* new settings make the old value invalid */ }
            if (typeof f.set === "function" && "value" in f && f.type === "counter") f.set(f.value);   // clamp to new limits
          }
        }
        e.replaceField(op.key, f);
        return;
      }
      case "field.remove": {
        e.field(op.key);
        e.removeField(op.key);
        for (const page of p.layout.pages) page.tiles = page.tiles.filter((x) => !(x.kind === "field" && x.field === op.key));
        return;
      }
      case "field.rename": {
        renameFieldEverywhere(p, op.key, op.to);
        return;
      }
      case "field.move": {
        e.moveField(op.key, op.index);
        return;
      }
      case "board.add": {
        const b = op.copyOf ? copyBoard(p.board(op.copyOf) ?? (() => { throw new Error("No such board."); })()) : makeBoard(op.board ?? {});
        if (op.copyOf) b.name = `${b.name} copy`;
        p.boards.splice(op.index ?? p.boards.length, 0, b);
        op.result = b.id;
        return;
      }
      case "board.put": {
        const i = p.boards.findIndex((b) => b.id === op.board.id);
        if (i < 0) throw new Error("That board no longer exists.");
        p.boards[i] = makeBoard(op.board);
        return;
      }
      case "board.remove": {
        if (p.boards.length <= 1) throw new Error("A project keeps at least one board.");
        p.boards = p.boards.filter((b) => b.id !== op.id);
        p.outputs.image_boards = p.outputs.image_boards.filter((x) => x !== op.id);
        for (const page of p.layout.pages) page.tiles = page.tiles.filter((x) => !(x.kind === "preview" && x.board === op.id));
        return;
      }
      case "button.put": {
        const b = makeButton(op.button);
        const i = p.buttons.findIndex((x) => x.id === b.id);
        if (i < 0) p.buttons.push(b); else p.buttons[i] = b;
        return;
      }
      case "button.remove": {
        p.buttons = p.buttons.filter((b) => b.id !== op.id);
        for (const page of p.layout.pages) page.tiles = page.tiles.filter((x) => !(x.kind === "button" && x.button === op.id));
        return;
      }
      case "layout.put": p.layout = makeLayout(op.layout); return;
      case "conditions.put": e.setConditions((op.conditions || []).map((c) => Condition.fromDict(c))); return;
      case "animations.put": {
        const list = (op.animations || []).map(makeAnimation).map(({ builtin, ...a }) => a);
        const names = list.map((a) => a.name);
        if (new Set(names).size !== names.length) throw new Error("Two animations have the same name.");
        p.animations = list;
        return;
      }
      case "outputs.put": p.outputs = makeOutputs({ ...p.outputs, ...op.outputs }); return;
      case "source.put": p.source = makeSource({ ...p.source, ...op.source }); return;
      default: throw new Error(`Unknown edit "${op.op}".`);
    }
  }

  // ----- files --------------------------------------------------------------------------------
  async newProject(preset) {
    const p = makeProject(preset);
    await this.load(p);
    return p;
  }

  async openFile(file) {
    const p = loadProject(file);
    await this.load(p);
    if (!p.importedFrom) this.settings.addRecent(file);
    return p;
  }

  save(file) {
    const p = this.project;
    if (!p) throw new ProjectError("Nothing to save.");
    file = file || p.path;
    if (!file) throw new ProjectError("Choose where to save the project first.");
    // New projects save as .corbel; a TeleScore .tsproj keeps its own name (same format).
    if (!/\.(corbel|tsproj)$/i.test(file)) file += ".corbel";
    if (p.importedFrom && path.resolve(file).toLowerCase() === path.resolve(p.importedFrom).toLowerCase()) {
      throw new ProjectError("That is the older file this project came from. Save under a new name so the original stays as it was.");
    }
    if (!p.path && p.name === "Untitled") p.name = path.basename(file).replace(/\.(corbel|tsproj)$/i, "");
    saveProject(p, file);
    p.importedFrom = "";
    this.dirty = false;
    this.settings.addRecent(file);
    this.clearRecovery();
    this.writer.reconfigure(p.outputs, p.name);
    this._sendProject();
    return file;
  }

  async restoreRecovery() {
    const d = JSON.parse(fs.readFileSync(this.recoveryFile, "utf8"));
    const meta = d._recovery || {};
    delete d._recovery;
    const p = Project.fromDict(d);
    p.path = meta.path || "";
    await this.load(p);
    this._markDirty();
    this._status();
    return p;
  }

  // ----- global shortcuts (Electron) --------------------------------------------------------------
  _bindGlobalKeys() {
    if (!this.host?.setGlobalShortcuts) return;
    const p = this.project;
    const on = this.settings.get("global_keys");
    this.host.setGlobalShortcuts(on && p ? p.buttons.filter((b) => b.hotkey).map((b) => ({ key: b.hotkey, run: () => this.submit(b.action) })) : []);
  }

  // ----- studio API ------------------------------------------------------------------------------
  state() {
    return { version: APP_VERSION, project: this.projectInfo(), status: this.statusInfo(), settings: this.settings.forUi(),
      presets: Object.keys(PRESETS), blurbs: BLURBS, recovery: this.recoveryInfo(), types: Object.keys(FIELD_TYPES),
      host: { dialogs: !!this.host?.dialog, projector: !!this.host?.openProjector, png: !!this.host?.capturePng, globalKeys: !!this.host?.setGlobalShortcuts },
      snapshot: this.project?.engine.snapshot() ?? null };
  }

  _okHost(req) {
    const h = String(req.headers.host || "");
    return h === `127.0.0.1:${this.studio.port}` || h === `localhost:${this.studio.port}`;
  }

  async _studio(req, res, url) {
    // Only this computer's CORBELscore window: the right host name (no DNS
    // rebinding). Read-only pages need nothing more; editing needs the key.
    if (!this._okHost(req)) return send(res, 403, "Forbidden.");
    const p = url.pathname;
    if (p === "/" ) return send(res, 302, "", "text/plain", { Location: "/ui/index.html" });
    if (serveStaticUi(res, url)) return;
    if (!p.startsWith("/api/") && p !== "/file") {
      const handled = await publicRoutes(this, this.publicHub, req, res, url, { token: "\u0000locked" });
      if (!handled) send(res, 404, "Not found.");
      return;
    }
    const key = req.headers["x-corbelscore-key"] || url.searchParams.get("key");
    if (key !== this.key) return send(res, 403, "This page belongs to the CORBELscore window.");
    if (p === "/file") {
      // Pictures and sounds the operator picked, for previews and buzzers.
      return serveFile(res, url.searchParams.get("path"), (full, ext) => (IMAGE_TYPES.has(ext) || SOUND_TYPES.has(ext)) && fs.existsSync(full));
    }
    if (p === "/api/events") {
      this.uiHub.join(res, [["state", this.state()]]);
      return;
    }
    if (p === "/api/state") return json(res, 200, this.state());
    if (req.method !== "POST") return send(res, 405, "Use POST.");
    let body;
    try { body = JSON.parse((await readBody(req)) || "{}"); } catch { return json(res, 400, { ok: false, error: "The request was not JSON." }); }
    try {
      const out = await this._api(p, body);
      return json(res, 200, { ok: true, ...(out || {}) });
    } catch (e) {
      return json(res, 200, { ok: false, error: e.message || String(e) });
    }
  }

  async _api(p, b) {
    const proj = this.project;
    switch (p) {
      case "/api/action": {
        const [code, body] = await runAction(this, b.action);
        if (code !== 200) throw new Error(body.error);
        return {};
      }
      case "/api/edit": {
        const ops = Array.isArray(b.ops) ? b.ops : [b];
        const rev = await this.edit(ops, b.label);
        return { rev, results: ops.map((o) => o.result) };
      }
      case "/api/undo": return { label: await this.undoEdit() };
      case "/api/redo": return { label: await this.redoEdit() };
      case "/api/references": return { refs: proj ? fieldReferences(proj, b.key) : [] };
      case "/api/suggest": {
        const keys = Object.keys(this.source?.keys ?? {});
        return { map: proj ? suggest(keys, [...proj.engine.fields.keys()].filter((k) => !proj.engine.fields.get(k).source)) : {} };
      }
      case "/api/live-keys": return { keys: this.source?.keys ?? {} };
      case "/api/token": {
        this.settings.set("sportzcast_token", String(b.token ?? ""));
        if (this.source) { this._sourceChanged = true; this._status(); }
        return {};
      }
      case "/api/connect": case "/api/reconnect": if (proj) this._connect(); return {};
      case "/api/disconnect": this._disconnect(); return {};
      case "/api/settings": {
        for (const k of ["scheme", "global_keys", "last_board"]) if (b[k] !== undefined) this.settings.set(k, b[k]);
        this._bindGlobalKeys();
        this.uiHub.broadcast("settings", this.settings.forUi());
        return {};
      }
      case "/api/file": return this._file(b);
      case "/api/pick": {
        if (!this.host?.dialog) throw new Error("Choosing files needs the CORBELscore app window. Type the path instead.");
        return { path: await this.host.dialog(b.kind, b) };
      }
      case "/api/projector": {
        if (!this.host?.openProjector) throw new Error("Projector windows need the CORBELscore app window.");
        await this.host.openProjector(this.studio.url(`/board/${encodeURIComponent(b.board)}?bg=black`), b);
        return {};
      }
      case "/api/displays": return { displays: (await this.host?.displays?.()) ?? [] };
      case "/api/open": {
        if (!this.host?.openPath) throw new Error("Needs the CORBELscore app window.");
        await this.host.openPath(b.path || this.writer?.folder, b.kind);
        return {};
      }
      case "/api/recovery": {
        if (b.restore) await this.restoreRecovery(); else this.clearRecovery();
        return {};
      }
      default: throw new Error("Unknown request.");
    }
  }

  async _file(b) {
    const op = b.op;
    if (["new", "open", "close", "restore"].includes(op) && this.dirty && !b.force) return { needsConfirm: true };
    if (op === "new") { await this.newProject(b.preset); this.clearRecovery(); return {}; }
    if (op === "close") { this._closeProject(); this.clearRecovery(); return {}; }
    if (op === "open") {
      let file = b.path;
      if (!file) {
        if (!this.host?.dialog) throw new Error("Type the project's path, or use the CORBELscore app window.");
        file = await this.host.dialog("project");
        if (!file) return { cancelled: true };
      }
      const p = await this.openFile(file);
      this.clearRecovery();
      return { imported: !!p.importedFrom, notes: p.importNotes };
    }
    if (op === "save" || op === "saveAs") {
      let file = op === "save" ? this.project?.path : b.path;
      if (!file) {
        if (b.path) file = b.path;
        else if (this.host?.dialog) {
          const suggestName = this.project.importedFrom ? this.project.importedFrom.replace(/\.[^.\\/]+$/, ".corbel") : `${this.project.name}.corbel`;
          file = await this.host.dialog("save", { name: suggestName });
          if (!file) return { cancelled: true };
        } else throw new Error("Type where to save the project.");
      }
      return { path: this.save(file) };
    }
    throw new Error("Unknown file request.");
  }
}

const VALUE_CHANGE = (changes) => Object.keys(changes).some((k) => VALUE_KEYS.has(k));
