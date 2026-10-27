// The service as other programs see it: files on disk, the public web server
// (browser sources, feeds, remote control), the studio API's guard, and
// design edits that undo without touching the game. Plus the layout maths.

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { App } from "../app/service/app.js";
import { makeProject, PRESETS } from "../app/core/presets.js";
import { parseXml } from "../app/service/xml.js";
import { overlaps, findSpot, settle, autoLayout, COLUMNS } from "../app/core/layout.js";
import { textFilename } from "../app/core/formats.js";

let app, dir, pub, studio;
const PORT = 20000 + Math.floor(Math.random() * 20000);

before(async () => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "ts-svc-"));
  app = new App({ dataDir: path.join(dir, "data") });
  await app.start();
  const p = makeProject("Basketball");
  p.outputs.folder = path.join(dir, "out");
  p.outputs.http_port = PORT;
  p.outputs.http_token = "s3cret";
  await app.load(p);
  pub = (q) => `http://127.0.0.1:${PORT}${q}`;
  studio = (q) => app.studio.url(q);
});

after(async () => {
  await app.stop();
  fs.rmSync(dir, { recursive: true, force: true });
});

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 3000) {
  const end = Date.now() + ms;
  for (;;) { try { const v = await fn(); if (v) return v; } catch { /* not yet */ } if (Date.now() > end) throw new Error("timed out"); await wait(40); }
}

test("files: text, XML and JSON are written and follow the score", async () => {
  const txt = path.join(dir, "out", "text", "away.score.txt");
  await until(() => fs.existsSync(txt));
  assert.equal(fs.readFileSync(txt, "utf8"), "0");
  app.project.engine.perform({ do: "add", field: "away.score", amount: 2 });
  await until(() => fs.readFileSync(txt, "utf8") === "2");
  const nested = parseXml(fs.readFileSync(path.join(dir, "out", "corbelscore.xml"), "utf8"));
  assert.ok(nested, "corbelscore.xml parses");
  // XML and JSON are rewritten at most 20 times a second, so they may land a moment after the text file.
  const json = path.join(dir, "out", "state.json");
  await until(() => String(JSON.parse(fs.readFileSync(json, "utf8")).values["away.score"]) === "2");
});

test("files: names are safe on Windows", () => {
  assert.equal(textFilename("con"), "_con.txt");
  assert.equal(textFilename("a/b:c"), "a_b_c.txt");
});

test("web: feeds, boards and the field list", async () => {
  const s = await (await fetch(pub("/state.json"))).json();
  assert.ok("clock.game" in s.values);
  for (const f of ["/corbelscore.xml", "/vmix.xml", "/fields.xml"]) {
    const r = await fetch(pub(f));
    assert.equal(r.status, 200, f);
    assert.ok(parseXml(await r.text()), `${f} parses`);
  }
  const board = app.project.boards[0];
  const html = await (await fetch(pub(`/board/${board.id}`))).text();
  assert.match(html, /<html/i);
  assert.equal((await fetch(pub("/board/nope"))).status, 404);
  const fields = await (await fetch(pub("/api/fields"))).json();
  assert.ok(fields.some((f) => f.key === "home.score" && f.type === "counter"));
});

test("web: remote control needs the token and scores once", async () => {
  const before = Number(app.project.engine.snapshot().values["home.score"]);
  assert.equal((await fetch(pub("/api/action?do=add&field=home.score&amount=3"))).status, 403);
  const r = await fetch(pub("/api/action?do=add&field=home.score&amount=3&token=s3cret"));
  assert.equal(r.status, 200);
  assert.equal(Number(app.project.engine.snapshot().values["home.score"]), before + 3);
  const bad = await fetch(pub("/api/action?do=add&field=home.score&amount=x&token=s3cret"));
  assert.equal(bad.status, 400);
  const post = await fetch(pub("/api/action"), { method: "POST", headers: { "X-TeleScore-Token": "s3cret", "Content-Type": "application/json" },
    body: JSON.stringify({ do: "set", field: "home.score", value: before }) });
  assert.equal(post.status, 200);
  assert.equal(Number(app.project.engine.snapshot().values["home.score"]), before);
});

test("studio: the API needs the key and this computer's address", async () => {
  const post = (q, headers = {}) => fetch(studio(q), { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: "{}" });
  assert.equal((await post("/api/state")).status === 200, false, "no key, no answer");
  const ok = await post("/api/state", { "X-CORBELscore-Key": app.key });
  assert.equal(ok.status, 200);
  // A web page on another site that resolves to 127.0.0.1 (DNS rebinding) sends its own Host.
  const http = await import("node:http");
  const status = await new Promise((resolve) => {
    const u = new URL(studio("/api/state"));
    const req = http.request({ host: "127.0.0.1", port: u.port, path: u.pathname, method: "POST",
      headers: { Host: "evil.example:80", "X-CORBELscore-Key": app.key, "Content-Type": "application/json" } }, (res) => { res.resume(); resolve(res.statusCode); });
    req.end("{}");
  });
  assert.notEqual(status, 200);
});

test("studio: design undo restores the layout and never the score", async () => {
  const before = structuredClone(app.project.layout);
  app.project.engine.perform({ do: "set", field: "away.score", value: 7 });
  const page = structuredClone(before.pages[0]);
  page.tiles[0].y += 3;
  await app.edit([{ op: "layout.put", layout: { ...before, pages: [page, ...before.pages.slice(1)] } }], "Move control");
  assert.notDeepEqual(app.project.layout, before);
  app.project.engine.perform({ do: "add", field: "away.score", amount: 1 });
  await app.undoEdit();
  assert.deepEqual(app.project.layout, before);
  assert.equal(String(app.project.engine.snapshot().values["away.score"]), "8");
  await app.redoEdit();
  assert.notDeepEqual(app.project.layout, before);
});

test("layout: every template's pages fit 24 columns with no overlaps", () => {
  for (const name of Object.keys(PRESETS)) {
    const p = makeProject(name);
    for (const pg of p.layout.pages) {
      for (const t of pg.tiles) assert.ok(t.x >= 0 && t.x + t.w <= COLUMNS && t.y >= 0, `${name}/${pg.name}: ${JSON.stringify(t)}`);
      pg.tiles.forEach((a, i) => pg.tiles.slice(i + 1).forEach((b) => assert.ok(!overlaps(a, b), `${name}/${pg.name}: ${a.id} overlaps ${b.id}`)));
    }
  }
});

test("layout: settle pushes others down and keeps the moved one", () => {
  const tiles = [{ id: "a", x: 0, y: 0, w: 8, h: 2 }, { id: "b", x: 0, y: 2, w: 8, h: 2 }, { id: "c", x: 0, y: 1, w: 8, h: 2 }];
  const out = settle(tiles, ["c"]);
  const c = out.find((t) => t.id === "c");
  assert.deepEqual([c.x, c.y], [0, 1]);
  out.forEach((a, i) => out.slice(i + 1).forEach((b) => assert.ok(!overlaps(a, b))));
  const spot = findSpot(out, 24, 1);
  assert.ok(out.every((t) => !overlaps(t, { ...spot, w: 24, h: 1 })));
});

test("layout: autoLayout places every field once", () => {
  const p = makeProject("Hockey");
  const l = autoLayout(p.engine.fieldsToList(), p.buttons);
  const keys = l.pages.flatMap((pg) => pg.tiles.filter((t) => t.kind === "field").map((t) => t.field));
  assert.equal(new Set(keys).size, keys.length, "no field twice");
  assert.deepEqual(new Set(keys), new Set(p.engine.fieldsToList().map((f) => f.key)), "and none left out");
});
