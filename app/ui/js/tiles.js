// The controls on a layout page. Each tile is drawn for what it holds: a
// field's control (by the field's type), one of the project's buttons, a
// heading, or a live picture of a board. update(snapshot) refreshes values
// without rebuilding, so typing and pressing are never interrupted.

import { act, fileUrl, store } from "./api.js";
import { button, chip, h, kbd } from "./dom.js";
import { attempt, toast } from "./ui.js";
import { BoardView } from "/render/board-view.js";

const run = (action) => act(action).catch((e) => toast(e.message, true));

function entry(placeholder, onSet, { k, width } = {}) {
  const el = h("input.input", { placeholder, "data-k": k, spellcheck: false, style: width ? { maxWidth: width } : null });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" && el.value.trim()) { onSet(el.value.trim()); el.value = ""; } if (e.key === "Escape") { el.value = ""; el.blur(); } });
  return el;
}

// LIVE / OVERRIDE / WAITING beside a field's label (Rally: colour and word).
function stateChip(f, snap) {
  if (f.override_on) {
    const c = h("button.chip.chip-user", { type: "button", title: "An override is showing instead of the value. Click to turn it off." }, "Override");
    c.addEventListener("click", () => import("./api.js").then(({ edit }) => edit({ op: "field.update", key: f.key, changes: { override_on: false } }, "Override off")));
    return c;
  }
  if (f.source) {
    const live = snap?.live?.includes(f.key);
    return live ? chip("Live", "accent", `Following live data: ${f.source}`) : chip("Waiting", "muted", `Waiting for live data: ${f.source}`);
  }
  return null;
}

function head(label, f, snap, extra = null) {
  const chipSlot = h("span.t-chip");
  const sc = f ? stateChip(f, snap) : null;
  if (sc) chipSlot.append(sc);
  return [h("div.t-head", h("span.t-label", { title: label }, label), extra, chipSlot), chipSlot];
}

export function renderTile(t, { project, snap }) {
  const el = h(`div.tile.kind-${t.kind}`, { "data-tile": t.id });
  let update = () => {};
  if (t.kind === "heading") {
    el.append(h("div.h", t.text || "Heading"));
  } else if (t.kind === "preview") {
    const b = project.boards.find((x) => x.id === t.board);
    if (!b) { el.classList.add("missing"); el.append(h("span.small", "That board was deleted.")); }
    else {
      el.classList.add("checker");
      const host = h("div", { style: { position: "absolute", inset: "0" } });
      el.append(host);
      const view = new BoardView(host, { assetUrl: fileUrl });
      view.setBoard(b, project.animations);
      update = (s) => s && view.setValues(s.values, s.fx);
      el._destroy = () => view.destroy();
    }
  } else if (t.kind === "button") {
    const b = project.buttons.find((x) => x.id === t.button);
    if (!b) { el.classList.add("missing"); el.append(h("span.small", "That button was deleted.")); }
    else {
      const pb = h(`button.btn.pbtn${b.role && b.role !== "neutral" ? ".btn-" + b.role : ""}`, { type: "button", "data-button": b.id,
        title: b.hotkey ? `${b.label} · shortcut ${b.hotkey}` : b.label, onclick: () => run(b.action) },
        h("span.lbl", b.label), b.hotkey ? kbd(b.hotkey) : null);
      el.append(pb);
    }
  } else {
    const f = project.fields.find((x) => x.key === t.field);
    if (!f) { el.classList.add("missing"); el.append(h("span.small", `There is no field “${t.field}” any more.`)); }
    else ({ update } = fieldTile(el, f, t, snap));
  }
  el.append(h("div.rz", { title: "Drag to resize" }));
  update(snap);
  return { el, update };
}

