// Properties: the right panel in Edit mode. Shows whatever is selected: a
// control on the page, a field, a button, or (with nothing selected) the page.

import { act, call, edit, store } from "./api.js";
import { button, chip, clear, h, kbd, rerender } from "./dom.js";
import { formatMs, parseTime } from "/core/timefmt.js";
import { TYPE_NAMES, validKey } from "/core/fields.js";
import { ROLES } from "/core/project.js";
import { display, fromEvent, isGlobalSafe, normalise } from "./keys.js";
import { attempt, check, colorInput, confirmDialog, numberInput, select, textInput, toast, ui } from "./ui.js";

export function renderProps(el, ctx) {
  if (!store.project) return;
  rerender(el, () => h("div.side-body", { "data-scroll": "props" }, body(ctx)));
}

function body(ctx) {
  const p = store.project;
  const sel = ui.sel;
  if (sel?.kind === "tile") {
    const t = ctx.page()?.tiles.find((x) => x.id === sel.id);
    if (t) return tileProps(t, ctx);
  }
  if (sel?.kind === "field") {
    const f = p.fields.find((x) => x.key === sel.id);
    if (f) return [h("div.section-title", `Field · ${TYPE_NAMES[f.type]}`), addToPage(ctx, { kind: "field", field: f.key }), fieldForm(f, ctx)];
  }
  if (sel?.kind === "button") {
    const b = p.buttons.find((x) => x.id === sel.id);
    if (b) return [h("div.section-title", "Shortcut"), addToPage(ctx, { kind: "button", button: b.id }), buttonForm(b, ctx)];
  }
  return pageProps(ctx);
}

function addToPage(ctx, item) {
  const on = ctx.page()?.tiles.some((t) => (item.field && t.field === item.field) || (item.button && t.button === item.button));
  return h("div.row", { style: { marginBottom: "12px" } }, button(on ? "Add another to this page" : "Add to this page", () => ctx.addTile(item), { role: on ? "" : "accent" }),
    on ? h("span.hint", "It is already on this page.") : null);
}

// ---- page -------------------------------------------------------------------------------------
function pageProps(ctx) {
  const pg = ctx.page();
  if (!pg) return h("p.hint", "No page.");
  const rename = (v) => {
    const L = structuredClone(store.project.layout);
    L.pages.find((x) => x.id === pg.id).name = v.trim() || "Page";
    attempt(() => edit({ op: "layout.put", layout: L }, "Rename page"));
  };
  return [
    h("div.section-title", "Page"),
    h("div.form", h("label", "Name"), textInput(pg.name, rename, { k: "page-name" })),
    h("p.hint", { style: { marginTop: "12px" } }, `${pg.tiles.length} controls on this page.`),
    h("div.panel", h("h3", "How to arrange"), h("ul.hint", { style: { margin: 0, paddingLeft: "18px" } },
      h("li", "Drag a field or shortcut from the Library onto the grid."),
      h("li", "Click a control to select it. Drag it to move; drag its right or bottom edge, or the corner, to resize."),
      h("li", "Arrow keys move the selected control; Shift + arrows resize it. Delete removes it from the page."),
      h("li", "Right-click a page tab to rename, move or delete it."),
      h("li", `${display("Ctrl+Z", { app: true })} undoes a layout change. Scores and clocks are never undone by it.`),
      h("li", "Press Locked (or L) to run the game."))),
  ];
}

