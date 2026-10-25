// Per-computer settings (not part of any project): recent files, theme,
// background shortcuts, and the Sportzcast token, which never goes into a
// project file so projects can be shared safely.

import fs from "node:fs";
import path from "node:path";
import { atomicWriteText } from "./files.js";

export const SETTINGS_DEFAULTS = { recent: [], scheme: "Keystone Dark", global_keys: false, last_board: "", window: null,
  sportzcast_token: "" };

export class Settings {
  constructor(dir) {
    this.dir = dir;
    fs.mkdirSync(dir, { recursive: true });
    this.file = path.join(dir, "settings.json");
    this.data = { ...SETTINGS_DEFAULTS };
    try { Object.assign(this.data, JSON.parse(fs.readFileSync(this.file, "utf8"))); } catch { /* first run or damaged: defaults */ }
  }
  get(k) { return this.data[k]; }
  set(k, v) { this.data[k] = v; this.save(); }
  save() { try { atomicWriteText(this.file, JSON.stringify(this.data, null, 1)); } catch (e) { console.error("settings", e.message); } }
  addRecent(file) {
    const norm = (p) => path.resolve(p).toLowerCase();
    const list = [path.resolve(file), ...this.data.recent.filter((p) => norm(p) !== norm(file))].slice(0, 12);
    this.set("recent", list);
  }
  // What the UI may see: no secrets.
  forUi() {
    const { sportzcast_token, window, ...rest } = this.data;
    return { ...rest, has_token: !!sportzcast_token, recent: this.data.recent.filter((p) => fs.existsSync(p)).map((p) => {
      let mtime = 0;
      try { mtime = fs.statSync(p).mtimeMs; } catch { /* */ }
      return { path: p, name: path.basename(p).replace(/\.tsproj$/i, ""), folder: path.dirname(p), mtime };
    }) };
  }
}