function fieldTile(el, f, t, snap) {
  const label = t.label || f.label;
  el.classList.add(`k-${f.type}`);
  const [hd, chipSlot] = head(label, f, snap);
  const val = (s) => s?.values?.[f.key] ?? "";
  const refreshChip = (s) => { const c = stateChip(f, s); chipSlot.replaceChildren(...(c ? [c] : [])); };
  el.append(hd);

  if (f.type === "counter") {
    const value = h("div.t-value", "0");
    const steps = h("div.t-steps",
      button("−1", () => run({ do: "add", field: f.key, amount: -1 }), { role: "alert", title: `${label} −1` }),
      (f.steps || [1]).map((s) => button(s > 0 ? `+${s}` : String(s), () => run({ do: "add", field: f.key, amount: s }), { title: `${label} ${s > 0 ? "+" : ""}${s}` })));
    el.append(h("div.t-main", value, steps),
      h("div.t-set", entry("Set to…", (v) => run({ do: "set", field: f.key, value: v }), { k: `set-${t.id}` }), button("Reset", () => run({ do: "reset", field: f.key }), { title: `Back to ${f.default}` })));
    return { update: (s) => { value.textContent = val(s) || (f.blank_zero ? "0" : ""); refreshChip(s); } };
  }

  if (f.type === "clock") {
    const value = h("div.t-value", "");
    const runChip = h("span");
    hd.insertBefore(runChip, chipSlot);
    const go = button("Start", () => run({ do: "toggle", field: f.key }), { role: "accent", big: true, cls: "t-go" });
    const adj = h("div.t-row.t-adj", [["−1m", -60_000], ["−1s", -1000], ["+1s", 1000], ["+1m", 60_000]].map(([l, ms]) =>
      button(l, () => run({ do: "adjust", field: f.key, ms }), { title: `${ms > 0 ? "Add" : "Remove"} ${Math.abs(ms) >= 60_000 ? "a minute" : "a second"}` })));
    const set = h("div.t-set", entry(f.fmt || "m:ss", (v) => run({ do: "set", field: f.key, value: v }), { k: `set-${t.id}` }),
      button("Reset", () => run({ do: "reset", field: f.key }), { title: "Back to the period length" }));
    el.append(value, go, adj, set);
    return { update: (s) => {
      value.textContent = val(s);
      const running = s?.values?.[`${f.key}.running`] === "1";
      go.textContent = running ? "Stop" : "Start";
      go.className = `btn btn-big t-go ${running ? "btn-danger" : "btn-accent"}`;
      runChip.replaceChildren(running ? chip("Running", "accent") : chip("Stopped", "muted"));
      const live = s?.live?.includes(f.key);
      go.disabled = !!live;
      go.title = live ? "Live data is running this clock" : running ? "Stop the clock" : "Start the clock";
      refreshChip(s);
    } };
  }

  if (f.type === "choice") {
    const value = h("div.t-value", "");
    const opts = f.options || [];
    let row;
    if (opts.length <= 6) {
      row = h("div.t-opts", opts.map((o, i) => button(o || "—", () => run({ do: "set", field: f.key, value: i }), { title: `Set ${label} to ${o}` })));
      el.append(row);
    } else {
      el.append(value, h("div.t-row", button("◀ Previous", () => run({ do: "prev", field: f.key })), button("Next ▶", () => run({ do: "next", field: f.key }))));
    }
    return { update: (s) => {
      value.textContent = val(s);
      if (row) {
        const idx = Number(s?.values?.[`${f.key}.index`] ?? 0) - 1;
        [...row.children].forEach((b, i) => b.setAttribute("aria-pressed", String(i === idx)));
      }
      refreshChip(s);
    } };
  }

  if (f.type === "toggle") {
    const sw = button("Off", () => run({ do: "toggle", field: f.key }), { big: true, cls: "t-switch" });
    el.append(sw);
    return { update: (s) => {
      const on = s?.raw?.[f.key] === true;
      sw.textContent = on ? `On${f.on_text && f.on_text !== "1" ? ` · ${f.on_text}` : ""}` : "Off";
      sw.classList.toggle("on", on);
      sw.setAttribute("aria-pressed", String(on));
      refreshChip(s);
    } };
  }

  if (f.type === "text") {
    const box = h("input.input", { "data-k": `text-${t.id}`, spellcheck: false, placeholder: "Type and press Enter" });
    const send = () => run({ do: "set", field: f.key, value: box.value });
    box.addEventListener("keydown", (e) => { if (e.key === "Enter") send(); if (e.key === "Escape") { box.value = box.dataset.v ?? ""; box.blur(); } });
    box.addEventListener("blur", () => { if (box.value !== (box.dataset.v ?? "")) send(); });
    el.append(h("div.t-fill", h("div.t-set", box, button("Clear", () => { box.value = ""; send(); }))));
    return { update: (s) => {
      const v = s?.raw?.[f.key] ?? "";
      if (document.activeElement !== box) box.value = v;
      box.dataset.v = v;
      refreshChip(s);
    } };
  }

  if (f.type === "image") {
    const thumb = h("div.t-thumb", "No picture");
    el.append(thumb, h("div.t-row",
      button("Choose…", async () => {
        const { call } = await import("./api.js");
        const r = await attempt(() => call("/api/pick", { kind: "image" }));
        if (r?.path) run({ do: "set", field: f.key, value: r.path });
      }),
      button("Clear", () => run({ do: "set", field: f.key, value: "" }))));
    return { update: (s) => {
      const p = s?.values?.[f.key] ?? "";
      if (thumb.dataset.p === p) return;
      thumb.dataset.p = p;
      thumb.replaceChildren(p ? h("img", { src: fileUrl(p), alt: "", onerror: (e) => e.target.replaceWith("Missing picture") }) : "No picture");
      thumb.title = p;
    } };
  }

  if (f.type === "penalties") {
    const list = h("div.t-list", { "data-scroll": `pen-${t.id}` });
    const player = h("input.input", { placeholder: "Player, e.g. #12", "data-k": `pp-${t.id}`, spellcheck: false });
    const time = h("input.input", { value: "2:00", "data-k": `pt-${t.id}`, style: { maxWidth: "70px" } });
    const add = (tm) => run({ do: "penalty.add", field: f.key, player: player.value.trim(), time: tm || time.value }).then(() => { player.value = ""; });
    player.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
    el.append(list, h("div.t-row", player, time, button("2:00", () => add("2:00")), button("5:00", () => add("5:00")), button("Add", () => add(), { role: "accent" })));
    return { update: (s) => {
      const n = Number(s?.values?.[`${f.key}.count`] ?? 0);
      const rows = [];
      const entries = s ? (store.project.fields.find((x) => x.key === f.key)?.entries ?? []) : [];
      for (let i = 0; i < Math.max(n, 0); i++) {
        const slot = i < f.slots;
        const pl = slot ? s.values[`${f.key}.${i + 1}.player`] : entries[i]?.player ?? "";
        const tm = slot ? s.values[`${f.key}.${i + 1}.time`] : "waiting";
        rows.push(h(`div.t-pen${slot ? "" : ".waiting"}`, h("span.muted.small", String(i + 1)), h("span", pl || "—"), h("b", tm),
          button("Remove", () => run({ do: "penalty.remove", field: f.key, index: i + 1 }), { role: "ghost", cls: "btn-sm" })));
      }
      list.replaceChildren(...(rows.length ? rows : [h("span.hint", "No penalties. They count down only while the game clock runs.")]));
    } };
  }
  return { update: () => {} };
}
