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

test("no errors in the page", { skip }, () => {
  assert.deepEqual(errors, []);
});