// ---- tiles --------------------------------------------------------------------------------------
function tileProps(t, ctx) {
  const p = store.project;
  const setTile = (changes, label = "Change control") => {
    const tiles = ctx.page().tiles.map((x) => (x.id === t.id ? { ...x, ...changes } : x));
    return ctx.commitTiles(tiles, label, [t.id]);
  };
  const size = h("div.form",
    h("label", "Width"), numberInput(t.w, (v) => setTile({ w: v }, "Resize control"), { k: "tile-w", min: 1, max: 24, suffix: "columns of 24" }),
    h("label", "Height"), numberInput(t.h, (v) => setTile({ h: v }, "Resize control"), { k: "tile-h", min: 1, max: 40, suffix: "rows" }));
  const remove = button("Remove from page", () => ctx.removeTile(t.id), { role: "alert", title: "Delete (the field or button stays in the project)" });
  const out = [];
  if (t.kind === "field") {
    const f = p.fields.find((x) => x.key === t.field);
    out.push(h("div.section-title", "Control"),
      h("div.form", h("label", "Label"), textInput(t.label || "", (v) => setTile({ label: v.trim() || undefined }), { k: "tile-label", placeholder: f?.label ?? "" })),
      h("div.hint", "Leave empty to use the field's own name."), size, h("div.row", { style: { margin: "10px 0 16px" } }, remove));
    if (f) out.push(h("div.section-title", `Field · ${TYPE_NAMES[f.type]}`), fieldForm(f, ctx));
  } else if (t.kind === "button") {
    const b = p.buttons.find((x) => x.id === t.button);
    out.push(h("div.section-title", "Control"), size, h("div.row", { style: { margin: "10px 0 16px" } }, remove));
    if (b) out.push(h("div.section-title", "Shortcut"), buttonForm(b, ctx));
  } else if (t.kind === "heading") {
    out.push(h("div.section-title", "Heading"), h("div.form", h("label", "Text"), textInput(t.text, (v) => setTile({ text: v }), { k: "tile-text" })), size,
      h("div.row", { style: { marginTop: "10px" } }, remove));
  } else if (t.kind === "preview") {
    out.push(h("div.section-title", "Board preview"),
      h("div.form", h("label", "Board"), select(p.boards.map((b) => [b.id, b.name]), t.board, (v) => setTile({ board: v }), { k: "tile-board" })),
      h("p.hint", "A live picture of a graphic, exactly as it goes on air."), size, h("div.row", { style: { marginTop: "10px" } }, remove));
  }
  return out;
}

// ---- fields -----------------------------------------------------------------------------------------
const msText = (ms) => formatMs(ms, ms >= 3_600_000 ? "h:mm:ss" : "m:ss", false) + (ms % 1000 ? "." + String(Math.floor((ms % 1000) / 100)) : "");

