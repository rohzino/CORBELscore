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

__all__ = ["overlay_html"]

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
<script>
"use strict";
const BOARD = __BOARD__;
const TOKEN_RE = /\\{\\{|\\}\\}|\\{([a-z0-9_.]+)\\}/g;
const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
let values = {};
const stage = document.getElementById("stage");
if (new URLSearchParams(location.search).has("debug")) document.body.classList.add("debug");

function tpl(s){ return (s||"").replace(TOKEN_RE,(m,k)=> m==="{{"?"{": m==="}}"?"}": (values[k]??"")); }
function color(s){
  let v = (s||"").includes("{") ? tpl(s).trim() : (s||"").trim();
  if(!v) return ""; if(v[0]!=="#") v="#"+v;
  if(!HEX_RE.test(v)) return "";
  if(v.length===4) v="#"+[...v.slice(1)].map(c=>c+c).join("");
  if(v.length===9){ const a=parseInt(v.slice(7),16)/255; const r=parseInt(v.slice(1,3),16),g=parseInt(v.slice(3,5),16),b=parseInt(v.slice(5,7),16); return `rgba(${r},${g},${b},${a.toFixed(3)})`; }
  return v;
}
function shown(e){ if(e.visible===false) return false; if(!e.show_when) return true;
  const v=String(values[e.show_when]??"").trim(); return !(v===""||v==="0"||v==="false"||v==="False"); }

const D = {x:0,y:0,w:200,h:80,opacity:1,fill:"",stroke:"",stroke_width:0,radius:0,text:"",font:"Archivo",
  size:48,weight:700,italic:false,color:"#ffffff",align:"center",valign:"middle",uppercase:false,tracking:0,
  fit:true,tabular:true,padding:0,src:"",contain:true,show_when:"",visible:true};
