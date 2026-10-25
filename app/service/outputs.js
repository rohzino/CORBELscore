// Writes snapshots to disk without ever stalling the clock: writes are
// asynchronous, only the newest snapshot is kept, so a burst of changes costs
// one write and the files always end on the latest state.
//   text files: one per value key, rewritten only when that value changes
//   XML and JSON: rewritten whole, at most maxRate times a second
// Every write is atomic (temp file + rename).

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { XML_PROFILES, stateJson, textFilename } from "../core/formats.js";

export function defaultOutputFolder(projectName) {
  let docs = path.join(os.homedir(), "Documents");
  if (!fs.existsSync(docs)) docs = os.homedir();
  const safe = String(projectName || "").replace(/[^A-Za-z0-9 _-]/g, "_").trim() || "Untitled";
  return path.join(docs, "CORBELscore Output", safe);
}

let tmpSeq = 0;
async function atomicWrite(file, text) {
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${tmpSeq++}.tmp`);
  await fs.promises.writeFile(tmp, text);
  for (let i = 0; i < 5; i++) {
    try { await fs.promises.rename(tmp, file); return; } catch (e) {
      if (!["EPERM", "EACCES", "EBUSY"].includes(e.code)) { await fs.promises.rm(tmp, { force: true }); throw e; }
      await new Promise((r) => setTimeout(r, 10 * (i + 1)));
    }
  }
  try { await fs.promises.writeFile(file, text); } finally { await fs.promises.rm(tmp, { force: true }); }
}

const problem = (e, what, where) => `${what} ${where}: ${e.code === "EACCES" || e.code === "EPERM" ? "permission denied" : e.code === "ENOSPC" ? "the disk is full" : e.message}. Pick another folder under Outputs.`;

export class OutputWriter {
  constructor(settings, projectName = "Untitled", { maxRate = 20, onStatus = null } = {}) {
    this.settings = settings;
    this.projectName = projectName;
    this.minInterval = 1000 / maxRate;
    this.onStatus = onStatus;
    this.pending = null;
    this.busy = false;
    this.written = new Map();   // text key -> last text written
    this.lastDoc = 0;
    this.closed = false;
    this.status = Object.fromEntries(["text", "xml", "json"].map((n) => [n, { name: n, state: "off", detail: "", last_write: 0, writes: 0 }]));
    this._idle = [];
  }

  get folder() { return this.settings.folder || defaultOutputFolder(this.projectName); }

  reconfigure(settings, projectName) {
    this.settings = settings;
    if (projectName !== undefined) this.projectName = projectName;
    this.written.clear();       // write everything again to the (maybe new) folder
    if (this.lastSnap) this.submit(this.lastSnap);
  }

  submit(snap) {
    if (this.closed) return;
    this.lastSnap = snap;
    this.pending = snap;
    if (!this.busy) this._run();
  }

  // Resolves once the newest snapshot is on disk (tests, exit).
  flush() {
    if (!this.busy && !this.pending) return Promise.resolve(true);
    return new Promise((r) => this._idle.push(r));
  }

  close() { this.closed = true; return this.flush(); }

  async _run() {
    this.busy = true;
    while (this.pending) {
      const snap = this.pending;
      this.pending = null;
      try { await this._write(snap, this.settings); } catch (e) { console.error("output writer", e); }
    }
    this.busy = false;
    for (const r of this._idle.splice(0)) r(true);
  }

  _set(name, state, detail = "", wrote = false) {
    const st = this.status[name];
    const changed = st.state !== state || st.detail !== detail;
    st.state = state;
    st.detail = detail;
    if (wrote) { st.last_write = Date.now() / 1000; st.writes += 1; }
    if ((changed || wrote) && this.onStatus) { try { this.onStatus(this.status, changed); } catch { /* */ } }
  }

  async _write(snap, s) {
    const folder = this.folder;
    if (s.text_enabled) {
      const tdir = path.join(folder, "text");
      try {
        await fs.promises.mkdir(tdir, { recursive: true });
        let n = 0;
        for (const [key, text] of Object.entries(snap.values)) {
          if (this.written.get(key) === text) continue;
          await atomicWrite(path.join(tdir, textFilename(key)), text);
          this.written.set(key, text);
          n++;
        }
        this._set("text", "ok", tdir, n > 0);
      } catch (e) { this._set("text", "error", problem(e, "Cannot write text files to", tdir)); }
    } else this._set("text", "off");

    // Whole documents, rate limited.
    const wait = this.minInterval - (Date.now() - this.lastDoc);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait));
    this.lastDoc = Date.now();
    if (s.xml_enabled) {
      try {
        await fs.promises.mkdir(folder, { recursive: true });
        for (const prof of s.xml_profiles) {
          const p = XML_PROFILES[prof];
          if (p) await atomicWrite(path.join(folder, p[0]), p[1](snap));
        }
        this._set("xml", "ok", folder, true);
      } catch (e) { this._set("xml", "error", problem(e, "Cannot write XML to", folder)); }
    } else this._set("xml", "off");
    if (s.json_enabled) {
      try {
        await fs.promises.mkdir(folder, { recursive: true });
        await atomicWrite(path.join(folder, "state.json"), stateJson(snap, 1));
        this._set("json", "ok", folder, true);
      } catch (e) { this._set("json", "error", problem(e, "Cannot write JSON to", folder)); }
    } else this._set("json", "off");
  }
}
