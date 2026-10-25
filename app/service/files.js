// Project files on disk. Saving is atomic: the file is written beside the
// target and moved into place, so a crash or a full disk never leaves a
// half-written file, and OBS never reads half a value.

import fs from "node:fs";
import path from "node:path";
import { isLegacy, importLegacy } from "../core/legacy.js";
import { FORMAT, Project, ProjectError } from "../core/project.js";

const sleep = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

// Readers see the old or the new file, never a partial one. On Windows a
// reader can briefly block the replace: retry, then write directly.
export function atomicWriteText(file, text, retries = 5) {
  const dir = path.dirname(path.resolve(file));
  fs.mkdirSync(dir, { recursive: true });
  const tmp = path.join(dir, `.${path.basename(file)}.${process.pid}.tmp`);
  const fd = fs.openSync(tmp, "w");
  try {
    fs.writeSync(fd, text);
    try { fs.fsyncSync(fd); } catch { /* not all file systems */ }
  } finally { fs.closeSync(fd); }
  for (let i = 0; i < retries; i++) {
    try { fs.renameSync(tmp, file); return; } catch (e) {
      if (!["EPERM", "EACCES", "EBUSY"].includes(e.code)) { try { fs.unlinkSync(tmp); } catch { /* */ } throw e; }
      sleep(10 * (i + 1));
    }
  }
  try { fs.writeFileSync(file, text); } finally { try { fs.unlinkSync(tmp); } catch { /* */ } }
}

export function saveProject(project, file = project.path) {
  if (!file) throw new ProjectError("Choose where to save the project first.");
  atomicWriteText(file, JSON.stringify(project.toDict(), null, 1));
  project.path = file;
  return file;
}

export function loadProject(file) {
  let text;
  try { text = fs.readFileSync(file, "utf8"); } catch (e) {
    throw new ProjectError(e.code === "ENOENT" ? "The file does not exist." : `The file could not be read (${e.code}).`);
  }
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  let data;
  try { data = JSON.parse(text); } catch (e) {
    const line = /line (\d+)/.exec(e.message)?.[1] ?? /position (\d+)/.exec(e.message) ? text.slice(0, Number(/position (\d+)/.exec(e.message)[1])).split("\n").length : "?";
    throw new ProjectError(`The file is not valid JSON (line ${line}). It may be damaged.`);
  }
  let p;
  if (data && typeof data === "object" && data.format === FORMAT) {
    p = Project.fromDict(data);
    if (Number(data.version) < 3) {
      // An older 2.0 file: converted, so Save asks for a name rather than replacing it.
      p.importedFrom = file;
      return p;
    }
  } else {
    if (!isLegacy(data)) throw new ProjectError("This file is not a CORBELscore or TeleScore project.");
    p = importLegacy(data);
    p.importedFrom = file;
    return p;   // Save asks for a new .corbel name; the 1.x file is never overwritten
  }
  p.path = file;
  return p;
}
