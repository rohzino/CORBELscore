// The two local web servers.
//   public  (port 8130 by default, set in Outputs): browser sources for OBS
//           and vMix, the XML/JSON feeds, remote control for Stream Deck and
//           Companion, and the list page at /.
//   studio  (127.0.0.1, a random port): the TeleScore window itself and its
//           editing API, locked to a key made fresh on every start.
// Both serve the shared modules (/core, /render) and fonts, so a board looks
// the same everywhere it is drawn.

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { XML_PROFILES, stateJson } from "../core/formats.js";
import { Ticket } from "../core/engine.js";
import { overlayHtml, indexHtml } from "./pages.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const APP_DIR = path.resolve(HERE, "..");
const STATIC = { "/core/": path.join(APP_DIR, "core"), "/render/": path.join(APP_DIR, "ui", "render"), "/fonts/": path.join(APP_DIR, "assets", "fonts"),
  "/ui/": path.join(APP_DIR, "ui") };
const TYPES = { ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
  ".ttf": "font/ttf", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
  ".webp": "image/webp", ".bmp": "image/bmp", ".ico": "image/x-icon", ".json": "application/json; charset=utf-8", ".wav": "audio/wav",
  ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".txt": "text/plain; charset=utf-8" };
export const IMAGE_TYPES = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"]);
export const SOUND_TYPES = new Set([".wav", ".mp3", ".ogg", ".m4a"]);

export function send(res, code, body, type = "text/plain; charset=utf-8", extra = {}) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(String(body));
  res.writeHead(code, { "Content-Type": type, "Content-Length": buf.length, "Cache-Control": "no-store", ...extra });
  res.end(res.req.method === "HEAD" ? undefined : buf);
}
export const json = (res, code, obj, extra) => send(res, code, JSON.stringify(obj), "application/json; charset=utf-8", extra);