const nodes = [];
function build(){
  stage.style.width = BOARD.width+"px"; stage.style.height = BOARD.height+"px";
  stage.style.background = color(BOARD.background) || "transparent";
  for(const raw of BOARD.elements){
    const e = Object.assign({}, D, raw);
    const n = document.createElement("div"); n.className="el";
    Object.assign(n.style,{left:e.x+"px",top:e.y+"px",width:e.w+"px",height:e.h+"px",opacity:e.opacity,
      borderRadius:e.radius+"px",padding:e.padding+"px"});
    n.style.justifyContent = {left:"flex-start",center:"center",right:"flex-end"}[e.align]||"center";
    n.style.alignItems = {top:"flex-start",middle:"center",bottom:"flex-end"}[e.valign]||"center";
    let inner = null;
    if(e.kind==="text"){
      inner = document.createElement("span"); inner.className="t";
      Object.assign(inner.style,{fontFamily:`"${e.font}", Archivo, "Helvetica Neue", Arial, sans-serif`,
        fontWeight:e.weight,fontStyle:e.italic?"italic":"normal",letterSpacing:e.tracking+"em",
        textTransform:e.uppercase?"uppercase":"none",fontVariantNumeric:e.tabular?"tabular-nums":"normal",
        textAlign:e.align});
      n.appendChild(inner);
    } else if(e.kind==="image"){
      inner = document.createElement("img"); inner.alt=""; inner.style.objectFit = e.contain?"contain":"fill";
      n.appendChild(inner);
    }
    stage.appendChild(n);
    nodes.push({e,n,inner,last:{}});
  }
  fit(); window.addEventListener("resize", fit);
}
function fit(){
  const s = Math.min(innerWidth/BOARD.width, innerHeight/BOARD.height);
  stage.style.transform = `scale(${s})`;
  stage.style.left = ((innerWidth-BOARD.width*s)/2)+"px";
  stage.style.top = ((innerHeight-BOARD.height*s)/2)+"px";
}
function fitText(o){
  const {e,n,inner} = o; const avail = e.w - 2*e.padding - 2*(e.stroke_width||0);
  let size = e.size; inner.style.fontSize = size+"px";
  if(!e.fit) return;
  const availH = e.h - 2*e.padding;
  let guard = 0;
  while(size > 6 && (inner.scrollWidth > avail + 0.5 || inner.offsetHeight > availH + 0.5) && guard++ < 40){
    size = Math.max(6, size * Math.min(0.97, avail / Math.max(1, inner.scrollWidth)));
    inner.style.fontSize = size+"px";
  }
}
function render(){
  for(const o of nodes){
    const {e,n,inner,last} = o;
    const vis = shown(e);
    if(last.vis!==vis){ n.style.display = vis?"flex":"none"; last.vis=vis; }
    if(!vis) continue;
    const fill = color(e.fill), stroke = color(e.stroke);
    if(last.fill!==fill){ n.style.background = fill||"transparent"; last.fill=fill; }
    const border = (stroke && e.stroke_width>0) ? `${e.stroke_width}px solid ${stroke}` : "none";
    if(last.border!==border){ n.style.border = border; last.border=border; }
    if(e.kind==="text"){
      const txt = tpl(e.text), col = color(e.color)||"#ffffff";
      if(last.txt!==txt){ inner.textContent = txt; last.txt=txt; last.fitted=false; }
      if(last.col!==col){ inner.style.color = col; last.col=col; }
      if(!last.fitted){ fitText(o); last.fitted=true; }
    } else if(e.kind==="image"){
      const p = tpl(e.src).trim();
      const url = p ? (/^(https?:|data:)/.test(p) ? p : "/asset?path="+encodeURIComponent(p)) : "";
      if(last.src!==url){ if(url){ inner.src=url; inner.style.visibility="visible"; } else { inner.removeAttribute("src"); inner.style.visibility="hidden"; } last.src=url; }
    }
  }
}
function online(ok){ document.getElementById("offline").style.display = ok ? "none" : ""; }
let poller = null;
function poll(){
  if(poller) return;
  poller = setInterval(()=>fetch("/state.json",{cache:"no-store"}).then(r=>r.json())
    .then(s=>{values=s.values; render(); online(true);}).catch(()=>online(false)), 250);
}
function connect(){
  if(!window.EventSource){ poll(); return; }
  const es = new EventSource("/events");
  es.addEventListener("full", ev=>{ values = JSON.parse(ev.data); render(); online(true); if(poller){clearInterval(poller);poller=null;} });
  es.addEventListener("diff", ev=>{ const d = JSON.parse(ev.data); for(const k in d){ if(d[k]===null) delete values[k]; else values[k]=d[k]; } render(); });
  es.onerror = ()=>{ online(false); es.close(); poll(); setTimeout(connect, 2000); };
}
function refit(){ for(const o of nodes) o.last.fitted=false; render(); }
build(); render(); connect();
if(document.fonts){
  // Faces load lazily, so fonts.ready can resolve before Archivo arrives.
  // Ask for every face the board uses, and refit whenever any face finishes.
  const faces = new Set(BOARD.elements.filter(e=>(e.kind||"text")==="text")
    .map(e=>`${e.italic?"italic ":""}${e.weight||700} 48px "${e.font||"Archivo"}"`));
  Promise.all([...faces].map(f=>document.fonts.load(f).catch(()=>null))).then(refit);
  document.fonts.addEventListener && document.fonts.addEventListener("loadingdone", refit);
}
</script></body></html>
"""


def overlay_html(board: dict, page_bg: str = "transparent") -> str:
    """Render the browser-source page. ``page_bg`` fills around a scaled board
    and behind a transparent one: transparent | green | blue | black."""
    bg = {"green": "#00b140", "blue": "#0047bb", "black": "#000000"}.get(page_bg, "transparent")
    data = json.dumps(board, ensure_ascii=False).replace("</", "<\\/")
    return (_PAGE.replace("__TITLE__", html.escape(str(board.get("name", "Board"))))
                 .replace("__PAGEBG__", bg)
                 .replace("__BOARD__", data))
