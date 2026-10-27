// TeleScore 1.x import. The fixture follows ProjectFile.save() in 1.0.3.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { elementShown, boardKeys } from "../app/core/board.js";
import { loadProject, saveProject } from "../app/service/files.js";

// "0" header, "1" layouts, "2" components, "9" properties, "11" connections
const LEGACY = {
 "0": {
  "Name": "Friday Hockey",
  "Author": "glenn",
  "Global Directory": "C:/Stream/Score",
  "CC": 9,
  "LC": 1,
  "Date": "",
  "FN": "",
  "Version": "1.0.3 Beta Preview 1"
 },
 "1": [
  {
   "9": {
    "Component Name": "Main",
    "Width": 1280,
    "Height": 720,
    "Background Image": "",
    "Background Color": "#3E5768",
    "Maintain Aspect Ratio": true,
    "Pop Out On Start": false
   },
   "2": [
    {
     "0": "Time Display",
     "9": {
      "Component Name": "Game Clock",
      "X": 500,
      "Y": 20,
      "Width": 280,
      "Height": 100,
      "Format": 0,
      "Default Time": "20:00",
      "Stopwatch": false,
      "Clr when time = 0": false,
      "Tenth of a second": true,
      "Buzzer Sound": "",
      "Font Color": "#FF9B42",
      "Background Color": "#242325",
      "Font Size": 40,
      "Font Weight": 4,
      "Text Alignment": 1,
      "Display Font": "Arial",
      "Transparent Background": false,
      "Lock": false
     },
     "11": {
      "Clock Stop": []
     }
    },
    {
     "0": "Points Display",
     "9": {
      "Component Name": "Home Score",
      "X": 100,
      "Y": 200,
      "Width": 200,
      "Height": 200,
      "Suffix (st, nd, rd, th)": 0,
      "Clr when points = 0": false,
      "Font Size": 60,
      "Font Weight": 6,
      "Transparent Background": true
     },
     "11": {}
    },
    {
     "0": "Points Display",
     "9": {
      "Component Name": "Period",
      "X": 600,
      "Y": 200,
      "Width": 100,
      "Height": 80,
      "Suffix (st, nd, rd, th)": 2
     },
     "11": {}
    },
    {
     "0": "Text Display",
     "9": {
      "Component Name": "Sponsor",
      "X": 0,
      "Y": 650,
      "Width": 1280,
      "Height": 70,
      "Display Text": "Brought to you by Joe's"
     },
     "11": {}
    },
    {
     "0": "Penalty",
     "9": {
      "Component Name": "Home Penalties",
      "X": 100,
      "Y": 450,
      "Width": 300,
      "Height": 120,
      "Format": 0
     },
     "11": {}
    },
    {
     "0": "Start Time",
     "9": {
      "Component Name": "Start Time 1",
      "Display Text": "Start",
      "Hotkey": "Space"
     },
     "11": {
      "Start": [
       "Game Clock",
       "Home Penalties"
      ]
     }
    },
    {
     "0": "Stop Time",
     "9": {
      "Component Name": "Stop Time 1",
      "Display Text": "Stop"
     },
     "11": {
      "Stop": [
       "Game Clock"
      ]
     }
    },
    {
     "0": "Add Points",
     "9": {
      "Component Name": "Add Points 1",
      "Display Text": "+2",
      "Set Amount": 2
     },
     "11": {
      "Add Points": [
       "Home Score"
      ]
     }
    },
    {
     "0": "Invisible",
     "9": {
      "Component Name": "Hide Sponsor",
      "Display Text": "Hide"
     },
     "11": {
      "Set Invisible": [
       "Sponsor"
      ]
     }
    },
    {
     "0": "Visible",
     "9": {
      "Component Name": "Show Sponsor",
      "Display Text": "Show"
     },
     "11": {
      "Set Visible": [
       "Sponsor"
      ]
     }
    },
    {
     "0": "Type Text",
     "9": {
      "Component Name": "Type Text 1"
     },
     "11": {
      "Set Text": [
       "Sponsor"
      ]
     }
    },
    {
     "0": "Reset",
     "9": {
      "Component Name": "Orphan"
     },
     "11": {
      "Reset": []
     }
    }
   ]
  }
 ]
};

function load() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), "ts-"));
  const file = path.join(d, "old.json");
  fs.writeFileSync(file, JSON.stringify(LEGACY));
  return [loadProject(file), file];
}

test("legacy: fields and board", () => {
  const [p, file] = load();
  assert.equal(p.name, "Friday Hockey");
  assert.equal(p.importedFrom, file);
  assert.equal(p.path, "");
  const snap = p.engine.snapshot().values;
  assert.equal(snap["clock.game_clock"], "20:00");
  assert.equal(snap.period, "0th");
  assert.equal(snap.sponsor, "Brought to you by Joe's");
  assert.equal(p.engine.field("home_penalties").master, "clock.game_clock");
  const board = p.boards[0];
  assert.deepEqual([board.name, board.width, board.height], ["Main", 1280, 720]);
  const clock = board.elements.find((e) => e.name === "Game Clock");
  assert.deepEqual([clock.x, clock.y, clock.w, clock.h], [500, 20, 280, 100]);
  assert.equal(clock.weight, 700);
  assert.equal(clock.fill, "#242325");
  assert.equal(board.elements.find((e) => e.name === "Home Score").fill, "");
  assert.deepEqual(boardKeys(board).filter((k) => !(k in snap)), []);
  assert.equal(p.outputs.folder, "C:/Stream/Score");
  assert.ok(p.layout.pages[0].tiles.some((t) => t.field === "clock.game_clock"));
});

test("legacy: buttons reproduce connections", () => {
  const [p] = load();
  const btns = Object.fromEntries(p.buttons.map((b) => [b.label, b]));
  assert.deepEqual(btns.Start.action, { do: "start", field: "clock.game_clock" });
  assert.equal(btns.Start.hotkey, "Space");
  assert.deepEqual(btns["+2"].action, { do: "add", field: "home_score", amount: 2 });
  const hide = btns.Hide.action, show = btns.Show.action;
  assert.equal(hide.field, show.field);
  const e = p.engine;
  const sponsor = p.boards[0].elements.find((x) => x.name === "Sponsor");
  e.perform(hide, 0);
  assert.equal(elementShown(sponsor, e.snapshot().values), false);
  e.perform(show, 0);
  assert.equal(elementShown(sponsor, e.snapshot().values), true);
  for (const b of p.buttons) e.perform(b.action, 0);
  assert.ok(!("Orphan" in btns));
  const notes = p.importNotes.join(" ");
  assert.ok(notes.includes("Orphan"));
  assert.ok(notes.includes("Type Text"));
});

test("legacy: an imported project saves as a new file", () => {
  const [p, file] = load();
  const out = file.replace(/\.json$/, ".tsproj");
  saveProject(p, out);
  const q = loadProject(out);
  assert.equal(q.engine.snapshot().values.sponsor, "Brought to you by Joe's");
  assert.deepEqual(JSON.parse(fs.readFileSync(file, "utf8")), LEGACY);
});
