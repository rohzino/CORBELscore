// Draws a board in a browser: the OBS/vMix browser source, the designer
// canvas, the live view and previews all use this, so what you design is what
// goes on air. Elements are positioned in board pixels on a stage that is
// scaled to fit its container. Conditions' effects (fx) and animations
// (Tracker) apply exactly as in every output.
//
// Text is either Fixed (its box is set; the text can wrap and shrinks to fit)
// or Auto (the box hugs the text and grows from its alignment point, like an
// OBS text source without custom extents). A "board" element draws another
// board inside this one.

import { ELEMENT_DEFAULTS, cssColor, renderTemplate, resolveColor } from "/core/board.js";
import { Tracker, elementText } from "/core/animation.js";
import { fontStack } from "/core/fonts.js";

const ID = { opacity: 1, x: 0, y: 0, scale: 1, clip: [0, 0, 1, 1] };
const now = () => performance.now() / 1000;
const MAX_DEPTH = 4;   // boards inside boards inside boards… stop somewhere sensible

export class BoardView {
  // options: fit "contain" | "none"; background override (css colour or "");
  // animate (default true); assetUrl(path) -> url for pictures; show_all (the
  // designer draws elements hidden by logic, faintly); box {w, h}: fit into a
  // fixed size instead of the host (for a board inside a board).
  constructor(host, options = {}) {
    this.host = host;
    this.opt = { fit: "contain", animate: true, assetUrl: (p) => "/asset?path=" + encodeURIComponent(p), depth: 0, chain: [], ...options };
    this.wrap = document.createElement("div");
    this.wrap.className = "bv-wrap";
    Object.assign(this.wrap.style, { position: "absolute", inset: "0", overflow: this.opt.box ? "visible" : "hidden" });
    this.stage = document.createElement("div");
    this.stage.className = "bv-stage";
    Object.assign(this.stage.style, { position: "absolute", left: "0", top: "0", transformOrigin: "0 0" });
    this.wrap.appendChild(this.stage);
    host.appendChild(this.wrap);
    this.board = null;
    this.boards = new Map();
    this.values = {};
    this.fx = {};
    this.nodes = [];
    this.tracker = new Tracker();
    this.animations = [];
    this.scale = 1;
    this.raf = 0;
    if (!this.opt.box) {
      this.ro = new ResizeObserver(() => this.fit());
      this.ro.observe(host);
    }
    this._onFonts = () => this.refit();
    document.fonts?.addEventListener?.("loadingdone", this._onFonts);
  }

  destroy() {
    this.ro?.disconnect();
    document.fonts?.removeEventListener?.("loadingdone", this._onFonts);
    cancelAnimationFrame(this.raf);
    for (const o of this.nodes) o.child?.destroy();
    this.wrap.remove();
  }

  // Every board in the project, for "board" elements.
  setBoards(list) {
    this.boards = new Map((list || []).map((b) => [b.id, b]));
    if (this.board && this.board.elements.some((e) => e.kind === "board")) this.build();
  }

  setBoard(board, animations = this.animations) {
    this.board = board ? structuredClone(board) : null;
    this.animations = animations;
    this.tracker.setBoard(null);
    this.tracker.setBoard(this.board, animations);
    this.build();
  }

  setAnimations(animations) {
    this.animations = animations;
    this.tracker.setBoard(this.board, animations);
    for (const o of this.nodes) o.child?.setAnimations(animations);
  }

  setValues(values, fx = this.fx) {
    this.values = values || {};
    this.fx = fx || {};
    this.render();
  }

  play(eid, name) {
    this.tracker.play(eid, name, now());
    this.schedule();
  }

