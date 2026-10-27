// HTML pages served to browsers: the board page (OBS/vMix browser source) and
// the index of sources and feeds.

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
// JSON inside a <script>: no way to close the tag or open a comment.
const scriptJson = (o) => JSON.stringify(o).replace(/</g, "\\u003c").replace(/>/g, "\\u003e").replace(/&/g, "\\u0026").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");

import { fontFaceCss } from "../core/fonts.js";

const FONT_FACE = fontFaceCss("/fonts/");

// boards: every board in the project, so a board placed inside this one draws.
export function overlayHtml(board, bg = "transparent", animations = [], boards = []) {
  const BG = { transparent: "transparent", green: "#00b140", blue: "#0047bb", black: "#000000", magenta: "#ff00ff" };
  const back = BG[bg] ?? (/^#[0-9a-fA-F]{3,8}$/.test(bg) ? bg : "transparent");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(board.name)} · CORBELscore</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>${FONT_FACE}
html,body{margin:0;height:100%;overflow:hidden;background:${back}}
#host{position:fixed;inset:0}
#offline{position:fixed;left:8px;bottom:8px;font:600 12px "Red Hat Text",Arial,sans-serif;color:#fff;background:#b3261e;padding:3px 8px;border-radius:3px;display:none}
body.debug #offline{display:block}
</style></head><body><div id="host"></div><div id="offline">CORBELscore is not reachable</div>
<script type="module">
import { BoardView } from "/render/board-view.js";
const BOARD_ID = ${scriptJson(board.id)};
let board = ${scriptJson(board)}, anims = ${scriptJson(animations)}, boards = ${scriptJson(boards)};
if (new URLSearchParams(location.search).has("debug")) document.body.classList.add("debug");
const view = new BoardView(document.getElementById("host"));
view.setBoards(boards);
view.setBoard(board, anims);
let values = {}, fx = {}, rev = null;
const offline = (on) => { document.getElementById("offline").style.display = on ? "block" : ""; };
async function reload() {
  try { const r = await fetch("/board/" + encodeURIComponent(BOARD_ID) + ".json", { cache: "no-store" }); if (!r.ok) return;
    const d = await r.json(); board = d.board; anims = d.animations; view.setBoards(d.boards || []); view.setBoard(board, anims); view.setValues(values, fx); } catch {}
}
function connect() {
  const es = new EventSource("/events");
  es.addEventListener("full", (ev) => { values = JSON.parse(ev.data); view.setValues(values, fx); offline(false); });
  es.addEventListener("diff", (ev) => { const d = JSON.parse(ev.data); for (const k in d) { if (d[k] === null) delete values[k]; else values[k] = d[k]; } view.setValues(values, fx); });
  es.addEventListener("fx", (ev) => { fx = JSON.parse(ev.data) || {}; view.setValues(values, fx); });
  // The board was edited in CORBELscore: redraw it without a refresh.
  es.addEventListener("boards", (ev) => { const r = JSON.parse(ev.data); if (rev !== null && r !== rev) reload(); rev = r; });
  es.onerror = () => { offline(true); es.close(); setTimeout(connect, 2000); };
}
connect();
if (document.fonts) document.fonts.ready.then(() => view.refit()).catch(() => {});
</script></body></html>`;
}

export function indexHtml(app, host) {
  const base = `http://${host}`;
  const rows = app.project.boards.map((b) => `<tr><td>${esc(b.name)}</td><td><a href="/board/${encodeURIComponent(b.id)}">${esc(base)}/board/${esc(b.id)}</a></td><td>${b.width} × ${b.height}</td></tr>`).join("");
  const feeds = [["JSON", "/state.json", "Anything"], ["XML, nested", "/corbelscore.xml", "Ross XPression, Chyron"], ["XML, flat", "/vmix.xml", "vMix data source, XPath //row"],
    ["XML, key/value", "/fields.xml", "//field[@key='home.score']"]].map(([l, p, u]) => `<tr><td>${l}</td><td><a href="${p}">${esc(base)}${p}</a></td><td>${esc(u)}</td></tr>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CORBELscore</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>${FONT_FACE}
:root{--bg:#0c0d0d;--panel:#151717;--ink:#f5f5f1;--muted:#a9aaa4;--rule:#2e3232;--hi:#4cc9d6;--accent-text:#8fdde5}
body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.45 "Red Hat Text",system-ui,sans-serif;font-variant-numeric:tabular-nums}
header{background:#080909;padding:16px;display:flex;align-items:center;gap:14px}header img{height:20px;opacity:.91}header span{color:var(--muted)}
main{padding:16px;max-width:980px}h2{font:700 18px "Red Hat Display",sans-serif;display:inline-block;box-shadow:inset 0 -3px 0 var(--hi);margin:18px 0 10px;padding-bottom:2px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--rule);border-radius:6px}td{padding:6px 12px;border-top:1px solid var(--rule)}a{color:var(--accent-text)}
code{font:12.5px "Red Hat Mono",ui-monospace,Consolas,monospace;background:#1e2121;padding:1px 4px;border-radius:3px}p{color:var(--muted)}
</style></head><body><header><img src="/brand/wordmark.svg" alt="CORBELscore"><span>${esc(app.project.name)}</span></header><main>
<h2>Browser sources</h2><table>${rows || '<tr><td colspan="3">No boards yet.</td></tr>'}</table>
<p>In OBS add a Browser source with the board's URL and its width and height. Add <code>?bg=green</code> for a keyer that needs chroma green.</p>
<h2>Data feeds</h2><table>${feeds}</table>
<h2>Remote control</h2><p>Send an action with a GET or POST to <code>${esc(base)}/api/action</code>, for example
<code>${esc(base)}/api/action?do=add&amp;field=home.score&amp;amount=1</code> or <code>?do=toggle&amp;field=clock.game</code>. Field keys are listed at <a href="/api/fields">/api/fields</a>.</p>
</main></body></html>`;
}
