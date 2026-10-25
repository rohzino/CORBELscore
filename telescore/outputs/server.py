"""
A small local web server: browser sources, live data feeds and remote control.

    GET  /                      index of everything below, with copyable URLs
    GET  /board/<id>            browser source for a board (?bg=green|blue|black)
    GET  /board/<id>.json       the board definition
    GET  /state.json            every value, as JSON
    GET  /telescore.xml         nested XML      (Ross XPression, Chyron)
    GET  /vmix.xml              flat XML        (vMix data source, XPath //row)
    GET  /fields.xml            key/value XML   (anything that looks up by key)
    GET  /events                Server-Sent Events: "full" then "diff" messages
    GET  /api/fields            field keys, types and labels (for Companion setup)
    GET  /api/action?do=..&field=..&amount=..   run an action (Stream Deck, Companion)
    POST /api/action            the same with a JSON body
    GET  /asset?path=..         an image the project uses (and nothing else)
    GET  /fonts/<file>          the bundled Archivo font

Listens on 127.0.0.1 unless LAN access is switched on. When a token is set,
/api/* calls must carry it (?token=.. or the X-TeleScore-Token header).
Uses only the standard library.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

from ..core.engine import Snapshot, Ticket
from .formats import XML_PROFILES, state_json
from .overlay import overlay_html

__all__ = ["ScoreServer", "ServerData"]

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}


class ServerData:
    """What the server needs from the app. The app replaces the board list and
    allowed assets on the UI thread; the server only reads references."""

    def __init__(self, snapshot: Callable[[], Snapshot],
                 submit: Callable[[dict, Callable[[Optional[str]], None], Ticket], None]):
        self.snapshot = snapshot
        self.submit = submit
        self.boards: List[dict] = []
        self.animations: List[dict] = []
        self.assets: frozenset = frozenset()
        self.token: str = ""

    def set_boards(self, boards: List[dict]) -> None:
        self.boards = list(boards)

    def set_assets(self, paths) -> None:
        self.assets = frozenset(os.path.normcase(os.path.abspath(p)) for p in paths if p)

    def board(self, bid: str) -> Optional[dict]:
        for b in self.boards:
            if b.get("id") == bid:
                return b
        return None


class _Handler(BaseHTTPRequestHandler):
    server_version = "TeleScore/2"
    protocol_version = "HTTP/1.1"
    data: ServerData = None          # set per server class
    hub: "_EventHub" = None

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    # ----- helpers -----------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _text(self, code: int, text: str, ctype: str = "text/plain; charset=utf-8") -> None:
        self._send(code, text.encode("utf-8"), ctype)

    def _json(self, code: int, obj) -> None:
        self._text(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _authorised(self, qs: dict) -> bool:
        token = self.data.token
        if not token:
            return True
        given = self.headers.get("X-TeleScore-Token") or (qs.get("token") or [""])[0]
        return given == token

    # ----- routes ------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-TeleScore-Token")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        qs = parse_qs(url.query)
        try:
            if path in ("/", "/index.html"):
                return self._text(200, self._index(), "text/html; charset=utf-8")
            if path == "/state.json":
                return self._text(200, state_json(self.data.snapshot()), "application/json; charset=utf-8")
            for fname, fn in XML_PROFILES.values():
                if path == "/" + fname:
                    return self._text(200, fn(self.data.snapshot()), "application/xml; charset=utf-8")
            if path == "/events":
                return self._events()
            if path.startswith("/board/"):
                rest = path[len("/board/"):]
                as_json = rest.endswith(".json")
                bid = rest[:-5] if as_json else rest
                board = self.data.board(bid)
                if board is None:
                    return self._text(404, "There is no board with that id. Open / for the list.")
                if as_json:
                    return self._json(200, board)
                bg = (qs.get("bg") or ["transparent"])[0]
                return self._text(200, overlay_html(board, bg, self.data.animations), "text/html; charset=utf-8")
            if path == "/api/fields":
                snap = self.data.snapshot()
                return self._json(200, [{"key": k, "type": snap.types[k], "label": snap.labels.get(k, k)}
                                        for k in snap.types])
            if path == "/api/action":
                if not self._authorised(qs):
                    return self._json(403, {"ok": False, "error": "This TeleScore needs a token. Add ?token=..."})
                action = {k: v[0] for k, v in qs.items() if k != "token"}
                for numeric in ("amount", "ms", "index"):
                    if numeric in action:
                        try:
                            action[numeric] = int(float(action[numeric]))
                        except ValueError:
                            return self._json(400, {"ok": False, "error": f"{numeric} must be a number."})
                return self._act(action)
            if path == "/asset":
                return self._asset((qs.get("path") or [""])[0])
            if path.startswith("/fonts/"):
                name = os.path.basename(path)
                fp = os.path.join(FONT_DIR, name)
                if name.endswith(".ttf") and os.path.isfile(fp):
                    with open(fp, "rb") as fh:
                        return self._send(200, fh.read(), "font/ttf", {"Cache-Control": "max-age=86400"})
            return self._text(404, "Not found. Open / for the list of pages.")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path != "/api/action":
            return self._text(404, "Not found.")
        if not self._authorised(qs):
            return self._json(403, {"ok": False, "error": "This TeleScore needs a token."})
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            action = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "The body must be JSON, like {\"do\":\"add\"}."})
        return self._act(action)

    def _act(self, action: dict):
        done = threading.Event()
        result: Dict[str, Optional[str]] = {"error": None}

        def finished(err: Optional[str]) -> None:
            result["error"] = err
            done.set()

        ticket = Ticket()
        self.data.submit(action, finished, ticket)
        if not done.wait(2.0):
            if ticket.withdraw():
                # Withdrawn before it ran, so a retry can never score twice.
                return self._json(504, {"ok": False, "error": "TeleScore was busy and did not run the action. "
                                                              "It is safe to try again."})
            done.wait(5.0)                    # it started just now: let it finish
            if not done.is_set():
                return self._json(504, {"ok": False, "error": "The action started but did not finish in time."})
        if result["error"]:
            return self._json(400, {"ok": False, "error": result["error"]})
        return self._json(200, {"ok": True})

    def _asset(self, path: str):
        full = os.path.normcase(os.path.abspath(path))
        if full not in self.data.assets or os.path.splitext(full)[1].lower() not in IMAGE_TYPES:
            return self._text(403, "Only pictures used by this project are served.")
        try:
            with open(full, "rb") as fh:
                body = fh.read()
        except OSError:
            return self._text(404, "That picture is missing.")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        return self._send(200, body, ctype, {"Cache-Control": "max-age=5"})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = self.hub.join()
        try:
            snap = self.data.snapshot()
            last = dict(snap.values)
            last_fx = snap.fx
            self._sse("full", last)
            self._sse("fx", last_fx)
            while not self.hub.closed:
                newest = q.wait(15.0)
                if newest is None:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    continue
                diff = {k: v for k, v in newest.values.items() if last.get(k) != v}
                for k in last:
                    if k not in newest.values:
                        diff[k] = None
                if diff:
                    self._sse("diff", diff)
                    last = dict(newest.values)
                if newest.fx != last_fx:
                    last_fx = newest.fx
                    self._sse("fx", last_fx)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            self.hub.leave(q)
            self.close_connection = True

    def _sse(self, event: str, payload) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _index(self) -> str:
        host = self.headers.get("Host") or "127.0.0.1"
        base = f"http://{host}"
        rows = "".join(
            f'<tr><td>{_esc(b.get("name", ""))}</td><td><a href="/board/{quote(b["id"])}">{base}/board/{_esc(b["id"])}</a></td>'
            f'<td>{b.get("width")} × {b.get("height")}</td></tr>' for b in self.data.boards)
        feeds = "".join(f'<tr><td>{label}</td><td><a href="{p}">{base}{p}</a></td><td>{use}</td></tr>' for label, p, use in [
            ("JSON", "/state.json", "Anything"),
            ("XML, nested", "/telescore.xml", "Ross XPression, Chyron"),
            ("XML, flat", "/vmix.xml", "vMix data source, XPath //row"),
            ("XML, key/value", "/fields.xml", "//field[@key='home.score']"),
        ])
        return _INDEX.replace("__BOARDS__", rows or '<tr><td colspan="3">No boards yet.</td></tr>') \
                     .replace("__FEEDS__", feeds).replace("__BASE__", _esc(base))


def _esc(s: str) -> str:
    import html
    return html.escape(str(s))


_INDEX = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>TeleScore</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
@font-face{font-family:Archivo;src:url(/fonts/Archivo.ttf);font-weight:100 900;font-stretch:62% 125%}
:root{--bg:#0f1513;--panel:#18211e;--ink:#e8f1ec;--muted:#aeb7b2;--rule:#3b4441;--hi:#5ad1e6;--accent-text:#63e19b}
body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.4 Archivo,system-ui,sans-serif;font-variant-numeric:tabular-nums}
header{background:#0a0f0d;padding:14px 16px;font-weight:900;letter-spacing:.05em;text-transform:uppercase}
main{padding:16px;max-width:980px}
h2{font-size:17px;font-weight:900;letter-spacing:.04em;text-transform:uppercase;display:inline-block;box-shadow:inset 0 -4px 0 var(--hi);margin:18px 0 10px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--rule);border-radius:6px}
td{padding:6px 12px;border-top:1px solid var(--rule)}a{color:var(--accent-text)}
code{font:12.5px ui-monospace,Consolas,monospace;background:#151e1b;padding:1px 4px;border-radius:3px}
p{color:var(--muted)}
</style></head><body><header>TeleScore</header><main>
<h2>Browser sources</h2><table>__BOARDS__</table>
<p>In OBS add a Browser source with the board's URL and its width and height. Add <code>?bg=green</code> for a keyer that needs chroma green.</p>
<h2>Data feeds</h2><table>__FEEDS__</table>
<h2>Remote control</h2>
<p>Send an action with a GET or POST to <code>__BASE__/api/action</code>, for example
<code>__BASE__/api/action?do=add&amp;field=home.score&amp;amount=1</code> or <code>?do=toggle&amp;field=clock.game</code>.
Field keys are listed at <a href="/api/fields">/api/fields</a>.</p>
</main></body></html>"""