  build() {
    for (const o of this.nodes) o.child?.destroy();
    this.stage.textContent = "";
    this.nodes = [];
    const b = this.board;
    if (!b) return;
    this.stage.style.width = b.width + "px";
    this.stage.style.height = b.height + "px";
    const bg = this.opt.background !== undefined ? this.opt.background : cssColor(resolveColor(b.background, this.values));
    this.stage.style.background = bg || "transparent";
    for (const raw of b.elements) {
      const e = { ...ELEMENT_DEFAULTS, ...raw };
      const n = document.createElement("div");
      n.className = "bv-el";
      n.dataset.id = e.id;
      Object.assign(n.style, { position: "absolute", boxSizing: "border-box", display: "flex", left: e.x + "px", top: e.y + "px",
        width: e.w + "px", height: e.h + "px", borderRadius: e.radius + "px", padding: e.padding + "px", transformOrigin: "50% 50%",
        overflow: e.kind === "board" ? "visible" : "hidden" });
      n.style.justifyContent = { left: "flex-start", center: "center", right: "flex-end" }[e.align] || "center";
      n.style.alignItems = { top: "flex-start", middle: "center", bottom: "flex-end" }[e.valign] || "center";
      let inner = null, child = null;
      if (e.kind === "text") {
        inner = document.createElement("span");
        const wrap = e.extent !== "auto" && e.wrap;
        Object.assign(inner.style, { fontWeight: e.weight, fontStyle: e.italic ? "italic" : "normal", letterSpacing: e.tracking + "em",
          textTransform: e.uppercase ? "uppercase" : "none", fontVariantNumeric: e.tabular ? "tabular-nums" : "normal",
          textAlign: e.align, whiteSpace: wrap ? "pre-wrap" : "pre", overflowWrap: wrap ? "break-word" : "normal", lineHeight: "1.1",
          maxWidth: wrap ? "100%" : "none", flex: "none" });
        n.appendChild(inner);
      } else if (e.kind === "image") {
        inner = document.createElement("img");
        inner.alt = "";
        inner.draggable = false;
        Object.assign(inner.style, { width: "100%", height: "100%", objectFit: e.contain ? "contain" : "fill" });
        n.appendChild(inner);
      } else if (e.kind === "board") {
        const target = this.boards.get(e.board);
        const chain = [...this.opt.chain, b.id];
        if (target && !chain.includes(target.id) && this.opt.depth < MAX_DEPTH) {
          const box = document.createElement("div");
          Object.assign(box.style, { position: "absolute", inset: "0" });
          n.appendChild(box);
          child = new BoardView(box, { ...this.opt, box: { w: e.w, h: e.h }, depth: this.opt.depth + 1, chain, background: "", show_all: false });
          child.boards = this.boards;
          child.setBoard(target, this.animations);
        }
      }
      this.stage.appendChild(n);
      this.nodes.push({ e, n, inner, child, last: {}, rect: { x: e.x, y: e.y, w: e.w, h: e.h } });
    }
    this.fit();
    this.render();
  }

  fit() {
    const b = this.board;
    if (!b) return;
    let left, top;
    if (this.view) {                       // the designer's zoom and pan
      this.scale = this.view.s;
      left = this.view.x; top = this.view.y;
    } else {
      const r = this.opt.box ? { width: this.opt.box.w, height: this.opt.box.h } : this.host.getBoundingClientRect();
      this.scale = this.opt.fit === "none" ? 1 : Math.max(0.0001, Math.min(r.width / b.width, r.height / b.height));
      left = (r.width - b.width * this.scale) / 2;
      top = (r.height - b.height * this.scale) / 2;
      if (!this.opt.box) { left = Math.round(left); top = Math.round(top); }
    }
    this.stage.style.transform = `scale(${this.scale})`;
    this.stage.style.left = left + "px";
    this.stage.style.top = top + "px";
    this.onfit?.();
  }

  // Fixed scale and offset (host px), or null to fit the board in the host.
  setView(v) { this.view = v; this.fit(); }
  fitScale() {
    const r = this.host.getBoundingClientRect();
    return this.board ? Math.max(0.01, Math.min(r.width / this.board.width, r.height / this.board.height)) : 1;
  }

  // board px -> host px
  origin() { return { x: parseFloat(this.stage.style.left) || 0, y: parseFloat(this.stage.style.top) || 0, s: this.scale }; }

  // Where an element really is, in board px: Auto text is as big as its text.
  rectOf(id) {
    const o = this.nodes.find((x) => x.e.id === id);
    return o ? { ...o.rect } : null;
  }

  refit() { for (const o of this.nodes) { o.last.fitted = false; o.child?.refit(); } this.render(); }

