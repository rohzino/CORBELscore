// Control tab: design and run the game in one place.
//   Edit    Library | Layout | Properties. Drag fields and buttons onto the
//           grid, move and resize tiles; controls do not fire while editing.
//   Locked  the layout alone, full width, every control live.
// Edit mode is shown two ways at once (NN/g on modes): the amber EDITING
// band and the dotted grid.

import { call, edit, on, store } from "./api.js";
import { button, chip, clear, h } from "./dom.js";
import { COLUMNS, defaultSize, findSpot, overlaps, settle } from "/core/layout.js";
import { newId } from "/core/ids.js";
import { renderTile } from "./tiles.js";
import { attempt, ask, claimKeys, confirmDialog, menu, remember, toast, ui } from "./ui.js";
import { renderLibrary } from "./library.js";
import { renderProps } from "./props.js";

const ROW = 40, GAP = 8;
const ROW_MIN = 30, ROW_MAX = 60;   // Locked: rows stretch or shrink so the page fits the window

export function mountControl(root) {
  const view = h("div.view");
  const subbar = h("div.subbar");
  const band = h("div.editband");
  const work = h("div.work");
  const lib = h("aside.side", { "aria-label": "Library" });
  const center = h("section.center");
  const props = h("aside.side.right", { "aria-label": "Properties" });
  const scroll = h("div.canvas-scroll");
  const layout = h("div.layout", { style: { "--cols": COLUMNS, "--row": ROW + "px", "--gap": GAP + "px" } });
  scroll.append(layout);
  center.append(scroll);
  view.append(subbar, band, work);
  root.append(view);

  let tiles = new Map();     // tile id -> {el, update, t}
  let drag = null;
  let rowH = ROW;

  const page = () => {
    const p = store.project;
    let pg = p.layout.pages.find((x) => x.id === ui.page);
    if (!pg) { pg = p.layout.pages[0]; ui.page = pg?.id ?? null; }
    return pg;
  };
  const editing = () => ui.mode === "edit";

  // ---- sub-bar: pages and mode ----------------------------------------------------------
  function renderSubbar() {
    const p = store.project;
    const pg = page();
    clear(subbar);
    const tabs = h("div.pagetabs", { role: "tablist", "aria-label": "Pages" }, p.layout.pages.map((x) =>
      h("button", { role: "tab", "aria-selected": String(x.id === pg?.id), title: editing() ? "Right-click to rename or delete" : "",
        onclick: () => { ui.page = x.id; ui.sel = null; remember(); renderAll(); },
        oncontextmenu: (e) => { if (!editing()) return; e.preventDefault(); pageMenu(e, x); } }, x.name)));
    subbar.append(tabs);
    if (editing()) subbar.append(button("+ Page", addPage, { cls: "btn-sm", title: "Add a page of controls" }));
    subbar.append(h("span.spacer"));
    if (editing()) {
      const st = store.status;
      subbar.append(
        button("Add heading", () => addTile({ kind: "heading", text: "Heading" })),
        button("Add board preview", () => addTile({ kind: "preview", board: p.boards[0]?.id }), { disabled: !p.boards.length }),
        h("span.sep", { style: { width: "1px", alignSelf: "stretch", background: "var(--rule)" } }),
        button("Undo", designUndo, { disabled: !st.canUndo, title: st.canUndo ? `Undo ${st.undoLabel} (Ctrl+Z)` : "Nothing to undo" }),
        button("Redo", designRedo, { disabled: !st.canRedo, title: st.canRedo ? `Redo ${st.redoLabel} (Ctrl+Y)` : "Nothing to redo" }));
    }
    const sw = h("div.modeswitch", { role: "group", "aria-label": "Mode" },
      h("button.edit", { type: "button", "aria-pressed": String(editing()), onclick: () => setMode("edit"), title: "Arrange controls and change settings (E)" }, "Edit"),
      h("button.lock", { type: "button", "aria-pressed": String(!editing()), onclick: () => setMode("locked"), title: "Run the game: controls are live, layout is locked (L)" }, "Locked"));
    subbar.append(sw);
  }

  function setMode(m) {
    if (ui.mode === m) return;
    ui.mode = m;
    if (m === "locked") ui.sel = null;
    remember();
    renderAll();
  }

  async function addPage() {
    const name = await ask("Add page", "Page name", `Page ${store.project.layout.pages.length + 1}`);
    if (!name) return;
    const L = structuredClone(store.project.layout);
    const id = newId();
    L.pages.push({ id, name, tiles: [] });
    ui.page = id;
    await attempt(() => edit({ op: "layout.put", layout: L }, "Add page"));
  }

  function pageMenu(e, pg) {
    menu({ x: e.clientX, y: e.clientY, getBoundingClientRect: () => ({ left: e.clientX, right: e.clientX, top: e.clientY, bottom: e.clientY }) }, [
      { label: "Rename…", run: async () => {
        const name = await ask("Rename page", "Page name", pg.name);
        if (!name) return;
        const L = structuredClone(store.project.layout);
        L.pages.find((x) => x.id === pg.id).name = name;
        attempt(() => edit({ op: "layout.put", layout: L }, "Rename page"));
      } },
      { label: "Move left", disabled: store.project.layout.pages[0].id === pg.id, run: () => movePage(pg.id, -1) },
      { label: "Move right", disabled: store.project.layout.pages.at(-1).id === pg.id, run: () => movePage(pg.id, 1) },
      "-",
      { label: "Delete page", disabled: store.project.layout.pages.length < 2, run: async () => {
        if (pg.tiles.length && !(await confirmDialog("Delete page", `Delete “${pg.name}” and its ${pg.tiles.length} controls? Fields and shortcuts stay in the project.`, "Delete", "danger"))) return;
        const L = structuredClone(store.project.layout);
        L.pages = L.pages.filter((x) => x.id !== pg.id);
        attempt(() => edit({ op: "layout.put", layout: L }, "Delete page"));
      } },
    ]);
  }

  function movePage(id, d) {
    const L = structuredClone(store.project.layout);
    const i = L.pages.findIndex((x) => x.id === id);
    const [pg] = L.pages.splice(i, 1);
    L.pages.splice(i + d, 0, pg);
    attempt(() => edit({ op: "layout.put", layout: L }, "Move page"));
  }

  // ---- layout geometry --------------------------------------------------------------------
  const colW = () => (layout.clientWidth - (COLUMNS - 1) * GAP) / COLUMNS;
  const rect = (t) => {
    const cw = colW();
    return { left: t.x * (cw + GAP), top: t.y * (rowH + GAP), width: t.w * cw + (t.w - 1) * GAP, height: t.h * rowH + (t.h - 1) * GAP };
  };
  const place = (el, t) => { const r = rect(t); Object.assign(el.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" }); };
  const cellAt = (clientX, clientY) => {
    const b = layout.getBoundingClientRect();
    const cw = colW();
    return { x: Math.floor((clientX - b.left) / (cw + GAP)), y: Math.floor((clientY - b.top) / (rowH + GAP)) };
  };
  // Fractional cells, so a resize follows the pointer by half a cell, not a whole one.
  const cellsBetween = (x0, y0, x1, y1) => ({ x: Math.round((x1 - x0) / (colW() + GAP)), y: Math.round((y1 - y0) / (rowH + GAP)) });
  // Which part of a tile is under the pointer: its right edge, bottom edge, corner, or body.
  const EDGE = 12;
  function zoneOf(tileEl, clientX, clientY) {
    const r = tileEl.getBoundingClientRect();
    const right = clientX > r.right - EDGE, bottom = clientY > r.bottom - EDGE;
    return right && bottom ? "se" : right ? "e" : bottom ? "s" : "";
  }
  function fitHeight() {
    const pg = page();
    const used = Math.max(0, ...(pg?.tiles ?? []).map((t) => t.y + t.h));
    if (editing()) rowH = ROW;
    else {
      const avail = scroll.clientHeight - 28;
      rowH = used ? Math.max(ROW_MIN, Math.min(ROW_MAX, Math.floor((avail - (used - 1) * GAP) / used))) : ROW;
    }
    layout.style.setProperty("--row", rowH + "px");
    const rows = used + (editing() ? 6 : 0);
    layout.style.height = Math.max(rows * (rowH + GAP) - GAP, editing() ? scroll.clientHeight - 30 : 0) + "px";
  }

  // ---- layout render ----------------------------------------------------------------------
  function renderLayout() {
    const p = store.project;
    const pg = page();
    for (const { el } of tiles.values()) el._destroy?.();
    tiles = new Map();
    clear(layout);
    if (!pg) return;
    fitHeight();
    for (const t of pg.tiles) {
      const r = renderTile(t, { project: p, snap: store.snapshot });
      if (ui.sel?.kind === "tile" && ui.sel.id === t.id) r.el.classList.add("sel");
      place(r.el, t);
      tiles.set(t.id, { ...r, t });
      layout.append(r.el);
    }
    if (!pg.tiles.length) {
      layout.append(h("div.layout-empty", h("div", editing()
        ? [h("p", h("b", "This page is empty.")), h("p.hint", "Drag fields and shortcuts here from the Library on the left, or select one and press “Add to page”.")]
        : [h("p", h("b", "Nothing to operate on this page yet.")), h("p.hint", "Switch to Edit to add controls.")])));
    }
    fitHeight();
  }

  function relayout() { fitHeight(); for (const { el, t } of tiles.values()) place(el, t); }
  const ro = new ResizeObserver(relayout);
  ro.observe(layout);
  ro.observe(scroll);

  function renderAll() {
    const ed = editing();
    view.classList.toggle("editing", ed);
    work.classList.toggle("locked", !ed);
    band.classList.toggle("hidden", !ed);
    clear(band);
    if (ed) band.append(chip("Editing"), h("span", "Drag to move, drag an edge or corner to resize. Controls do not fire while you edit. Shortcuts still do."),
      h("span.spacer"), button("Done: lock the layout", () => setMode("locked"), { cls: "btn-sm" }));
    // Re-attach the panels only when the mode changed: moving a panel in the
    // page drops the focus of whatever box is open in it.
    const want = ed ? [lib, center, props] : [center];
    if (want.length !== work.children.length || want.some((x, i) => work.children[i] !== x)) { clear(work); work.append(...want); }
    renderSubbar();
    renderLayout();
    if (ed) { renderLibrary(lib, ctx); renderProps(props, ctx); }
  }

  // ---- editing: select, move, resize ------------------------------------------------------
  function select(sel) {
    ui.sel = sel;
    for (const [id, { el }] of tiles) el.classList.toggle("sel", sel?.kind === "tile" && sel.id === id);
    renderProps(props, ctx);
    renderLibrary(lib, ctx);
  }

  function commitTiles(newTiles, label, fixedIds = []) {
    const L = structuredClone(store.project.layout);
    const pg = L.pages.find((x) => x.id === page().id);
    pg.tiles = settle(newTiles.map((t) => ({ ...t })), fixedIds);
    return attempt(() => edit({ op: "layout.put", layout: L }, label));
  }

  layout.addEventListener("pointerdown", (e) => {
    if (!editing() || e.button !== 0) return;
    const tileEl = e.target.closest(".tile");
    if (!tileEl) { select(null); return; }
    const id = tileEl.dataset.tile;
    const entryT = tiles.get(id);
    if (!entryT) return;
    select({ kind: "tile", id });
    const zone = e.target.classList.contains("rz") ? "se" : zoneOf(tileEl, e.clientX, e.clientY);
    const start = cellAt(e.clientX, e.clientY);
    drag = { id, resizing: zone, start, px: { x: e.clientX, y: e.clientY }, orig: { ...entryT.t }, cur: { ...entryT.t }, moved: false, ghost: null };
    layout.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  layout.addEventListener("pointermove", (e) => {
    if (!drag) {
      // Show what a press here would do: resize at the right and bottom edges, move elsewhere.
      if (!editing()) return;
      const tileEl = e.target.closest?.(".tile");
      if (tileEl) tileEl.style.cursor = { se: "nwse-resize", e: "ew-resize", s: "ns-resize" }[zoneOf(tileEl, e.clientX, e.clientY)] ?? "move";
      return;
    }
    const o = drag.orig;
    let next;
    if (drag.resizing) {
      const d = cellsBetween(drag.px.x, drag.px.y, e.clientX, e.clientY);
      next = { ...o,
        w: drag.resizing.includes("e") ? Math.max(1, Math.min(COLUMNS - o.x, o.w + d.x)) : o.w,
        h: drag.resizing.includes("s") ? Math.max(1, o.h + d.y) : o.h };
    } else {
      const c = cellAt(e.clientX, e.clientY);
      const dx = c.x - drag.start.x, dy = c.y - drag.start.y;
      next = { ...o, x: Math.max(0, Math.min(COLUMNS - o.w, o.x + dx)), y: Math.max(0, o.y + dy) };
    }
    if (next.x === drag.cur.x && next.y === drag.cur.y && next.w === drag.cur.w && next.h === drag.cur.h) return;
    drag.cur = next;
    drag.moved = true;
    if (!drag.ghost) { drag.ghost = h("div.ghost"); layout.append(drag.ghost); }
    place(drag.ghost, next);
    const others = page().tiles.filter((t) => t.id !== drag.id);
    drag.ghost.classList.toggle("bad", false);
    drag.ghost.title = others.some((t) => overlaps(t, next)) ? "Tiles underneath will move down" : "";
    const el = tiles.get(drag.id).el;
    el.style.opacity = ".55";
  });

  const endDrag = (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    d.ghost?.remove();
    const el = tiles.get(d.id)?.el;
    if (el) el.style.opacity = "";
    if (!d.moved) return;
    const next = page().tiles.map((t) => (t.id === d.id ? d.cur : t));
    commitTiles(next, d.resizing ? "Resize control" : "Move control", [d.id]);
  };
  layout.addEventListener("pointerup", endDrag);
  layout.addEventListener("pointercancel", endDrag);

  // Drops from the Library (fields, buttons, headings, previews).
  layout.addEventListener("dragover", (e) => {
    if (!editing() || !e.dataTransfer.types.includes("application/x-telescore")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    const info = JSON.parse(sessionStorage.getItem("ts-drag") || "{}");
    const [w, hh] = info.size || [4, 2];
    const c = cellAt(e.clientX, e.clientY);
    const t = { x: Math.max(0, Math.min(COLUMNS - w, c.x)), y: Math.max(0, c.y), w, h: hh };
    let g = layout.querySelector(".ghost.drop");
    if (!g) { g = h("div.ghost.drop"); layout.append(g); }
    place(g, t);
    g.dataset.t = JSON.stringify(t);
  });
  layout.addEventListener("dragleave", (e) => { if (!layout.contains(e.relatedTarget)) layout.querySelector(".ghost.drop")?.remove(); });
  layout.addEventListener("drop", (e) => {
    const g = layout.querySelector(".ghost.drop");
    if (!g) return;
    e.preventDefault();
    const at = JSON.parse(g.dataset.t);
    g.remove();
    let item;
    try { item = JSON.parse(e.dataTransfer.getData("application/x-telescore")); } catch { return; }
    addTile(item, at);
  });

  function addTile(item, at = null) {
    const p = store.project;
    const pg = page();
    let size = item.size;
    if (!size) {
      const f = item.kind === "field" ? p.fields.find((x) => x.key === item.field) : null;
      size = defaultSize(item.kind, f?.type, f);
    }
    const [w, hh] = size;
    const spot = at ?? findSpot(pg.tiles, w, hh);
    const t = { id: newId(), kind: item.kind, x: spot.x, y: spot.y, w, h: hh };
    if (item.kind === "field") t.field = item.field;
    if (item.kind === "button") t.button = item.button;
    if (item.kind === "heading") t.text = item.text || "Heading";
    if (item.kind === "preview") t.board = item.board;
    ui.sel = { kind: "tile", id: t.id };
    return commitTiles([...pg.tiles, t], "Add control", [t.id]);
  }

  function removeTile(id) {
    ui.sel = null;
    return commitTiles(page().tiles.filter((t) => t.id !== id), "Remove control");
  }

  async function designUndo() { const r = await attempt(() => call("/api/undo")); if (r?.label) toast(`Undid: ${r.label}`); }
  async function designRedo() { const r = await attempt(() => call("/api/redo")); if (r?.label) toast(`Redid: ${r.label}`); }

  // Keys while editing: arrows move, Shift+arrows resize, Delete removes,
  // Ctrl+D duplicates, Ctrl+Z / Ctrl+Y undo and redo the design.
  const releaseKeys = claimKeys((e, combo) => {
    if (store.project == null || ui.tab !== "control") return false;
    const inBox = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (combo === "E" && !inBox && !editing()) { setMode("edit"); return true; }
    if (combo === "L" && !inBox && editing() && !ui.sel) { setMode("locked"); return true; }
    if (!editing() || inBox) return false;
    if (combo === "Ctrl+Z") { designUndo(); return true; }
    if (combo === "Ctrl+Y" || combo === "Ctrl+Shift+Z") { designRedo(); return true; }
    if (combo === "Esc") { select(null); return true; }
    if (ui.sel?.kind !== "tile") return false;
    const t = page().tiles.find((x) => x.id === ui.sel.id);
    if (!t) return false;
    if (combo === "Del" || combo === "Backspace") { removeTile(t.id); return true; }
    if (combo === "Ctrl+D") {
      const spot = findSpot(page().tiles, t.w, t.h, t.y);
      const c = { ...t, id: newId(), x: spot.x, y: spot.y };
      ui.sel = { kind: "tile", id: c.id };
      commitTiles([...page().tiles, c], "Duplicate control", [c.id]);
      return true;
    }
    const mv = { Left: [-1, 0], Right: [1, 0], Up: [0, -1], Down: [0, 1] };
    const m = combo.match(/^(Shift\+)?(Left|Right|Up|Down)$/);
    if (m) {
      const [dx, dy] = mv[m[2]];
      const n = m[1] ? { ...t, w: Math.max(1, Math.min(COLUMNS - t.x, t.w + dx)), h: Math.max(1, t.h + dy) }
        : { ...t, x: Math.max(0, Math.min(COLUMNS - t.w, t.x + dx)), y: Math.max(0, t.y + dy) };
      commitTiles(page().tiles.map((x) => (x.id === t.id ? n : x)), m[1] ? "Resize control" : "Move control", [t.id]);
      return true;
    }
    return false;
  });

  // What the side panels need from the canvas.
  const ctx = { page, select, addTile, removeTile, commitTiles, refresh: () => renderAll(), setMode };

  const offs = [
    on("project", (p) => { if (p) renderAll(); }),
    on("snap", (s) => { for (const { update } of tiles.values()) update(s); }),
    on("status", () => { if (editing()) { renderSubbar(); renderLibrary(lib, ctx, true); } }),   // ambient: waits while typing
  ];
  renderAll();
  return () => { offs.forEach((f) => f()); releaseKeys(); ro.disconnect(); for (const { el } of tiles.values()) el._destroy?.(); };
}

// The live controls on their own, for the split view under the graphics
// editor: one page at a time, every control live, nothing to arrange.
export function mountControlPane(root) {
  const bar = h("div.cp-bar");
  const grid = h("div.cp-grid", { style: { "--cols": COLUMNS } });
  root.append(bar, grid);
  let tiles = [];
  const page = () => {
    const p = store.project;
    return p.layout.pages.find((x) => x.id === ui.splitPage) ?? p.layout.pages.find((x) => x.id === ui.page) ?? p.layout.pages[0];
  };
  function render() {
    for (const t of tiles) t.el._destroy?.();
    tiles = [];
    clear(bar);
    clear(grid);
    const p = store.project;
    if (!p) return;
    const pg = page();
    bar.append(h("span.caps", "Controls"),
      h("div.pagetabs", { role: "tablist", "aria-label": "Pages" }, p.layout.pages.map((x) =>
        h("button", { role: "tab", "aria-selected": String(x.id === pg?.id), onclick: () => { ui.splitPage = x.id; remember(); render(); } }, x.name))),
      h("span.spacer"), h("span.hint", "Live: these change the game, as in Control."));
    if (!pg?.tiles.length) { grid.append(h("p.hint", { style: { padding: "12px" } }, "This page has no controls yet. Add some in Control → Edit.")); return; }
    for (const t of pg.tiles) {
      const r = renderTile(t, { project: p, snap: store.snapshot });
      Object.assign(r.el.style, { gridColumn: `${t.x + 1} / span ${t.w}`, gridRow: `${t.y + 1} / span ${t.h}` });
      grid.append(r.el);
      tiles.push(r);
    }
  }
  render();
  const offs = [on("project", (p) => { if (p) render(); }), on("snap", (s) => { for (const t of tiles) t.update(s); })];
  return () => { offs.forEach((f) => f()); for (const t of tiles) t.el._destroy?.(); };
}
