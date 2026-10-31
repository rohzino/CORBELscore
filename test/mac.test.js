// Mac keys and Finder opens. The platform is passed in, so these run the same on every system.
import { test } from "node:test";
import assert from "node:assert/strict";
import { appCombo, display, fromEvent, hotkeyCombo, normalise, undoKey } from "../app/ui/js/keys.js";
import { startFile } from "../app/start-file.js";
import { PRESETS } from "../app/core/presets.js";

const key = (o) => fromEvent({ key: o.key, code: o.code ?? "", ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...o });

test("mac: ⌘ is the app's command key", () => {
  assert.equal(appCombo(key({ key: "s", code: "KeyS", metaKey: true }), true), "Ctrl+S", "⌘S saves");
  assert.equal(appCombo(key({ key: "s", code: "KeyS", metaKey: true, shiftKey: true }), true), "Ctrl+Shift+S", "⌘⇧S saves as");
  assert.equal(appCombo(key({ key: "z", code: "KeyZ", metaKey: true }), true), "Ctrl+Z", "⌘Z is design undo");
  assert.equal(appCombo(key({ key: "z", code: "KeyZ", metaKey: true, shiftKey: true }), true), "Ctrl+Shift+Z", "⌘⇧Z is design redo");
  assert.equal(appCombo(key({ key: "p", code: "KeyP", metaKey: true, shiftKey: true }), true), "Ctrl+Shift+P", "⌘⇧P pops out");
  assert.equal(appCombo(key({ key: "t", code: "KeyT", metaKey: true, shiftKey: true }), true), "Ctrl+Shift+T", "⌘⇧T is always on top");
  for (const [k, want] of [["=", "Ctrl+="], ["-", "Ctrl+-"], ["0", "Ctrl+0"]]) assert.equal(appCombo(key({ key: k, metaKey: true }), true), want, `⌘${k}`);
  assert.equal(appCombo(key({ key: "1", code: "Digit1", metaKey: true }), true), "F1", "⌘1 is the Control tab");
  assert.equal(appCombo(key({ key: "2", code: "Digit2", metaKey: true }), true), "F2", "⌘2 is the View tab");
});

test("mac: ⌃ keeps its stored meaning", () => {
  const ctrlSpace = key({ key: " ", code: "Space", ctrlKey: true });
  assert.equal(ctrlSpace, "Ctrl+Space");
  assert.equal(appCombo(ctrlSpace, true), "Ctrl+Space");
  assert.equal(hotkeyCombo(ctrlSpace, true), "Ctrl+Space");
  assert.equal(normalise("Ctrl+Space"), hotkeyCombo(ctrlSpace, true), "a project's Ctrl+Space matches ⌃Space");
  assert.equal(appCombo(key({ key: "z", code: "KeyZ", ctrlKey: true }), true), "Ctrl+Z", "⌃Z still undoes the design");
  assert.equal(hotkeyCombo("Ctrl+Z", true), "Ctrl+Z", "and scores undo in Locked mode");
});

test("mac: ⌘Space is left to Spotlight and matches no project shortcut", () => {
  const cmdSpace = key({ key: " ", code: "Space", metaKey: true });
  assert.equal(hotkeyCombo(cmdSpace, true), "Meta+Space");
  assert.notEqual(hotkeyCombo(cmdSpace, true), normalise("Ctrl+Space"));
});

test("mac: ⌘Z and ⌘⇧Z are the score's undo and redo where the templates keep Ctrl+Z / Ctrl+Y", () => {
  assert.equal(hotkeyCombo(key({ key: "z", code: "KeyZ", metaKey: true }), true), "Ctrl+Z");
  assert.equal(hotkeyCombo(key({ key: "z", code: "KeyZ", metaKey: true, shiftKey: true }), true), "Ctrl+Y", "the keys as the keyboard sends them");
  assert.equal(undoKey(key({ key: "z", code: "KeyZ", metaKey: true }), true), "undo");
  assert.equal(undoKey(key({ key: "z", code: "KeyZ", metaKey: true, shiftKey: true }), true), "redo");
  assert.equal(undoKey(key({ key: "z", code: "KeyZ", ctrlKey: true }), true), "");
  let seen = 0;
  for (const name of Object.keys(PRESETS)) {
    for (const b of PRESETS[name]().buttons) {
      if (b.action?.do === "undo") { assert.equal(normalise(b.hotkey), "Ctrl+Z", name); seen++; }
      if (b.action?.do === "redo") assert.equal(normalise(b.hotkey), "Ctrl+Y", name);
    }
  }
  assert.ok(seen > 3, "the templates ship the Undo shortcut");
  assert.equal(hotkeyCombo("Meta+S", true), "Meta+S", "no other ⌘ key becomes a project shortcut");
});

test("not a mac: nothing changes", () => {
  assert.equal(appCombo("Meta+S", false), "Meta+S");
  assert.equal(appCombo("Ctrl+S", false), "Ctrl+S");
  assert.equal(hotkeyCombo("Meta+Z", false), "Meta+Z");
  assert.equal(display("Ctrl+Shift+S", { app: true, mac: false }), "Ctrl+Shift+S");
  assert.equal(display("Ctrl+Space", { mac: false }), "Ctrl+Space");
});

test("mac: keys are shown with Mac symbols, the stored strings stay", () => {
  assert.equal(display("Ctrl+S", { app: true, mac: true }), "⌘S");
  assert.equal(display("Ctrl+Shift+S", { app: true, mac: true }), "⇧⌘S");
  assert.equal(display("Ctrl+Space", { mac: true }), "⌃Space");
  assert.equal(display("Ctrl+Alt+Shift+K", { mac: true }), "⌃⌥⇧K");
  assert.equal(display("F5", { mac: true }), "F5");
});

test("Finder: a queued open wins over the command line, -psn_… is ignored", () => {
  assert.equal(startFile(["/a/game.corbel"], ["x.corbel"]), "/a/game.corbel");
  assert.equal(startFile([], ["-psn_0_12345", "/b/old.tsproj"]), "/b/old.tsproj");
  assert.equal(startFile([], ["-psn_0_12345"]), "");
  assert.equal(startFile(["/a/notes.txt"], []), "");
});
