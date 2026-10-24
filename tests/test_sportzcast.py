"""Sportzcast live data: parsers, a fake MQTT broker, a fake legacy socket, LiveXML files."""

import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telescore.core.presets import PRESETS  # noqa: E402
from telescore.core.sportzcast import (SourceSettings, SportzcastSource, flatten_json, flatten_xml,  # noqa: E402
                                       mqtt_decode_length, mqtt_encode_length, parse_payload, split_frames,
                                       suggest)

# Field names from the Sportzcast base contract (docs.sportzcast.net)
CONTRACT = {"OriginTypeId": 2, "OriginType": "Cloud", "Clock": "4:07", "FullClock": "4:07.0", "ClockStatus": "R",
            "EventId": 3, "BotNumber": 175, "GuestTeamName": "GUEST", "HomeTeamName": "HOME",
            "HomeScore": 42, "GuestScore": 30, "Period": 2}
# LiveXML shape as shown in the OBS "XML Data Bridge" resource
LIVEXML = """<?xml version="1.0" encoding="utf-8"?>
<info><Hscore>42</Hscore><Vscore>30</Vscore><possession>H</possession>
<Htimeouts>4</Htimeouts><Vtimeouts>3</Vtimeouts><down>2</down><downtext>2nd</downtext></info>"""


class ParserTests(unittest.TestCase):
    def test_flatten(self):
        self.assertEqual(flatten_json({"a": {"b": 1}, "c": [5, None], "d": True, "e": 2.0}),
                         {"a.b": "1", "c.0": "5", "c.1": "", "d": "1", "e": "2"})
        x = flatten_xml(LIVEXML)
        self.assertEqual((x["Hscore"], x["downtext"]), ("42", "2nd"))
        x = flatten_xml('<r xmlns="urn:x"><t a="1"><v>1</v><v>2</v></t></r>')
        self.assertEqual(x, {"t_a": "1", "t.v.1": "1", "t.v.2": "2"})
        self.assertEqual(parse_payload(json.dumps(CONTRACT).encode())["HomeScore"], "42")
        self.assertEqual(parse_payload(b"\xef\xbb\xbf" + LIVEXML.encode())["Vscore"], "30")
        self.assertEqual(parse_payload(b"12|34|R")["field2"], "34")
        with self.assertRaises(ValueError):
            parse_payload(b"hello")

    def test_framing(self):
        frames, rest = split_frames(b"junk\x02one\x03\x02two\x03\x02thr")
        self.assertEqual((frames, rest), ([b"one", b"two"], b"\x02thr"))

    def test_mqtt_lengths(self):
        for n in (0, 127, 128, 16383, 16384, 2097151, 268435455):
            enc = mqtt_encode_length(n)
            buf = iter(enc)
            self.assertEqual(mqtt_decode_length(lambda k: bytes([next(buf)])), n)

    def test_suggest(self):
        p = PRESETS["Basketball"]()
        m = suggest(list(CONTRACT) + ["Hscore"], p.engine.fields)
        self.assertEqual(m["home.score"], "HomeScore")
        self.assertEqual(m["away.score"], "GuestScore")
        self.assertEqual(m["clock.game"], "Clock")
        self.assertEqual(m["period"], "Period")
        self.assertEqual(m["home.name"], "HomeTeamName")
        m2 = suggest(flatten_xml(LIVEXML), PRESETS["Football"]().engine.fields)
        self.assertEqual((m2["home.score"], m2["away.timeouts"], m2["down"]), ("Hscore", "Vtimeouts", "down"))


def _str(data, pos):
    n = struct.unpack("!H", data[pos:pos + 2])[0]
    return data[pos + 2:pos + 2 + n].decode(), pos + 2 + n