export function fieldForm(f, ctx) {
  const p = store.project;
  const upd = (changes, label = `Change ${f.label}`) => attempt(() => edit({ op: "field.update", key: f.key, changes }, label));
  const rows = [];
  const row = (label, control, hint) => rows.push(h("label", label), control, hint ? h("div.hint", hint) : null);
  row("Name", textInput(f.label, (v) => upd({ label: v.trim() || f.key }), { k: `f-label-${f.key}` }));
  row("Key", textInput(f.key, async (v, el) => {
    v = v.trim();
    if (!validKey(v)) { el.classList.add("error"); toast("A key is lower-case words joined by dots, for example home.score.", true); return; }
    el.classList.remove("error");
    const r = await attempt(() => edit({ op: "field.rename", key: f.key, to: v }, `Rename ${f.key}`));
    if (r && ui.sel?.kind === "field") ui.sel = { kind: "field", id: v };
  }, { k: `f-key-${f.key}`, cls: "mono" }), "Used in file names, XML and graphics. Renaming updates every graphic, shortcut and condition.");

  if (f.type === "counter") {
    row("Value", numberInput(store.snapshot?.raw?.[f.key] ?? f.value, (v) => act({ do: "set", field: f.key, value: v }).catch((e) => toast(e.message, true)), { k: `f-val-${f.key}` }));
    row("Reset to", numberInput(f.default, (v) => upd({ default: v }), { k: `f-def-${f.key}` }));
    row("Lowest", textInput(f.minimum ?? "", (v) => upd({ minimum: v.trim() === "" ? null : Number(v) }), { k: `f-min-${f.key}`, placeholder: "no limit" }));
    row("Highest", textInput(f.maximum ?? "", (v) => upd({ maximum: v.trim() === "" ? null : Number(v) }), { k: `f-max-${f.key}`, placeholder: "no limit" }));
    row("Steps", textInput((f.steps || [1]).join(", "), (v) => {
      const steps = v.split(/[ ,]+/).map(Number).filter((n) => Number.isInteger(n) && n !== 0);
      upd({ steps: steps.length ? steps : [1] });
    }, { k: `f-steps-${f.key}`, placeholder: "1, 2, 3" }), "The + buttons on its control, e.g. 1, 2, 3 for basketball.");
    rows.push(h("div.full.col", check("Show as 1st, 2nd, 3rd", f.ordinal, (v) => upd({ ordinal: v }), { k: `f-ord-${f.key}` }),
      check("Show nothing at zero", f.blank_zero, (v) => upd({ blank_zero: v }), { k: `f-bz-${f.key}` })));
    row("Digits", numberInput(f.pad, (v) => upd({ pad: v }), { k: `f-pad-${f.key}`, min: 0, max: 6 }), "Pad with zeros, e.g. 2 shows 07.");
  } else if (f.type === "text") {
    row("Reset to", textInput(f.default, (v) => upd({ default: v }), { k: `f-def-${f.key}` }));
    rows.push(h("div.full", check("Show in capitals", f.uppercase, (v) => upd({ uppercase: v }), { k: `f-up-${f.key}` })));
    rows.push(h("div.full", check("Drop leading zeros from numbers (06 shows as 6)", f.trim_zeros, (v) => upd({ trim_zeros: v }), { k: `f-trim-${f.key}` })));
  } else if (f.type === "toggle") {
    row("On shows", textInput(f.on_text, (v) => upd({ on_text: v }), { k: `f-on-${f.key}` }), "The text that goes out while it is on, e.g. BONUS.");
    row("Off shows", textInput(f.off_text, (v) => upd({ off_text: v }), { k: `f-off-${f.key}`, placeholder: "nothing" }));
    rows.push(h("div.full", check("On when reset", f.default, (v) => upd({ default: v }), { k: `f-def-${f.key}` })));
  } else if (f.type === "choice") {
    const ta = h("textarea.input", { "data-k": `f-opts-${f.key}`, rows: Math.min(8, Math.max(3, f.options.length)), spellcheck: false }, f.options.join("\n"));
    ta.addEventListener("change", () => upd({ options: ta.value.split("\n").map((s) => s.trim()).filter((s, i, a) => s !== "" || a.length === 1) }));
    row("Options", ta, "One per line, in order.");
    row("Reset to", select(f.options.map((o, i) => [i, o || "—"]), f.default, (v) => upd({ default: Number(v) }), { k: `f-def-${f.key}` }));
    rows.push(h("div.full", check("After the last, go back to the first", f.wrap, (v) => upd({ wrap: v }), { k: `f-wrap-${f.key}` })));
  } else if (f.type === "clock") {
    row("Counts", select([["down", "Down (game clock)"], ["up", "Up (stopwatch)"]], f.countdown ? "down" : "up", (v) => upd({ countdown: v === "down" }), { k: `f-cd-${f.key}` }));
    if (f.countdown) row("Period length", textInput(msText(f.initial_ms), (v, el) => {
      try { upd({ initial_ms: parseTime(v) }); el.classList.remove("error"); } catch (e) { el.classList.add("error"); toast(e.message, true); }
    }, { k: `f-init-${f.key}` }), "Reset goes back to this.");
    else row("Stop at", textInput(f.limit_ms ? msText(f.limit_ms) : "", (v, el) => {
      try { upd({ limit_ms: v.trim() ? parseTime(v) : 0 }); el.classList.remove("error"); } catch (e) { el.classList.add("error"); toast(e.message, true); }
    }, { k: `f-lim-${f.key}`, placeholder: "never" }));
    row("Shows as", select(["m:ss", "mm:ss", "h:mm:ss", "s", "ss", "m:ss.t", "mm:ss.t", "s.t"].map((x) => [x, `${x}  (${formatMs(f.countdown ? 754_300 : 54_300, x, f.countdown)})`]), f.fmt,
      (v) => upd({ fmt: v }), { k: `f-fmt-${f.key}` }));
    if (f.countdown) {
      row("Tenths under", select([[0, "never"], [60_000, "1:00"], [10_000, "0:10"], [5_000, "0:05"]], f.tenths_under_ms, (v) => upd({ tenths_under_ms: Number(v) }), { k: `f-ten-${f.key}` }),
        "Switch to tenths of a second near the end, like an arena clock. With live data, tenths also show whenever the scoreboard shows them.");
      rows.push(h("div.full", check("Show nothing at 0:00", f.blank_at_zero, (v) => upd({ blank_at_zero: v }), { k: `f-blank-${f.key}` })));
    }
    row("Buzzer", h("div.row", textInput(f.buzzer || "", (v) => upd({ buzzer: v.trim() }), { k: `f-buzz-${f.key}`, placeholder: "No sound" }),
      store.state.host.dialogs ? button("Choose…", async () => { const r = await attempt(() => call("/api/pick", { kind: "sound" })); if (r?.path) upd({ buzzer: r.path }); }) : null),
      "Played on this computer when it reaches zero.");
  } else if (f.type === "penalties") {
    const clocks = p.fields.filter((x) => x.type === "clock");
    row("Runs with", select([["", "— no clock —"], ...clocks.map((c) => [c.key, c.label])], f.master, (v) => upd({ master: v }), { k: `f-master-${f.key}` }),
      "Penalties count down only while this clock runs.");
    row("On the board", numberInput(f.slots, (v) => upd({ slots: v }), { k: `f-slots-${f.key}`, min: 1, max: 9, suffix: "at once" }));
    row("Shows as", select(["m:ss", "mm:ss", "s"], f.fmt, (v) => upd({ fmt: v }), { k: `f-fmt-${f.key}` }));
  } else if (f.type === "image") {
    row("Picture", h("div.row", textInput(store.snapshot?.raw?.[f.key] ?? f.value, (v) => act({ do: "set", field: f.key, value: v.trim() }).catch((e) => toast(e.message, true)), { k: `f-val-${f.key}`, placeholder: "No picture" }),
      store.state.host.dialogs ? button("Choose…", async () => { const r = await attempt(() => call("/api/pick", { kind: "image" })); if (r?.path) act({ do: "set", field: f.key, value: r.path }); }) : null));
    row("Reset to", textInput(f.default, (v) => upd({ default: v.trim() }), { k: `f-def-${f.key}`, placeholder: "No picture" }));
  }

  const logic = [];
  const lrow = (label, control, hint) => logic.push(h("label", label), control, hint ? h("div.hint", hint) : null);
  lrow("Live key", textInput(f.source, (v) => upd({ source: v.trim() }, "Live key"), { k: `f-src-${f.key}`, placeholder: "not bound", list: "live-keys" }),
    "A key from Live data, e.g. HomeScore. The field then shows the bot's value.");
  lrow("Rules", textInput(f.rules, (v) => upd({ rules: v }, "Rules"), { k: `f-rules-${f.key}`, placeholder: "0:00=FINAL|NULL=—" }),
    "Replace shown values everywhere: text files, XML and graphics.");
  lrow("Override", h("div.row", textInput(f.override, (v) => upd({ override: v }, "Override"), { k: `f-ovr-${f.key}`, placeholder: "e.g. HALFTIME" }),
    button(f.override_on ? "On" : "Off", () => upd({ override_on: !f.override_on }, f.override_on ? "Override off" : "Override on"),
      { role: f.override_on ? "user" : "", title: "While on, every output shows the override text instead of the value" })));

  const refs = h("div.hint", "…");
  call("/api/references", { key: f.key }).then((r) => refs.replaceChildren(r.refs.length ? h("ul", { style: { margin: 0, paddingLeft: "18px" } }, r.refs.map((x) => h("li", x))) : "Not used by any graphic, shortcut or condition yet.")).catch(() => {});
  return [
    h("div.form", ...rows),
    h("div.section-title", { style: { marginTop: "14px" } }, "Live data, rules, override"),
    h("div.form", ...logic),
    h("div.section-title", { style: { marginTop: "14px" } }, "Used by"), refs,
    h("div.row", { style: { marginTop: "14px" } }, button("Delete field", async () => {
      const r = await call("/api/references", { key: f.key }).catch(() => ({ refs: [] }));
      const extra = r.refs.length ? ` It is used by ${r.refs.length} thing${r.refs.length === 1 ? "" : "s"}, which will show nothing.` : "";
      if (await confirmDialog("Delete field", `Delete “${f.label}” (${f.key})? Its controls leave every page.${extra}`, "Delete", "danger")) {
        ui.sel = null;
        attempt(() => edit({ op: "field.remove", key: f.key }, `Delete ${f.label}`));
      }
    }, { role: "alert" })),
  ];
}

