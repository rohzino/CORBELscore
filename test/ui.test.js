// End-to-end check of the studio window in a real browser: start page,
// scoring in Locked mode, Edit mode, and that design undo never rewinds a score.
// Needs Playwright with Chromium; skipped when it is not installed.

import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { App } from "../app/service/app.js";

let chromium = null;
try { ({ chromium } = createRequire(path.join(process.cwd(), "x"))("playwright")); } catch { /* not installed */ }
const skip = chromium ? false : "Playwright is not installed";

let app, browser, page, dataDir;
const errors = [];

before(async () => {
  if (skip) return;
  dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "ts-ui-"));
  app = new App({ dataDir });
  const url = await app.start();
  browser = await chromium.launch();
  page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(url);
});

after(async () => {
  await browser?.close();
  await app?.stop();
  if (dataDir) fs.rmSync(dataDir, { recursive: true, force: true });
});

const tile = (label) => page.locator(".tile", { has: page.getByText(label, { exact: true }) }).first();

test("start page lists the templates and opens one with its values", { skip }, async () => {
  await page.getByRole("button", { name: /Basketball/ }).first().click();
  await page.getByText("10:00", { exact: true }).waitFor();
  assert.match(await tile("Away score").innerText(), /^\s*AWAY SCORE\s*0/i);
});

test("Locked mode: a score button adds to the score", { skip }, async () => {
  await tile("Away score").getByRole("button", { name: "+3" }).click();
  await page.waitForFunction(() => /AWAY SCORE\s*3/i.test(document.querySelector(".layout")?.innerText ?? ""));
  assert.equal(app.project.engine.snapshot().values["away.score"], "3");
});

test("Edit mode shows the library and the editing band; design undo keeps the score", { skip }, async () => {
  await page.locator("button.edit").click();
  await page.getByText(/^editing$/i).first().waitFor();
  await page.locator(".side-tabs").getByText("Fields").waitFor();
  // Move a control with the keyboard, then undo the move.
  await tile("Away fouls").click();
  const before = JSON.stringify(app.project.layout);
  await page.keyboard.press("ArrowDown");
  await page.waitForTimeout(300);
  assert.notEqual(JSON.stringify(app.project.layout), before, "the arrow key moved the control");
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(300);
  assert.equal(JSON.stringify(app.project.layout), before, "undo put it back");
  assert.equal(app.project.engine.snapshot().values["away.score"], "3", "undo never rewinds the game");
  await page.locator("button.lock").click();
});

