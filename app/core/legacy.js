// Import TeleScore 1.x project files. 1.x saved a JSON object keyed by numbers
// ("0" header, "1" layouts; per layout "9" properties and "2" components; per
// component "0" type, "9" properties, "11" connections). Display widgets become
// fields plus board elements; buttons become buttons whose actions reproduce the
// old connections. Anything that cannot be converted is listed in importNotes.

import { makeBoard, makeElement } from "./board.js";
import { Clock } from "./clock.js";
import { Engine } from "./engine.js";
import { ClockField, CounterField, ImageField, PenaltyField, TextField, ToggleField, normaliseKey } from "./fields.js";
import { autoLayout } from "./layout.js";
import { makeButton, makeOutputs, Project } from "./project.js";
import { LEGACY_FORMATS, parseTime } from "./timefmt.js";

const WEIGHTS = [300, 400, 500, 600, 700, 800, 900];
const ALIGN = ["left", "center", "right"];
const INPUT_TYPES = new Set(["Type Time Amount", "Type Points Amount", "Type Text", "Image Set"]);
const CLOCK_SIGNALS = { Start: { do: "start" }, Stop: { do: "stop" }, Reset: { do: "reset" }, ADDS: { do: "adjust", ms: 1000 },
  SUBS: { do: "adjust", ms: -1000 }, ADDM: { do: "adjust", ms: 60_000 }, SUBM: { do: "adjust", ms: -60_000 } };
const BUTTON_ROLES = { "Start Time": "accent", "Stop Time": "alert", Reset: "hi", "Sub Points": "alert", "Add Points": "accent" };

export const isLegacy = (d) => !!d && typeof d === "object" && "0" in d && Array.isArray(d["1"]);

function unique(key, used) {
  const base = key;
  let n = 2;
  while (used.has(key) || [...used].some((u) => u.startsWith(key + ".") || key.startsWith(u + "."))) key = `${base}_${n++}`;
  used.add(key);
  return key;
}

function style(el, p) {
  if (p["Font Color"]) el.color = String(p["Font Color"]);
  if (p["Display Font"]) el.font = String(p["Display Font"]);
  const s = Number(p["Font Size"] ?? 10);
  if (Number.isFinite(s)) el.size = Math.max(6, (s * 96) / 72);   // points at 96 dpi
  const w = p["Font Weight"];
  if (Number.isInteger(w) && w >= 0 && w < WEIGHTS.length) el.weight = WEIGHTS[w];
  const a = p["Text Alignment"];
  if (Number.isInteger(a) && a >= 0 && a < ALIGN.length) el.align = ALIGN[a];
  el.fit = true;
  el.tabular = true;
}

function geom(p) {
  const num = (k, d) => { const n = Number(p[k] ?? d); return Number.isFinite(n) ? n : d; };
  return [num("X", 0), num("Y", 0), Math.max(8, num("Width", 100)), Math.max(8, num("Height", 40))];
}

