"""Engine tests. Standard library only: python -m unittest discover -s tests"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.board import Board, Element, render_template, resolve_color  # noqa: E402
from telescore.core.clock import Clock  # noqa: E402
from telescore.core.engine import ActionError, Engine  # noqa: E402
from telescore.core.fields import (ChoiceField, ClockField, CounterField, PenaltyField, TextField,  # noqa: E402
                                   ToggleField, field_from_dict, normalise_key)
from telescore.core.presets import PRESETS  # noqa: E402
from telescore.core.project import Project, ProjectError, atomic_write_text  # noqa: E402
from telescore.core.timefmt import TimeParseError, format_ms, ordinal, parse_time  # noqa: E402


class TimeFormatTests(unittest.TestCase):
    def test_countdown_rounds_up(self):
        self.assertEqual(format_ms(4_999, "m:ss"), "0:05")
        self.assertEqual(format_ms(4_001, "m:ss"), "0:05")
        self.assertEqual(format_ms(4_000, "m:ss"), "0:04")
        self.assertEqual(format_ms(1, "m:ss"), "0:01")
        self.assertEqual(format_ms(0, "m:ss"), "0:00")

    def test_stopwatch_rounds_down(self):
        self.assertEqual(format_ms(4_999, "m:ss", countdown=False), "0:04")
        self.assertEqual(format_ms(59_999, "mm:ss", countdown=False), "00:59")

    def test_total_units(self):
        self.assertEqual(format_ms(90 * 60_000, "mm:ss"), "90:00")       # no hour token: total minutes
        self.assertEqual(format_ms(90 * 60_000, "h:mm:ss"), "1:30:00")
        self.assertEqual(format_ms(125_000, "ss"), "125")                 # no minute token: total seconds

    def test_tenths_and_hundredths(self):
        self.assertEqual(format_ms(4_070, "s.t"), "4.0")   # fractions truncate, like arena clocks
        self.assertEqual(format_ms(4_070, "s.t", countdown=False), "4.0")
        self.assertEqual(format_ms(4_071, "ss.tt"), "04.07")
        self.assertEqual(format_ms(247_300, "mm:ss.z"), "04:07.3")  # legacy 'z'

    def test_literals_survive(self):
        self.assertEqual(format_ms(65_000, "Clock m'ss"), "Clock 1'05")

    def test_parse(self):
        self.assertEqual(parse_time("12:00"), 720_000)
        self.assertEqual(parse_time("1:02:03"), 3_723_000)
        self.assertEqual(parse_time("45"), 45_000)
        self.assertEqual(parse_time("90"), 90_000)
        self.assertEqual(parse_time("4:07.3"), 247_300)
        self.assertEqual(parse_time("0:00.25"), 250)
        self.assertEqual(parse_time(".5"), 500)
        self.assertEqual(parse_time("8:"), 480_000)
        self.assertEqual(parse_time(" 2 : 00 "), 120_000)
        for bad in ("", "abc", "1:60", "1:61:00", "1:2:3:4", "-5"):
            with self.subTest(bad=bad), self.assertRaises(TimeParseError):
                parse_time(bad)

    def test_ordinal(self):
        cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 13: "13th",
                 21: "21st", 22: "22nd", 101: "101st", 111: "111th", 112: "112th", 0: "0th"}
        for n, want in cases.items():
            self.assertEqual(ordinal(n), want)


class ClockTests(unittest.TestCase):
    def test_countdown_runs_and_pauses_exactly(self):
        c = Clock(countdown=True, initial_ms=10_000)
        c.start(100.0)
        self.assertEqual(c.value(104.9), 5_100)
        c.stop(104.9)
        self.assertEqual(c.value(500.0), 5_100)        # fraction kept across a pause (1.x lost it)
        c.start(600.0)
        self.assertEqual(c.value(601.0), 4_100)
        self.assertEqual(c.display(601.0), "0:05")

    def test_expiry_fires_once_and_stops(self):
        c = Clock(countdown=True, initial_ms=1_000)
        c.start(0.0)
        self.assertFalse(c.tick(0.5))
        self.assertTrue(c.tick(1.2))
        self.assertFalse(c.running)
        self.assertEqual(c.value(9.0), 0)
        self.assertFalse(c.tick(9.0))
        self.assertFalse(c.start(10.0))                 # nothing to run at zero

    def test_toggle_is_not_inverted(self):
        c = Clock(initial_ms=5_000)
        self.assertTrue(c.toggle(0.0))
        self.assertFalse(c.toggle(1.0))
        self.assertEqual(c.value(), 4_000)

    def test_set_while_running_keeps_running(self):
        c = Clock(initial_ms=60_000)
        c.start(0.0)
        c.set(30_000, 5.0)
        self.assertTrue(c.running)
        self.assertEqual(c.value(6.0), 29_000)

    def test_adjust_and_bounds(self):
        c = Clock(initial_ms=5_000)
        c.adjust(-10_000, 0)
        self.assertEqual(c.value(0), 0)
        c.adjust(Clock.MAX_MS * 2, 0)
        self.assertEqual(c.value(0), Clock.MAX_MS)

    def test_stopwatch_limit(self):
        c = Clock(countdown=False, initial_ms=0, limit_ms=3_000)
        c.start(0.0)
        self.assertEqual(c.value(5.0), 3_000)
        self.assertTrue(c.tick(5.0))
        self.assertFalse(c.running)

    def test_tenths_threshold_and_blank(self):
        c = Clock(initial_ms=65_000, tenths_under_ms=60_000, tenths_fmt="s.t", blank_at_zero=True)
        self.assertEqual(c.display(0), "1:05")
        c.set(60_000, 0)
        self.assertEqual(c.display(0), "1:00")
        c.set(59_999, 0)
        self.assertEqual(c.display(0), "59.9")          # seamless hand-off at the threshold
        c.set(4_321, 0)
        self.assertEqual(c.display(0), "4.3")
        c.set(0, 0)
        self.assertEqual(c.display(0), "")

    def test_roundtrip_opens_stopped(self):
        c = Clock(initial_ms=20 * 60_000, fmt="mm:ss")
        c.start(0.0)
        d = c.to_dict(65.0)
        c2 = Clock.from_dict(json.loads(json.dumps(d)))
        self.assertFalse(c2.running)
        self.assertEqual(c2.value(), 20 * 60_000 - 65_000)
        self.assertEqual(c2.fmt, "mm:ss")


class FieldTests(unittest.TestCase):
    def test_keys(self):
        with self.assertRaises(ValueError):
            TextField("Home Score")
        self.assertEqual(normalise_key("Home Score!"), "home_score")
        self.assertEqual(normalise_key("..a..b.."), "a.b")

    def test_counter(self):
        f = CounterField("x", minimum=0, maximum=3, pad=2)
        f.add(5)
        self.assertEqual(f.display(), "03")
        f.add(-9)
        self.assertEqual(f.value, 0)
        with self.assertRaises(ValueError):
            f.set("two")
        f2 = CounterField("p", value=2, ordinal=True)
        self.assertEqual(f2.display(), "2nd")
        f3 = CounterField("z", blank_zero=True)
        self.assertEqual(f3.display(), "")

    def test_choice(self):
        f = ChoiceField("period", options=["1st", "2nd", "OT"])
        f.step(5)
        self.assertEqual(f.display(), "OT")
        f.set("2ND")
        self.assertEqual(f.index, 1)
        self.assertEqual(f.extra(), {"index": "2"})
        w = ChoiceField("half", options=["▲", "▼"], wrap=True)
        w.step(1); w.step(1)
        self.assertEqual(w.display(), "▲")
        with self.assertRaises(ValueError):
            f.set("4th")

    def test_toggle_strings(self):
        f = ToggleField("pp", on_text="PP")
        f.set("on")
        self.assertEqual(f.display(), "PP")
        f.set("0")
        self.assertEqual(f.display(), "")

    def test_roundtrip_every_type(self):
        proj = PRESETS["Hockey"]()
        for f in proj.engine.fields.values():
            with self.subTest(key=f.key):
                g = field_from_dict(json.loads(json.dumps(f.to_dict())))
                self.assertEqual(type(g), type(f))
                self.assertEqual(g.display(), f.display())


def make_engine():
    return Engine([
        CounterField("home.score", "Home score"),
        CounterField("away.score", "Away score"),
        TextField("home.name", value="Hawks"),
        ClockField("clock.game", "Game clock", clock=Clock(initial_ms=20 * 60_000)),
        PenaltyField("home.penalties", master="clock.game", slots=2),
        ToggleField("home.pp", on_text="PP"),
        ChoiceField("period", options=["1st", "2nd", "3rd"]),
    ])


class EngineTests(unittest.TestCase):
    def test_actions_and_snapshot(self):
        e = make_engine()
        e.perform({"do": "add", "field": "home.score", "amount": 3}, t=0)
        e.perform({"do": "next", "field": "period"}, t=0)
        s = e.snapshot()
        self.assertEqual(s.values["home.score"], "3")
        self.assertEqual(s.values["period"], "2nd")
        self.assertEqual(s.values["period.index"], "2")
        self.assertEqual(s.values["clock.game.running"], "0")
        self.assertEqual(s.raw["clock.game"], 1_200_000)

    def test_errors_are_operator_readable(self):
        e = make_engine()
        with self.assertRaisesRegex(ActionError, "no field called"):
            e.perform({"do": "add", "field": "nope"})
        with self.assertRaisesRegex(ActionError, "Unknown action"):
            e.perform({"do": "explode", "field": "home.score"})
        with self.assertRaisesRegex(ActionError, "does not apply"):
            e.perform({"do": "toggle", "field": "home.score"})
        with self.assertRaisesRegex(ActionError, "not a time"):
            e.perform({"do": "set", "field": "clock.game", "value": "soon"})

    def test_batch_is_all_or_nothing(self):
        e = make_engine()
        with self.assertRaises(ActionError):
            e.perform({"do": "batch", "actions": [
                {"do": "add", "field": "home.score", "amount": 2},
                {"do": "add", "field": "missing"}]}, t=0)
        self.assertEqual(e.snapshot().values["home.score"], "0")
        self.assertFalse(e.can_undo())

    def test_undo_redo(self):
        e = make_engine()
        e.perform({"do": "add", "field": "home.score", "amount": 2}, t=0)
        e.perform({"do": "batch", "actions": [{"do": "add", "field": "home.score", "amount": 1},
                                             {"do": "set", "field": "home.name", "value": "Owls"}]}, t=0)
        e.perform({"do": "undo"}, t=0)
        s = e.snapshot()
        self.assertEqual((s.values["home.score"], s.values["home.name"]), ("2", "Hawks"))
        e.perform({"do": "redo"}, t=0)
        self.assertEqual(e.snapshot().values["home.name"], "Owls")
        e.perform({"do": "undo"}, t=0)
        e.perform({"do": "undo"}, t=0)
        self.assertEqual(e.snapshot().values["home.score"], "0")
        e.perform({"do": "undo"}, t=0)  # nothing left: harmless

    def test_undo_clock_set_keeps_time_that_ran(self):
        e = make_engine()
        e.perform({"do": "start", "field": "clock.game"}, t=0.0)
        e.perform({"do": "set", "field": "clock.game", "value": "5:00"}, t=10.0)   # mistake
        e.perform({"do": "undo"}, t=13.0)
        # Clock was at 19:50 when the mistake happened and has run 3 s since.
        self.assertEqual(e.field("clock.game").clock.value(13.0), 20 * 60_000 - 13_000)
        self.assertTrue(e.field("clock.game").clock.running)

    def test_score_undo_does_not_rewind_running_clock(self):
        e = make_engine()
        e.perform({"do": "start", "field": "clock.game"}, t=0.0)
        e.perform({"do": "add", "field": "home.score"}, t=5.0)
        e.perform({"do": "undo"}, t=9.0)
        self.assertEqual(e.field("clock.game").clock.value(9.0), 20 * 60_000 - 9_000)

    def test_cannot_start_clock_at_zero(self):
        e = make_engine()
        e.perform({"do": "set", "field": "clock.game", "value": "0"}, t=0)
        with self.assertRaisesRegex(ActionError, "at zero"):
            e.perform({"do": "toggle", "field": "clock.game"}, t=0)

    def test_penalties_follow_the_game_clock(self):
        e = make_engine()
        e.perform({"do": "penalty.add", "field": "home.penalties", "player": "#12", "time": "2:00"}, t=0.0)
        e.perform({"do": "penalty.add", "field": "home.penalties", "player": "#7", "time": "2:00"}, t=0.0)
        e.perform({"do": "penalty.add", "field": "home.penalties", "player": "#3", "time": "2:00"}, t=0.0)
        e.tick(30.0)                                    # clock stopped: penalties hold
        self.assertEqual(e.snapshot().values["home.penalties.1.time"], "2:00")
        e.perform({"do": "start", "field": "clock.game"}, t=30.0)
        for i in range(1, 61):                          # 60 s of ticks
            e.tick(30.0 + i)
        e.perform({"do": "stop", "field": "clock.game"}, t=90.0)
        e.tick(200.0)                                   # stoppage
        s = e.snapshot()
        self.assertEqual(s.values["home.penalties.1.time"], "1:00")
        self.assertEqual(s.values["home.penalties.2.time"], "1:00")
        self.assertEqual(s.values["home.penalties.count"], "3")   # the third waits its turn
        e.perform({"do": "start", "field": "clock.game"}, t=200.0)
        e.tick(260.5)
        s = e.snapshot()
        self.assertEqual(s.values["home.penalties.count"], "1")
        self.assertEqual(s.values["home.penalties.1.player"], "#3")
        self.assertEqual(s.values["home.penalties.1.time"], "2:00")   # starts now

    def test_adjusting_master_does_not_move_penalties(self):
        e = make_engine()
        e.perform({"do": "penalty.add", "field": "home.penalties", "player": "", "time": "2:00"}, t=0.0)
        e.perform({"do": "start", "field": "clock.game"}, t=0.0)
        e.perform({"do": "adjust", "field": "clock.game", "ms": -5000}, t=10.0)
        e.tick(10.0)
        self.assertEqual(e.field("home.penalties").entries[0]["ms"], 110_000)

    def test_expiry_listener_and_queue(self):
        e = Engine([ClockField("shot", clock=Clock(initial_ms=1000))])
        hits = []
        e.on_expired(hits.append)
        e.perform({"do": "start", "field": "shot"}, t=0.0)
        e.tick(0.5)
        e.tick(1.5)
        e.tick(2.5)
        self.assertEqual(hits, ["shot"])
        results = []
        e.submit({"do": "reset", "field": "shot"}, results.append)
        e.submit({"do": "add", "field": "nope"}, results.append)
        e.tick(3.0)
        self.assertEqual(results[0], None)
        self.assertIn("no field", results[1])

    def test_listener_gets_only_changes(self):
        e = make_engine()
        seen = []
        e.on_change(lambda snap, changed: seen.append(changed))
        e.perform({"do": "add", "field": "away.score"}, t=0)
        self.assertEqual(seen[-1], {"away.score"})
        n = len(seen)
        e.tick(0)                                       # nothing changed: no notification
        self.assertEqual(len(seen), n)

    def test_collisions_rejected(self):
        e = make_engine()
        with self.assertRaises(ValueError):
            e.add_field(TextField("home.score"))
        with self.assertRaises(ValueError):
            e.add_field(TextField("clock.game.running"))

    def test_rename(self):
        e = make_engine()
        e.rename_field("home.name", "home.title")
        self.assertIn("home.title", e.fields)
        self.assertEqual(list(e.fields).index("home.title"), 2)


class BoardTests(unittest.TestCase):
    def test_templates(self):
        v = {"home.score": "3", "a": "x"}
        self.assertEqual(render_template("{home.score}-{missing}", v), "3-")
        self.assertEqual(render_template("{{literal}} {a}", v), "{literal} x")

    def test_colors(self):
        self.assertEqual(resolve_color("{c}", {"c": "ABC"}), "#aabbcc")
        self.assertEqual(resolve_color("#0a0f0df2", {}), "#0a0f0df2")
        self.assertEqual(resolve_color("{c}", {"c": "red"}), "")
        self.assertEqual(resolve_color("", {}), "")

    def test_align_distribute_reorder(self):
        b = Board(width=1000, height=500)
        a, c, d = Element(x=10, y=0, w=100), Element(x=500, y=20, w=50), Element(x=200, y=40, w=100)
        b.elements = [a, c, d]
        b.align([a.id, c.id], "left")
        self.assertEqual(c.x, 10)
        b.align([a.id], "hcenter")                      # one element: to the canvas
        self.assertEqual(a.x, 450)
        b.elements = [Element(x=0, w=100), Element(x=150, w=100), Element(x=900, w=100)]
        ids = [e.id for e in b.elements]
        b.distribute(ids, "h")
        self.assertEqual([e.x for e in b.elements], [0, 450, 900])
        b.reorder(ids[0], "front")
        self.assertEqual(b.elements[-1].id, ids[0])
        b.reorder(ids[0], "backward")
        self.assertEqual(b.elements[-2].id, ids[0])

    def test_show_when(self):
        e = Element(show_when="home.pp")
        self.assertFalse(e.shown({"home.pp": ""}))
        self.assertFalse(e.shown({"home.pp": "0"}))
        self.assertTrue(e.shown({"home.pp": "PP"}))

    def test_compact_roundtrip(self):
        e = Element(kind="text", text="{a}", size=60)
        d = e.to_dict()
        self.assertNotIn("font", d)                     # defaults left out
        self.assertEqual(Element.from_dict(d), e)
        with self.assertRaises(ValueError):
            Board.from_dict({"width": 99999, "height": 10})


class ProjectTests(unittest.TestCase):
    def test_presets_are_consistent(self):
        for name, make in PRESETS.items():
            with self.subTest(preset=name):
                p = make()
                keys = set(p.engine.snapshot().values)
                for b in p.boards:
                    self.assertEqual(b.missing_keys(keys), [], f"{name}/{b.name}")
                for panel in p.panels:
                    for btn in panel.buttons:
                        acts = btn.action.get("actions", [btn.action])
                        for a in acts:
                            if a.get("do") not in ("undo", "redo", "stop_all"):
                                self.assertIn(a["field"], p.engine.fields, f"{name}: {btn.label}")
                        # every button must actually run
                        p.engine.perform(btn.action, t=0)

    def test_save_load_roundtrip(self):
        p = PRESETS["Basketball"]()
        p.engine.perform({"do": "add", "field": "home.score", "amount": 7}, t=0)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "game.tsproj")
            p.save(path)
            q = Project.load(path)
            self.assertEqual(q.engine.snapshot().values["home.score"], "7")
            self.assertEqual([b.to_dict() for b in q.boards], [b.to_dict() for b in p.boards])
            self.assertEqual(q.panels[0].to_dict(), p.panels[0].to_dict())
            self.assertEqual(q.path, path)
            self.assertFalse([f for f in os.listdir(d) if f.endswith(".tmp")])

    def test_bad_files(self):
        with tempfile.TemporaryDirectory() as d:
            for name, content in (("a.tsproj", "{oops"), ("b.tsproj", '{"hello": 1}'),
                                  ("c.tsproj", '{"format":"telescore-project","version":99}')):
                path = os.path.join(d, name)
                with open(path, "w") as fh:
                    fh.write(content)
                with self.subTest(name=name), self.assertRaises(ProjectError):
                    Project.load(path)

    def test_atomic_write_replaces(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "x.txt")
            atomic_write_text(path, "one")
            atomic_write_text(path, "two")
            with open(path) as fh:
                self.assertEqual(fh.read(), "two")
            self.assertEqual(os.listdir(os.path.dirname(path)), ["x.txt"])


if __name__ == "__main__":
    unittest.main()


class RefactorTests(unittest.TestCase):
    def test_rename_everywhere(self):
        from telescore.core.refactor import field_references, rename_field_everywhere
        p = PRESETS["Hockey"]()
        self.assertIn("Button “Home minor”", field_references(p, "home.penalties"))
        n = rename_field_everywhere(p, "home.penalties", "home.pen")
        self.assertGreater(n, 0)
        keys = set(p.engine.snapshot().values)
        for b in p.boards:
            self.assertEqual(b.missing_keys(keys), [])
        txt = next(e.text for e in p.boards[0].elements if e.name == "Power play text")
        self.assertIn("{home.pen.1.time}", txt)
        rename_field_everywhere(p, "clock.game", "clock.main")
        self.assertEqual(p.engine.field("home.pen").master, "clock.main")
        for panel in p.panels:
            for btn in panel.buttons:
                p.engine.perform(btn.action, t=0)
        self.assertEqual(field_references(p, "clock.game"), [])