test("Edit mode: a tile resizes from its right edge, by half a cell", { skip }, async () => {
  await page.locator("button.edit").click();
  const t = tile("Away fouls");
  const id = await t.getAttribute("data-tile");
  const w0 = app.project.layout.pages[0].tiles.find((x) => x.id === id).w;
  const b = await t.boundingBox();
  const cell = (await page.locator(".layout").boundingBox()).width / 24;
  await page.mouse.move(b.x + b.width - 4, b.y + b.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width - 4 + cell * 1.6, b.y + b.height / 2, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(400);
  assert.equal(app.project.layout.pages[0].tiles.find((x) => x.id === id).w, w0 + 2, "1.6 cells rounds to 2");
  await page.keyboard.press("Control+z");
  await page.waitForTimeout(300);
  await page.locator("button.lock").click();
});

test("a blank project opens straight into Edit with the Library", { skip }, async () => {
  app.dirty = false;
  app._closeProject();
  await page.getByRole("button", { name: /Blank project/ }).first().click();
  await page.locator(".side-tabs").getByText("Shortcuts").waitFor();
  await page.getByText(/^editing$/i).first().waitFor();
  assert.equal(await page.locator("button.edit").getAttribute("aria-pressed"), "true");
});

test("live data connects only when Connect is pressed", { skip }, async () => {
  const xml = path.join(dataDir, "live.xml");
  fs.writeFileSync(xml, `<?xml version="1.0"?><Scoreboard><HomeScore>5</HomeScore></Scoreboard>`);
  await page.locator(".side-tabs").getByText("Live data").click();
  await page.locator('[data-k="live-kind"]').selectOption("livexml");
  const pathBox = page.locator('[data-k="live-path"]');
  await pathBox.fill(xml);
  await pathBox.press("Enter");
  await page.waitForTimeout(500);
  assert.equal(app.source, null, "changing the settings did not connect");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.waitForFunction(() => /live/i.test(document.querySelector('[data-ambient="live-status"]')?.innerText ?? ""));
  const first = app.source;
  assert.ok(first, "Connect connected");
  // Changing a setting while connected keeps the connection and says so.
  const stale = page.locator('[data-k="live-stale"]');
  await stale.fill("9");
  await stale.press("Tab");
  await page.waitForTimeout(400);
  await page.locator('[data-ambient="live-status"]').screenshot({ path: "/tmp/claude-0/shots/live-row.png" }).catch(() => {});
  await page.getByText("Settings changed. Reconnect to use them.").waitFor();
  assert.equal(app.source, first, "the connection was not restarted by itself");
  await page.getByRole("button", { name: "Disconnect" }).click();
  await page.waitForFunction(() => /not connected/i.test(document.querySelector('[data-ambient="live-status"]')?.innerText ?? ""));
  assert.equal(app.source, null);
});

test("status changes never interrupt typing or a drop-down", { skip }, async () => {
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await page.waitForFunction(() => /live/i.test(document.querySelector('[data-ambient="live-status"]')?.innerText ?? ""));
  const xml = path.join(dataDir, "live.xml");
  let n = 0;
  const timer = setInterval(() => fs.writeFileSync(xml, `<?xml version="1.0"?><Scoreboard><HomeScore>${n++}</HomeScore><GuestScore>${n % 3}</GuestScore></Scoreboard>`), 150);
  try {
    const poll = page.locator('[data-k="live-poll"]');
    await poll.click();
    await poll.fill("");
    await page.keyboard.type("12", { delay: 120 });
    for (let i = 0; i < 5; i++) { app._status(); await page.waitForTimeout(150); }
    await page.keyboard.type("34", { delay: 120 });
    await page.waitForTimeout(600);
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.k), "live-poll", "focus stayed in the box");
    assert.equal(await poll.inputValue(), "1234", "nothing typed was lost");
    await poll.press("Escape");   // leave without saving
    const bind = page.locator('[data-k^="bind-"]').first();
    await bind.focus();
    const handle = await bind.elementHandle();
    for (let i = 0; i < 5; i++) { app._status(); await page.waitForTimeout(150); }
    const state = await handle.evaluate((x) => ({ connected: x.isConnected, focused: document.activeElement === x, active: document.activeElement?.dataset?.k ?? document.activeElement?.tagName }));
    assert.deepEqual(state, { connected: true, focused: true, active: state.active }, `the drop-down stayed open (focus on ${state.active})`);
  } finally { clearInterval(timer); }
  await page.getByRole("button", { name: "Disconnect" }).click();
});

test("graphics: a board inside a board goes on and off air from its switch", { skip }, async () => {
  app.dirty = false;
  await app.newProject("Basketball");
  await page.locator("nav.tabs").getByText("View").click();
  await page.locator(".toolbar").getByRole("button", { name: "Text" }).waitFor();
  // A second board with a box on it.
  await page.locator(".side-body .row").getByRole("button", { name: "+" }).click();
  await page.locator(".menu").getByText("New blank board").click();
  await page.waitForFunction(() => { const t = document.querySelector('[data-k="g-board"]')?.selectedOptions[0]?.textContent ?? ""; window.__dbg = t; return t.startsWith("Board 3"); }, null, { timeout: 5000 }).catch(async (e) => { console.log("DBG board select:", await page.evaluate(() => window.__dbg)); throw e; });
  await page.locator(".toolbar").getByRole("button", { name: "Box" }).click();
  await page.waitForTimeout(300);
  const inner = app.project.boards.find((b) => b.name === "Board 3");
  assert.equal(inner.elements.length, 1);
  // Back to the scorebug: put Board 3 inside it.
  await page.locator('[data-k="g-board"]').selectOption({ index: 0 });
  await page.locator(".toolbar").getByRole("button", { name: "Board" }).click();
  await page.locator(".menu").getByText(/^Board 3/).click();
  await page.waitForFunction(() => document.body.innerText.includes("On air switch"), null, { timeout: 5000 }).catch(async (e) => { console.log("DBG text:", await page.evaluate(() => document.querySelector(".toasts")?.innerText)); throw e; });
  const outer = app.project.boards[0];
  const el = outer.elements.find((e) => e.kind === "board");
  assert.ok(el && el.board === inner.id && el.show_when.startsWith("onair."), "a board element with a switch");
  const f = app.project.engine.field(el.show_when);
  assert.equal(f.type, "toggle");
  assert.ok(app.project.layout.pages[0].tiles.some((t) => t.field === el.show_when), "the switch is on the first control page");
  // On air: the browser source draws the inner box; off air it does not.
  const out = await browser.newPage({ viewport: { width: 960, height: 540 } });
  await out.goto(`http://127.0.0.1:${app.public.port}/board/${outer.id}`);
  const nested = out.locator(`.bv-el[data-id="${el.id}"]`);
  await nested.waitFor({ state: "visible" });
  assert.equal(await out.locator(`.bv-el[data-id="${el.id}"] .bv-el`).count(), 1, "the inner board's box is drawn inside");
  app.project.engine.perform({ do: "set", field: el.show_when, value: false });
  await nested.waitFor({ state: "hidden" });
  app.project.engine.perform({ do: "set", field: el.show_when, value: true });
  await nested.waitFor({ state: "visible" });
  await out.close();
});

