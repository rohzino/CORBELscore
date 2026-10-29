// A CORBELscore project (.corbel; TeleScore's .tsproj is the same format, JSON). Format 3 keeps fields, graphics boards,
// buttons, the control layout, outputs, animations, live-data settings and
// conditions in one readable file. Format 2 (TeleScore 2.0 alphas) and 1.x
// files are converted on the way in; the original file is never overwritten.

import { makeAnimation } from "./animation.js";
import { compactBoard, makeBoard } from "./board.js";
import { Engine } from "./engine.js";
import { fieldFromDict } from "./fields.js";
import { newId } from "./ids.js";
import { autoLayout, makeLayout } from "./layout.js";
import { Condition } from "./logic.js";
import { makeSource } from "./source.js";

export const FORMAT = "telescore-project";
export const VERSION = 3;
export const APP_VERSION = "2.0.0a5";

export class ProjectError extends Error {}

export const ROLES = { neutral: "Plain", accent: "Main action (green)", hi: "Highlight", user: "Warning (amber)",
  alert: "Danger (red)" };

export function makeButton(o = {}) {
  return { id: String(o.id || newId()), label: String(o.label ?? "Button"), action: structuredClone(o.action ?? {}),
    role: ROLES[o.role] ? o.role : "neutral", hotkey: String(o.hotkey ?? "") };
}

export const OUTPUT_DEFAULTS = {
  folder: "",               // "" = <Documents>/CORBELscore Output/<project>
  text_enabled: true,
  xml_enabled: true,
  xml_profiles: ["nested", "flat", "fields"],
  json_enabled: true,
  http_enabled: true,
  http_port: 8130,
  http_lan: false,          // listen beyond this computer
  http_token: "",           // required for control calls when set
  image_boards: [],         // board ids written as PNG
};

export function makeOutputs(o = {}) {
  const s = structuredClone(OUTPUT_DEFAULTS);
  for (const k of Object.keys(OUTPUT_DEFAULTS)) if (o?.[k] !== undefined) s[k] = structuredClone(o[k]);
  s.http_port = Math.trunc(Number(s.http_port));
  if (!(s.http_port >= 1024 && s.http_port <= 65535)) s.http_port = 8130;
  return s;
}

function load(fn, items, what) {
  return (items || []).map((d) => {
    try { return fn(d); } catch (e) { throw new ProjectError(`A ${what} could not be read: ${e.message}`); }
  });
}

export class Project {
  constructor(o = {}) {
    this.name = o.name ?? "Untitled";
    this.author = o.author ?? "";
    this.sport = o.sport ?? "generic";
    this.created = o.created ?? new Date().toISOString().slice(0, 19);
    this.engine = o.engine ?? new Engine([]);
    this.boards = o.boards ?? [];
    this.buttons = o.buttons ?? [];
    this.layout = o.layout ?? makeLayout();
    this.outputs = o.outputs ?? makeOutputs();
    this.animations = o.animations ?? [];
    this.source = o.source ?? makeSource();
    this.path = "";            // not saved
    this.importedFrom = "";    // not saved; set when an older file was converted
    this.importNotes = [];     // not saved
  }

  board(id) { return this.boards.find((b) => b.id === id) ?? null; }
  button(id) { return this.buttons.find((b) => b.id === id) ?? null; }

  toDict() {
    return {
      format: FORMAT, version: VERSION, app: APP_VERSION, name: this.name, author: this.author, sport: this.sport,
      created: this.created, saved: new Date().toISOString().slice(0, 19),
      fields: this.engine.fieldsToList(),
      boards: this.boards.map(compactBoard),
      buttons: structuredClone(this.buttons),
      layout: structuredClone(this.layout),
      outputs: structuredClone(this.outputs),
      conditions: this.engine.logic.conditions.map((c) => c.toDict()),
      animations: this.animations.map(({ builtin, ...a }) => a),
      source: { ...this.source },
    };
  }

  static fromDict(d) {
    if (d?.format !== FORMAT) throw new ProjectError("This is not a CORBELscore project.");
    const version = Math.trunc(Number(d.version ?? 0));
    if (version > VERSION) {
      throw new ProjectError(`This project was saved by a newer CORBELscore (format ${d.version}). Update CORBELscore to open it.`);
    }
    const fields = (d.fields || []).map((fd) => {
      try { return fieldFromDict(fd); } catch (e) { throw new ProjectError(`Field "${fd?.key ?? "?"}" could not be read: ${e.message}`); }
    });
    let engine;
    try { engine = new Engine(fields); } catch (e) { throw new ProjectError(e.message); }
    const p = new Project({
      name: String(d.name ?? "Untitled"), author: String(d.author ?? ""), sport: String(d.sport ?? "generic"),
      created: String(d.created ?? ""), engine,
      boards: load(makeBoard, d.boards, "board"),
      outputs: makeOutputs(d.outputs),
      animations: load(makeAnimation, d.animations, "animation"),
      source: makeSource(d.source),
    });
    if (version < 3) {
      // 2.0 alphas kept buttons in panels and built controls from the field list.
      p.buttons = (d.panels || []).flatMap((panel) => (panel.buttons || []).map(makeButton));
      p.layout = autoLayout(engine.fieldsToList(), p.buttons);
      p.importNotes.push("The controls were laid out automatically from your fields and buttons. Arrange them in Edit.");
    } else {
      p.buttons = load(makeButton, d.buttons, "button");
      p.layout = makeLayout(d.layout);
    }
    engine.setConditions(load((c) => Condition.fromDict(c), d.conditions, "condition"));
    return p;
  }
}