export function importLegacy(data) {
  const header = data["0"] || {};
  const notes = [];
  const used = new Set();
  const fields = [];
  const boards = [];
  const buttons = [];
  const compField = {};
  const pendingButtons = [];
  const elementsByComp = {};
  let firstClock = null;
  const penalties = [];

  for (const layout of data["1"] || []) {
    const lp = layout["9"] || {};
    const board = makeBoard({ name: String(lp["Component Name"] || `Layout ${boards.length + 1}`),
      width: Math.trunc(Number(lp.Width) || 800), height: Math.trunc(Number(lp.Height) || 600),
      background: String(lp["Background Color"] || "#000000") });
    if (lp["Background Image"]) {
      board.elements.push(makeElement({ kind: "image", name: "Background image", x: 0, y: 0, w: board.width, h: board.height,
        src: String(lp["Background Image"]), locked: true }));
    }
    for (const comp of layout["2"] || []) {
      const ctype = String(comp["0"] ?? "");
      const p = comp["9"] || {};
      const cname = String(p["Component Name"] || ctype);
      const conns = comp["11"] || {};
      const [x, y, w, h] = geom(p);
      const fill = p["Transparent Background"] ? "" : String(p["Background Color"] || "");
      let key, el;
      if (ctype === "Time Display") {
        key = unique(normaliseKey(cname.toLowerCase().startsWith("clock") ? cname : "clock." + cname), used);
        const fi = p.Format ?? 0;
        const fmt = Number.isInteger(fi) && fi >= 0 && fi < LEGACY_FORMATS.length ? LEGACY_FORMATS[fi] : "mm:ss";
        const stopwatch = !!p.Stopwatch;
        let initial = 0;
        try { initial = parseTime(String(p["Default Time"] || "00:00")); } catch {
          notes.push(`${cname}: the default time "${p["Default Time"]}" could not be read; set to 0:00.`);
        }
        const c = new Clock({ countdown: !stopwatch, initial_ms: initial, fmt, blank_at_zero: !!p["Clr when time = 0"],
          tenths_under_ms: p["Tenth of a second"] && !stopwatch ? 60_000 : 0, tenths_fmt: "ss.t" });
        fields.push(new ClockField(key, { label: cname, clock: c, buzzer: String(p["Buzzer Sound"] || "") }));
        firstClock ??= key;
        el = makeElement({ kind: "text", name: cname, x, y, w, h, text: `{${key}}`, fill });
        style(el, p);
      } else if (ctype === "Points Display") {
        key = unique(normaliseKey(cname), used);
        fields.push(new CounterField(key, { label: cname, minimum: null, ordinal: [2, true].includes(p["Suffix (st, nd, rd, th)"]),
          blank_zero: !!p["Clr when points = 0"] }));
        el = makeElement({ kind: "text", name: cname, x, y, w, h, text: `{${key}}`, fill });
        style(el, p);
      } else if (ctype === "Text Display") {
        key = unique(normaliseKey(cname), used);
        fields.push(new TextField(key, { label: cname, value: String(p["Display Text"] || "") }));
        el = makeElement({ kind: "text", name: cname, x, y, w, h, text: `{${key}}`, fill });
        style(el, p);
      } else if (ctype === "Image Display") {
        key = unique(normaliseKey(cname), used);
        fields.push(new ImageField(key, { label: cname, value: String(p["Default Image"] || "") }));
        el = makeElement({ kind: "image", name: cname, x, y, w, h, src: `{${key}}` });
      } else if (ctype === "Team Attribute") {
        key = unique(normaliseKey(cname), used);
        for (const s of ["name", "attr", "logo"]) used.add(`${key}.${s}`);
        fields.push(new TextField(`${key}.name`, { label: `${cname} name` }), new TextField(`${key}.attr`, { label: `${cname} detail` }),
          new ImageField(`${key}.logo`, { label: `${cname} logo` }));
        el = makeElement({ kind: "text", name: cname, x, y, w, h, text: `{${key}.name}`, fill });
        style(el, p);
      } else if (ctype === "Penalty") {
        key = unique(normaliseKey(cname), used);
        const pf = new PenaltyField(key, { label: cname, master: "", slots: 2 });
        penalties.push(pf);
        fields.push(pf);
        el = makeElement({ kind: "text", name: cname, x, y, w, h, text: `{${key}.1.player} {${key}.1.time}`, fill });
        style(el, p);
      } else if (INPUT_TYPES.has(ctype)) {
        notes.push(`${cname} (${ctype}): typing a value is built into every control now, so this box was not carried over.`);
        continue;
      } else {
        pendingButtons.push([ctype, p, conns]);
        continue;
      }
      compField[cname] = [ctype, key];
      board.elements.push(el);
      (elementsByComp[cname] ??= []).push(el);
    }
    boards.push(board);
  }
  for (const pf of penalties) {
    if (firstClock) pf.master = firstClock;
    else notes.push(`${pf.label}: there is no game clock to run penalties from; add one and pick it in the field's properties.`);
  }

  const visKeys = {};
  for (const [ctype, p, conns] of pendingButtons) {
    const label = String(p["Display Text"] || p["Component Name"] || ctype).replace(/\n/g, " ").trim();
    const actions = [];
    for (const [signal, receivers] of Object.entries(conns || {})) {
      for (const rname of receivers || []) {
        const target = compField[rname];
        if (!target) continue;
        const [kind, key] = target;
        if (CLOCK_SIGNALS[signal] && kind === "Time Display") actions.push({ ...CLOCK_SIGNALS[signal], field: key });
        else if (["Add Points", "Sub Points", "Set Points"].includes(signal) && kind === "Points Display") {
          let amount = Math.trunc(Number(p["Set Amount"] ?? 1));
          if (!Number.isFinite(amount)) amount = 1;
          if (signal === "Set Points") actions.push({ do: "set", field: key, value: amount });
          else actions.push({ do: "add", field: key, amount: signal === "Add Points" ? amount : -amount });
        } else if (signal === "Set Visible" || signal === "Set Invisible") {
          let vis = visKeys[rname];
          if (!vis) {
            vis = visKeys[rname] = unique(normaliseKey(`show.${rname}`), used);
            fields.push(new ToggleField(vis, { label: `Show ${rname}`, value: true, default: true }));
            for (const el of elementsByComp[rname] || []) el.show_when = vis;
          }
          actions.push({ do: "set", field: vis, value: signal === "Set Visible" });
        } else if (kind === "Penalty") { /* penalties now follow their master clock */ }
        else notes.push(`Button "${label}": its "${signal}" connection to "${rname}" has no 2.0 equivalent.`);
      }
    }
    if (!actions.length) { notes.push(`Button "${label}" (${ctype}) was not connected to anything and was left out.`); continue; }
    buttons.push(makeButton({ label, action: actions.length === 1 ? actions[0] : { do: "batch", actions }, role: BUTTON_ROLES[ctype] ?? "neutral",
      hotkey: String(p.Hotkey || "") }));
  }
  const outputs = makeOutputs();
  const gd = String(header["Global Directory"] || "");
  if (gd && !["./Output", "./Output/{}"].includes(gd)) outputs.folder = gd.replace("/{}", "");
  const engine = new Engine(fields);
  const project = new Project({ name: String(header.Name || "Imported project"), author: String(header.Author || ""), engine,
    boards: boards.length ? boards : [makeBoard({ name: "Board 1" })], buttons, outputs, sport: "imported",
    layout: autoLayout(engine.fieldsToList(), buttons, { pageName: "Imported" }) });
  notes.push("Text files are now named after field keys (for example home.score.txt in the text folder); update the file paths in OBS or vMix once.");
  project.importNotes = notes;
  return project;
}