class _Waiter:
    def __init__(self):
        self._cond = threading.Condition()
        self._snap: Optional[Snapshot] = None

    def push(self, snap: Snapshot) -> None:
        with self._cond:
            self._snap = snap
            self._cond.notify()

    def wait(self, timeout: float) -> Optional[Snapshot]:
        with self._cond:
            if self._snap is None:
                self._cond.wait(timeout)
            snap, self._snap = self._snap, None
            return snap


class _EventHub:
    def __init__(self):
        self._lock = threading.Lock()
        self._waiters: List[_Waiter] = []
        self.closed = False

    def join(self) -> _Waiter:
        w = _Waiter()
        with self._lock:
            self._waiters.append(w)
        return w

    def leave(self, w: _Waiter) -> None:
        with self._lock:
            if w in self._waiters:
                self._waiters.remove(w)

    def publish(self, snap: Snapshot) -> None:
        with self._lock:
            ws = list(self._waiters)
        for w in ws:
            w.push(snap)

    def close(self) -> None:
        self.closed = True
        with self._lock:
            ws = list(self._waiters)
        for w in ws:
            w.push(None)

    @property
    def clients(self) -> int:
        with self._lock:
            return len(self._waiters)


class _HTTPServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second program bind the same port and
    # steal requests; only reuse addresses where it means TIME_WAIT reuse.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