  fitText(o) {
    const { e, n, inner } = o;
    const sw = e.stroke_width || 0;
    let size = e.size;
    inner.style.fontSize = size + "px";
    if (e.extent === "auto") {
      // The box hugs the text and grows from its alignment point.
      const w = Math.ceil(inner.offsetWidth) + 2 * e.padding + 2 * sw;
      const h = Math.ceil(inner.offsetHeight) + 2 * e.padding + 2 * sw;
      const x = e.align === "left" ? e.x : e.align === "right" ? e.x + e.w - w : e.x + e.w / 2 - w / 2;
      const y = e.valign === "top" ? e.y : e.valign === "bottom" ? e.y + e.h - h : e.y + e.h / 2 - h / 2;
      Object.assign(n.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
      o.rect = { x, y, w, h };
      return;
    }
    o.rect = { x: e.x, y: e.y, w: e.w, h: e.h };
    if (!e.fit) return;
    const avail = e.w - 2 * e.padding - 2 * sw;
    const availH = e.h - 2 * e.padding - 2 * sw;
    let guard = 0;
    while (size > 6 && (inner.scrollWidth > avail + 0.5 || inner.offsetHeight > availH + 0.5) && guard++ < 60) {
      const byW = inner.scrollWidth > avail + 0.5 ? avail / Math.max(1, inner.scrollWidth) : 1;
      const byH = inner.offsetHeight > availH + 0.5 ? Math.sqrt(availH / Math.max(1, inner.offsetHeight)) : 1;
      size = Math.max(6, size * Math.min(0.97, byW, byH));
      inner.style.fontSize = size + "px";
    }
  }

  render() {
    if (!this.board) return;
    this.tracker.update(this.values, this.fx, now(), this.opt.animate);
    for (const o of this.nodes) {
      const { e, n, inner, last } = o;
      const fx = this.fx[e.id] || {};
      const fill = cssColor(resolveColor(fx.fill || (e.kind === "box" ? fx.color || "" : "") || e.fill, this.values));
      if (last.fill !== fill) { n.style.background = fill || "transparent"; last.fill = fill; }
      const stroke = cssColor(resolveColor(e.stroke, this.values));
      const border = stroke && e.stroke_width > 0 ? `${e.stroke_width}px solid ${stroke}` : "none";
      if (last.border !== border) { n.style.border = border; last.border = border; }
      if (e.kind === "text") {
        const txt = elementText(e, this.values, fx);
        const col = cssColor(resolveColor(fx.color || e.color, this.values)) || "#ffffff";
        const fam = fontStack(fx.font || e.font);
        if (last.fam !== fam) { inner.style.fontFamily = fam; last.fam = fam; last.fitted = false; }
        if (last.txt !== txt) { inner.textContent = txt; last.txt = txt; last.fitted = false; }
        if (last.col !== col) { inner.style.color = col; last.col = col; }
        if (!last.fitted && last.vis) { this.fitText(o); last.fitted = true; }
      } else if (e.kind === "image") {
        const p = String(fx.src || renderTemplate(e.src, this.values)).trim();
        const url = p ? (/^(https?:|data:|blob:)/.test(p) ? p : this.opt.assetUrl(p)) : "";
        if (last.src !== url) {
          if (url) { inner.src = url; inner.style.visibility = "visible"; } else { inner.removeAttribute("src"); inner.style.visibility = "hidden"; }
          last.src = url;
        }
      } else if (e.kind === "board") {
        o.child?.setValues(this.values, this.fx);
      }
    }
    this.schedule();
  }

  schedule() { if (!this.raf) this.raf = requestAnimationFrame(() => this.paint()); }

  paint() {
    this.raf = 0;
    const t = now();
    let busy = false;
    for (const o of this.nodes) {
      const { e, n, last } = o;
      let lk = this.tracker.look(e, t);
      let dim = false;
      if (!lk && this.opt.show_all && e.visible !== false) { lk = ID; dim = true; }   // designer: hidden by logic, drawn faint
      const vis = !!lk;
      if (last.vis !== vis) { n.style.display = vis ? "flex" : "none"; last.vis = vis; }
      if (!vis) continue;
      if (this.tracker.state[e.id]?.anim) busy = true;
      const tr = lk.x || lk.y || lk.scale !== 1 ? `translate(${lk.x}px,${lk.y}px) scale(${lk.scale})` : "";
      if (last.tr !== tr) { n.style.transform = tr; last.tr = tr; }
      const op = String(Math.max(0, Math.min(1, e.opacity * lk.opacity * (dim ? 0.35 : 1))));
      if (last.op !== op) { n.style.opacity = op; last.op = op; }
      const c = lk.clip;
      const cp = c[0] > 0 || c[1] > 0 || c[2] < 1 || c[3] < 1 ? `inset(${c[1] * 100}% ${(1 - c[2]) * 100}% ${(1 - c[3]) * 100}% ${c[0] * 100}%)` : "";
      if (last.cp !== cp) { n.style.clipPath = cp; last.cp = cp; }
      if (!last.fitted && e.kind === "text") { this.fitText(o); last.fitted = true; }
    }
    if (busy) this.schedule();
    this.onpaint?.();
  }
}
