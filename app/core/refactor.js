// Project-wide field renames and usage lookups.

import { elementKeys, templateKeys } from "./board.js";
import { PenaltyField } from "./fields.js";

const swapKey = (k, oldKey, newKey) => (k === oldKey ? newKey : k.startsWith(oldKey + ".") ? newKey + k.slice(oldKey.length) : k);

function* walk(a) {
  if (!a || typeof a !== "object") return;
  yield a;
  for (const sub of a.actions || []) yield* walk(sub);
}

// Rename a field and update every template, show-when, button action, layout
// tile, condition and penalty master that refers to it (sub-keys included, so
// {home.penalties.1.time} follows home.penalties). Returns references changed.
export function renameFieldEverywhere(project, oldKey, newKey) {
  project.engine.renameField(oldKey, newKey);
  let count = 0;
  const tpl = (t) => {
    if (!t || !t.includes("{")) return t;
    let out = t;
    for (const k of new Set(templateKeys(t))) {
      const nk = swapKey(k, oldKey, newKey);
      if (nk !== k) { out = out.split(`{${k}}`).join(`{${nk}}`); count++; }
    }
    return out;
  };
  const key = (k) => {
    if (!k) return k;
    const nk = swapKey(k, oldKey, newKey);
    if (nk !== k) count++;
    return nk;
  };
  for (const b of project.boards) {
    b.background = tpl(b.background);
    for (const e of b.elements) {
      for (const p of ["text", "src", "fill", "stroke", "color"]) e[p] = tpl(e[p]);
      e.show_when = key(e.show_when);
    }
  }
  for (const btn of project.buttons) for (const a of walk(btn.action)) if (a.field) a.field = key(a.field);
  for (const page of project.layout.pages) for (const t of page.tiles) if (t.kind === "field") t.field = key(t.field);
  for (const c of project.engine.logic.conditions) {
    c.principal = key(c.principal);
    if (c.target_kind === "field") c.target = key(c.target);
    for (const a of walk(c.run)) if (a.field) a.field = key(a.field);
  }
  for (const f of project.engine.fields.values()) {
    if (f instanceof PenaltyField && f.master === oldKey) { f.master = newKey; count++; }
  }
  project.engine.setConditions(project.engine.logic.conditions);
  return count;
}

// Human-readable places where key (or one of its sub-keys) is used.
export function fieldReferences(project, key) {
  const uses = (k) => !!k && (k === key || k.startsWith(key + "."));
  const out = [];
  for (const b of project.boards) for (const e of b.elements) if (elementKeys(e).some(uses)) out.push(`${b.name} → ${e.name || e.kind}`);
  for (const btn of project.buttons) if ([...walk(btn.action)].some((a) => uses(a.field))) out.push(`Button “${btn.label}”`);
  for (const page of project.layout.pages) for (const t of page.tiles) if (t.kind === "field" && uses(t.field)) out.push(`Control on page “${page.name}”`);
  for (const c of project.engine.logic.conditions) {
    if (uses(c.principal) || (c.target_kind === "field" && uses(c.target)) || [...walk(c.run)].some((a) => uses(a.field))) out.push(`Condition “${c.describe()}”`);
  }
  for (const f of project.engine.fields.values()) if (f instanceof PenaltyField && f.master === key) out.push(`${f.label} (runs from this clock)`);
  return out;
}