export function readBody(req, limit = 4 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let n = 0;
    req.on("data", (c) => { n += c.length; if (n > limit) { reject(new Error("too large")); req.destroy(); } else chunks.push(c); });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function serveStatic(res, url, extra = {}) {
  for (const [prefix, dir] of Object.entries(STATIC)) {
    if (!url.pathname.startsWith(prefix) || (prefix === "/ui/" && !extra.ui)) continue;
    const rel = decodeURIComponent(url.pathname.slice(prefix.length));
    const file = path.resolve(dir, rel);
    if (!file.startsWith(dir + path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) return send(res, 404, "Not found."), true;
    const type = TYPES[path.extname(file).toLowerCase()] || "application/octet-stream";
    send(res, 200, fs.readFileSync(file), type, prefix === "/fonts/" ? { "Cache-Control": "max-age=86400" } : {});
    return true;
  }
  return false;
}

export const serveStaticUi = (res, url) => serveStatic(res, url, { ui: true });

export function serveFile(res, file, allowed) {
  const full = path.resolve(String(file || ""));
  const ext = path.extname(full).toLowerCase();
  if (!allowed(full, ext)) return send(res, 403, "Only pictures and sounds used by this project are served.");
  fs.readFile(full, (err, buf) => {
    if (err) return send(res, 404, "That file is missing.");
    send(res, 200, buf, TYPES[ext] || "application/octet-stream", { "Cache-Control": "max-age=5" });
  });
}

// Server-sent events: a full set of values, then only what changed.
export class EventHub {
  constructor() { this.clients = new Set(); }
  join(res, initial = []) {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store", Connection: "keep-alive", "Access-Control-Allow-Origin": "*" });
    const c = { res, last: null, lastFx: null };
    this.clients.add(c);
    for (const [ev, data] of initial) this.write(c, ev, data);
    const ping = setInterval(() => res.write(": keep-alive\n\n"), 15_000);
    res.on("close", () => { clearInterval(ping); this.clients.delete(c); });
    return c;
  }
  write(c, ev, data) { c.res.write(`event: ${ev}\ndata: ${JSON.stringify(data)}\n\n`); }
  broadcast(ev, data) { for (const c of this.clients) this.write(c, ev, data); }
  // Values as diffs per client; effects when they change.
  snapshot(snap) {
    for (const c of this.clients) {
      if (!c.last) { this.write(c, "full", snap.values); c.last = { ...snap.values }; }
      else {
        const diff = {};
        let any = false;
        for (const [k, v] of Object.entries(snap.values)) if (c.last[k] !== v) { diff[k] = v; any = true; }
        for (const k of Object.keys(c.last)) if (!(k in snap.values)) { diff[k] = null; any = true; }
        if (any) { this.write(c, "diff", diff); c.last = { ...snap.values }; }
      }
      const fx = JSON.stringify(snap.fx);
      if (fx !== c.lastFx) { c.lastFx = fx; this.write(c, "fx", snap.fx); }
    }
  }
  closeAll() { for (const c of this.clients) c.res.end(); this.clients.clear(); }
}

export class WebServer {
  constructor(name, handler) {
    this.name = name;
    this.handler = handler;
    this.server = null;
    this.port = 0;
    this.host = "";
    this.error = "";
    this.sockets = new Set();
  }
  get running() { return !!this.server; }
  start(port, host = "127.0.0.1") {
    return new Promise((resolve) => {
      this.stop().then(() => {
        const srv = http.createServer((req, res) => {
          let url;
          try { url = new URL(req.url, "http://localhost"); } catch { return send(res, 400, "Bad request."); }
          Promise.resolve(this.handler(req, res, url)).catch((e) => {
            console.error(this.name, e);
            if (!res.headersSent) send(res, 500, "Something went wrong: " + e.message);
          });
        });
        srv.keepAliveTimeout = 5000;
        srv.on("connection", (s) => { this.sockets.add(s); s.on("close", () => this.sockets.delete(s)); });
        srv.once("error", (e) => {
          this.error = `Port ${port} is in use or blocked (${e.code}). Pick another port under Outputs.`;
          resolve(false);
        });
        srv.listen(port, host, () => {
          this.server = srv;
          this.port = srv.address().port;
          this.host = host;
          this.error = "";
          resolve(true);
        });
      });
    });
  }
  stop() {
    if (!this.server) return Promise.resolve();
    const srv = this.server;
    this.server = null;
    for (const s of this.sockets) s.destroy();
    this.sockets.clear();
    return new Promise((r) => srv.close(() => r()));
  }
  url(p = "/") {
    const host = ["", "127.0.0.1", "0.0.0.0"].includes(this.host) ? "127.0.0.1" : this.host;
    return `http://${host}:${this.port}${p}`;
  }
}

// ---- routes shared by both servers -----------------------------------------------

// Remote actions wait up to 2 s for the engine; a withdrawn action means "did
// not run, safe to retry", so a Stream Deck retry can never score twice.
export function runAction(app, action) {
  return new Promise((resolve) => {
    const ticket = new Ticket();
    let settled = false;
    const finish = (code, body) => { if (!settled) { settled = true; resolve([code, body]); } };
    app.submit(action, (err) => finish(err ? 400 : 200, err ? { ok: false, error: err } : { ok: true }), ticket);
    setTimeout(() => {
      if (settled) return;
      if (ticket.withdraw()) finish(504, { ok: false, error: "TeleScore was busy and did not run the action. It is safe to try again." });
      else setTimeout(() => finish(504, { ok: false, error: "The action started but did not finish in time." }), 5000);
    }, 2000);
  });
}

export async function publicRoutes(app, hub, req, res, url, { token }) {
  const p = url.pathname;
  if (req.method === "OPTIONS") {
    res.writeHead(204, { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-TeleScore-Token", "Content-Length": 0 });
    return res.end(), true;
  }
  const cors = { "Access-Control-Allow-Origin": "*" };
  if (serveStatic(res, url)) return true;
  if (!app.project) return send(res, 503, "No project is open in TeleScore."), true;
  const snap = app.project.engine.snapshot();
  if (p === "/" || p === "/index.html") return send(res, 200, indexHtml(app, req.headers.host || "127.0.0.1"), TYPES[".html"]), true;
  if (p === "/state.json") return send(res, 200, stateJson(snap), TYPES[".json"], cors), true;
  for (const [fname, fn] of Object.values(XML_PROFILES)) if (p === "/" + fname) return send(res, 200, fn(snap), "application/xml; charset=utf-8", cors), true;
  if (p === "/events") {
    const c = hub.join(res, [["full", snap.values], ["fx", snap.fx], ["boards", app.rev]]);
    c.last = { ...snap.values };
    c.lastFx = JSON.stringify(snap.fx);
    return true;
  }
  if (p.startsWith("/board/")) {
    let id = decodeURIComponent(p.slice(7));
    const asJson = id.endsWith(".json");
    if (asJson) id = id.slice(0, -5);
    const board = app.project.board(id);
    if (!board) return send(res, 404, "There is no board with that id. Open / for the list."), true;
    if (asJson) return json(res, 200, { board, animations: app.project.animations }, cors), true;
    return send(res, 200, overlayHtml(board, url.searchParams.get("bg") || "transparent", app.project.animations), TYPES[".html"]), true;
  }
  if (p === "/api/fields") {
    return json(res, 200, Object.keys(snap.types).map((k) => ({ key: k, type: snap.types[k], label: snap.labels[k] ?? k })), cors), true;
  }
  if (p === "/api/action") {
    const given = req.headers["x-telescore-token"] || url.searchParams.get("token") || "";
    if (token && given !== token) return json(res, 403, { ok: false, error: "This TeleScore needs a token. Add ?token=..." }, cors), true;
    let action;
    if (req.method === "POST") {
      try { action = JSON.parse((await readBody(req, 64 * 1024)) || "{}"); } catch { return json(res, 400, { ok: false, error: 'The body must be JSON, like {"do":"add"}.' }, cors), true; }
    } else {
      action = {};
      for (const [k, v] of url.searchParams) if (k !== "token") action[k] = v;
      for (const k of ["amount", "ms", "index"]) {
        if (k in action) {
          const n = Number(action[k]);
          if (!Number.isFinite(n)) return json(res, 400, { ok: false, error: `${k} must be a number.` }, cors), true;
          action[k] = Math.trunc(n);
        }
      }
    }
    const [code, body] = await runAction(app, action);
    return json(res, code, body, cors), true;
  }
  if (p === "/asset") return serveFile(res, url.searchParams.get("path"), (full, ext) => IMAGE_TYPES.has(ext) && app.assetAllowed(full)), true;
  return false;
}
