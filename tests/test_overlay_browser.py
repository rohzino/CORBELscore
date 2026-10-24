"""Browser-source rendering in a real Chromium (skipped without Playwright)."""

import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.presets import PRESETS  # noqa: E402
from telescore.outputs.server import ScoreServer, ServerData  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

SHOTS = os.environ.get("TELESCORE_SHOTS", "")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipIf(sync_playwright is None, "Playwright is not installed")
class OverlayBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def serve(self, preset):
        proj = PRESETS[preset]()
        eng = proj.engine
        data = ServerData(eng.snapshot, eng.submit)
        data.set_boards([b.to_dict() for b in proj.boards])
        self.server_data = data
        server = ScoreServer(data)
        port = free_port()
        self.assertTrue(server.start(port))
        eng.on_change(server.publish)
        stop = threading.Event()

        def pump():
            while not stop.is_set():
                eng.tick()
                time.sleep(0.02)
        threading.Thread(target=pump, daemon=True).start()
        self.addCleanup(lambda: (stop.set(), server.stop()))
        return proj, port

    def overflowing(self, page):
        return page.evaluate("""() => [...document.querySelectorAll('.el')].filter(n => n.style.display !== 'none')
            .map(n => { const t = n.querySelector('.t'); if (!t || !t.textContent) return null;
                        const r = t.getBoundingClientRect(), b = n.getBoundingClientRect();
                        return (r.width > b.width + 1 || r.height > b.height + 1) ? t.textContent : null; })
            .filter(Boolean)""")

    def test_every_preset_renders_without_overflow(self):
        for preset in PRESETS:
            if preset == "Blank project":
                continue
            with self.subTest(preset=preset):
                proj, port = self.serve(preset)
                proj.engine.submit({"do": "set", "field": "home.name", "value": "Fells Point Longshoremen"})
                for b in proj.boards:
                    page = self.browser.new_page(viewport={"width": b.width, "height": b.height})
                    page.goto(f"http://127.0.0.1:{port}/board/{b.id}?bg=black")
                    page.wait_for_function("document.fonts.status === 'loaded'")
                    page.wait_for_timeout(400)
                    self.assertEqual(self.overflowing(page), [], f"{preset}/{b.name}")
                    family = page.evaluate("getComputedStyle(document.querySelector('.t')).fontFamily")
                    self.assertIn("Archivo", family)
                    if SHOTS:
                        os.makedirs(SHOTS, exist_ok=True)
                        page.screenshot(path=os.path.join(SHOTS, f"{preset}-{b.name}.png".replace(" ", "_")))
                    page.close()

    def test_live_updates_and_show_when(self):
        proj, port = self.serve("Hockey")
        bug = proj.boards[0]
        page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{port}/board/{bug.id}")
        page.wait_for_function("document.fonts.status === 'loaded'")
        texts = lambda: page.evaluate("[...document.querySelectorAll('.t')].map(t => t.textContent)")  # noqa: E731
        page.wait_for_timeout(300)
        self.assertIn("20:00", texts())
        pp_box = page.locator(".el").nth([e.name for e in bug.elements].index("Power play"))
        self.assertFalse(pp_box.is_visible())
        proj.engine.submit({"do": "add", "field": "home.score", "amount": 4})
        proj.engine.submit({"do": "toggle", "field": "home.pp"})
        proj.engine.submit({"do": "start", "field": "clock.game"})
        page.wait_for_function("[...document.querySelectorAll('.t')].some(t => t.textContent === '4')", timeout=3000)
        self.assertTrue(pp_box.is_visible())
        page.wait_for_function("[...document.querySelectorAll('.t')].some(t => t.textContent === '19:59')",
                               timeout=3000)
        # colour templates: the home colour strip follows {home.color}
        proj.engine.submit({"do": "set", "field": "home.color", "value": "#ff0000"})
        idx = [e.name for e in bug.elements].index("Home colour")
        page.wait_for_function(f"getComputedStyle(document.querySelectorAll('.el')[{idx}]).backgroundColor"
                               " === 'rgb(255, 0, 0)'", timeout=3000)
        page.close()

    def test_js_matches_python(self):
        """Easing, animation samples, rules and element text agree in both languages."""
        import json as _json
        from telescore.core.animation import BUILTIN, EASINGS, ease, element_text, sample
        from telescore.core.board import Element
        from telescore.core.logic import apply_rules
        proj, port = self.serve("General scoreboard")
        page = self.browser.new_page()
        page.goto(f"http://127.0.0.1:{port}/board/{proj.boards[0].id}")
        page.wait_for_function("window.__ts !== undefined")
        xs = [i / 20 for i in range(21)]
        for name in EASINGS:
            js = page.evaluate(f"[{','.join(map(str, xs))}].map(x => __ts.ease({_json.dumps(name)}, x))")
            for x, v in zip(xs, js):
                self.assertAlmostEqual(v, ease(name, x), places=5, msg=f"{name} at {x}")
        for a in BUILTIN:
            d = _json.dumps(a.to_dict())
            for ms in (0, 50, a.duration * 0.37, a.duration / 2, a.duration, a.total + 5):
                js = page.evaluate(f"__ts.sample({d}, {ms})")
                py = sample(a, ms)
                for k in ("opacity", "x", "y", "scale"):
                    self.assertAlmostEqual(js[k], py[k], places=5, msg=f"{a.name} {k} at {ms}")
                for j, c in enumerate(py["clip"]):
                    self.assertAlmostEqual(js["clip"][j], c, places=5)
        cases = [("0.0=Final|2:00=Two-minute Warning!", "2:00"), ("NULL=—", ""), ("0:0*=UNDER", "0:07"),
                 ("1={value}st", "1"), (r"a\=b=c\|d", "a=b"), ("[1]=one", "[1]"), ("x=y", "z"), ("a.b=c", "axb")]
        for rules, value in cases:
            js = page.evaluate(f"__ts.applyRules({_json.dumps(rules)}, {_json.dumps(value)})")
            self.assertEqual(js, apply_rules(rules, value), f"{rules} on {value}")
        el = Element(text="{c}", rules="0:00=FINAL")
        for vals, fx in (({"c": "0:00"}, {}), ({"c": "1:00"}, {"rule": "1:00=ONE"}), ({"c": "2"}, {})):
            page.evaluate(f"(() => {{ values = {_json.dumps(vals)}; }})()")
            js = page.evaluate(f"__ts.elementText({_json.dumps(dict(el.to_dict(), rules=el.rules))}, "
                               f"{_json.dumps(fx)})")
            self.assertEqual(js, element_text(el, vals, fx))
        page.close()

    def test_condition_driven_animation(self):
        from telescore.core.board import Element
        from telescore.core.logic import Condition
        proj, port = self.serve("Hockey")
        bug = proj.boards[0]
        tag = Element(kind="box", name="Goal tag", x=100, y=100, w=200, h=60, fill="#ff0000", visible=True,
                      anim_in="Fly in from left")
        bug.elements.append(tag)
        proj.engine.set_conditions([
            Condition(principal="home.score", op="changes", target=tag.id, action="show", arg="3000"),
            Condition(principal="home.score", op="equals", value="0", target=tag.id, action="hide", arg="*"),
        ])
        # the server reads boards at request time from its data object
        self.server_data.set_boards([b.to_dict() for b in proj.boards])
        page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(f"http://127.0.0.1:{port}/board/{bug.id}")
        page.wait_for_timeout(300)
        node = page.locator(f'.el[data-id="{tag.id}"]')
        self.assertFalse(node.is_visible())
        proj.engine.submit({"do": "add", "field": "home.score"})
        page.wait_for_function(f"document.querySelector('.el[data-id=\"{tag.id}\"]').style.transform"
                               ".includes('translate(-')", timeout=3000)
        page.wait_for_timeout(700)
        self.assertTrue(node.is_visible())
        self.assertIn(node.evaluate("n => n.style.transform"), ("", "none"))
        page.wait_for_timeout(2800)                        # shown for 3 s, then hidden
        self.assertFalse(node.is_visible())
        page.close()

    def test_scales_to_any_window(self):
        proj, port = self.serve("General scoreboard")
        b = proj.boards[1]
        page = self.browser.new_page(viewport={"width": 960, "height": 540})
        page.goto(f"http://127.0.0.1:{port}/board/{b.id}")
        box = page.locator("#stage").bounding_box()
        self.assertAlmostEqual(box["width"], 960, delta=1)
        self.assertAlmostEqual(box["height"], 540, delta=1)
        page.close()


if __name__ == "__main__":
    unittest.main()
