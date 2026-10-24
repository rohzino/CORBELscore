"""TeleScore 1.x project import. The fixture follows ProjectFile.save() in 1.0.3."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.project import Project  # noqa: E402

# Keys in 1.x files: "0" header, "1" layouts, "2" components, "9" properties, "11" connections
LEGACY = {
    "0": {"Name": "Friday Hockey", "Author": "glenn", "Global Directory": "C:/Stream/Score",
          "CC": 9, "LC": 1, "Date": "", "FN": "", "Version": "1.0.3 Beta Preview 1"},
    "1": [{
        "9": {"Component Name": "Main", "Width": 1280, "Height": 720, "Background Image": "",
              "Background Color": "#3E5768", "Maintain Aspect Ratio": True, "Pop Out On Start": False},
        "2": [
            {"0": "Time Display", "9": {"Component Name": "Game Clock", "X": 500, "Y": 20, "Width": 280,
                                        "Height": 100, "Format": 0, "Default Time": "20:00", "Stopwatch": False,
                                        "Clr when time = 0": False, "Tenth of a second": True, "Buzzer Sound": "",
                                        "Font Color": "#FF9B42", "Background Color": "#242325", "Font Size": 40,
                                        "Font Weight": 4, "Text Alignment": 1, "Display Font": "Arial",
                                        "Transparent Background": False, "Lock": False}, "11": {"Clock Stop": []}},
            {"0": "Points Display", "9": {"Component Name": "Home Score", "X": 100, "Y": 200, "Width": 200,
                                          "Height": 200, "Suffix (st, nd, rd, th)": 0, "Clr when points = 0": False,
                                          "Font Size": 60, "Font Weight": 6, "Transparent Background": True},
             "11": {}},
            {"0": "Points Display", "9": {"Component Name": "Period", "X": 600, "Y": 200, "Width": 100,
                                          "Height": 80, "Suffix (st, nd, rd, th)": 2}, "11": {}},
            {"0": "Text Display", "9": {"Component Name": "Sponsor", "X": 0, "Y": 650, "Width": 1280, "Height": 70,
                                        "Display Text": "Brought to you by Joe's"}, "11": {}},
            {"0": "Penalty", "9": {"Component Name": "Home Penalties", "X": 100, "Y": 450, "Width": 300,
                                   "Height": 120, "Format": 0}, "11": {}},
            {"0": "Start Time", "9": {"Component Name": "Start Time 1", "Display Text": "Start", "Hotkey": "Space"},
             "11": {"Start": ["Game Clock", "Home Penalties"]}},
            {"0": "Stop Time", "9": {"Component Name": "Stop Time 1", "Display Text": "Stop"},
             "11": {"Stop": ["Game Clock"]}},
            {"0": "Add Points", "9": {"Component Name": "Add Points 1", "Display Text": "+2", "Set Amount": 2},
             "11": {"Add Points": ["Home Score"]}},
            {"0": "Invisible", "9": {"Component Name": "Hide Sponsor", "Display Text": "Hide"},
             "11": {"Set Invisible": ["Sponsor"]}},
            {"0": "Visible", "9": {"Component Name": "Show Sponsor", "Display Text": "Show"},
             "11": {"Set Visible": ["Sponsor"]}},
            {"0": "Type Text", "9": {"Component Name": "Type Text 1"}, "11": {"Set Text": ["Sponsor"]}},
            {"0": "Reset", "9": {"Component Name": "Orphan"}, "11": {"Reset": []}},
        ],
    }],
}


class LegacyImportTests(unittest.TestCase):
    def load(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "old.json")
        with open(path, "w") as fh:
            json.dump(LEGACY, fh)
        return Project.load(path), path

    def test_fields_and_board(self):
        p, path = self.load()
        self.assertEqual(p.name, "Friday Hockey")
        self.assertEqual(p.imported_from, path)
        self.assertEqual(p.path, "")                         # never overwrites the 1.x file
        snap = p.engine.snapshot().values
        self.assertEqual(snap["clock.game_clock"], "20:00")
        self.assertEqual(snap["period"], "0th")              # ordinal carried over
        self.assertEqual(snap["sponsor"], "Brought to you by Joe's")
        self.assertEqual(p.engine.field("home_penalties").master, "clock.game_clock")
        board = p.boards[0]
        self.assertEqual((board.name, board.width, board.height), ("Main", 1280, 720))
        clock_el = next(e for e in board.elements if e.name == "Game Clock")
        self.assertEqual((clock_el.x, clock_el.y, clock_el.w, clock_el.h), (500, 20, 280, 100))
        self.assertEqual(clock_el.weight, 700)
        self.assertEqual(clock_el.fill, "#242325")
        score_el = next(e for e in board.elements if e.name == "Home Score")
        self.assertEqual(score_el.fill, "")                  # transparent background respected
        self.assertEqual(board.missing_keys(snap), [])
        self.assertEqual(p.outputs.folder, "C:/Stream/Score")

    def test_buttons_reproduce_connections(self):
        p, _ = self.load()
        btns = {b.label: b for b in p.panels[0].buttons}
        self.assertEqual(btns["Start"].action, {"do": "start", "field": "clock.game_clock"})
        self.assertEqual(btns["Start"].hotkey, "Space")
        self.assertEqual(btns["+2"].action, {"do": "add", "field": "home_score", "amount": 2})
        hide, show = btns["Hide"].action, btns["Show"].action
        self.assertEqual(hide["field"], show["field"])        # one toggle for both buttons
        e = p.engine
        e.perform(hide, t=0)
        sponsor = next(el for el in p.boards[0].elements if el.name == "Sponsor")
        self.assertFalse(sponsor.shown(e.snapshot().values))
        e.perform(show, t=0)
        self.assertTrue(sponsor.shown(e.snapshot().values))
        for b in p.panels[0].buttons:
            e.perform(b.action, t=0)
        self.assertNotIn("Orphan", btns)
        notes = " ".join(p.import_notes)
        self.assertIn("Orphan", notes)
        self.assertIn("Type Text", notes)

    def test_imported_project_saves_as_v2(self):
        p, path = self.load()
        out = os.path.splitext(path)[0] + ".tsproj"
        p.save(out)
        q = Project.load(out)
        self.assertEqual(q.engine.snapshot().values["sponsor"], "Brought to you by Joe's")
        with open(path) as fh:
            self.assertEqual(json.load(fh), LEGACY)           # original untouched


if __name__ == "__main__":
    unittest.main()