// ---- buttons --------------------------------------------------------------------------------------------
export const STEPS = {
  add: ["Add", ["counter", "clock", "choice"]], set: ["Set to", ["counter", "text", "toggle", "choice", "clock", "image"]],
  reset: ["Reset", ["counter", "text", "toggle", "choice", "clock", "image", "penalties"]], toggle: ["Start/stop or flip", ["clock", "toggle"]],
  start: ["Start", ["clock"]], stop: ["Stop", ["clock"]], adjust: ["Add time", ["clock"]], next: ["Next", ["choice", "counter"]], prev: ["Previous", ["choice", "counter"]],
  "penalty.add": ["Add penalty", ["penalties"]], "penalty.remove": ["Remove penalty", ["penalties"]], "penalty.clear": ["Clear penalties", ["penalties"]],
  stop_all: ["Stop every clock", null], undo: ["Undo", null], redo: ["Redo", null],
};

export function describe(a) {
  const name = STEPS[a.do]?.[0] ?? a.do;
  const f = a.field ?? "";
  if (a.do === "add") return `${f} ${Number(a.amount ?? 1) >= 0 ? "+" : ""}${Number(a.amount ?? 1)}`;
  if (a.do === "set") return `${f} = ${a.value ?? ""}`;
  if (a.do === "adjust") return `${f} ${Number(a.ms ?? 0) >= 0 ? "+" : ""}${Number(a.ms ?? 0) / 1000} s`;
  if (a.do === "penalty.add") return `${f}: add ${a.player || "penalty"} ${a.time ?? "2:00"}`;
  if (a.do === "batch") return (a.actions || []).map(describe).join(" · ");
  return `${name} ${f}`.trim();
}

