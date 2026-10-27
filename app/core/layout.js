// The control layout: pages of tiles on a grid, arranged by the operator.
//   layout = { columns: 24, pages: [{ id, name, tiles: [tile] }] }
//   tile   = { id, kind, x, y, w, h, ...props }   (x, w in columns; y, h in rows)
// kinds:
//   field    a control for one field, drawn by its type   { field, label? }
//   button   one of the project's buttons                 { button }
//   heading  a section title                              { text }
//   preview  a live picture of a board                    { board }

import { newId } from "./ids.js";

export const COLUMNS = 24;
export const TILE_KINDS = ["field", "button", "heading", "preview"];

// Comfortable default sizes (columns x rows) per tile; rows are about 40 px.
export function defaultSize(kind, fieldType, field = null) {
  if (kind === "button") return [3, 2];
  if (kind === "heading") return [8, 1];
  if (kind === "preview") return [8, 5];
  if (fieldType === "counter" && (field?.steps?.length ?? 1) > 1) return [8, 3];   // a score with +1 +2 +3
  if (fieldType === "choice") return [8, (field?.options?.length ?? 0) > 6 ? 3 : 2];
  return ({ clock: [8, 5], counter: [4, 3], text: [8, 2], toggle: [4, 2], choice: [8, 2], penalties: [8, 5],
    image: [4, 3] })[fieldType] ?? [4, 2];
}

// Fields an operator sets before the game (names, colours, logos) go on their
// own page so the game page stays short.
export const isSetupField = (f) => f.type === "image" || (f.type === "text" && /\.(name|short|abbr|color|colour|logo)$/.test(f.key));

export function makeTile(o = {}) {
  const t = { ...structuredClone(o) };
  t.id = o.id || newId();
  t.kind = o.kind || "field";
  if (!TILE_KINDS.includes(t.kind)) throw new Error(`Unknown tile kind "${t.kind}".`);
  for (const k of ["x", "y", "w", "h"]) t[k] = Math.max(k === "w" || k === "h" ? 1 : 0, Math.trunc(Number(t[k] ?? (k === "w" || k === "h" ? 2 : 0))));
  t.w = Math.min(COLUMNS, t.w);
  t.x = Math.min(COLUMNS - t.w, t.x);
  return t;
}

export function makePage(o = {}) {
  return { id: o.id || newId(), name: String(o.name ?? "Page"), tiles: (o.tiles || []).map(makeTile) };
}

export function makeLayout(o = {}) {
  const pages = (o.pages || []).map(makePage);
  return { columns: COLUMNS, pages: pages.length ? pages : [makePage({ name: "Controls" })] };
}

export const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

// The first free place for a w x h tile, scanning rows top to bottom.
export function findSpot(tiles, w, h, startY = 0) {
  for (let y = startY; y < 500; y++) {
    for (let x = 0; x + w <= COLUMNS; x++) {
      const probe = { x, y, w, h };
      if (!tiles.some((t) => overlaps(t, probe))) return { x, y };
    }
  }
  return { x: 0, y: bottom(tiles) };
}

export const bottom = (tiles) => tiles.reduce((m, t) => Math.max(m, t.y + t.h), 0);

// Push tiles down so none overlap, keeping the moved ones where they were put.
export function settle(tiles, fixedIds = []) {
  const fixed = new Set(fixedIds);
  const order = [...tiles].sort((a, b) => (fixed.has(b.id) - fixed.has(a.id)) || a.y - b.y || a.x - b.x);
  const placed = [];
  for (const t of order) {
    while (placed.some((p) => overlaps(p, t))) t.y += 1;
    placed.push(t);
  }
  return tiles;
}

// A starting layout from fields and buttons: on the Game page, away fields on
// the left, home on the right, clocks and the rest in the middle, buttons
// below; names, colours and logos on a Teams page.
export function autoLayout(fields, buttons = [], { pageName = "Game" } = {}) {
  const game = fields.filter((f) => !isSetupField(f));
  const setup = fields.filter(isSetupField);
  const pages = [makePage({ name: pageName, tiles: columns(game, buttons.filter((b) => b.place !== false)) })];
  if (setup.length) pages.push(makePage({ name: "Teams", tiles: columns(setup, []) }));
  return { columns: COLUMNS, pages };
}

function columns(fields, buttons) {
  const tiles = [];
  const cols = { away: [0, 8], home: [16, 8], mid: [8, 8] };
  const y = { away: 0, home: 0, mid: 0 };
  // possession.home and serve.home belong to a team as much as home.score does.
  const side = (key) => { const parts = key.split("."); return parts.includes("away") ? "away" : parts.includes("home") ? "home" : "mid"; };
  const hasTeams = fields.some((f) => side(f.key) !== "mid");
  if (hasTeams) {
    for (const [s, text] of [["away", "Away"], ["mid", "Game"], ["home", "Home"]]) {
      if (s === "mid" && !fields.some((f) => side(f.key) === "mid")) continue;
      tiles.push(makeTile({ kind: "heading", text, x: cols[s][0], y: 0, w: 8, h: 1 }));
      y[s] = 1;
    }
  }
  // Within a column, half-width tiles of the same height pair up side by side.
  const pending = { away: null, home: null, mid: null };
  let clocks = 0;
  for (const f of fields) {
    let [w0, h] = defaultSize("field", f.type, f);
    if (f.type === "clock" && clocks++ > 0) h = 4;                 // the game clock is the big one
    if (f.type === "text" && side(f.key) === "mid" && hasTeams) w0 = 4;  // e.g. distance, added time
    const s = hasTeams ? side(f.key) : "mid";
    if (!hasTeams) {
      const spot = findSpot(tiles, w0, h);
      tiles.push(makeTile({ kind: "field", field: f.key, x: spot.x, y: spot.y, w: w0, h }));
      continue;
    }
    const [x0, width] = cols[s];
    const w = Math.min(w0, width);
    const half = width / 2;
    const p = pending[s];
    if (w <= half && p && p.h === h) {
      tiles.push(makeTile({ kind: "field", field: f.key, x: x0 + half, y: p.y, w: half, h }));
      pending[s] = null;
      continue;
    }
    pending[s] = null;
    tiles.push(makeTile({ kind: "field", field: f.key, x: x0, y: y[s], w: w <= half ? half : width, h }));
    if (w <= half) pending[s] = { y: y[s], h };
    y[s] += h;
  }
  if (buttons.length) {
    const top = bottom(tiles) + (tiles.length ? 1 : 0);
    tiles.push(makeTile({ kind: "heading", text: "Shortcuts", x: 0, y: top, w: 24, h: 1 }));
    buttons.forEach((b, i) => tiles.push(makeTile({ kind: "button", button: b.id, x: (i % 8) * 3, y: top + 1 + Math.floor(i / 8) * 2, w: 3, h: 2 })));
  }
  return settle(tiles);
}

// Field keys a layout uses (for renames and checks).
export function layoutFieldKeys(layout) {
  return layout.pages.flatMap((p) => p.tiles.filter((t) => t.kind === "field").map((t) => t.field));
}