class ScoreServer:
    """Start, stop and feed the web server."""

    def __init__(self, data: ServerData):
        self.data = data
        self.hub = _EventHub()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.error = ""
        self.port = 0
        self.host = ""

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, port: int, lan: bool = False) -> bool:
        self.stop()
        self.hub = _EventHub()
        handler = type("Handler", (_Handler,), {"data": self.data, "hub": self.hub})
        host = "0.0.0.0" if lan else "127.0.0.1"
        try:
            httpd = _HTTPServer((host, port), handler)
        except OSError as e:
            self.error = (f"Port {port} is in use or blocked ({e.strerror or e}). "
                          "Pick another port in Setup → Outputs.")
            return False
        httpd.daemon_threads = True
        self._httpd, self.port, self.host, self.error = httpd, port, host, ""
        self._thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.25},
                                        name="TeleScore web server", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._httpd is None:
            return
        self.hub.close()
        httpd, self._httpd = self._httpd, None
        httpd.shutdown()
        httpd.server_close()
        if self._thread:
            self._thread.join(2.0)

    def publish(self, snap: Snapshot, changed: Optional[set] = None) -> None:
        """Engine listener: wake every connected browser source."""
        if self._httpd is not None:
            self.hub.publish(snap)

    def url(self, path: str = "/") -> str:
        host = "127.0.0.1" if self.host in ("", "127.0.0.1", "0.0.0.0") else self.host
        return f"http://{host}:{self.port}{path}"
