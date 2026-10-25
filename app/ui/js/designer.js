// View → Graphics: design the on-air boards.
//   Left   Elements (boards, layers, fields to drag in) · Logic · Animations
//   Middle the board, drawn by the same renderer OBS uses
//   Right  properties of the selection, the board, a condition or an animation
// Drag to move (snaps to the grid and to other elements, with guides), drag a
// handle to resize, drag on empty space to select several. Arrow keys nudge.

import { call, edit, fileUrl, on, store } from "./api.js";
import { button, chip, clear, h, rerender } from "./dom.js";
import { BoardView } from "/render/board-view.js";
import { ELEMENT_DEFAULTS, align, distribute, makeElement, reorder } from "/core/board.js";
import { ELEMENT_ACTIONS, FIELD_ACTIONS, NO_VALUE_OPS, OPS, compareValue } from "/core/logic.js";
import { EASINGS, makeAnimation, sample } from "/core/animation.js";
import { newId } from "/core/ids.js";
import { attempt, check, claimKeys, colorInput, confirmDialog, menu, numberInput, remember, select, textInput, toast, ui } from "./ui.js";

const SNAP_PX = 6;          // screen pixels within which an edge snaps
const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];

export function mountDesigner(root) {
  const work = h("div.work");
  const left = h("aside.side", { "aria-label": "Graphics library" });
  const center = h("section.center");
  const right = h("aside.side.right", { "aria-label": "Properties" });
  const toolbar = h("div.toolbar");
  const stageWrap = h("div.dz-scroll");
  const host = h("div.dz-host.checker");
  const overlay = h("div.dz-overlay", { tabindex: 0, "aria-label": "Board canvas" });
  stageWrap.append(host, overlay);
  center.append(toolbar, stageWrap);
  work.append(left, center, right);
  root.append(work);

  const view = new BoardView(host, { assetUrl: fileUrl, show_all: true, animate: true });
  let board = null;          // working copy of the board being designed
  let zoom = null;           // null = fit; else {s, x, y}
  let showValues = true;
  let snapOn = true;
  let grid = 10;
  let drag = null;
  let clipboard = [];

  const project = () => store.project;
  const pickBoard = () => {
    const p = project();
    if (!p.boards.some((b) => b.id === ui.board)) ui.board = p.boards[0]?.id ?? null;
    return p.boards.find((b) => b.id === ui.board) ?? null;
  };

  // ---- data in and out --------------------------------------------------------------------
  function load() {
    const b = pickBoard();
    board = b ? structuredClone(b) : null;
    // Project files keep only what differs from the defaults; the designer needs every property.
    if (board) board.elements = board.elements.map((e) => ({ ...structuredClone(ELEMENT_DEFAULTS), ...e }));
    ui.gsel = ui.gsel.filter((id) => board?.elements.some((e) => e.id === id));
    view.setBoard(board, project().animations);
    applyValues();
    applyZoom();
  }

  function valuesForView() {
    const s = store.snapshot;
    if (showValues || !s) return s?.values ?? {};
    // Templates instead of values, except colours and pictures so the board still looks right.
    return new Proxy(s.values, { get: (t, k) => (typeof k === "string" && (/\.(color|colour|logo)$/.test(k) || s.types[k] === "image") ? t[k] : `{${String(k)}}`) });
  }
  function applyValues() { view.setValues(valuesForView(), store.snapshot?.fx ?? {}); drawOverlay(); }

  const commit = (label) => attempt(() => edit({ op: "board.put", board }, label));

  // ---- geometry -----------------------------------------------------------------------------
  const org = () => view.origin();
  const toBoard = (cx, cy) => { const r = overlay.getBoundingClientRect(); const o = org(); return { x: (cx - r.left - o.x) / o.s, y: (cy - r.top - o.y) / o.s }; };
  const toScreen = (bx, by) => { const o = org(); return { x: o.x + bx * o.s, y: o.y + by * o.s }; };
  const el = (id) => board?.elements.find((e) => e.id === id);
  const selected = () => ui.gsel.map(el).filter(Boolean);

  function applyZoom() {
    view.setView(zoom);
    zoomLabel.textContent = `${Math.round((zoom?.s ?? view.fitScale()) * 100)}%`;
    drawOverlay();
  }
  function setZoom(s, cx, cy) {
    const r = overlay.getBoundingClientRect();
    const o = org();
    const px = cx ?? r.left + r.width / 2, py = cy ?? r.top + r.height / 2;
    const bx = (px - r.left - o.x) / o.s, by = (py - r.top - o.y) / o.s;
    s = Math.max(0.05, Math.min(8, s));
    zoom = { s, x: px - r.left - bx * s, y: py - r.top - by * s };
    applyZoom();
  }

  // ---- overlay: selection, handles, guides --------------------------------------------------------
  function drawOverlay(guides = [], band = null) {
    clear(overlay);
    if (!board) return;
    const o = org();
    for (const e of selected()) {
      const p = toScreen(e.x, e.y);
      const box = h(`div.dz-sel${ui.gsel.length === 1 ? ".primary" : ""}`, { style: { left: p.x + "px", top: p.y + "px", width: e.w * o.s + "px", height: e.h * o.s + "px" } });
      overlay.append(box);
      if (ui.gsel.length === 1 && !e.locked) {
        for (const hd of HANDLES) {
          const hx = hd.includes("w") ? 0 : hd.includes("e") ? e.w * o.s : (e.w * o.s) / 2;
          const hy = hd.includes("n") ? 0 : hd.includes("s") ? e.h * o.s : (e.h * o.s) / 2;
          overlay.append(h("div.dz-handle", { "data-h": hd, style: { left: p.x + hx + "px", top: p.y + hy + "px", cursor: `${hd}-resize` } }));
        }
      }
    }
    for (const [axis, v] of guides) {
      const p = toScreen(v, v);
      overlay.append(h("div.dz-guide", { style: axis === "v" ? { left: p.x + "px", top: 0, bottom: 0, width: "1px" } : { top: p.y + "px", left: 0, right: 0, height: "1px" } }));
    }
    if (band) overlay.append(h("div.dz-band", { style: { left: band.x + "px", top: band.y + "px", width: band.w + "px", height: band.h + "px" } }));
  }

  function hit(bx, by) {
    for (let i = board.elements.length - 1; i >= 0; i--) {
      const e = board.elements[i];
      if (e.visible === false || e.locked) continue;
      if (bx >= e.x && bx <= e.x + e.w && by >= e.y && by <= e.y + e.h) return e;
    }
    return null;
  }

  // Snap lines: board edges and centre, and other elements' edges and centres.
  function snapMove(ids, dx, dy) {
    if (!snapOn) return { dx, dy, guides: [] };
    const set = new Set(ids);
    const moving = board.elements.filter((e) => set.has(e.id));
    const x1 = Math.min(...moving.map((e) => drag.start[e.id].x)) + dx, y1 = Math.min(...moving.map((e) => drag.start[e.id].y)) + dy;
    const x2 = Math.max(...moving.map((e) => drag.start[e.id].x + e.w)) + dx, y2 = Math.max(...moving.map((e) => drag.start[e.id].y + e.h)) + dy;
    const xs = [0, board.width / 2, board.width], ys = [0, board.height / 2, board.height];
    for (const e of board.elements) if (!set.has(e.id) && e.visible !== false) { xs.push(e.x, e.x + e.w / 2, e.x + e.w); ys.push(e.y, e.y + e.h / 2, e.y + e.h); }
    const tol = SNAP_PX / org().s;
    const best = (cands, own) => {
      let pick = null;
      for (const c of cands) for (const v of own) { const d = c - v; if (Math.abs(d) <= tol && (!pick || Math.abs(d) < Math.abs(pick.d))) pick = { d, c }; }
      return pick;
    };
    const guides = [];
    const sx = best(xs, [x1, (x1 + x2) / 2, x2]);
    const sy = best(ys, [y1, (y1 + y2) / 2, y2]);
    if (sx) { dx += sx.d; guides.push(["v", sx.c]); } else dx = Math.round((x1) / grid) * grid - (x1 - dx);
    if (sy) { dy += sy.d; guides.push(["h", sy.c]); } else dy = Math.round((y1) / grid) * grid - (y1 - dy);
    return { dx, dy, guides };
  }

  const sn = (v) => (snapOn ? Math.round(v / grid) * grid : Math.round(v));

  overlay.addEventListener("pointerdown", (e) => {
    if (!board) return;
    overlay.focus({ preventScroll: true });
    const r = overlay.getBoundingClientRect();
    if (e.button === 1 || (e.button === 0 && e.altKey && !e.target.dataset.h)) {      // pan
      drag = { kind: "pan", sx: e.clientX, sy: e.clientY, z: { ...(zoom ?? { s: view.scale, ...org() }) } };
    } else if (e.button === 0 && e.target.dataset.h) {
      const t = selected()[0];
      drag = { kind: "resize", h: e.target.dataset.h, b0: toBoard(e.clientX, e.clientY), orig: { x: t.x, y: t.y, w: t.w, h: t.h }, id: t.id };
    } else if (e.button === 0) {
      const p = toBoard(e.clientX, e.clientY);
      const target = hit(p.x, p.y);
      if (target) {
        if (e.shiftKey || e.ctrlKey) ui.gsel = ui.gsel.includes(target.id) ? ui.gsel.filter((x) => x !== target.id) : [...ui.gsel, target.id];
        else if (!ui.gsel.includes(target.id)) ui.gsel = [target.id];
        drag = { kind: "move", b0: p, start: Object.fromEntries(selected().filter((x) => !x.locked).map((x) => [x.id, { x: x.x, y: x.y }])), moved: false };
      } else {
        if (!e.shiftKey) ui.gsel = [];
        drag = { kind: "band", sx: e.clientX - r.left, sy: e.clientY - r.top, keep: [...ui.gsel] };
      }
      renderRight(); renderLeft(true); drawOverlay();
    } else return;
    overlay.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  overlay.addEventListener("pointermove", (e) => {
    if (!drag) { const p = toBoard(e.clientX, e.clientY); overlay.style.cursor = board && hit(p.x, p.y) ? "move" : "default"; return; }
    if (drag.kind === "pan") {
      zoom = { s: drag.z.s, x: drag.z.x + e.clientX - drag.sx, y: drag.z.y + e.clientY - drag.sy };
      applyZoom();
      return;
    }
    const p = toBoard(e.clientX, e.clientY);
    if (drag.kind === "move") {
      const ids = Object.keys(drag.start);
      if (!ids.length) return;
      const { dx, dy, guides } = snapMove(ids, p.x - drag.b0.x, p.y - drag.b0.y);
      for (const id of ids) { const x = el(id); x.x = Math.round(drag.start[id].x + dx); x.y = Math.round(drag.start[id].y + dy); }
      drag.moved = true;
      view.setBoard(board, project().animations); applyValuesQuiet();
      drawOverlay(guides);
    } else if (drag.kind === "resize") {
      const t = el(drag.id), o = drag.orig, hd = drag.h;
      const dx = p.x - drag.b0.x, dy = p.y - drag.b0.y;
      let { x, y, w, h: hh } = o;
      if (hd.includes("e")) w = Math.max(4, sn(o.x + o.w + dx) - o.x);
      if (hd.includes("s")) hh = Math.max(4, sn(o.y + o.h + dy) - o.y);
      if (hd.includes("w")) { const nx = Math.min(o.x + o.w - 4, sn(o.x + dx)); w = o.x + o.w - nx; x = nx; }
      if (hd.includes("n")) { const ny = Math.min(o.y + o.h - 4, sn(o.y + dy)); hh = o.y + o.h - ny; y = ny; }
      Object.assign(t, { x, y, w, h: hh });
      drag.moved = true;
      view.setBoard(board, project().animations); applyValuesQuiet();
      drawOverlay();
    } else if (drag.kind === "band") {
      const r = overlay.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const band = { x: Math.min(x, drag.sx), y: Math.min(y, drag.sy), w: Math.abs(x - drag.sx), h: Math.abs(y - drag.sy) };
      const a = toBoard(band.x + r.left, band.y + r.top), b = toBoard(band.x + band.w + r.left, band.y + band.h + r.top);
      const inside = board.elements.filter((x2) => x2.visible !== false && !x2.locked && x2.x < b.x && x2.x + x2.w > a.x && x2.y < b.y && x2.y + x2.h > a.y).map((x2) => x2.id);
      ui.gsel = [...new Set([...drag.keep, ...inside])];
      drawOverlay([], band);
    }
  });

  const endDrag = () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if ((d.kind === "move" || d.kind === "resize") && d.moved) commit(d.kind === "move" ? "Move" : "Resize");
    renderRight(); renderLeft(true); drawOverlay();
  };
  overlay.addEventListener("pointerup", endDrag);
  overlay.addEventListener("pointercancel", endDrag);
  overlay.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) {      // scroll pans when zoomed in
      if (!zoom) return;
      zoom = { ...zoom, x: zoom.x - e.deltaX, y: zoom.y - e.deltaY };
      applyZoom(); e.preventDefault(); return;
    }
    e.preventDefault();
    setZoom((zoom?.s ?? view.scale) * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX, e.clientY);
  }, { passive: false });
  overlay.addEventListener("dblclick", (e) => {
    const p = toBoard(e.clientX, e.clientY);
    const t = hit(p.x, p.y);
    if (t?.kind === "text") right.querySelector('[data-k="el-text"]')?.focus();
  });

  // Fields dragged in from the list become text elements.
  overlay.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("application/x-telescore-field")) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
  overlay.addEventListener("drop", (e) => {
    const key = e.dataTransfer.getData("application/x-telescore-field");
    if (!key || !board) return;
    e.preventDefault();
    const p = toBoard(e.clientX, e.clientY);
    const f = project().fields.find((x) => x.key === key);
    const kind = f?.type === "image" ? "image" : "text";
    addElement(kind, { x: sn(p.x - 100), y: sn(p.y - 40), ...(kind === "image" ? { src: `{${key}}` } : { text: `{${key}}` }), name: f?.label ?? key });
  });

  function applyValuesQuiet() { view.setValues(valuesForView(), store.snapshot?.fx ?? {}); }

  // ---- element commands -------------------------------------------------------------------------
  function addElement(kind, extra = {}) {
    if (!board) return;
    const base = { kind, name: { text: "Text", box: "Box", image: "Picture" }[kind], x: sn(board.width / 2 - 150), y: sn(board.height / 2 - 50), w: 300, h: 100 };
    if (kind === "text") Object.assign(base, { text: "Text", size: 64, weight: 900, color: "#e8f1ec" });
    if (kind === "box") Object.assign(base, { fill: "#18211e", radius: 3 });
    const e = makeElement({ ...base, ...extra });
    board.elements.push(e);
    ui.gsel = [e.id];
    commit(`Add ${base.name.toLowerCase()}`);
  }
  function removeSelected() {
    if (!ui.gsel.length) return;
    const set = new Set(ui.gsel);
    board.elements = board.elements.filter((e) => !set.has(e.id));
    ui.gsel = [];
    commit("Delete");
  }
  function duplicateSelected(dx = 20, dy = 20) {
    const copies = selected().map((e) => ({ ...structuredClone(e), id: newId(), x: e.x + dx, y: e.y + dy, name: e.name ? `${e.name} copy` : "" }));
    board.elements.push(...copies);
    ui.gsel = copies.map((c) => c.id);
    commit("Duplicate");
  }
  function arrange(fn, label) { if (!ui.gsel.length) return; fn(board, ui.gsel); commit(label); }

  async function designUndo() { const r = await attempt(() => call("/api/undo")); if (r?.label) toast(`Undid: ${r.label}`); }
  async function designRedo() { const r = await attempt(() => call("/api/redo")); if (r?.label) toast(`Redid: ${r.label}`); }

  const releaseKeys = claimKeys((e, combo) => {
    if (ui.tab !== "view" || ui.viewSection !== "graphics" || !board) return false;
    const inBox = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (inBox || document.activeElement?.closest?.(".side")) return false;
    if (combo === "Ctrl+Z") { designUndo(); return true; }
    if (combo === "Ctrl+Y" || combo === "Ctrl+Shift+Z") { designRedo(); return true; }
    if (combo === "Ctrl+A") { ui.gsel = board.elements.filter((x) => !x.locked && x.visible !== false).map((x) => x.id); renderRight(); renderLeft(true); drawOverlay(); return true; }
    if (combo === "Esc") { ui.gsel = []; renderRight(); renderLeft(true); drawOverlay(); return true; }
    if (!ui.gsel.length) return false;
    if (combo === "Del" || combo === "Backspace") { removeSelected(); return true; }
    if (combo === "Ctrl+D") { duplicateSelected(); return true; }
    if (combo === "Ctrl+C") { clipboard = selected().map((x) => structuredClone(x)); toast(`Copied ${clipboard.length}.`); return true; }
    const m = combo.match(/^(Shift\+)?(Left|Right|Up|Down)$/);
    if (m) {
      const step = m[1] ? 10 : 1;
      const [dx, dy] = { Left: [-step, 0], Right: [step, 0], Up: [0, -step], Down: [0, step] }[m[2]];
      for (const x of selected()) if (!x.locked) { x.x += dx; x.y += dy; }
      view.setBoard(board, project().animations); applyValuesQuiet(); drawOverlay();
      clearTimeout(nudgeT); nudgeT = setTimeout(() => commit("Nudge"), 400);
      return true;
    }
    return false;
  });
  let nudgeT = 0;
  const releasePaste = claimKeys((e, combo) => {
    if (ui.tab !== "view" || ui.viewSection !== "graphics" || !board || combo !== "Ctrl+V" || !clipboard.length) return false;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return false;
    const copies = clipboard.map((x) => ({ ...structuredClone(x), id: newId(), x: x.x + 20, y: x.y + 20 }));
    board.elements.push(...copies);
    ui.gsel = copies.map((c) => c.id);
    commit("Paste");
    return true;
  });

  // ---- toolbar ---------------------------------------------------------------------------------
  const zoomLabel = h("span.small.muted", { style: { minWidth: "42px", textAlign: "center" } }, "");
  const zoomBar = h("div.zoombar");
  stageWrap.append(zoomBar);
  function renderToolbar() {
    clear(toolbar);
    const st = store.status;
    const n = ui.gsel.length;
    toolbar.append(
      button("Text", () => addElement("text"), { title: "Add a text element" }), button("Box", () => addElement("box")), button("Picture", () => addElement("image")),
      h("span.sep"),
      button("Align", (e) => menu(e.currentTarget, [
        ...[["Left", "left"], ["Centre", "hcenter"], ["Right", "right"], ["Top", "top"], ["Middle", "vcenter"], ["Bottom", "bottom"]].map(([l, how]) => ({ label: `Align ${l.toLowerCase()}`, run: () => arrange((b, ids) => align(b, ids, how), `Align ${l.toLowerCase()}`) })),
        "-", { label: "Distribute across", disabled: n < 3, run: () => arrange((b, ids) => distribute(b, ids, "h"), "Distribute") },
        { label: "Distribute down", disabled: n < 3, run: () => arrange((b, ids) => distribute(b, ids, "v"), "Distribute") },
      ]), { disabled: !n, title: "One element aligns to the board; several align to each other" }),
      button("Order", (e) => menu(e.currentTarget, [["Bring to front", "front"], ["Bring forward", "forward"], ["Send backward", "backward"], ["Send to back", "back"]].map(([l, w]) =>
        ({ label: l, run: () => { for (const id of [...ui.gsel]) reorder(board, id, w); commit(l); } }))), { disabled: !n }),
      button("Duplicate", () => duplicateSelected(), { disabled: !n, title: "Ctrl+D" }),
      button("Delete", removeSelected, { role: "alert", disabled: !n, title: "Delete" }),
      h("span.sep"),
      button("Undo", designUndo, { disabled: !st.canUndo, title: st.canUndo ? `Undo ${st.undoLabel} (Ctrl+Z)` : "Nothing to undo" }),
      button("Redo", designRedo, { disabled: !st.canRedo, title: st.canRedo ? `Redo ${st.redoLabel} (Ctrl+Y)` : "Nothing to redo" }),
      h("span.spacer"),
      check("Values", showValues, (v) => { showValues = v; applyValues(); }, { title: "Off shows the templates, such as {home.score}" }),
      check("Snap", snapOn, (v) => { snapOn = v; }, { title: "Snap to a 10 px grid and to other elements. Hold Alt and drag to pan." }));
    clear(zoomBar);
    zoomBar.append(button("−", () => setZoom((zoom?.s ?? view.scale) / 1.25), { cls: "btn-sm", title: "Zoom out (Ctrl+wheel)" }), zoomLabel,
      button("+", () => setZoom((zoom?.s ?? view.scale) * 1.25), { cls: "btn-sm", title: "Zoom in" }),
      button("Fit", () => { zoom = null; applyZoom(); }, { cls: "btn-sm" }),
      button("100%", () => setZoom(1), { cls: "btn-sm" }));
    zoomLabel.textContent = `${Math.round((zoom?.s ?? view.scale) * 100)}%`;
  }

  // ---- left: elements, logic, animations ----------------------------------------------------------------
  function renderLeft(light = false) {
    rerender(left, () => h("div", { style: { display: "contents" } },
      h("div.side-tabs", { role: "tablist" }, [["elements", "Elements"], ["logic", "Logic"], ["animations", "Animations"]].map(([id, label]) =>
        h("button", { role: "tab", "aria-selected": String(ui.gside === id), onclick: () => { ui.gside = id; ui.gpick = null; remember(); renderLeft(); renderRight(); } }, label))),
      h("div.side-body", { "data-scroll": `g-${ui.gside}` }, ui.gside === "elements" ? elementsPanel() : ui.gside === "logic" ? logicPanel() : animationsPanel())));
  }

  function elementsPanel() {
    const p = project();
    const boardRow = h("div.row",
      select(p.boards.map((b) => [b.id, `${b.name} · ${b.width}×${b.height}`]), ui.board, (v) => { ui.board = v; ui.gsel = []; remember(); load(); renderAll(); }, { k: "g-board" }),
      button("+", (e) => menu(e.currentTarget, [
        { label: "New blank board", run: async () => { const r = await attempt(() => edit({ op: "board.add", board: { name: `Board ${p.boards.length + 1}` } }, "New board")); if (r) { ui.board = r.results[0]; remember(); } } },
        { label: "Copy of this board", run: async () => { const r = await attempt(() => edit({ op: "board.add", copyOf: ui.board }, "Copy board")); if (r) { ui.board = r.results[0]; remember(); } } },
        "-", { label: "Delete this board", disabled: p.boards.length < 2, run: async () => {
          if (await confirmDialog("Delete board", `Delete “${board.name}”? Browser sources showing it stop working.`, "Delete", "danger")) attempt(() => edit({ op: "board.remove", id: ui.board }, "Delete board"));
        } },
      ]), { title: "New, copy or delete a board" }));
    const layers = [...(board?.elements ?? [])].reverse().map((e) => {
      const sel = ui.gsel.includes(e.id);
      return h(`div.item${sel ? ".sel" : ""}`, { tabindex: 0,
        onclick: (ev) => { ui.gsel = ev.shiftKey || ev.ctrlKey ? (sel ? ui.gsel.filter((x) => x !== e.id) : [...ui.gsel, e.id]) : [e.id]; renderLeft(true); renderRight(); drawOverlay(); renderToolbar(); } },
        h("span.typ", { style: { width: "34px" } }, e.kind),
        h("span.name", { title: e.text || e.src || "" }, e.name || e.text || e.kind),
        e.show_when ? h("span.typ", { title: `Shown while ${e.show_when} is on` }, "if") : null,
        h("button.btn.btn-ghost.btn-sm", { type: "button", title: e.visible === false ? "Hidden in every output. Click to show." : "Click to hide everywhere",
          onclick: (ev) => { ev.stopPropagation(); el(e.id).visible = e.visible === false; commit(e.visible === false ? "Show" : "Hide"); } }, e.visible === false ? "Hidden" : "Shown"),
        h("button.btn.btn-ghost.btn-sm", { type: "button", title: e.locked ? "Locked: cannot be selected on the canvas" : "Lock it so clicks pass through",
          onclick: (ev) => { ev.stopPropagation(); el(e.id).locked = !e.locked; commit(e.locked ? "Unlock" : "Lock"); } }, e.locked ? "Locked" : "Lock"));
    });
    const fields = p.fields.map((f) => h("div.item", { draggable: true, title: `{${f.key}} · drag onto the board`,
      ondragstart: (ev) => { ev.dataTransfer.setData("application/x-telescore-field", f.key); ev.dataTransfer.effectAllowed = "copy"; },
      ondblclick: () => addElement(f.type === "image" ? "image" : "text", f.type === "image" ? { src: `{${f.key}}`, name: f.label } : { text: `{${f.key}}`, name: f.label }) },
      h("span.grip", "⋮⋮"), h("div.grow", h("div.name", f.label), h("div.sub.mono", `{${f.key}}`))));
    return [h("div.group-title", h("span.caps", "Board")), boardRow,
      h("div.group-title", h("span.caps", "Layers · top is in front")), layers.length ? h("div.list", layers) : h("p.hint", "Empty. Add Text, Box or Picture from the toolbar, or drag a field onto the board."),
      h("div.group-title", h("span.caps", "Fields · drag onto the board")), h("div.list", fields)];
  }

  // ---- logic ----------------------------------------------------------------------------------------------
  const conds = () => project().conditions ?? [];
  const putConds = (list, label) => attempt(() => edit({ op: "conditions.put", conditions: list }, label));
  function describeCond(c) {
    const p = project();
    let tgt = c.target;
    if (c.target_kind === "element") for (const b of p.boards) { const e = b.elements.find((x) => x.id === c.target); if (e) tgt = `${b.name} › ${e.name || e.kind}`; }
    const v = NO_VALUE_OPS.includes(c.op) ? "" : ` ${c.value || "NULL"}`;
    const act = (c.target_kind === "element" ? ELEMENT_ACTIONS : FIELD_ACTIONS)[c.action] ?? c.action;
    return `If ${c.principal} ${OPS[c.op] ?? c.op}${v} → ${tgt || "?"} ${act}${c.action === "action" ? "" : " " + (c.arg ?? "")}`;
  }
  function logicPanel() {
    const list = conds();
    return [
      h("div.row", button("+ Add condition", () => {
        const f = project().fields[0]?.key ?? "";
        const target = ui.gsel[0] ?? board?.elements[0]?.id ?? "";
        const c = { id: newId(), principal: f, op: "changes", value: "", target_kind: "element", target, action: "animate", arg: "Pulse" };
        ui.gpick = { kind: "condition", id: c.id };
        putConds([...list, c], "Add condition");
      }, { role: "accent" })),
      h("p.hint", "Checked whenever the field's value changes, like SportzSuite checking new bot data. Use a pair (has value F → show; does not have value F → hide) for both states."),
      list.length ? h("div.list", list.map((c) => h(`div.item${ui.gpick?.id === c.id ? ".sel" : ""}`, { tabindex: 0, onclick: () => { ui.gpick = { kind: "condition", id: c.id }; renderLeft(true); renderRight(); } },
        h("input", { type: "checkbox", checked: c.enabled !== false, title: "On", onclick: (e) => e.stopPropagation(),
          onchange: (e) => putConds(list.map((x) => (x.id === c.id ? { ...x, enabled: e.target.checked } : x)), e.target.checked ? "Condition on" : "Condition off") }),
        h("span.name", { style: { whiteSpace: "normal" } }, c.note || describeCond(c)))))
        : h("p.hint", "No conditions yet."),
    ];
  }

  function conditionEditor(c) {
    const p = project();
    const list = conds();
    const put = (patch, label = "Change condition") => putConds(list.map((x) => (x.id === c.id ? { ...x, ...patch } : x)), label);
    const snap = store.snapshot;
    const keys = Object.keys(snap?.values ?? {});
    const acts = c.target_kind === "element" ? ELEMENT_ACTIONS : FIELD_ACTIONS;
    const elementOpts = p.boards.flatMap((b) => b.elements.map((e) => [e.id, `${b.name} › ${e.name || e.text || e.kind}`]));
    const animOpts = (project().library ?? []).map((a) => [a.name, `${a.name} (${a.kind})`]);
    let argCtl;
    const a = c.action;
    if (["show", "show_once", "hide"].includes(a)) argCtl = h("div.row", textInput(c.arg ?? "*", (v) => put({ arg: v.trim() || "*" }), { k: "c-arg", placeholder: "*" }), h("span.hint", "ms, or * until changed"));
    else if (a === "color" || a === "fill") argCtl = colorInput(c.arg ?? "", (v) => put({ arg: v }), { k: "c-arg" });
    else if (a === "animate") argCtl = select(animOpts, c.arg, (v) => put({ arg: v }), { k: "c-arg" });
    else if (a === "pulse") argCtl = h("div.row", textInput(c.arg ?? "3000", (v) => put({ arg: v.trim() }), { k: "c-arg" }), h("span.hint", "ms"));
    else if (a === "action") argCtl = select([["", "— choose a shortcut —"], ...p.buttons.map((b) => [b.id, b.label])], "", (v) => { const b = p.buttons.find((x) => x.id === v); if (b) put({ run: b.action, arg: b.label }); }, { k: "c-run" });
    else argCtl = textInput(c.arg ?? "", (v) => put({ arg: v }), { k: "c-arg", placeholder: a === "rule" ? "1=Joe|2=John" : a === "image" ? "C:\\pictures\\alt.png" : a === "font" ? "Archivo" : "value" });
    const now = snap ? (NO_VALUE_OPS.includes(c.op) && c.op === "changes" ? null : (() => { try { return compareValue(c.op, snap.values[c.principal] ?? "", c.value, null); } catch { return null; } })()) : null;
    const HELP = { show: "Show the element. For a time, or until another condition hides it.", show_once: "Show it only when the condition first becomes true.",
      hide: "Hide the element. For a time, or until another condition shows it.", color: "Text colour for text, fill for a box.", fill: "Background fill.",
      font: "Font family for text.", image: "Swap the picture (an alternate picture).", rule: "Rules that apply only while the condition holds. A plain rule still wins.",
      animate: "Play an animation. An 'out' animation hides the element at its end.", set: "Set the field. This is not an undo step.",
      pulse: "Switch an on/off field on for a while, then off. Good for 'flash this graphic' flags in XML.", action: "Run a shortcut, e.g. 'Next period' when the clock reaches 0:00." };
    return [
      h("div.row", h("div.section-title", "Condition"), h("span.spacer"), now === null ? null : chip(now ? "True now" : "False now", now ? "accent" : "muted")),
      h("div.panel", h("h3", "If"), h("div.form",
        h("label", "Field"), select(keys.map((k) => [k, k]).concat(c.principal && !keys.includes(c.principal) ? [[c.principal, `${c.principal} (missing)`]] : []), c.principal, (v) => put({ principal: v }), { k: "c-field" }),
        h("label", "Test"), select(Object.entries(OPS), c.op, (v) => put({ op: v }), { k: "c-op" }),
        ...(NO_VALUE_OPS.includes(c.op) ? [] : [h("label", "Value"), textInput(c.value ?? "", (v) => put({ value: v }), { k: "c-value", placeholder: "NULL means empty · 2:00 compares as time" })]))),
      h("div.panel", h("h3", "Then"), h("div.form",
        h("label", "Target"), select([["element", "An element on a board"], ["field", "A field (reaches .txt and .xml)"]], c.target_kind, (v) => put({ target_kind: v, target: v === "element" ? elementOpts[0]?.[0] ?? "" : p.fields[0]?.key ?? "", action: v === "element" ? "show" : "set", arg: v === "element" ? "*" : "" }), { k: "c-tk" }),
        ...(c.target_kind === "field" && c.action === "action" ? [] : [h("label", ""), c.target_kind === "element" ? select(elementOpts, c.target, (v) => put({ target: v }), { k: "c-target" }) : select(p.fields.map((f) => [f.key, f.label]), c.target, (v) => put({ target: v }), { k: "c-target" })]),
        h("label", "Do"), select(Object.entries(acts), c.action, (v) => put({ action: v, arg: v === "animate" ? "Pulse" : ["show", "hide", "show_once"].includes(v) ? "*" : v === "pulse" ? "3000" : "" }), { k: "c-action" }),
        h("label", ""), argCtl), h("p.hint", HELP[a] ?? "")),
      h("div.panel", check("Afterwards, do something else", !!(c.finish_ms && c.finish), (v) => put(v ? { finish_ms: 4000, finish: c.target_kind === "element" ? "hide" : "set:" } : { finish_ms: 0, finish: "" }), { k: "c-fin" }),
        c.finish_ms && c.finish ? h("div.form", { style: { marginTop: "8px" } },
          h("label", "After"), numberInput(c.finish_ms, (v) => put({ finish_ms: v }), { k: "c-fms", min: 1, suffix: "ms" }),
          h("label", "Do"), c.target_kind === "element"
            ? select([["hide", "Hide"], ["show", "Show"], ...animOpts.map(([n]) => [`animate:${n}`, `Animate ${n}`])], c.finish, (v) => put({ finish: v }), { k: "c-fdo" })
            : textInput(c.finish.replace(/^set:/, ""), (v) => put({ finish: `set:${v}` }), { k: "c-fset", placeholder: "set the field to…" })) : null,
        h("p.hint", "Like SportzSuite's finish animations: tween out, then 4000 ms later tween back in.")),
      h("div.form", h("label", "Note"), textInput(c.note ?? "", (v) => put({ note: v }), { k: "c-note", placeholder: "e.g. goal flash" })),
      h("div.row", { style: { marginTop: "12px" } },
        button("Duplicate", () => { const d = { ...structuredClone(c), id: newId() }; ui.gpick = { kind: "condition", id: d.id }; putConds([...list, d], "Duplicate condition"); }),
        button("Up", () => { const i = list.findIndex((x) => x.id === c.id); if (i > 0) { const l = [...list]; [l[i - 1], l[i]] = [l[i], l[i - 1]]; putConds(l, "Move condition"); } }),
        button("Delete", () => { ui.gpick = null; putConds(list.filter((x) => x.id !== c.id), "Delete condition"); }, { role: "alert" })),
    ];
  }

  // ---- animations --------------------------------------------------------------------------------------------
  const custom = () => project().animations ?? [];
  const putAnims = (list, label) => attempt(() => edit({ op: "animations.put", animations: list }, label));
  function animationsPanel() {
    const lib = project().library ?? [];
    const uniq = (base) => { const names = new Set(lib.map((a) => a.name)); let n = base, i = 2; while (names.has(n)) n = `${base} ${i++}`; return n; };
    return [
      h("div.row", button("+ New", () => { const a = makeAnimation({ name: uniq("My animation"), kind: "in", duration: 450, x: -120, opacity: 0 }); ui.gpick = { kind: "animation", id: a.name }; putAnims([...custom(), a], "New animation"); }, { role: "accent" }),
        button("Copy", () => {
          const src = lib.find((a) => a.name === ui.gpick?.id);
          if (!src) return toast("Pick an animation to copy.");
          const { builtin, ...rest } = src;
          const a = { ...rest, name: uniq(`${src.name} copy`) };
          ui.gpick = { kind: "animation", id: a.name };
          putAnims([...custom(), a], "Copy animation");
        }, { title: "An editable copy, e.g. of a built-in" })),
      h("p.hint", "Elements play these when they appear, disappear or change (Properties → Motion), or when a condition says Animate."),
      h("div.list", lib.map((a) => h(`div.item${ui.gpick?.id === a.name ? ".sel" : ""}`, { tabindex: 0, onclick: () => { ui.gpick = { kind: "animation", id: a.name }; renderLeft(true); renderRight(); } },
        h("span.name", a.name), h("span.typ", a.builtin ? "built in" : a.kind)))),
    ];
  }

  let previewView = null;
  function animationEditor(a) {
    const editable = !a.builtin;
    const list = custom();
    const put = (patch, label = "Change animation") => {
      if (!editable) return;
      if (patch.name !== undefined) { patch.name = patch.name.trim(); if (!patch.name) return; ui.gpick = { kind: "animation", id: patch.name }; }
      putAnims(list.map((x) => (x.name === a.name ? { ...x, ...patch } : x)), label);
    };
    const num = (k, label, o = {}) => [h("label", label), editable ? numberInput(a[k], (v) => put({ [k]: v }), { k: `a-${k}`, ...o }) : h("span", String(a[k]) + (o.suffix ? " " + o.suffix : ""))];
    const sel = (k, label, opts) => [h("label", label), editable ? select(opts, a[k], (v) => put({ [k]: v }), { k: `a-${k}` }) : h("span", String(opts.find((x) => x[0] === a[k])?.[1] ?? a[k]))];
    const stage = h("div.checker", { style: { position: "relative", height: "180px", borderRadius: "6px", overflow: "hidden" } });
    queueMicrotask(() => {
      previewView?.destroy();
      previewView = new BoardView(stage);
      previewView.setBoard({ id: "pv", name: "Preview", width: 640, height: 280, background: "", elements: [makeElement({ id: "s", kind: "text", text: "HOME 3", x: 180, y: 95, w: 280, h: 90, fill: "#0a0f0df2", color: "#e8f1ec", size: 46, weight: 900, radius: 3 })] }, [a]);
      previewView.setValues({}, {});
    });
    return [
      h("div.section-title", "Animation"),
      editable ? null : h("p.hint", "A built-in. Use Copy to make one you can change."),
      h("div.form",
        h("label", "Name"), editable ? h("input.input", { value: a.name, "data-k": "a-name", onchange: (e) => put({ name: e.target.value }, "Rename animation") }) : h("span", a.name),
        ...sel("kind", "Type", [["in", "In: the element appears"], ["out", "Out: the element disappears"], ["emphasis", "Emphasis: plays, then returns"]]),
        ...num("duration", "Duration", { min: 1, max: 20000, suffix: "ms" }), ...num("delay", "Delay", { min: 0, max: 20000, suffix: "ms" }),
        ...sel("easing", "Easing", Object.keys(EASINGS).map((e) => [e, e])),
        ...num("opacity", "Opacity", { min: 0, max: 1, step: 0.05 }), ...num("x", "Offset X", { suffix: "px" }), ...num("y", "Offset Y", { suffix: "px" }),
        ...num("scale", "Scale", { min: 0, max: 10, step: 0.05 }),
        ...sel("wipe", "Wipe", [["", "None"], ["left", "From/to the left"], ["right", "From/to the right"], ["up", "Upward"], ["down", "Downward"]]),
        ...(a.kind === "emphasis" ? num("repeat", "Repeat", { min: 1, max: 50, suffix: "times" }) : [])),
      h("p.hint", explain(a)),
      h("div.row", { style: { margin: "10px 0 6px" } }, h("span.caps", "Preview"), h("span.spacer"),
        button("Play", () => previewView?.play("s", a.name), { role: "accent" }),
        ui.gsel.length ? button("Play on selection", () => { for (const id of ui.gsel) view.play(id, a.name); }) : null),
      stage,
      editable ? h("div.row", { style: { marginTop: "12px" } }, button("Delete", () => { ui.gpick = null; putAnims(list.filter((x) => x.name !== a.name), "Delete animation"); }, { role: "alert" })) : null,
    ];
  }
  function explain(a) {
    const parts = [];
    if (a.opacity !== 1) parts.push(`opacity ${Math.round(a.opacity * 100)}%`);
    if (a.x || a.y) parts.push(`offset ${a.x >= 0 ? "+" : ""}${a.x}, ${a.y >= 0 ? "+" : ""}${a.y} px`);
    if (a.scale !== 1) parts.push(`scale ${Math.round(a.scale * 100)}%`);
    if (a.wipe) parts.push(`a wipe ${a.wipe}`);
    const look = parts.join(", ") || "no change";
    if (a.kind === "in") return `Starts at ${look} and moves to normal in ${a.duration} ms.`;
    if (a.kind === "out") return `Moves from normal to ${look} in ${a.duration} ms, then hides.`;
    return `Goes to ${look} and back, ${a.repeat}× in ${a.duration * a.repeat} ms.`;
  }

  // ---- right: properties --------------------------------------------------------------------------------------------
  function renderRight() {
    if (ui.gside === "logic" && ui.gpick?.kind === "condition") {
      const c = conds().find((x) => x.id === ui.gpick.id);
      if (c) return rerender(right, () => h("div.side-body", { "data-scroll": "g-props" }, conditionEditor(c)));
    }
    if (ui.gside === "animations" && ui.gpick?.kind === "animation") {
      const a = (project().library ?? []).find((x) => x.name === ui.gpick.id);
      if (a) return rerender(right, () => h("div.side-body", { "data-scroll": "g-props" }, animationEditor(a)));
    }
    rerender(right, () => h("div.side-body", { "data-scroll": "g-props" }, ui.gsel.length ? elementProps() : boardProps()));
  }

  function boardProps() {
    if (!board) return h("p.hint", "No board.");
    const put = (patch, label = "Board settings") => { Object.assign(board, patch); commit(label); };
    const sizes = [["1920x1080", "1920 × 1080 (HD)"], ["1280x720", "1280 × 720"], ["3840x2160", "3840 × 2160 (4K)"], ["1080x1920", "1080 × 1920 (vertical)"], ["1080x1080", "1080 × 1080 (square)"]];
    const cur = `${board.width}x${board.height}`;
    return [h("div.section-title", "Board"),
      h("div.form",
        h("label", "Name"), textInput(board.name, (v) => put({ name: v.trim() || "Board" }, "Rename board"), { k: "b-name" }),
        h("label", "Size"), select([...sizes, ...(sizes.some(([k]) => k === cur) ? [] : [[cur, `${board.width} × ${board.height}`]])], cur, (v) => { const [w, hh] = v.split("x").map(Number); put({ width: w, height: hh }, "Board size"); }, { k: "b-size" }),
        h("label", "Width"), numberInput(board.width, (v) => put({ width: v }, "Board size"), { k: "b-w", min: 16, max: 8192, suffix: "px" }),
        h("label", "Height"), numberInput(board.height, (v) => put({ height: v }, "Board size"), { k: "b-h", min: 16, max: 8192, suffix: "px" }),
        h("label", "Background"), colorInput(board.background, (v) => put({ background: v.trim() }), { k: "b-bg", placeholder: "transparent" })),
      h("p.hint", "Leave the background empty for a transparent graphic to key over video. Projector windows show it on black."),
      h("p.hint", "Select an element to change it. Shift-click or drag across empty space to select several. Ctrl+wheel zooms; Alt-drag pans.")];
  }

  function elementProps() {
    const sel = selected();
    const e = sel[0];
    if (!e) return boardProps();
    const many = sel.length > 1;
    const p = project();
    // A change applies to every selected element; geometry only to one.
    const put = (patch, label = "Change") => { for (const x of selected()) Object.assign(x, patch); commit(label); };
    const n = (k, label, o = {}) => [h("label", label), numberInput(e[k], (v) => put({ [k]: v }), { k: `el-${k}`, ...o })];
    const t = (k, label, o = {}) => [h("label", label), textInput(e[k] ?? "", (v) => put({ [k]: v }), { k: `el-${k}`, ...o })];
    const c = (k, label, o = {}) => [h("label", label), colorInput(e[k] ?? "", (v) => put({ [k]: v.trim() }), { k: `el-${k}`, ...o })];
    const animSel = (k, label, kinds) => [h("label", label), select([["", "None"], ...(p.library ?? []).filter((a) => kinds.includes(a.kind)).map((a) => [a.name, a.name])], e[k], (v) => put({ [k]: v }), { k: `el-${k}` })];
    const toggles = p.fields.filter((f) => ["toggle", "text", "counter", "image"].includes(f.type));
    const fieldKeys = p.fields.map((f) => f.key);
    const out = [h("div.section-title", many ? `${sel.length} elements` : { text: "Text", box: "Box", image: "Picture" }[e.kind])];
    if (!many) out.push(h("div.form", ...t("name", "Name", { placeholder: e.kind }), ...n("x", "X", { suffix: "px" }), ...n("y", "Y", { suffix: "px" }),
      ...n("w", "Width", { min: 1, suffix: "px" }), ...n("h", "Height", { min: 1, suffix: "px" })));
    if (e.kind === "text") {
      const tpl = h("input.input", { value: e.text, "data-k": "el-text", spellcheck: false, list: "ts-keys" });
      tpl.addEventListener("change", () => put({ text: tpl.value }, "Text"));
      out.push(h("div.panel", h("h3", "Text"), h("div.form",
        h("label", "Text"), tpl, h("div.hint", "Type, or put a field in braces: {home.score}. {{ and }} are braces."),
        ...t("font", "Font"), ...n("size", "Size", { min: 4, max: 2000, suffix: "px max" }),
        h("label", "Weight"), select([300, 400, 500, 600, 700, 800, 900].map((w) => [w, String(w)]), e.weight, (v) => put({ weight: Number(v) }), { k: "el-weight" }),
        ...c("color", "Colour", { placeholder: "#ffffff or {home.color}" }),
        h("label", "Align"), h("div.row", select([["left", "Left"], ["center", "Centre"], ["right", "Right"]], e.align, (v) => put({ align: v }), { k: "el-align" }),
          select([["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]], e.valign, (v) => put({ valign: v }), { k: "el-valign" })),
        ...n("tracking", "Spacing", { step: 0.01, suffix: "em" }), ...n("padding", "Padding", { min: 0, suffix: "px" }),
        h("div.full.col", check("Shrink to fit the box", e.fit, (v) => put({ fit: v }), { k: "el-fit" }), check("Capitals", e.uppercase, (v) => put({ uppercase: v }), { k: "el-up" }),
          check("Italic", e.italic, (v) => put({ italic: v }), { k: "el-it" }), check("Even-width numbers", e.tabular, (v) => put({ tabular: v }), { k: "el-tab" })))));
    }
    if (e.kind === "image") {
      out.push(h("div.panel", h("h3", "Picture"), h("div.form",
        h("label", "Picture"), h("div.row", textInput(e.src, (v) => put({ src: v.trim() }), { k: "el-src", placeholder: "{home.logo} or a file" }),
          store.state.host.dialogs ? button("Choose…", async () => { const r = await attempt(() => call("/api/pick", { kind: "image" })); if (r?.path) put({ src: r.path }); }) : null),
        h("div.full", check("Keep its shape (fit inside)", e.contain, (v) => put({ contain: v }), { k: "el-contain" })))));
    }
    out.push(h("div.panel", h("h3", e.kind === "text" ? "Box behind the text" : "Box"), h("div.form",
      ...c("fill", "Fill", { placeholder: "none" }), ...c("stroke", "Border", { placeholder: "none" }), ...n("stroke_width", "Border", { min: 0, suffix: "px" }),
      ...n("radius", "Corners", { min: 0, suffix: "px" }), ...n("opacity", "Opacity", { min: 0, max: 1, step: 0.05 }))));
    out.push(h("div.panel", h("h3", "Show"), h("div.form",
      h("label", "Only while"), select([["", "Always shown"], ...toggles.map((f) => [f.key, `${f.label} is on / not empty`])], e.show_when, (v) => put({ show_when: v }, "Show while"), { k: "el-sw" })),
      h("p.hint", "Conditions under Logic can also show, hide, recolour and animate it.")));
    out.push(h("div.panel", h("h3", "Rules and motion"), h("div.form",
      ...t("rules", "Rules", { placeholder: "0:00=FINAL|NULL=—  (this graphic only)" }),
      ...animSel("anim_in", "Appears", ["in"]), ...animSel("anim_out", "Disappears", ["out"]), ...animSel("anim_change", "On change", ["emphasis", "in"])),
      h("p.hint", "Rules here change only this graphic. A field's own rules (Control → Edit → Fields) also reach .txt and .xml."),
      h("div.row", ...["anim_in", "anim_out", "anim_change"].filter((k) => e[k]).map((k) => button(`Play ${e[k]}`, () => { for (const id of ui.gsel) view.play(id, e[k]); }, { cls: "btn-sm" })))));
    out.push(h("datalist#ts-keys", fieldKeys.map((k) => h("option", { value: `{${k}}` }))));
    return out;
  }

  // ---- wiring ---------------------------------------------------------------------------------------------------
  function renderAll() { renderToolbar(); renderLeft(); renderRight(); drawOverlay(); }
  view.onfit = () => { if (!drag) drawOverlay(); zoomLabel.textContent = `${Math.round(view.scale * 100)}%`; };
  load();
  renderAll();
  const offs = [
    on("project", (p) => { if (!p || drag) return; load(); renderAll(); }),
    on("snap", () => { if (!drag) applyValues(); }),
    on("status", () => renderToolbar()),
  ];
  return () => { offs.forEach((f) => f()); releaseKeys(); releasePaste(); view.destroy(); previewView?.destroy(); previewView = null; };
}
