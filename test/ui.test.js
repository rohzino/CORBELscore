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

test("no errors in the page", { skip }, () => {
  assert.deepEqual(errors, []);
});
