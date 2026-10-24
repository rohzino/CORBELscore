"""
Live scoreboard data from Sportzcast.

Sportzcast reads a venue's scoreboard controller (Daktronics, Nevco, ...)
through a ScoreLink/ScoreConnect "bot" and republishes it. TeleScore can take
that data four ways, all standard library, all feeding the same field binding:

    mqtt     Recommended by Sportzcast. Cloud broker score.sportzcast.net:8883
             (TLS; username = account e-mail, password = access token), or a
             local ScoreConnect III / Scorelink+ broker on port 1883 (no login).
             Topic bot/{botNumber}/json, QoS 0, subscribe only.
    tcp      Legacy socket on port 1402: GT <email> <token> -> connection token;
             FB<bot> -> serving node; then XB/JB stream request. STX/ETX framing.
    livexml  The XML file written by Sportzcast's LiveXML software (or any XML
             or JSON file or http URL), polled.
    json     The same as livexml, for a JSON document.

Whatever arrives is flattened to ``{key: text}`` (nested keys joined with
dots) and fed to :meth:`Engine.feed`. A field shows a live key when its
``source`` is set to it (Setup → Fields); rules, overrides and conditions then apply
as usual. :func:`suggest` proposes bindings for the usual names.

Sources: docs.sportzcast.net (MQTT integration, base contract, TCP legacy).
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

__all__ = ["SourceSettings", "SourceStatus", "SportzcastSource", "flatten_json", "flatten_xml", "parse_payload",
           "suggest", "MqttClient", "mqtt_encode_length", "mqtt_decode_length", "split_frames", "KNOWN_KEYS",
           "CLOUD_HOST", "LEGACY_HOST"]

CLOUD_HOST = "score.sportzcast.net"
LEGACY_HOST = "scorebot.sportzcast.net"
STX, ETX = b"\x02", b"\x03"


# ----- settings and status ----------------------------------------------------------

@dataclass
class SourceSettings:
    kind: str = ""                 # "" (off) | mqtt | tcp | livexml | json
    cloud: bool = True             # mqtt/tcp: Sportzcast cloud; False = local device on this network
    host: str = ""                 # local device address, or another broker/node
    port: int = 0                  # 0 = the standard port for the kind
    bot: int = 0                   # bot number
    username: str = ""             # account e-mail (the token is kept in the user's settings, not the project)
    data_type: str = "json"        # mqtt topic suffix (json) / tcp stream (json or xml)
    path: str = ""                 # livexml/json: a file path or an http(s) URL
    poll_ms: int = 250
    stale_s: int = 30              # amber warning when nothing arrives for this long

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Mapping]) -> "SourceSettings":
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                setattr(s, k, v)
        s.port, s.bot, s.poll_ms, s.stale_s = int(s.port or 0), int(s.bot or 0), max(50, int(s.poll_ms)), \
            max(1, int(s.stale_s))
        return s

    def describe(self) -> str:
        if self.kind == "mqtt":
            where = CLOUD_HOST if self.cloud else (self.host or "local device")
            return f"Sportzcast MQTT · {where} · bot {self.bot}"
        if self.kind == "tcp":
            return f"Sportzcast socket · bot {self.bot}"
        if self.kind in ("livexml", "json"):
            return f"{'LiveXML' if self.kind == 'livexml' else 'JSON'} · {self.path or 'no file chosen'}"
        return "Off"


@dataclass
class SourceStatus:
    state: str = "off"             # off | connecting | live | stale | error
    detail: str = ""
    packets: int = 0
    last_packet: float = 0.0       # time.time()
    keys: int = 0


# ----- flattening ---------------------------------------------------------------------

def _scalar(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def flatten_json(obj: Any, prefix: str = "") -> Dict[str, str]:
    """{"a": {"b": 1}, "c": [5, 6]} -> {"a.b": "1", "c.0": "5", "c.1": "6"}"""
    out: Dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten_json(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten_json(v, f"{prefix}.{i}" if prefix else str(i)))
    else:
        out[prefix or "value"] = _scalar(obj)
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def flatten_xml(text: str) -> Dict[str, str]:
    """The root's descendants as dotted keys: <info><Hscore>42</Hscore></info>
    -> {"Hscore": "42"}. Repeated siblings get .1, .2 ...; attributes become
    ``tag_attr`` keys. Namespaces are dropped."""
    root = ET.fromstring(text)
    out: Dict[str, str] = {}

    def walk(el, path):
        for a, v in el.attrib.items():
            out[f"{path}_{_local(a)}" if path else _local(a)] = v
        kids = list(el)
        if not kids:
            if path:
                out[path] = (el.text or "").strip()
            return
        counts: Dict[str, int] = {}
        for k in kids:
            counts[_local(k.tag)] = counts.get(_local(k.tag), 0) + 1
        seen: Dict[str, int] = {}
        for k in kids:
            name = _local(k.tag)
            if counts[name] > 1:
                seen[name] = seen.get(name, 0) + 1
                name = f"{name}.{seen[name]}"
            walk(k, f"{path}.{name}" if path else name)

    walk(root, "")
    return out


def parse_payload(data: bytes) -> Dict[str, str]:
    """JSON or XML, detected from the first character."""
    text = data.decode("utf-8-sig", errors="replace").strip().strip("\x00")
    if not text:
        return {}
    if text[0] in "{[":
        return flatten_json(json.loads(text))
    if text[0] == "<":
        return flatten_xml(text)
    if "|" in text:   # SB data: pipe-separated positions
        return {f"field{i + 1}": p for i, p in enumerate(text.split("|"))}
    raise ValueError("The data is not JSON or XML.")


def split_frames(buf: bytes) -> Tuple[List[bytes], bytes]:
    """STX ... ETX frames from a byte stream. Returns (payloads, leftover)."""
    frames = []
    while True:
        s = buf.find(STX)
        if s < 0:
            return frames, b""
        e = buf.find(ETX, s + 1)
        if e < 0:
            return frames, buf[s:]
        frames.append(buf[s + 1:e])
        buf = buf[e + 1:]


# ----- binding suggestions --------------------------------------------------------------

# Sportzcast key -> TeleScore preset field. Names come from the base contract
# (HomeScore, GuestScore, Clock, ...) and from LiveXML (Hscore, Vscore, ...).
KNOWN_KEYS = {
    "HomeScore": "home.score", "GuestScore": "away.score", "HomeRuns": "home.score", "GuestRuns": "away.score",
    "HomeTeamName": "home.name", "GuestTeamName": "away.name", "Clock": "clock.game", "Period": "period",
    "Quarter": "period", "Half": "period", "Inning": "inning", "ShotClock": "clock.shot", "PlayClock": "clock.play",
    "HomeFouls": "home.fouls", "GuestFouls": "away.fouls", "HomeTimeouts": "home.timeouts",
    "GuestTimeouts": "away.timeouts", "HomeTOL": "home.timeouts", "GuestTOL": "away.timeouts",
    "HomeShots": "home.shots", "GuestShots": "away.shots", "HomeSOG": "home.shots", "GuestSOG": "away.shots",
    "Down": "down", "ToGo": "distance", "Distance": "distance", "Balls": "balls", "Ball": "balls",
    "Strikes": "strikes", "Strike": "strikes", "Outs": "outs", "Out": "outs",
    "HomeSets": "home.sets", "GuestSets": "away.sets", "Set": "set",
    "Hscore": "home.score", "Vscore": "away.score", "Htimeouts": "home.timeouts", "Vtimeouts": "away.timeouts",
    "Hfouls": "home.fouls", "Vfouls": "away.fouls", "period": "period", "down": "down", "clock": "clock.game",
}


def _norm(k: str) -> str:
    k = k.rsplit(".", 1)[-1]
    s = re.sub(r"[^a-z0-9]", "", k.lower())
    for a, b in (("guest", "away"), ("visitor", "away"), ("visiting", "away")):
        if s.startswith(a):
            s = b + s[len(a):]
    return s


def suggest(source_keys: Iterable[str], field_keys: Iterable[str]) -> Dict[str, str]:
    """Propose {field key: source key} for fields that are not bound yet."""
    fields = list(field_keys)
    fset = set(fields)
    out: Dict[str, str] = {}
    keys = list(source_keys)
    for sk in keys:
        tail = sk.rsplit(".", 1)[-1]
        fk = KNOWN_KEYS.get(tail)
        if fk in fset and fk not in out:
            out[fk] = sk
    by_norm = {_norm(f.replace(".", "")): f for f in fields}
    for sk in keys:
        fk = by_norm.get(_norm(sk))
        if fk and fk not in out and sk not in out.values():
            out[fk] = sk
    return out


# ----- MQTT 3.1.1, subscribe only -------------------------------------------------------

def mqtt_encode_length(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            return bytes(out)


def mqtt_decode_length(read: Callable[[int], bytes]) -> int:
    mult, value = 1, 0
    for _ in range(4):
        b = read(1)[0]
        value += (b & 0x7F) * mult
        if not b & 0x80:
            return value
        mult *= 128
    raise ValueError("Malformed MQTT length.")


def _mqtt_str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack("!H", len(b)) + b


class MqttError(Exception):
    pass


CONNACK_CODES = {1: "the broker does not accept MQTT 3.1.1", 2: "the client id was rejected",
                 3: "the broker is unavailable", 4: "the e-mail or token is wrong",
                 5: "this account is not allowed to read that bot"}


class MqttClient:
    """Just enough MQTT to subscribe: CONNECT, SUBSCRIBE, PUBLISH (QoS 0 and 1), PINGREQ."""

    def __init__(self, host: str, port: int, tls: bool, username: str = "", password: str = "",
                 keepalive: int = 30, timeout: float = 10.0):
        self.host, self.port, self.tls = host, port, tls
        self.username, self.password = username, password
        self.keepalive, self.timeout = keepalive, timeout
        self.sock: Optional[socket.socket] = None
        self._last_out = 0.0

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise MqttError("The broker closed the connection.")
            buf += chunk
        return buf

    def _send(self, data: bytes) -> None:
        self.sock.sendall(data)
        self._last_out = time.monotonic()

    def read_packet(self) -> Tuple[int, int, bytes]:
        h = self._read(1)[0]
        n = mqtt_decode_length(self._read)
        return h >> 4, h & 0x0F, self._read(n) if n else b""

    def connect(self) -> None:
        raw = socket.create_connection((self.host, self.port), timeout=self.timeout)
        if self.tls:
            ctx = ssl.create_default_context()
            raw = ctx.wrap_socket(raw, server_hostname=self.host)
        self.sock = raw
        flags = 0x02  # clean session
        payload = _mqtt_str("telescore-" + uuid.uuid4().hex[:12])
        if self.username:
            flags |= 0x80
            payload += _mqtt_str(self.username)
            if self.password:
                flags |= 0x40
                payload += _mqtt_str(self.password)
        var = _mqtt_str("MQTT") + bytes([4, flags]) + struct.pack("!H", self.keepalive)
        body = var + payload
        self._send(bytes([0x10]) + mqtt_encode_length(len(body)) + body)
        ptype, _, data = self.read_packet()
        if ptype != 2 or len(data) < 2:
            raise MqttError("The broker did not answer the connection.")
        if data[1] != 0:
            raise MqttError("Connection refused: " + CONNACK_CODES.get(data[1], f"code {data[1]}") + ".")

    def subscribe(self, topic: str) -> None:
        body = struct.pack("!H", 1) + _mqtt_str(topic) + bytes([0])
        self._send(bytes([0x82]) + mqtt_encode_length(len(body)) + body)

    def ping_if_due(self) -> None:
        if time.monotonic() - self._last_out > self.keepalive / 2:
            self._send(bytes([0xC0, 0x00]))

    def messages(self, stop: threading.Event):
        """Yield (topic, payload) until ``stop`` is set or the link drops."""
        self.sock.settimeout(1.0)
        while not stop.is_set():
            self.ping_if_due()
            try:
                ptype, flags, data = self.read_packet()
            except socket.timeout:
                continue
            if ptype == 3:   # PUBLISH
                tlen = struct.unpack("!H", data[:2])[0]
                topic = data[2:2 + tlen].decode("utf-8", errors="replace")
                pos = 2 + tlen
                qos = (flags >> 1) & 3
                if qos:
                    pid = data[pos:pos + 2]
                    pos += 2
                    if qos == 1:
                        self._send(bytes([0x40, 0x02]) + pid)
                yield topic, data[pos:]
            elif ptype == 9 and data[2:3] == b"\x80":
                raise MqttError("The broker refused the subscription. Check the bot number and your licence.")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self._send(bytes([0xE0, 0x00]))
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


# ----- the source --------------------------------------------------------------------

class SportzcastSource:
    """Runs one live-data connection on a background thread and feeds the engine.

    ``feed(values)`` and ``on_status(status)`` are called from that thread."""

    def __init__(self, settings: SourceSettings, token: str, feed: Callable[[Dict[str, str]], None],
                 on_status: Optional[Callable[[SourceStatus], None]] = None):
        self.s = settings
        self.token = token
        self.feed = feed
        self.on_status = on_status
        self.status = SourceStatus()
        self.keys: Dict[str, str] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

    # ----- control ------------------------------------------------------------------
    def start(self) -> None:
        self.stop()
        if not self.s.kind:
            self._set("off", "")
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="TeleScore live data", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(3.0)
            self._thread = None
        if self.status.state != "off":
            self._set("off", "")

    def snapshot_keys(self) -> Dict[str, str]:
        with self._lock:
            return dict(self.keys)

    def check_stale(self) -> None:
        """Called by the UI every second: live -> stale after ``stale_s`` of silence."""
        st = self.status
        if st.state == "live" and st.last_packet and time.time() - st.last_packet > self.s.stale_s:
            self._set("stale", f"Nothing received for {int(time.time() - st.last_packet)} s. "
                               "Check the bot, its network, and that the scoreboard is on.")

    # ----- internals ----------------------------------------------------------------
    def _set(self, state: str, detail: str) -> None:
        self.status.state, self.status.detail = state, detail
        if self.on_status:
            try:
                self.on_status(self.status)
            except Exception:
                pass

    def _deliver(self, values: Dict[str, str]) -> None:
        if not values:
            return
        with self._lock:
            self.keys.update(values)
            self.status.keys = len(self.keys)
        self.status.packets += 1
        self.status.last_packet = time.time()
        self.feed(values)
        if self.status.state != "live":
            self._set("live", self.s.describe())

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                if self.s.kind == "mqtt":
                    self._run_mqtt()
                elif self.s.kind == "tcp":
                    self._run_tcp()
                elif self.s.kind in ("livexml", "json"):
                    self._run_poll()
                else:
                    return
                backoff = 1.0
            except (OSError, MqttError, ValueError, ET.ParseError) as e:
                if self._stop.is_set():
                    return
                msg = str(e) or type(e).__name__
                if isinstance(e, socket.gaierror):
                    msg = "That address cannot be found. Check the host and the internet connection."
                elif isinstance(e, ConnectionRefusedError):
                    msg = "The connection was refused. Is the device on, and the port right?"
                self._set("error", f"{msg} Retrying in {int(backoff)} s.")
                self._stop.wait(backoff)
                backoff = min(backoff * 2, 30.0)

    def _run_mqtt(self) -> None:
        s = self.s
        host = s.host or (CLOUD_HOST if s.cloud else "")
        if not host:
            raise ValueError("Enter the local device's address.")
        tls = s.cloud and not s.host or (s.port == 8883)
        port = s.port or (8883 if tls else 1883)
        if s.cloud and not (s.username and self.token):
            raise ValueError("The Sportzcast cloud needs your account e-mail and access token.")
        self._set("connecting", f"Connecting to {host}:{port} …")
        c = MqttClient(host, port, tls, s.username if s.cloud else "", self.token if s.cloud else "")
        c.connect()
        self._sock = c.sock
        topic = f"bot/{s.bot}/{s.data_type or 'json'}"
        c.subscribe(topic)
        self._set("connecting", f"Connected. Waiting for data on {topic} …")
        try:
            for _topic, payload in c.messages(self._stop):
                try:
                    self._deliver(parse_payload(payload))
                except (ValueError, ET.ParseError):
                    continue    # one bad packet must not drop the link (QoS 0: the next one comes)
        finally:
            c.close()

    def _ask(self, host: str, port: int, command: str) -> bytes:
        with socket.create_connection((host, port), timeout=10) as sock:
            sock.sendall(command.encode("ascii"))
            buf = b""
            end = time.monotonic() + 10
            while time.monotonic() < end:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                frames, _ = split_frames(buf)
                if frames:
                    return frames[0]
            frames, _ = split_frames(buf)
            return frames[0] if frames else buf.strip(STX + ETX)

    def _run_tcp(self) -> None:
        s = self.s
        port = s.port or 1402
        bot5 = f"{int(s.bot):05d}"
        kind = "XB" if (s.data_type or "").lower() in ("xml", "xb") else "JB"
        if s.cloud:
            if not (s.username and self.token):
                raise ValueError("The Sportzcast socket needs your account e-mail and user token.")
            self._set("connecting", "Signing in …")
            auth = self._ask(LEGACY_HOST, port, f"GT {s.username} {self.token}").decode("ascii", "replace").split("|")
            if not auth or auth[0].strip() != "1" or len(auth) < 3:
                raise ValueError("Sign-in refused. Check the e-mail and user token.")
            conn_token = auth[2].strip()
            node = self._ask(LEGACY_HOST, port, f"FB{bot5}").decode("ascii", "replace").strip()
            if not node or node.upper().startswith("ERR"):
                self._stop.wait(10)   # Sportzcast asks for 10 s before retrying after ERR
                raise ValueError(f"Bot {s.bot} is not being served right now.")
            host = s.host or node
        else:
            host, conn_token = s.host, self.token
            if not host:
                raise ValueError("Enter the local BotServer's address.")
        self._set("connecting", f"Opening the {kind[0] == 'X' and 'XML' or 'JSON'} stream for bot {s.bot} …")
        sock = socket.create_connection((host, port), timeout=10)
        self._sock = sock
        sock.sendall(f"{kind}{bot5}000000~{conn_token}".encode("ascii"))
        sock.settimeout(1.0)
        buf = b""
        try:
            while not self._stop.is_set():
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    raise OSError("The stream closed.")
                buf += chunk
                frames, buf = split_frames(buf)
                for f in frames:
                    try:
                        self._deliver(parse_payload(f))
                    except (ValueError, ET.ParseError):
                        continue
                if len(buf) > 1_000_000:
                    buf = b""
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _run_poll(self) -> None:
        s = self.s
        path = s.path.strip()
        if not path:
            raise ValueError("Choose the LiveXML file or URL.")
        is_url = path.lower().startswith(("http://", "https://"))
        self._set("connecting", f"Watching {path} …")
        last_sig = None
        while not self._stop.is_set():
            try:
                if is_url:
                    with urllib.request.urlopen(path, timeout=5) as r:
                        data = r.read(5_000_000)
                    sig = hash(data)
                else:
                    st = os.stat(path)
                    sig = (st.st_mtime_ns, st.st_size)
                    data = None
                if sig != last_sig:
                    if data is None:
                        with open(path, "rb") as fh:
                            data = fh.read(5_000_000)
                    try:
                        values = parse_payload(data)
                    except (ValueError, ET.ParseError, json.JSONDecodeError):
                        values = None   # caught mid-write: keep the last good values, try again
                    if values is not None:
                        last_sig = sig
                        self._deliver(values)
                elif self.status.state == "live":
                    pass
            except FileNotFoundError:
                raise ValueError(f"{path} does not exist yet. Start LiveXML, or check the path.") from None
            self._stop.wait(s.poll_ms / 1000.0)
