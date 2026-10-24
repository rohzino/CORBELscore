"""
The browser-source page for one board (OBS, vMix, Wirecast, any browser).

The page draws the board at its canvas size, scales it to fit the window,
and follows the engine through Server-Sent Events, falling back to polling.
It uses only the bundled Archivo font and no network beyond this computer,
so graphics keep working with the internet down.
"""

from __future__ import annotations

import html
import json
import os
from typing import Iterable, Optional

from ..core.animation import Animation, library

__all__ = ["overlay_html"]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.js"), encoding="utf-8") as _fh:
    _JS = _fh.read()

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · TeleScore</title>
<style>
@font-face{font-family:"Archivo";src:url("/fonts/Archivo.ttf") format("truetype");font-weight:100 900;font-stretch:62% 125%;font-style:normal}
@font-face{font-family:"Archivo";src:url("/fonts/Archivo-Italic.ttf") format("truetype");font-weight:100 900;font-stretch:62% 125%;font-style:italic}
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:__PAGEBG__}
#stage{position:absolute;left:0;top:0;transform-origin:0 0;overflow:hidden}
.el{position:absolute;box-sizing:border-box;display:flex;overflow:hidden}
.el .t{white-space:nowrap;line-height:1}
.el img{width:100%;height:100%;display:block}
#offline{position:fixed;right:8px;top:8px;width:10px;height:10px;border-radius:50%;background:#ff6b6b;display:none}
body.debug #offline{display:block}
</style></head>
<body>
<div id="stage"></div><div id="offline" title="Not connected to TeleScore"></div>
<script>window.__TS_BOARD = __BOARD__; window.__TS_ANIMS = __ANIMS__;</script>
<script>
__JS__
</script></body></html>
"""


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def overlay_html(board: dict, page_bg: str = "transparent", animations: Optional[Iterable[dict]] = None) -> str:
    """Render the browser-source page. ``page_bg`` fills around a scaled board
    and behind a transparent one: transparent | green | blue | black.
    ``animations`` are the project's own animation recipes (built-ins are always included)."""
    bg = {"green": "#00b140", "blue": "#0047bb", "black": "#000000"}.get(page_bg, "transparent")
    custom = []
    for d in animations or []:
        try:
            custom.append(Animation.from_dict(d))
        except (TypeError, ValueError):
            pass
    anims = {name: a.to_dict() for name, a in library(custom).items()}
    # Trusted pieces first, the board (user text) last, so its content is never re-scanned.
    return (_PAGE.replace("__JS__", _JS.replace("</script", "<\\/script"))
                 .replace("__PAGEBG__", bg)
                 .replace("__ANIMS__", _json(anims))
                 .replace("__TITLE__", html.escape(str(board.get("name", "Board"))))
                 .replace("__BOARD__", _json(board)))
