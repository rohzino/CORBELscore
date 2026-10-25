// The Library: the left panel in Edit mode. What you can put on the layout
// (fields and buttons), where data comes from (live data), and where it goes
// (outputs). Drag an item onto the grid, or select it and use "Add to page".

import { call, edit, store } from "./api.js";
import { button, chip, h, kbd, rerender } from "./dom.js";
import { defaultSize } from "/core/layout.js";
import { TYPE_NAMES, normaliseKey } from "/core/fields.js";
import { attempt, check, confirmDialog, dialog, menu, numberInput, remember, select, textInput, toast, ui } from "./ui.js";

const SECTIONS = [["fields", "Fields"], ["buttons", "Shortcuts"], ["live", "Live data"], ["outputs", "Outputs"]];

// ambient: a refresh nobody asked for (status, live keys arriving); it waits while someone types.
export function renderLibrary(el, ctx, ambient = false) {
  if (!store.project) return;
  rerender(el, () => h("div", { style: { display: "contents" } },
    h("div.side-tabs", { role: "tablist" }, SECTIONS.map(([id, label]) => h("button", { role: "tab", "aria-selected": String(ui.side === id),
      onclick: () => { ui.side = id; remember(); renderLibrary(el, ctx); } }, label))),
    h("div.side-body", { "data-scroll": `lib-${ui.side}` }, ({ fields, buttons, live: liveData, outputs })[ui.side](ctx, (amb = false) => renderLibrary(el, ctx, amb)))), { ambient });
}

function startDrag(e, item) {
  e.dataTransfer.setData("application/x-telescore", JSON.stringify(item));
  e.dataTransfer.effectAllowed = "copy";
  sessionStorage.setItem("ts-drag", JSON.stringify(item));
}

// ---- fields -------------------------------------------------------------------------------
function fields(ctx) {
  const p = store.project;
  const snap = store.snapshot;
  const onPage = new Set(ctx.page()?.tiles.filter((t) => t.kind === "field").map((t) => t.field));
  const addBtn = button("+ New field", (e) => menu(e.currentTarget, Object.entries(TYPE_NAMES).map(([type, name]) => ({ label: name, run: () => newField(type, ctx) }))), { role: "accent" });
  const list = h("div.list", p.fields.map((f) => {
    const sel = ui.sel?.kind === "field" && ui.sel.id === f.key;
    const item = h(`div.item${sel ? ".sel" : ""}`, { tabindex: 0, draggable: true, title: `${f.key} · drag onto the page`,
      onclick: () => ctx.select({ kind: "field", id: f.key }), onkeydown: (e) => e.key === "Enter" && ctx.select({ kind: "field", id: f.key }),
      ondragstart: (e) => startDrag(e, { kind: "field", field: f.key, size: defaultSize("field", f.type, f) }) },
      h("span.grip", "⋮⋮"),
      h("div.grow", h("div.name", f.label), h("div.sub", `${f.key} · ${snap?.values?.[f.key] ?? ""}`)),
      onPage.has(f.key) ? h("span.dot.dot-hi", { title: "On this page" }) : null,
      h("span.typ", TYPE_NAMES[f.type]));
    return item;
  }));
  return [h("div.row", addBtn, h("span.spacer"), h("span.hint", `${p.fields.length} field${p.fields.length === 1 ? "" : "s"}`)),
    h("p.hint", "Fields hold the values: scores, clocks, names. Drag one onto the page to get its control. ● marks fields on this page."),
    list];
}

async function newField(type, ctx) {
  const p = store.project;
  const label = await (await import("./ui.js")).ask(`New ${TYPE_NAMES[type].toLowerCase()} field`, "Name", "");
  if (!label) return;
  let key = normaliseKey(label.replace(/\s+/g, "_"));
  const taken = new Set(p.fields.map((f) => f.key));
  for (let n = 2; taken.has(key); n++) key = `${normaliseKey(label)}_${n}`;
  const field = { key, type, label };
  if (type === "choice") field.options = ["1st", "2nd", "3rd", "4th"];
  if (type === "clock") Object.assign(field, { countdown: true, initial_ms: 600_000, value_ms: 600_000, fmt: "m:ss" });
  const ok = await attempt(() => edit({ op: "field.add", field }, `Add field ${label}`));
  if (ok) ctx.select({ kind: "field", id: key });
}