class FakeBroker(threading.Thread):
    """A one-client MQTT 3.1.1 broker that checks the login and publishes packets."""

    def __init__(self, user="", password="", payloads=(), qos=0):
        super().__init__(daemon=True)
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.user, self.password, self.payloads, self.qos = user, password, list(payloads), qos
        self.topic = None
        self.got_user = None
        self.pubacks = 0
        self.done = threading.Event()

    def run(self):
        conn, _ = self.srv.accept()
        conn.settimeout(5)

        def read(n):
            b = b""
            while len(b) < n:
                c = conn.recv(n - len(b))
                if not c:
                    raise OSError
                b += c
            return b

        def packet():
            h = read(1)[0]
            n = mqtt_decode_length(read)
            return h >> 4, read(n) if n else b""

        try:
            t, data = packet()
            assert t == 1
            name, pos = _str(data, 0)
            assert name == "MQTT" and data[pos] == 4
            flags = data[pos + 1]
            pos += 4
            _cid, pos = _str(data, pos)
            user = pw = ""
            if flags & 0x80:
                user, pos = _str(data, pos)
            if flags & 0x40:
                pw, pos = _str(data, pos)
            self.got_user = user
            ok = (user, pw) == (self.user, self.password)
            conn.sendall(bytes([0x20, 2, 0, 0 if ok else 4]))
            if not ok:
                return
            t, data = packet()
            assert t == 8
            self.topic, _ = _str(data, 2)
            conn.sendall(bytes([0x90, 3]) + data[:2] + b"\x00")
            for i, p in enumerate(self.payloads):
                topic = self.topic.encode()
                var = struct.pack("!H", len(topic)) + topic
                if self.qos:
                    var += struct.pack("!H", i + 1)
                body = var + p
                conn.sendall(bytes([0x30 | (self.qos << 1)]) + mqtt_encode_length(len(body)) + body)
                if self.qos:
                    t, _ = packet()
                    if t == 4:
                        self.pubacks += 1
                time.sleep(0.02)
            self.done.wait(5)
        except (OSError, AssertionError):
            pass
        finally:
            conn.close()
            self.srv.close()


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class SourceTests(unittest.TestCase):
    def run_source(self, settings, token=""):
        got, states = [], []
        src = SportzcastSource(settings, token, got.append, lambda st: states.append((st.state, st.detail)))
        src.start()
        self.addCleanup(src.stop)
        return src, got, states

    def test_mqtt_local(self):
        b = FakeBroker(payloads=[json.dumps(CONTRACT).encode(), b"not json", json.dumps({"HomeScore": 43}).encode()])
        b.start()
        src, got, states = self.run_source(SourceSettings(kind="mqtt", cloud=False, host="127.0.0.1", port=b.port,
                                                          bot=175))
        self.assertTrue(wait_for(lambda: len(got) >= 2), states)
        b.done.set()
        self.assertEqual(b.topic, "bot/175/json")
        self.assertEqual(got[0]["Clock"], "4:07")
        self.assertEqual(got[1]["HomeScore"], "43")          # a bad packet in between is skipped
        self.assertEqual(src.status.state, "live")
        self.assertEqual(src.snapshot_keys()["HomeScore"], "43")
        self.assertEqual(b.got_user, "")                      # local: no login

    def test_mqtt_login_and_qos1(self):
        b = FakeBroker(user="me@example.com", password="tok", payloads=[b'{"HomeScore": 1}'], qos=1)
        b.start()
        src, got, states = self.run_source(SourceSettings(kind="mqtt", cloud=True, host="127.0.0.1", port=b.port,
                                                          bot=9, username="me@example.com"), token="tok")
        self.assertTrue(wait_for(lambda: got), states)
        self.assertTrue(wait_for(lambda: b.pubacks == 1))
        b.done.set()

    def test_mqtt_wrong_token(self):
        b = FakeBroker(user="me@example.com", password="right")
        b.start()
        src, got, states = self.run_source(SourceSettings(kind="mqtt", cloud=True, host="127.0.0.1", port=b.port,
                                                          bot=9, username="me@example.com"), token="wrong")
        self.assertTrue(wait_for(lambda: src.status.state == "error"))
        self.assertIn("e-mail or token", src.status.detail)

    def test_cloud_needs_credentials(self):
        src, got, states = self.run_source(SourceSettings(kind="mqtt", cloud=True, bot=1))
        self.assertTrue(wait_for(lambda: src.status.state == "error"))
        self.assertIn("e-mail and access token", src.status.detail)

    def test_legacy_socket_local_stream(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        request = []

        def serve():
            c, _ = srv.accept()
            request.append(c.recv(200).decode())
            c.sendall(b"\x02" + LIVEXML.encode() + b"\x03\x02<info><Hscore>4")
            time.sleep(0.05)
            c.sendall(b"3</Hscore></info>\x03")
            time.sleep(0.5)
            c.close()
            srv.close()
        threading.Thread(target=serve, daemon=True).start()
        src, got, states = self.run_source(SourceSettings(kind="tcp", cloud=False, host="127.0.0.1", port=port,
                                                          bot=5083, data_type="xml"), token="TOK")
        self.assertTrue(wait_for(lambda: len(got) >= 2))
        self.assertEqual(request[0], "XB05083000000~TOK")
        self.assertEqual(got[0]["Vscore"], "30")
        self.assertEqual(got[1]["Hscore"], "43")              # a frame split across reads

    def test_livexml_file(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "live.xml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(LIVEXML)
        src, got, states = self.run_source(SourceSettings(kind="livexml", path=path, poll_ms=50))
        self.assertTrue(wait_for(lambda: got))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<info><Hscore>4")                        # caught mid-write: ignored
        time.sleep(0.2)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(LIVEXML.replace(">42<", ">45<"))
        self.assertTrue(wait_for(lambda: got[-1].get("Hscore") == "45"))
        self.assertTrue(all("Hscore" in g for g in got))

    def test_missing_file_and_stale(self):
        src, got, states = self.run_source(SourceSettings(kind="livexml", path="/no/such/file.xml", poll_ms=50))
        self.assertTrue(wait_for(lambda: src.status.state == "error"))
        self.assertIn("does not exist", src.status.detail)
        src.status.state, src.status.last_packet = "live", time.time() - 99
        src.s.stale_s = 30
        src.check_stale()
        self.assertEqual(src.status.state, "stale")

    def test_end_to_end_into_engine(self):
        p = PRESETS["Basketball"]()
        e = p.engine
        for fk, sk in suggest(CONTRACT, e.fields).items():
            e.field(fk).source = sk
        e.field("period").rules = "1=1st|2=2nd|3=3rd|4=4th|5=OT"
        b = FakeBroker(payloads=[json.dumps(CONTRACT).encode()])
        b.start()
        src = SportzcastSource(SourceSettings(kind="mqtt", cloud=False, host="127.0.0.1", port=b.port, bot=1),
                               "", e.feed)
        src.start()
        self.addCleanup(src.stop)
        self.assertTrue(wait_for(lambda: (e.tick(), e.snapshot().values["home.score"] == "42")[1]))
        b.done.set()
        v = e.snapshot().values
        self.assertEqual((v["away.score"], v["clock.game"], v["period"], v["clock.game.running"]),
                         ("30", "4:07", "2nd", "1"))


if __name__ == "__main__":
    unittest.main()
