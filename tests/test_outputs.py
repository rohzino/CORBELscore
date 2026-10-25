"""Feeds, file writer and web server. Uses lxml only when available (XSD check)."""

import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.clock import Clock  # noqa: E402
from telescore.core.engine import Engine  # noqa: E402
from telescore.core.fields import ClockField, CounterField, PenaltyField, TextField, ToggleField  # noqa: E402
from telescore.core.presets import PRESETS  # noqa: E402
from telescore.core.project import OutputSettings  # noqa: E402
from telescore.outputs.formats import (text_filename, xml_fields, xml_flat, xml_name,  # noqa: E402
                                       xml_nested, state_json)
from telescore.outputs.manager import OutputManager  # noqa: E402
from telescore.outputs.overlay import overlay_html  # noqa: E402
from telescore.outputs.server import ScoreServer, ServerData  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from lxml import etree as LX
except ImportError:  # pragma: no cover
    LX = None


def engine():
    return Engine([
        TextField("home.name", value='Hawks & "Owls" <A>'),
        CounterField("home.score", value=3),
        ClockField("clock.game", clock=Clock(initial_ms=247_300, fmt="m:ss")),
        PenaltyField("home.penalties", master="clock.game", slots=2,
                     entries=[{"player": "#12", "ms": 90_000}]),
        ToggleField("home.pp", value=True, on_text="PP"),
        TextField("set", value="2"),             # a key that is an XML-hostile word
        TextField("x1.ctrl", value="bad\x07char"),
    ])


class FormatTests(unittest.TestCase):
    def test_nested(self):
        snap = engine().snapshot()
        doc = ET.fromstring(xml_nested(snap))
        self.assertEqual(doc.tag, "telescore")
        self.assertEqual(doc.findtext("home/name"), 'Hawks & "Owls" <A>')
        self.assertEqual(doc.findtext("home/score"), "3")
        game = doc.find("clock/game")
        self.assertEqual(game.text, "4:08")
        self.assertEqual(game.get("running"), "0")
        pen = doc.find("home/penalties")
        self.assertEqual((pen.text, pen.get("p1_player"), pen.get("p1_time"), pen.get("p2_time")),
                         ("1", "#12", "1:30", ""))
        self.assertEqual("".join(game.itertext()), "4:08")   # string() is just the value
        self.assertEqual(doc.findtext("x1/ctrl"), "badchar")  # control characters dropped

    def test_flat_is_one_row(self):
        snap = engine().snapshot()
        doc = ET.fromstring(xml_flat(snap))
        rows = doc.findall("row")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].findtext("home_score"), "3")
        self.assertEqual(rows[0].findtext("home_penalties_1_time"), "1:30")
        self.assertEqual(len(rows[0]), len(snap.values))

    def test_fields_feed_validates(self):
        snap = engine().snapshot()
        text = xml_fields(snap)
        doc = ET.fromstring(text)
        got = {f.get("key"): f.text or "" for f in doc}
        want = dict(snap.values, **{"x1.ctrl": "badchar"})   # XML-illegal control char dropped
        self.assertEqual(got, want)
        clock = doc.find("field[@key='clock.game']")
        self.assertEqual(clock.get("raw"), "247300")
        if LX is not None:
            schema = LX.XMLSchema(LX.parse(os.path.join(ROOT, "docs", "schema", "fields.xsd")))
            schema.assertValid(LX.fromstring(text.encode("utf-8")))

    def test_every_preset_feeds_parse(self):
        for name, make in PRESETS.items():
            snap = make().engine.snapshot()
            with self.subTest(preset=name):
                for fn in (xml_nested, xml_flat, xml_fields):
                    ET.fromstring(fn(snap))
                json.loads(state_json(snap))

    def test_names(self):
        self.assertEqual(xml_name("1"), "_1")
        self.assertEqual(xml_name("xmlish"), "_xmlish")
        self.assertEqual(xml_name("a-b"), "a-b")
        self.assertEqual(text_filename("con"), "_con.txt")
        self.assertEqual(text_filename("home.score"), "home.score.txt")