// ---- buttons ------------------------------------------------------------------------------
function buttons(ctx) {
  const p = store.project;
  const onPage = new Set(p.layout.pages.flatMap((pg) => pg.tiles.filter((t) => t.kind === "button").map((t) => t.button)));
  return [
    h("div.row", button("+ New shortcut", () => newButton(ctx), { role: "accent" }), h("span.spacer"), h("span.hint", `${p.buttons.length} shortcut${p.buttons.length === 1 ? "" : "s"}`)),
    h("p.hint", "A shortcut runs one or more steps as one undo step. Put it on a page as a button, give it a key, or both. Shortcuts not on any page still work by their key."),
    h("div.list", p.buttons.map((b) => {
      const sel = ui.sel?.kind === "button" && ui.sel.id === b.id;
      return h(`div.item${sel ? ".sel" : ""}`, { tabindex: 0, draggable: true, title: "Drag onto the page",
        onclick: () => ctx.select({ kind: "button", id: b.id }), onkeydown: (e) => e.key === "Enter" && ctx.select({ kind: "button", id: b.id }),
        ondragstart: (e) => startDrag(e, { kind: "button", button: b.id, size: defaultSize("button") }) },
        h("span.grip", "⋮⋮"), h("span.name", b.label), b.hotkey ? kbd(b.hotkey) : null,
        onPage.has(b.id) ? null : h("span.typ", { title: "Not on any page: works by its key only" }, "Key only"));
    })),
  ];
}

async function newButton(ctx) {
  const p = store.project;
  const first = p.fields.find((f) => ["counter", "clock", "choice"].includes(f.type))?.key;   // a field "Add" can work on
  const b = { id: crypto.randomUUID().replace(/-/g, "").slice(0, 10), label: "New shortcut", role: "neutral", hotkey: "",
    action: first ? { do: "add", field: first, amount: 1 } : { do: "undo" } };
  const ok = await attempt(() => edit({ op: "button.put", button: b }, "Add shortcut"));
  if (ok) ctx.select({ kind: "button", id: b.id });
}

// ---- live data --------------------------------------------------------------------------------
const KINDS = [["", "Off"], ["mqtt-cloud", "Sportzcast cloud (MQTT)"], ["mqtt-local", "Sportzcast device on this network (MQTT)"],
  ["tcp", "Sportzcast socket (legacy)"], ["livexml", "LiveXML or XML file / URL"], ["json", "JSON file / URL"]];
const SHOW = { "": [], "mqtt-cloud": ["email", "token", "bot", "stale"], "mqtt-local": ["bot", "host", "port", "stale"],
  tcp: ["email", "token", "bot", "dtype", "stale"], livexml: ["path", "poll", "stale"], json: ["path", "poll", "stale"] };
const HELP = { "": "No live data. Fields keep their own values.",
  "mqtt-cloud": "Connects to score.sportzcast.net:8883 over TLS and reads bot/<bot>/json. Needs an active Sportzcast account, licence and the bot assigned to you.",
  "mqtt-local": "Reads a ScoreConnect III or Scorelink+ on this network (MQTT port 1883, no login). Turn on the device's local MQTT server first.",
  tcp: "The older socket interface. Sportzcast recommends MQTT for new setups.",
  livexml: "Watches the XML file written by Sportzcast LiveXML (or any XML file or web address) and reads it when it changes. A file caught half-written is skipped.",
  json: "Watches a JSON file or web address and reads it when it changes." };

