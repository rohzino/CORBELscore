// Live-data payloads -> flat {key: text}. Nested keys are joined with dots.

import { parseXml } from "./xml.js";

function scalar(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "1" : "0";
  return String(v);
}

// {"a": {"b": 1}, "c": [5, 6]} -> {"a.b": "1", "c.0": "5", "c.1": "6"}
export function flattenJson(obj, prefix = "", out = {}) {
  if (obj && typeof obj === "object") {
    const entries = Array.isArray(obj) ? obj.map((v, i) => [String(i), v]) : Object.entries(obj);
    for (const [k, v] of entries) flattenJson(v, prefix ? `${prefix}.${k}` : k, out);
  } else out[prefix || "value"] = scalar(obj);
  return out;
}

// The root's descendants as dotted keys: <info><Hscore>42</Hscore></info> ->
// {Hscore: "42"}. Repeated siblings get .1, .2 ...; attributes become tag_attr.
export function flattenXml(text) {
  const root = parseXml(text);
  const out = {};
  const walk = (el, p) => {
    for (const [a, v] of Object.entries(el.attrs)) out[p ? `${p}_${a}` : a] = v;
    if (!el.children.length) { if (p) out[p] = el.text.trim(); return; }
    const counts = {};
    for (const k of el.children) counts[k.name] = (counts[k.name] ?? 0) + 1;
    const seen = {};
    for (const k of el.children) {
      let name = k.name;
      if (counts[name] > 1) { seen[name] = (seen[name] ?? 0) + 1; name = `${name}.${seen[name]}`; }
      walk(k, p ? `${p}.${name}` : name);
    }
  };
  walk(root, "");
  return out;
}

// JSON or XML, detected from the first character; pipe-separated SB data too.
export function parsePayload(data) {
  let text = (typeof data === "string" ? data : Buffer.from(data).toString("utf8")).replace(/^﻿/, "").trim().replace(/^\0+|\0+$/g, "").trim();
  if (!text) return {};
  if (text[0] === "{" || text[0] === "[") return flattenJson(JSON.parse(text));
  if (text[0] === "<") return flattenXml(text);
  if (text.includes("|")) return Object.fromEntries(text.split("|").map((p, i) => [`field${i + 1}`, p]));
  throw new Error("The data is not JSON or XML.");
}

const STX = 0x02, ETX = 0x03;

// STX ... ETX frames from a byte stream: [payloads, leftover].
export function splitFrames(buf) {
  const frames = [];
  for (;;) {
    const s = buf.indexOf(STX);
    if (s < 0) return [frames, Buffer.alloc(0)];
    const e = buf.indexOf(ETX, s + 1);
    if (e < 0) return [frames, buf.subarray(s)];
    frames.push(buf.subarray(s + 1, e));
    buf = buf.subarray(e + 1);
  }
}

// Sportzcast key -> TeleScore template field. From the base contract
// (HomeScore, GuestScore, Clock ...) and LiveXML (Hscore, Vscore ...).
export const KNOWN_KEYS = {
  HomeScore: "home.score", GuestScore: "away.score", HomeRuns: "home.score", GuestRuns: "away.score",
  HomeTeamName: "home.name", GuestTeamName: "away.name", Clock: "clock.game", Period: "period", Quarter: "period",
  Half: "period", Inning: "inning", ShotClock: "clock.shot", PlayClock: "clock.play", HomeFouls: "home.fouls",
  GuestFouls: "away.fouls", HomeTimeouts: "home.timeouts", GuestTimeouts: "away.timeouts", HomeTOL: "home.timeouts",
  GuestTOL: "away.timeouts", HomeShots: "home.shots", GuestShots: "away.shots", HomeSOG: "home.shots", GuestSOG: "away.shots",
  Down: "down", DownNumber: "down", Downs: "down", ToGo: "distance", YardsToGo: "distance", YardsToGain: "distance", Distance: "distance",
  Qtr: "period", PeriodNumber: "period", Balls: "balls", Ball: "balls", Strikes: "strikes", Strike: "strikes",
  Outs: "outs", Out: "outs", HomeSets: "home.sets", GuestSets: "away.sets", Set: "set",
  Hscore: "home.score", Vscore: "away.score", Htimeouts: "home.timeouts", Vtimeouts: "away.timeouts", Hfouls: "home.fouls",
  Vfouls: "away.fouls", period: "period", down: "down", clock: "clock.game",
};

function norm(k) {
  let s = k.split(".").at(-1).toLowerCase().replace(/[^a-z0-9]/g, "");
  for (const [a, b] of [["guest", "away"], ["visitor", "away"], ["visiting", "away"]]) if (s.startsWith(a)) s = b + s.slice(a.length);
  return s;
}

// Propose {field key: source key} for fields not bound yet.
export function suggest(sourceKeys, fieldKeys) {
  const fields = [...fieldKeys];
  const fset = new Set(fields);
  const out = {};
  const keys = [...sourceKeys];
  for (const sk of keys) {
    const fk = KNOWN_KEYS[sk.split(".").at(-1)];
    if (fk && fset.has(fk) && !(fk in out)) out[fk] = sk;
  }
  const byNorm = Object.fromEntries(fields.map((f) => [norm(f.replace(/\./g, "")), f]));
  for (const sk of keys) {
    const fk = byNorm[norm(sk)];
    if (fk && !(fk in out) && !Object.values(out).includes(sk)) out[fk] = sk;
  }
  return out;
}