class ManagerTests(unittest.TestCase):
    def test_writes_files_and_only_changes(self):
        e = engine()
        with tempfile.TemporaryDirectory() as d:
            m = OutputManager(OutputSettings(folder=d), "Test")
            e.on_change(m.submit)
            m.submit(e.snapshot())
            self.assertTrue(m.flush())
            tdir = os.path.join(d, "text")
            with open(os.path.join(tdir, "home.score.txt"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "3")
            for f in ("telescore.xml", "vmix.xml", "fields.xml", "state.json"):
                self.assertTrue(os.path.isfile(os.path.join(d, f)), f)
            stamp = os.stat(os.path.join(tdir, "home.name.txt")).st_mtime_ns
            time.sleep(0.05)
            e.perform({"do": "add", "field": "home.score", "amount": 1})
            self.assertTrue(m.flush())
            with open(os.path.join(tdir, "home.score.txt")) as fh:
                self.assertEqual(fh.read(), "4")
            self.assertEqual(os.stat(os.path.join(tdir, "home.name.txt")).st_mtime_ns, stamp)
            self.assertEqual(m.status["text"].state, "ok")
            self.assertFalse([f for f in os.listdir(tdir) if f.endswith(".tmp")])
            m.close()

    def test_bad_folder_reports_error(self):
        with tempfile.NamedTemporaryFile() as f:          # a file where a folder should be
            m = OutputManager(OutputSettings(folder=f.name), "Test")
            m.submit(engine().snapshot())
            m.flush()
            self.assertEqual(m.status["text"].state, "error")
            self.assertIn("Pick another folder", m.status["text"].detail)
            m.close()

    def test_burst_coalesces(self):
        e = engine()
        with tempfile.TemporaryDirectory() as d:
            m = OutputManager(OutputSettings(folder=d, text_enabled=False, json_enabled=False), "T", max_rate=10)
            e.on_change(m.submit)
            for _ in range(200):
                e.perform({"do": "add", "field": "home.score"})
            m.flush()
            self.assertLess(m.status["xml"].writes, 20)
            self.assertEqual(ET.parse(os.path.join(d, "fields.xml")).getroot()
                             .find("field[@key='home.score']").text, "203")
            m.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.e = PRESETS["Basketball"]()
        self.engine = self.e.engine
        self.stop = threading.Event()
        data = ServerData(self.engine.snapshot, self.engine.submit)
        data.set_boards([b.to_dict() for b in self.e.boards])
        self.logo = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self.logo.write(b"\x89PNG\r\n\x1a\nfake")
        self.logo.close()
        data.set_assets([self.logo.name])
        self.data = data
        self.server = ScoreServer(data)
        self.port = free_port()
        self.assertTrue(self.server.start(self.port))
        self.engine.on_change(self.server.publish)

        def pump():                                      # stands in for the Qt timer
            while not self.stop.is_set():
                self.engine.tick()
                time.sleep(0.02)
        self.pumper = threading.Thread(target=pump, daemon=True)
        self.pumper.start()

    def tearDown(self):
        self.stop.set()
        self.server.stop()
        os.unlink(self.logo.name)

    def get(self, path, data=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "")
                text = body.decode("utf-8") if ("text" in ctype or "json" in ctype or "xml" in ctype) else body
                return r.status, text, r.headers
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode("utf-8"), e.headers

    def test_pages_and_feeds(self):
        code, body, _ = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("/board/" + self.e.boards[0].id, body)
        code, body, h = self.get("/vmix.xml")
        self.assertEqual(code, 200)
        self.assertIn("xml", h["Content-Type"])
        ET.fromstring(body)
        code, body, _ = self.get("/board/" + self.e.boards[0].id)
        self.assertIn("EventSource", body)
        code, body, _ = self.get("/board/nope")
        self.assertEqual(code, 404)
        code, body, _ = self.get("/api/fields")
        self.assertIn("clock.shot", [f["key"] for f in json.loads(body)])
        code, _, h = self.get("/fonts/Archivo.ttf")
        self.assertEqual((code, h["Content-Type"]), (200, "font/ttf"))

    def test_actions_get_and_post(self):
        code, body, _ = self.get("/api/action?do=add&field=home.score&amount=3")
        self.assertEqual((code, json.loads(body)), (200, {"ok": True}))
        code, body, _ = self.get("/api/action", data=json.dumps({"do": "add", "field": "home.score",
                                                                  "amount": 2}).encode(),
                                 headers={"Content-Type": "application/json"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(self.get("/state.json")[1])["values"]["home.score"], "5")
        code, body, _ = self.get("/api/action?do=add&field=nothing")
        self.assertEqual(code, 400)
        self.assertIn("no field", json.loads(body)["error"])
        code, body, _ = self.get("/api/action?do=add&field=home.score&amount=lots")
        self.assertEqual(code, 400)

    def test_busy_app_withdraws_the_action(self):
        """A 504 means "did not run", so a Stream Deck retry can never score twice."""
        self.stop.set()                                   # the app stops ticking (busy)
        self.pumper.join()
        before = self.engine.snapshot().values["home.score"]
        code, body, _ = self.get("/api/action?do=add&field=home.score&amount=3")
        self.assertEqual(code, 504)
        self.assertIn("safe to try again", json.loads(body)["error"])
        self.engine.tick()                                # the app catches up later...
        self.assertEqual(self.engine.snapshot().values["home.score"], before)   # ...and does not score late

    def test_token(self):
        self.data.token = "s3cret"
        self.assertEqual(self.get("/api/action?do=undo")[0], 403)
        self.assertEqual(self.get("/api/action?do=undo&token=s3cret")[0], 200)
        self.assertEqual(self.get("/api/action?do=undo", headers={"X-TeleScore-Token": "s3cret"})[0], 200)
        self.assertEqual(self.get("/state.json")[0], 200)      # reading stays open

    def test_assets_are_limited(self):
        from urllib.parse import quote
        code, body, _ = self.get("/asset?path=" + quote(self.logo.name))
        self.assertEqual(code, 200)
        code, _, _ = self.get("/asset?path=" + quote(os.path.abspath(__file__)))
        self.assertEqual(code, 403)
        code, _, _ = self.get("/asset?path=" + quote("../../etc/passwd"))
        self.assertEqual(code, 403)

    def test_events_stream(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        sock.sendall(b"GET /events HTTP/1.1\r\nHost: x\r\n\r\n")
        buf = b""
        deadline = time.time() + 5
        while b"event: full" not in buf and time.time() < deadline:
            buf += sock.recv(65536)
        self.assertIn(b"event: full", buf)
        self.engine.submit({"do": "add", "field": "away.score", "amount": 2})
        while b"event: diff" not in buf and time.time() < deadline:
            buf += sock.recv(65536)
        tail = buf.split(b"event: diff", 1)[1]
        while b"\n\n" not in tail and time.time() < deadline:
            more = sock.recv(65536)
            buf += more
            tail += more
        payload = json.loads(tail.split(b"data: ", 1)[1].split(b"\n", 1)[0])
        self.assertEqual(payload, {"away.score": "2"})
        sock.close()

    def test_port_in_use(self):
        other = ScoreServer(self.data)
        self.assertFalse(other.start(self.port))
        self.assertIn("in use", other.error)


class OverlayTests(unittest.TestCase):
    def test_defaults_match_element(self):
        """The page fills in defaults that Element.to_dict() leaves out."""
        import re
        from dataclasses import fields
        from telescore.core.board import Element
        page = overlay_html({"name": "x", "width": 10, "height": 10, "elements": []})
        block = re.search(r"const D = \{(.*?)\};", page, re.S).group(1)
        js = dict(re.findall(r"(\w+):(\"[^\"]*\"|[\w.]+)", block))
        e = Element()
        for f in fields(Element):
            if f.name in ("kind", "id", "name", "locked"):
                continue
            with self.subTest(field=f.name):
                self.assertIn(f.name, js)
                want = getattr(e, f.name)
                got = json.loads(js[f.name]) if js[f.name] not in ("true", "false") else js[f.name] == "true"
                self.assertEqual(got, want)

    def test_script_injection_is_escaped(self):
        page = overlay_html({"name": "<b>", "width": 10, "height": 10,
                             "elements": [{"kind": "text", "text": "</script><script>alert(1)</script>"}]})
        self.assertNotIn("</script><script>alert", page)
        self.assertIn("&lt;b&gt;", page)


if __name__ == "__main__":
    unittest.main()