let liveKeys = {};
let liveKeysAt = 0;
function liveData(ctx, redraw) {
  const p = store.project;
  const s = p.source;
  const st = store.status.live || { state: "off" };
  const kind = s.kind === "mqtt" ? (s.cloud ? "mqtt-cloud" : "mqtt-local") : s.kind;
  const show = new Set(SHOW[kind] ?? []);
  const put = (changes, label = "Live data settings") => attempt(() => edit({ op: "source.put", source: changes }, label));
  const setKind = (k) => put(k === "mqtt-cloud" ? { kind: "mqtt", cloud: true } : k === "mqtt-local" ? { kind: "mqtt", cloud: false } : k === "tcp" ? { kind: "tcp" } : { kind: k });
  const rows = [];
  const row = (id, label, control, hint) => { if (show.has(id)) rows.push(h("label", label), control, hint ? h("div.hint", hint) : null); };
  row("email", "E-mail", textInput(s.username, (v) => put({ username: v.trim() }), { k: "live-email", placeholder: "The e-mail your bot is assigned to" }));
  const tok = h("input.input", { type: "password", placeholder: store.settings.has_token ? "Saved · type to replace" : "Access token", "data-k": "live-token" });
  tok.addEventListener("change", () => attempt(() => call("/api/token", { token: tok.value }), "Token saved on this computer."));
  row("token", "Token", tok, "Kept in this computer's settings, never in the project file.");
  row("bot", "Bot number", numberInput(s.bot, (v) => put({ bot: v }), { k: "live-bot", min: 0, max: 999999 }));
  row("host", "Address", textInput(s.host, (v) => put({ host: v.trim() }), { k: "live-host", placeholder: "Device address, e.g. 192.168.1.40" }));
  row("port", "Port", numberInput(s.port, (v) => put({ port: v }), { k: "live-port", min: 0, max: 65535, title: "0 = the standard port" }), "0 uses the standard port.");
  row("dtype", "Data", select([["json", "JSON"], ["xml", "XML"]], s.data_type, (v) => put({ data_type: v }), { k: "live-dtype" }));
  row("path", "File or URL", h("div.row", textInput(s.path, (v) => put({ path: v.trim() }), { k: "live-path", placeholder: "C:\\LiveXML\\scoreboard.xml or http://…" }),
    store.state.host.dialogs ? button("Browse…", async () => { const r = await attempt(() => call("/api/pick", { kind: "data" })); if (r?.path) put({ path: r.path }); }) : null));
  row("poll", "Check every", numberInput(s.poll_ms, (v) => put({ poll_ms: v }), { k: "live-poll", min: 50, max: 10000, suffix: "ms" }));
  row("stale", "Warn after", numberInput(s.stale_s, (v) => put({ stale_s: v }), { k: "live-stale", min: 1, max: 3600, suffix: "s of silence" }));
  const word = { live: ["Live", "accent"], connecting: ["Connecting", "user"], stale: ["Silent", "user"], error: ["Failing", "alert"] }[st.state] ?? ["Off", "muted"];

  // keys and bindings
  const keysBox = h("div.col");
  const now = Date.now();
  if (st.state !== "off" && now - liveKeysAt > 900) {
    liveKeysAt = now;
    call("/api/live-keys").then((r) => { const before = Object.keys(liveKeys).length; liveKeys = r.keys; if (Object.keys(liveKeys).length !== before) redraw(true); }).catch(() => {});
  }
  const bound = Object.fromEntries(p.fields.filter((f) => f.source).map((f) => [f.source, f]));
  const keys = Object.keys(liveKeys).sort();
  if (!keys.length) keysBox.append(h("p.hint", st.state === "off" ? "Connect a source to see the keys it sends." : "No keys yet. They appear when data arrives."));
  for (const k of keys.slice(0, 400)) {
    const f = bound[k];
    const bind = select([["", "—"], ...p.fields.map((x) => [x.key, x.label])], f?.key ?? "", async (fk) => {
      const ops = [];
      if (f) ops.push({ op: "field.update", key: f.key, changes: { source: "" } });
      if (fk) ops.push({ op: "field.update", key: fk, changes: { source: k } });
      await attempt(() => edit(ops, `Bind ${k}`));
    }, { k: `bind-${k}`, title: "The field that follows this key" });
    Object.assign(bind.style, { flex: "0 0 46%", width: "46%" });   // leave room for the key's name
    keysBox.append(h("div.item", { title: `${k} = ${liveKeys[k]}` },
      h("div.grow", h("div.name.mono", k), h("div.sub", String(liveKeys[k] ?? ""))), bind));
  }
  return [
    h("div.section-title", "Connection"),
    h("div.form", h("label", "Source"), select(KINDS, kind, setKind, { k: "live-kind" }), ...rows),
    h("p.hint", HELP[kind] ?? ""),
    h("div.col", { style: { margin: "6px 0", gap: "6px" }, "data-ambient": "live-status" },
      h("div.row", h(`span.dot${st.state === "live" ? ".dot-ok" : ["connecting", "stale"].includes(st.state) ? ".dot-busy" : st.state === "error" ? ".dot-error" : ""}`),
        chip(word[0], word[1]), h("span.spacer"),
        st.connected ? [button("Reconnect", () => attempt(() => call("/api/connect")), { role: st.changed ? "accent" : "", title: "Connect again with the settings above", cls: "btn-sm" }),
          button("Disconnect", () => attempt(() => call("/api/disconnect")), { title: "Stop live data; bound fields show their own values again", cls: "btn-sm" })]
          : button("Connect", () => attempt(() => call("/api/connect")), { role: "accent", disabled: !kind, k: "live-connect" })),
      h("p.hint", { style: { margin: 0, color: st.changed ? "var(--user-text, var(--user))" : "" } },
        st.connected ? (st.changed ? "Settings changed. Reconnect to use them." : st.detail || "") : kind ? "Not connected. Set it up, then press Connect." : "")),
    h("div.section-title", { style: { marginTop: "14px" } }, "Keys and bindings"),
    h("p.hint", "Every key the source sends. Bind one to a field and the field follows it; rules and overrides still apply."),
    keys.length ? button("Suggest bindings", async () => {
      const r = await attempt(() => call("/api/suggest"));
      const pairs = Object.entries(r?.map ?? {});
      if (!pairs.length) return toast("No suggestions: the keys do not match this project's fields by name.");
      const ok = await confirmDialog("Suggest bindings", pairs.map(([fk, sk]) => `${sk} → ${fk}`).join("\n"), "Bind them");
      if (ok) attempt(() => edit(pairs.map(([fk, sk]) => ({ op: "field.update", key: fk, changes: { source: sk } })), "Suggested bindings"));
    }, { role: "accent" }) : null,
    keys.length ? button("Copy all keys", () => {
      const text = keys.map((k) => `${k} = ${liveKeys[k]}`).join("\n");
      navigator.clipboard.writeText(text).then(() => toast(`Copied ${keys.length} keys and their values.`), () => toast("Could not copy.", true));
    }, { title: "Every key and its current value, as text, e.g. to paste into a support request" }) : null,
    keysBox,
  ];
}