export function buttonForm(b, ctx) {
  const p = store.project;
  const put = (changes, label = `Change ${b.label}`) => attempt(() => edit({ op: "button.put", button: { ...b, ...changes } }, label));
  const steps = b.action?.do === "batch" ? b.action.actions || [] : b.action?.do ? [b.action] : [];
  const setSteps = (list) => put({ action: list.length === 1 ? list[0] : { do: "batch", actions: list } }, "Change steps");
  const clash = b.hotkey ? p.buttons.filter((x) => x.id !== b.id && x.hotkey && normalise(x.hotkey) === normalise(b.hotkey)).map((x) => x.label) : [];

  // Press the keys to set a shortcut.
  const keyBox = h("input.input", { value: b.hotkey, readOnly: true, placeholder: "Click, then press a key", "data-k": `b-key-${b.id}` });
  keyBox.addEventListener("keydown", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const combo = fromEvent(e);
    if (!combo || combo === "Tab" || combo === "Shift+Tab") return;
    if (combo === "Esc") { keyBox.blur(); return; }
    if (combo === "Backspace" || combo === "Del") { put({ hotkey: "" }, "Clear shortcut"); return; }
    put({ hotkey: combo }, "Set shortcut");
  });

  const fieldsFor = (types) => p.fields.filter((f) => types.includes(f.type));
  const stepRows = steps.map((s, i) => {
    const types = STEPS[s.do]?.[1];
    const change = (patch) => setSteps(steps.map((x, j) => (j === i ? clean({ ...x, ...patch }) : x)));
    const doSel = select(Object.entries(STEPS).map(([k, [label]]) => [k, label]), s.do, (v) => {
      const t = STEPS[v][1];
      const keep = t && fieldsFor(t).some((f) => f.key === s.field) ? s.field : t ? fieldsFor(t)[0]?.key : undefined;
      change({ do: v, field: keep, ...(v === "add" ? { amount: 1 } : v === "adjust" ? { ms: 1000 } : v === "set" ? { value: "" } : v === "penalty.add" ? { player: "", time: "2:00" } : v === "penalty.remove" ? { index: 1 } : {}) });
    }, { k: `b-do-${b.id}-${i}` });
    const fieldSel = types ? select(fieldsFor(types).map((f) => [f.key, f.label]).concat(s.field && !fieldsFor(types).some((f) => f.key === s.field) ? [[s.field, `${s.field} (${p.fields.some((f) => f.key === s.field) ? "cannot do this" : "missing"})`]] : []),
      s.field, (v) => change({ field: v }), { k: `b-f-${b.id}-${i}` }) : null;
    let param = null;
    if (s.do === "add") param = numberInput(Number(s.amount ?? 1), (v) => change({ amount: v }), { k: `b-amt-${b.id}-${i}`, min: -999, max: 999 });
    else if (s.do === "set") param = textInput(String(s.value ?? ""), (v) => change({ value: typedValue(p, s.field, v) }), { k: `b-val-${b.id}-${i}`, placeholder: "value, e.g. 0, 2:00, Hawks, on" });
    else if (s.do === "adjust") param = numberInput(Number(s.ms ?? 1000) / 1000, (v) => change({ ms: Math.round(v * 1000) }), { k: `b-ms-${b.id}-${i}`, step: 0.1, suffix: "s" });
    else if (s.do === "penalty.add") param = h("div.row", textInput(s.player ?? "", (v) => change({ player: v.trim() }), { k: `b-pl-${b.id}-${i}`, placeholder: "player" }),
      textInput(s.time ?? "2:00", (v) => change({ time: v.trim() || "2:00" }), { k: `b-tm-${b.id}-${i}` }));
    else if (s.do === "penalty.remove") param = numberInput(Number(s.index ?? 1), (v) => change({ index: v }), { k: `b-ix-${b.id}-${i}`, min: 1, max: 20 });
    return h("div.panel.col", { style: { padding: "8px" } },
      h("div.row", h("span.caps", `Step ${i + 1}`), h("span.spacer"),
        button("↑", () => { const l = [...steps]; [l[i - 1], l[i]] = [l[i], l[i - 1]]; setSteps(l); }, { cls: "btn-sm", disabled: i === 0, title: "Move up" }),
        button("Remove", () => setSteps(steps.filter((_, j) => j !== i)), { cls: "btn-sm", role: "alert", disabled: steps.length < 2 })),
      doSel, fieldSel, param);
  });

  return [
    h("div.form",
      h("label", "Label"), textInput(b.label, (v) => put({ label: v.trim() || "Shortcut" }), { k: `b-label-${b.id}` }),
      h("label", "Colour"), select(Object.entries(ROLES), b.role, (v) => put({ role: v }), { k: `b-role-${b.id}` }),
      h("label", "Key"), h("div.row", keyBox, button("Clear", () => put({ hotkey: "" }, "Clear key"), { disabled: !b.hotkey }))),
    h("p.hint", clash.length ? h("span", { style: { color: "var(--alert-text)" } }, `Also used by ${clash.join(", ")}. Only the first one runs.`)
      : b.hotkey ? (isGlobalSafe(b.hotkey) ? "Works while typing in a box too." : "Works anywhere in CORBELscore except while typing in a box.") : `Click the box and press a key, e.g. Space or ${display("Ctrl+1")}.`),
    h("div.section-title", { style: { marginTop: "10px" } }, "Steps · run in order, undone together"),
    h("div.col", stepRows),
    h("div.row", { style: { marginTop: "8px" } },
      button("Add step", () => setSteps([...steps, { do: "add", field: p.fields.find((f) => ["counter", "clock", "choice"].includes(f.type))?.key, amount: 1 }])),
      h("span.spacer"),
      button("Try it", () => act(b.action).then(() => toast(`Ran ${b.label}.`), (e) => toast(e.message, true)), { role: "accent", title: "Run the shortcut now" })),
    h("p.hint", describe(b.action ?? {})),
    h("div.row", { style: { marginTop: "14px" } }, button("Delete shortcut", async () => {
      if (await confirmDialog("Delete shortcut", `Delete “${b.label}”? It leaves every page and its key stops working.`, "Delete", "danger")) {
        ui.sel = null;
        attempt(() => edit({ op: "button.remove", id: b.id }, `Delete ${b.label}`));
      }
    }, { role: "alert" })),
  ];
}

const clean = (a) => Object.fromEntries(Object.entries(a).filter(([, v]) => v !== undefined));
function typedValue(p, key, text) {
  const f = p.fields.find((x) => x.key === key);
  if (f?.type === "toggle") return ["1", "true", "on", "yes", "show"].includes(text.trim().toLowerCase());
  if (f?.type === "counter" && /^-?\d+$/.test(text.trim())) return Number(text.trim());
  return text;
}