test("graphics: a picture arrives at its own size, and a big one can be fitted", { skip }, async () => {
  const img = path.join(dataDir, "big.png");
  // A 2400 x 1600 PNG, drawn by the browser.
  const b64 = await page.evaluate(() => { const c = document.createElement("canvas"); c.width = 2400; c.height = 1600; c.getContext("2d").fillRect(0, 0, 10, 10); return c.toDataURL("image/png").split(",")[1]; });
  fs.writeFileSync(img, Buffer.from(b64, "base64"));
  await page.locator('[data-k="g-board"]').selectOption({ index: 0 });
  await page.locator(".toolbar").getByRole("button", { name: "Picture" }).click();
  const src = page.locator('[data-k="el-src"]');
  await src.fill(img);
  await src.press("Enter");
  await page.locator("dialog").getByRole("button", { name: "Fit to the board" }).click();
  await page.waitForFunction(() => document.querySelector('[data-k="el-w"]')?.value === "1620");
  assert.equal(await page.locator('[data-k="el-h"]').inputValue(), "1080");
});

test("graphics: new text hugs its words; dragging an edge fixes its width", { skip }, async () => {
  await page.locator(".toolbar").getByRole("button", { name: "Text" }).click();
  await page.locator("[data-auto-size]").waitFor();
  const id = await page.evaluate(() => document.querySelector("[data-auto-size]").dataset.autoSize);
  const e = () => app.project.boards[0].elements.find((x) => x.id === id);
  assert.equal(e().extent, "auto");
  const edge = page.locator('.dz-edge[data-h="e"]');
  const b = await edge.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + 80, b.y + b.height / 2, { steps: 6 });
  await page.mouse.up();
  await page.waitForFunction(() => document.querySelector('[data-k="el-w"]'));
  assert.equal(e().extent, "fixed");
  // Opacity, as a percentage.
  const op = page.locator('[data-k="el-opacity"]');
  await op.fill("40");
  await op.press("Enter");
  await page.waitForTimeout(300);
  assert.equal(e().opacity, 0.4);
  // Fonts come from a list.
  await page.locator('[data-k="el-font"]').selectOption("Archivo");
  await page.waitForTimeout(300);
  assert.equal(e().font, "Archivo");
});

test("graphics: split view puts the live controls under the board", { skip }, async () => {
  await page.locator(".toolbar").getByRole("button", { name: "Split view" }).click();
  const pane = page.locator(".dz-split");
  await pane.getByText("Away score", { exact: true }).waitFor();
  const before = Number(app.project.engine.snapshot().values["away.score"]);
  await pane.locator(".tile", { has: page.getByText("Away score", { exact: true }) }).getByRole("button", { name: "+2" }).click();
  await page.waitForFunction((n) => true, before);
  await page.waitForTimeout(300);
  assert.equal(Number(app.project.engine.snapshot().values["away.score"]), before + 2);
  await page.locator(".toolbar").getByRole("button", { name: "Split view" }).click();
  await pane.waitFor({ state: "hidden" });
});

test("no errors in the page", { skip }, () => {
  assert.deepEqual(errors, []);
});