// ---- outputs -------------------------------------------------------------------------------------
function outputs(ctx) {
  const p = store.project;
  const o = p.outputs;
  const st = store.status;
  const put = (changes, label = "Output settings") => attempt(() => edit({ op: "outputs.put", outputs: changes }, label));
  const fileState = (name) => {
    const f = st.files?.[name] ?? { state: "off" };
    const [w, k] = { ok: ["Live", "accent"], error: ["Failing", "alert"], busy: ["Starting", "user"] }[f.state] ?? ["Off", "muted"];
    return h("div.row.small", { "data-ambient": `file-${name}` }, chip(w, k), h("span.hint.grow", { title: f.detail }, f.state === "error" ? f.detail : f.last_write ? `written ${ago(f.last_write)}` : ""));
  };
  const web = st.web || {};
  const urls = web.running ? [
    ...p.boards.map((b) => [b.name, `${web.url.replace(/\/$/, "")}/board/${b.id}`, `${b.width} × ${b.height}`]),
    ["JSON", `${web.url}state.json`, ""], ["XML nested", `${web.url}telescore.xml`, ""], ["vMix XML", `${web.url}vmix.xml`, "XPath //row"], ["XML fields", `${web.url}fields.xml`, ""],
  ] : [];
  const copy = (u) => navigator.clipboard.writeText(u).then(() => toast("Copied. In OBS add a Browser source with this address."), () => toast(u));
  return [
    h("div.section-title", "Files"),
    h("div.form",
      h("label", "Folder"), h("div.row", textInput(o.folder, (v) => put({ folder: v.trim() }), { k: "out-folder", placeholder: p.outputFolder }),
        store.state.host.dialogs ? button("Choose…", async () => { const r = await attempt(() => call("/api/pick", { kind: "folder" })); if (r?.path) put({ folder: r.path }); }) : null),
      h("div.hint", { style: { gridColumn: "1 / -1" }, "data-ambient": "out-folder-now" }, `Now writing to ${st.folder || p.outputFolder}`)),
    h("div.col", { style: { marginTop: "8px" } },
      check("Text files: one per value, for OBS Text sources", o.text_enabled, (v) => put({ text_enabled: v }), { k: "out-text" }), fileState("text"),
      check("XML", o.xml_enabled, (v) => put({ xml_enabled: v }), { k: "out-xml" }),
      h("div.col", { style: { paddingLeft: "24px" } }, [["nested", "telescore.xml · Ross XPression, Chyron"], ["flat", "vmix.xml · vMix data source"], ["fields", "fields.xml · look up by key"]].map(([prof, label]) =>
        check(label, o.xml_profiles.includes(prof), (v) => put({ xml_profiles: v ? [...new Set([...o.xml_profiles, prof])] : o.xml_profiles.filter((x) => x !== prof) }), { k: `out-${prof}` }))),
      fileState("xml"),
      check("JSON (state.json)", o.json_enabled, (v) => put({ json_enabled: v }), { k: "out-json" }), fileState("json"),
      store.state.host.dialogs ? button("Open folder", () => attempt(() => call("/api/open", { path: st.folder }))) : null),
    h("p.hint", "Files are replaced in one step, so a graphics system never reads half a file. XML and JSON are rewritten at most 20 times a second; text files only when their value changes."),
    h("div.section-title", { style: { marginTop: "12px" } }, "Browser sources and remote control"),
    h("div.col",
      check("Run the web server", o.http_enabled, (v) => put({ http_enabled: v }), { k: "out-http" }),
      h("div.form", h("label", "Port"), numberInput(o.http_port, (v) => put({ http_port: v }), { k: "out-port", min: 1024, max: 65535 })),
      check("Allow other computers and phones on this network", o.http_lan, (v) => put({ http_lan: v }), { k: "out-lan" }),
      h("div.form", h("label", "Token"), h("div.row", textInput(o.http_token, (v) => put({ http_token: v.trim() }), { k: "out-token", placeholder: "None: anyone who can reach it can press" }),
        button("Make one", () => put({ http_token: crypto.randomUUID().replace(/-/g, "").slice(0, 16) })))),
      h("div.row.small", { "data-ambient": "web-status" }, chip(web.running ? "Live" : web.error ? "Failing" : "Off", web.running ? "accent" : web.error ? "alert" : "muted"),
        h("span.hint", web.running ? `${web.lan ? "this network" : "this computer only"} · port ${web.port} · ${web.clients} connected` : web.error || ""))),
    urls.length ? h("div.list", { style: { marginTop: "8px" } }, urls.map(([name, url, sub]) => h("div.item", { title: url },
      h("div.grow", h("div.name", name), h("div.sub.mono", url)), sub ? h("span.typ", sub) : null, button("Copy", () => copy(url), { cls: "btn-sm" })))) : null,
    h("div.section-title", { style: { marginTop: "12px" } }, "Pictures"),
    h("p.hint", store.state.host.png ? "Write a PNG of a board whenever it changes, for systems that load pictures." : "PNG pictures of boards need the TeleScore app window."),
    h("div.col", p.boards.map((b) => check(b.name, o.image_boards.includes(b.id), (v) => put({ image_boards: v ? [...o.image_boards, b.id] : o.image_boards.filter((x) => x !== b.id) }), { k: `png-${b.id}` }))),
  ];
}

function ago(t) {
  const s = Math.max(0, Date.now() / 1000 - t);
  return s < 2 ? "just now" : s < 60 ? `${Math.round(s)} s ago` : `${Math.round(s / 60)} min ago`;
}
