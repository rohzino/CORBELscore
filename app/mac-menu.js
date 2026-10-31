// The menu bar on macOS. Without one, ⌘C, ⌘V, ⌘A and ⌘Q do nothing. Windows and
// Linux keep no menu at all (main.js sets it to null there).
//
// Undo and redo are the page's own (design undo, score undo, or the typing in a
// box, depending on where you are), so those two items only show their keys and
// forward to the page: `registerAccelerator: false` leaves ⌘Z to reach it.

import { Menu, app } from "electron";

export function buildMacMenu({ about, undo, redo, windowRoles = true }) {
  const template = [
    { label: app.name, submenu: [
      { label: `About ${app.name}`, click: about },
      { type: "separator" },
      { role: "hide" }, { role: "hideOthers" }, { role: "unhide" },
      { type: "separator" },
      { role: "quit" },
    ] },
    { label: "Edit", submenu: [
      { label: "Undo", accelerator: "CmdOrCtrl+Z", registerAccelerator: false, click: undo },
      { label: "Redo", accelerator: "CmdOrCtrl+Shift+Z", registerAccelerator: false, click: redo },
      { type: "separator" },
      { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "pasteAndMatchStyle" }, { role: "delete" }, { role: "selectAll" },
    ] },
    { label: "Window", submenu: [
      { role: "minimize" }, { role: "zoom" },
      { label: "Toggle Full Screen", accelerator: "Ctrl+Cmd+F", role: "togglefullscreen" },
      { type: "separator" },
      { role: "front" },
    ] },
  ];
  return Menu.buildFromTemplate(template);
}
