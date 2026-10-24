"""Rules, overrides, conditions, live sources and animations (engine side)."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.animation import BUILTIN, Animation, Tracker, ease, element_text, library, sample  # noqa: E402
from telescore.core.board import Board, Element  # noqa: E402
from telescore.core.clock import Clock  # noqa: E402
from telescore.core.engine import FX_KEY, Engine  # noqa: E402
from telescore.core.fields import ChoiceField, ClockField, CounterField, TextField, ToggleField  # noqa: E402
from telescore.core.logic import Condition, apply_rules, compare_value, parse_rules  # noqa: E402
from telescore.core.presets import PRESETS  # noqa: E402
from telescore.core.project import Project  # noqa: E402
from telescore.outputs.formats import xml_fields  # noqa: E402


class RuleTests(unittest.TestCase):
    def test_sportzsuite_examples(self):
        rules = "0.0=Final|2:00=Two-minute Warning!"
        self.assertEqual(apply_rules(rules, "0.0"), "Final")
        self.assertEqual(apply_rules(rules, "2:00"), "Two-minute Warning!")
        self.assertIsNone(apply_rules(rules, "1:59"))
        self.assertEqual(apply_rules("1=Joe|2=John|3=Bob", "2"), "John")

    def test_extras(self):
        self.assertEqual(apply_rules("NULL=—", ""), "—")
        self.assertEqual(apply_rules("0:0*=UNDER 10", "0:07"), "UNDER 10")
        self.assertEqual(apply_rules("1={value}st|2={value}nd", "2"), "2nd")
        self.assertEqual(apply_rules(r"a\=b=c\|d", "a=b"), "c|d")
        self.assertEqual(parse_rules("x=|=y|bad|k=v=w"), [("x", ""), ("", "y"), ("k", "v=w")])
        self.assertEqual(apply_rules("[1]=one", "[1]"), "one")       # brackets are literal

    def test_compare(self):
        self.assertTrue(compare_value("equals", "F", "F", None))
        self.assertTrue(compare_value("equals", "", "NULL", None))
        self.assertTrue(compare_value("less", "0:59", "1:00", None))     # times compare as seconds
        self.assertTrue(compare_value("greater", "34.5", "30", None))
        self.assertTrue(compare_value("changes_by", "2", "-1", "3"))     # timeouts 3 -> 2
        self.assertFalse(compare_value("changes_by", "2", "-1", None))
        self.assertTrue(compare_value("changes", "a", "", "b"))
        self.assertFalse(compare_value("greater", "2nd", "1", None))     # not a number: never true


def engine():
    return Engine([
        ClockField("clock.game", "Game", clock=Clock(initial_ms=120_000, fmt="m:ss")),
        CounterField("home.score"), CounterField("home.timeouts", value=3),
        TextField("flag", value=""), ChoiceField("half", options=["T", "B"]),
        TextField("atbat", value="1"), ToggleField("home.flash", on_text="1"),
    ])


class OverrideAndRuleTests(unittest.TestCase):
    def test_pipeline_order_reaches_xml(self):
        e = engine()
        f = e.field("clock.game")
        f.rules = "2:00=Two-minute warning"
        e.publish(force=True)
        self.assertEqual(e.snapshot().values["clock.game"], "Two-minute warning")
        self.assertEqual(e.snapshot().base["clock.game"], "2:00")
        f.override, f.override_on = "HALFTIME", True
        e.publish(force=True)
        self.assertEqual(e.snapshot().values["clock.game"], "HALFTIME")   # override beats rules
        self.assertIn('key="clock.game"', xml_fields(e.snapshot()))
        self.assertIn(">HALFTIME</field>", xml_fields(e.snapshot()))
        f.override_on = False
        e.publish(force=True)
        self.assertEqual(e.snapshot().values["clock.game"], "Two-minute warning")

    def test_live_source_wins_over_own_value(self):
        e = engine()
        e.field("home.score").source = "HomeScore"
        e.field("clock.game").source = "Clock"
        e.feed({"HomeScore": "21", "Clock": "4:07", "ClockStatus": "R"})
        e.tick(0)
        s = e.snapshot()
        self.assertEqual(s.values["home.score"], "21")
        self.assertEqual(s.raw["home.score"], 21)
        self.assertEqual(s.values["clock.game"], "4:07")
        self.assertEqual(s.raw["clock.game"], 247_000)
        self.assertEqual(s.values["clock.game.running"], "1")
        self.assertEqual(s.live, {"home.score", "clock.game"})
        e.perform({"do": "add", "field": "home.score", "amount": 3}, t=0)   # the bot stays in charge
        self.assertEqual(e.snapshot().values["home.score"], "21")
        e.field("home.score").override, e.field("home.score").override_on = "0", True
        e.publish(force=True)
        self.assertEqual(e.snapshot().values["home.score"], "0")

    def test_persisted(self):
        p = PRESETS["Basketball"]()
        f = p.engine.field("home.score")
        f.source, f.rules, f.override, f.override_on = "HomeScore", "0=—", "TBD", True
        p.engine.set_conditions([Condition(principal="home.score", op="changes", target="x", action="animate",
                                           arg="Pulse")])
        p.animations.append(Animation(name="Mine", kind="in", duration=500, x=-40))
        p.source.kind, p.source.bot = "mqtt", 175
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.tsproj")
            p.save(path)
            with open(path) as fh:
                data = json.load(fh)
            self.assertNotIn("token", json.dumps(data["source"]))    # secrets stay out of project files
            q = Project.load(path)
        g = q.engine.field("home.score")
        self.assertEqual((g.source, g.rules, g.override, g.override_on), ("HomeScore", "0=—", "TBD", True))
        self.assertEqual(q.engine.logic.conditions[0].arg, "Pulse")
        self.assertEqual(q.animations[0].x, -40)
        self.assertEqual((q.source.kind, q.source.bot), ("mqtt", 175))


class ConditionTests(unittest.TestCase):
    def test_show_hide_converse_pair(self):
        """SportzSuite: If flag1 has value F then rect2 show *; if not F then hide *."""
        e = engine()
        e.set_conditions([
            Condition(principal="flag", op="equals", value="F", target="rect2", action="show", arg="*"),
            Condition(principal="flag", op="not_equals", value="F", target="rect2", action="hide", arg="*"),
        ])
        self.assertFalse(e.snapshot().fx["rect2"]["visible"])        # evaluated once at the start
        seen = []
        e.on_change(lambda s, c: seen.append(c))
        e.perform({"do": "set", "field": "flag", "value": "F"}, t=1)
        self.assertTrue(e.snapshot().fx["rect2"]["visible"])
        self.assertIn(FX_KEY, seen[-1])
        e.perform({"do": "set", "field": "flag", "value": ""}, t=2)
        self.assertFalse(e.snapshot().fx["rect2"]["visible"])

    def test_timed_show_and_show_once(self):
        e = engine()
        e.set_conditions([
            Condition(principal="home.score", op="changes", target="goal", action="show", arg="5000"),
            Condition(principal="home.score", op="greater", value="0", target="first", action="show_once",
                      arg="2000"),
        ])
        e.perform({"do": "add", "field": "home.score"}, t=10)
        fx = e.snapshot().fx
        self.assertTrue(fx["goal"]["visible"])
        self.assertTrue(fx["first"]["visible"])
        e.tick(13)
        self.assertFalse(e.snapshot().fx["first"]["visible"])         # 2 s later
        self.assertTrue(e.snapshot().fx["goal"]["visible"])
        e.perform({"do": "add", "field": "home.score"}, t=14)         # still > 0: show once does not refire
        e.tick(14.5)
        self.assertFalse(e.snapshot().fx["first"]["visible"])
        e.tick(19.1)
        self.assertFalse(e.snapshot().fx["goal"]["visible"])           # 5 s after the second goal

    def test_conditional_rule_batter_names(self):
        """SportzSuite example: topbottom decides which lineup turns numbers into names."""
        e = engine()
        e.set_conditions([
            Condition(principal="half", op="equals", value="T", target_kind="field", target="atbat",
                      action="rule", arg="1=Joe|2=John"),
            Condition(principal="half", op="equals", value="B", target_kind="field", target="atbat",
                      action="rule", arg="1=Dirk|2=Luca"),
        ])
        self.assertEqual(e.snapshot().values["atbat"], "Joe")
        e.perform({"do": "set", "field": "half", "value": "B"}, t=1)
        self.assertEqual(e.snapshot().values["atbat"], "Dirk")
        e.perform({"do": "set", "field": "atbat", "value": "2"}, t=2)
        self.assertEqual(e.snapshot().values["atbat"], "Luca")
        e.field("atbat").rules = "2=Plain rule wins"                 # a plain rule beats a conditional one
        e.publish(force=True)
        self.assertEqual(e.snapshot().values["atbat"], "Plain rule wins")

    def test_changes_by_with_finish(self):
        """Timeout swap: on timeouts changing by -1, tween out, then back after 4 s."""
        e = engine()
        e.set_conditions([Condition(principal="home.timeouts", op="changes_by", value="-1", target="g1",
                                    action="animate", arg="Wipe out downward", finish_ms=4000,
                                    finish="animate:Wipe in downward")])
        e.perform({"do": "add", "field": "home.timeouts", "amount": -1}, t=5)
        a1 = e.snapshot().fx["g1"]["anim"]
        self.assertEqual(a1["name"], "Wipe out downward")
        e.tick(9.1)
        a2 = e.snapshot().fx["g1"]["anim"]
        self.assertEqual(a2["name"], "Wipe in downward")
        self.assertGreater(a2["id"], a1["id"])
        e.perform({"do": "add", "field": "home.timeouts", "amount": 1}, t=10)   # +1 does not fire
        self.assertEqual(e.snapshot().fx["g1"]["anim"]["id"], a2["id"])

    def test_field_actions_reach_outputs(self):
        e = engine()
        e.set_conditions([
            Condition(principal="home.score", op="changes", target_kind="field", target="home.flash",
                      action="pulse", arg="3000"),
            Condition(principal="clock.game", op="equals", value="0:00", target_kind="field", target="flag",
                      action="set", arg="FINAL"),
            Condition(principal="flag", op="equals", value="FINAL", target_kind="field", target="",
                      action="action", run={"do": "next", "field": "half"}),
        ])
        e.perform({"do": "add", "field": "home.score"}, t=0)
        e.tick(0.1)
        self.assertEqual(e.snapshot().values["home.flash"], "1")
        e.tick(3.2)
        e.tick(3.3)
        self.assertEqual(e.snapshot().values["home.flash"], "")
        e.perform({"do": "set", "field": "clock.game", "value": "0"}, t=4)
        e.tick(4.1)
        e.tick(4.2)
        e.tick(4.3)
        s = e.snapshot()
        self.assertEqual(s.values["flag"], "FINAL")
        self.assertEqual(s.values["half"], "B")                      # condition chain ran the action
        self.assertFalse(e.can_undo() and e._undo[-1][0][0] == "flag")  # automation is not an undo step

    def test_bad_action_is_reported_not_raised(self):
        e = engine()
        e.set_conditions([Condition(principal="home.score", op="changes", target_kind="field", target="nope",
                                    action="set", arg="x")])
        e.perform({"do": "add", "field": "home.score"}, t=0)
        e.tick(0.1)
        self.assertTrue(e.logic_errors)

    def test_condition_validation(self):
        with self.assertRaises(ValueError):
            Condition.from_dict({"principal": "a", "op": "bigger", "target": "x", "action": "show"})
        with self.assertRaises(ValueError):
            Condition.from_dict({"principal": "a", "op": "equals", "target_kind": "field", "target": "x",
                                 "action": "font"})


class AnimationTests(unittest.TestCase):
    def test_easing_endpoints_and_shape(self):
        for name in ("linear", "ease", "ease-in", "ease-out", "ease-in-out", "broadcast", "back-out", "bounce-out"):
            self.assertAlmostEqual(ease(name, 0), 0, places=6)
            self.assertAlmostEqual(ease(name, 1), 1, places=6)
        self.assertAlmostEqual(ease("linear", 0.37), 0.37, places=5)
        self.assertGreater(max(ease("back-out", x / 50) for x in range(51)), 1.0)   # overshoot

    def test_sample(self):
        a = library()["Fly in from left"]
        self.assertEqual(sample(a, 0)["x"], -260)
        self.assertEqual(sample(a, a.duration)["x"], 0)
        w = library()["Wipe in from left"]
        self.assertEqual(sample(w, 0)["clip"], (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(sample(w, w.duration)["clip"], (0.0, 0.0, 1.0, 1.0))
        o = library()["Fade out"]
        self.assertEqual(sample(o, o.duration)["opacity"], 0)
        f = library()["Flash"]
        self.assertAlmostEqual(sample(f, f.duration / 2)["opacity"], f.opacity)  # peak
        self.assertEqual(sample(f, f.duration * f.repeat + 1)["opacity"], 1.0)  # back to normal
        d = Animation(name="d", kind="in", duration=100, delay=200, x=50)
        self.assertEqual(sample(d, 150)["x"], 50)        # holds the start look during the delay

    def test_builtins_valid_and_named_uniquely(self):
        names = [a.name for a in BUILTIN]
        self.assertEqual(len(names), len(set(names)))
        for a in BUILTIN:
            Animation.from_dict(a.to_dict())

    def test_tracker_triggers(self):
        el = Element(id="pp", kind="text", text="{home.pp}", show_when="home.pp", anim_in="Slide in from left",
                     anim_out="Slide out to left", anim_change="Pulse")
        b = Board(elements=[el])
        tr = Tracker(b)
        tr.update({"home.pp": ""}, {}, 0.0)
        self.assertIsNone(tr.look(el, 0.0))
        tr.update({"home.pp": "PP"}, {}, 1.0)
        mid = tr.look(el, 1.1)
        self.assertLess(mid["x"], 0)
        self.assertEqual(tr.look(el, 2.0)["x"], 0)
        tr.update({"home.pp": "PP 1:59"}, {}, 3.0)          # text change: emphasis
        self.assertGreater(tr.look(el, 3.2)["scale"], 1.0)
        tr.update({"home.pp": ""}, {}, 4.0)                 # hidden: out animation, then gone
        self.assertIsNotNone(tr.look(el, 4.1))
        self.assertIsNone(tr.look(el, 5.0))
        self.assertFalse(tr.active(5.0))
        # a condition's Animate
        tr.update({"home.pp": ""}, {"pp": {"anim": {"name": "Pop in", "id": 7}}}, 6.0)
        self.assertIsNotNone(tr.look(el, 6.1))

    def test_element_text_rules(self):
        e = Element(text="{c}", rules="0:00=FINAL")
        self.assertEqual(element_text(e, {"c": "0:00"}), "FINAL")
        self.assertEqual(element_text(e, {"c": "1:00"}, {"rule": "1:00=ONE"}), "ONE")
        self.assertEqual(element_text(e, {"c": "0:00"}, {"rule": "0:00=LOSES"}), "FINAL")


if __name__ == "__main__":
    unittest.main()
