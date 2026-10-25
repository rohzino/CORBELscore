// Feed documents built from an engine snapshot. All UTF-8, regenerated whole.
//
// nested -> telescore.xml   field keys become a tree: home.score is
//   <home><score>3</score></home>; a field's sub-keys are attributes
//   (<game running="1">4:07</game>, penalty slots p1_player, p1_time), so
//   string() of an element is always its value. For Ross XPression and Chyron.
// flat -> vmix.xml          one <row> with every value as a child, dots as
//   underscores: <home_score>3</home_score>. vMix data source XPath //row.
// fields -> fields.xml      one <field key type label>value</field> per value,
//   validated by docs/schema/fields.xsd: //field[@key='home.score'].
// Plus state.json and one .txt file per key.

const NAME_BAD = /[^A-Za-z0-9_-]/g;
// XML 1.0 forbids most control characters even when escaped.
const XML_ILLEGAL = /[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]/g;

const clean = (t) => String(t ?? "").replace(XML_ILLEGAL, "");
export const escapeText = (t) => clean(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
export const quoteAttr = (t) => `"${escapeText(t).replace(/"/g, "&quot;").replace(/\n/g, "&#10;").replace(/\r/g, "&#13;").replace(/\t/g, "&#9;")}"`;

// A valid XML element name for part (keys may start with digits).
export function xmlName(part) {
  let n = String(part).replace(NAME_BAD, "_") || "_";
  if (!/^[A-Za-z_]/.test(n) || n.toLowerCase().startsWith("xml")) n = "_" + n;
  return n;
}

// Local time with milliseconds, no zone (xs:dateTime accepts it).
export function stamp(wall) {
  const d = new Date(wall * 1000);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

// Top-level field keys, and each field's sub-keys {field: {sub: text}}.
function split(snap) {
  const fields = Object.keys(snap.types);
  const fset = new Set(fields);
  const subs = Object.fromEntries(fields.map((k) => [k, {}]));
  for (const [key, text] of Object.entries(snap.values)) {
    if (fset.has(key)) continue;
    const parts = key.split(".");
    for (let i = parts.length - 1; i > 0; i--) {
      const cand = parts.slice(0, i).join(".");
      if (fset.has(cand)) { subs[cand][key.slice(cand.length + 1)] = text; break; }
    }
  }
  return [fields, subs];
}

// "1.player" -> "p1_player", "running" -> "running"
function attrName(sub) {
  const parts = sub.split(".");
  if (/^\d+$/.test(parts[0])) parts[0] = "p" + parts[0];
  return xmlName(parts.join("_"));
}

const VALUE = Symbol("value");

export function xmlNested(snap, root = "telescore") {
  const [fields, subs] = split(snap);
  const tree = new Map();
  for (const k of fields) {
    let node = tree;
    for (const part of k.split(".")) {
      if (!node.has(part)) node.set(part, new Map());
      node = node.get(part);
    }
    node[VALUE] = k;
  }
  const out = ['<?xml version="1.0" encoding="UTF-8"?>', `<${root} version="2" seq="${snap.seq}" updated="${stamp(snap.wall)}">`];
  const walk = (node, depth) => {
    const pad = "  ".repeat(depth);
    for (const [name, child] of node) {
      const tag = xmlName(name);
      const key = child[VALUE];
      let attrs = "";
      if (key !== undefined) {
        attrs = ` type=${quoteAttr(snap.types[key])}`;
        for (const [sub, text] of Object.entries(subs[key] ?? {})) attrs += ` ${attrName(sub)}=${quoteAttr(text)}`;
      }
      if (child.size) {
        if (key !== undefined) attrs += ` value=${quoteAttr(snap.values[key] ?? "")}`;
        out.push(`${pad}<${tag}${attrs}>`);
        walk(child, depth + 1);
        out.push(`${pad}</${tag}>`);
      } else {
        const text = key !== undefined ? escapeText(snap.values[key] ?? "") : "";
        out.push(`${pad}<${tag}${attrs}>${text}</${tag}>`);
      }
    }
  };
  walk(tree, 1);
  out.push(`</${root}>`);
  return out.join("\n") + "\n";
}

export function xmlFlat(snap) {
  const out = ['<?xml version="1.0" encoding="UTF-8"?>', `<data seq="${snap.seq}" updated="${stamp(snap.wall)}">`, "  <row>"];
  const seen = new Set();
  for (const [key, text] of Object.entries(snap.values)) {
    let tag = xmlName(key.replace(/\./g, "_"));
    while (seen.has(tag)) tag += "_";   // e.g. home.score_x vs home_score.x
    seen.add(tag);
    out.push(`    <${tag}>${escapeText(text)}</${tag}>`);
  }
  out.push("  </row>", "</data>");
  return out.join("\n") + "\n";
}

export function xmlFields(snap) {
  const [fields, subs] = split(snap);
  const out = ['<?xml version="1.0" encoding="UTF-8"?>', `<fields version="2" seq="${snap.seq}" updated="${stamp(snap.wall)}">`];
  for (const k of fields) {
    const raw = snap.raw[k];
    let rawAttr = "";
    if (typeof raw === "boolean") rawAttr = ` raw="${raw ? 1 : 0}"`;
    else if (Number.isInteger(raw) && String(raw) !== snap.values[k]) rawAttr = ` raw="${raw}"`;
    out.push(`  <field key=${quoteAttr(k)} type=${quoteAttr(snap.types[k])} label=${quoteAttr(snap.labels[k] ?? k)}${rawAttr}>${escapeText(snap.values[k] ?? "")}</field>`);
    for (const [sub, text] of Object.entries(subs[k] ?? {})) {
      out.push(`  <field key=${quoteAttr(`${k}.${sub}`)} type="sub" label=${quoteAttr(`${snap.labels[k] ?? k} ${sub}`)}>${escapeText(text)}</field>`);
    }
  }
  out.push("</fields>");
  return out.join("\n") + "\n";
}

export function stateJson(snap, indent) {
  const raw = {};
  for (const [k, v] of Object.entries(snap.raw)) raw[k] = ["number", "string", "boolean"].includes(typeof v) || v === null ? v : String(v);
  return JSON.stringify({ version: 2, seq: snap.seq, updated: stamp(snap.wall), values: snap.values, raw, types: snap.types,
    labels: snap.labels, fx: snap.fx }, null, indent);
}

export const XML_PROFILES = {
  nested: ["telescore.xml", xmlNested, "Ross XPression DataLinq, Chyron: address values by path, e.g. /telescore/home/score"],
  flat: ["vmix.xml", xmlFlat, "vMix data source: one row, XPath //row; columns are home_score, clock_game …"],
  fields: ["fields.xml", xmlFields, "Any system that looks values up by key: //field[@key='home.score']"],
};

const FILE_BAD = /[<>:"/\\|?*\x00-\x1f]/g;
const RESERVED = new Set(["CON", "PRN", "AUX", "NUL", ...[1, 2, 3, 4, 5, 6, 7, 8, 9].flatMap((i) => [`COM${i}`, `LPT${i}`])]);

// home.score -> home.score.txt (safe on Windows)
export function textFilename(key) {
  let name = key.replace(FILE_BAD, "_").replace(/^[. ]+|[. ]+$/g, "") || "field";
  if (RESERVED.has(name.split(".")[0].toUpperCase())) name = "_" + name;
  return name + ".txt";
}
