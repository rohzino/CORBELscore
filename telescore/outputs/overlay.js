"use strict";
/* TeleScore browser source.
 * Mirrors, in JavaScript, the Python rules for the same board:
 *   templates (core.board), rules (core.logic.apply_rules),
 *   element text (core.animation.element_text), easing and sample
 *   (core.animation), and the Tracker's animation triggers.
 * tests/test_overlay_browser.py checks both sides give the same answers. */
const BOARD = window.__TS_BOARD;
const ANIMS = window.__TS_ANIMS;          // name -> animation recipe
const TOKEN_RE = /\{\{|\}\}|\{([a-z0-9_.]+)\}/g;
const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
let values = {}, fxAll = {};
const stage = document.getElementById("stage");
if (new URLSearchParams(location.search).has("debug")) document.body.classList.add("debug");

/* ---- templates, colours, rules ------------------------------------------------ */
function tpl(s){ return (s||"").replace(TOKEN_RE,(m,k)=> m==="{{"?"{": m==="}}"?"}": (values[k]??"")); }
function color(s){
  let v = (s||"").includes("{") ? tpl(s).trim() : (s||"").trim();
  if(!v) return ""; if(v[0]!=="#") v="#"+v;
  if(!HEX_RE.test(v)) return "";
  if(v.length===4) v="#"+[...v.slice(1)].map(c=>c+c).join("");
  if(v.length===9){ const a=parseInt(v.slice(7),16)/255; const r=parseInt(v.slice(1,3),16),g=parseInt(v.slice(3,5),16),b=parseInt(v.slice(5,7),16); return `rgba(${r},${g},${b},${a.toFixed(3)})`; }
  return v;
}
function splitEsc(text, sep, keep){
  const out=[]; let cur="", esc=false;
  for(const ch of text){
    if(esc){ cur += keep ? "\\"+ch : ("|=\\".includes(ch) ? ch : "\\"+ch); esc=false; }
    else if(ch==="\\") esc=true;
    else if(ch===sep){ out.push(cur); cur=""; }
    else cur+=ch;
  }
  if(esc) cur+="\\";
  out.push(cur); return out;
}
const ruleCache = new Map();
function parseRules(text){
  if(ruleCache.has(text)) return ruleCache.get(text);
  const pairs=[];
  for(const piece of splitEsc(text||"","|",true)){
    if(!piece.trim()) continue;
    const parts = splitEsc(piece,"=");
    if(parts.length<2) continue;
    pairs.push([parts[0].trim(), parts.slice(1).join("=").trim()]);
  }
  ruleCache.set(text, pairs); return pairs;
}
function globRe(p){ return new RegExp("^"+p.replace(/[.+^${}()|\\]/g,"\\$&").replace(/\[/g,"\\[").replace(/\*/g,".*").replace(/\?/g,".")+"$","s"); }
function applyRules(rules, value){
  if(!rules) return null;
  const v = (value||"").trim();
  for(const [l,r] of parseRules(rules)){
    let hit;
    if(l==="NULL") hit = v==="";
    else if(l.includes("*")||l.includes("?")) hit = globRe(l).test(v);
    else hit = v===l;
    if(hit) return r.split("{value}").join(value||"");
  }
  return null;
}
function shown(e){ if(e.visible===false) return false; if(!e.show_when) return true;
  const v=String(values[e.show_when]??"").trim(); return !(v===""||v==="0"||v==="false"||v==="False"); }
function elementText(e, fx){
  const text = tpl(e.text);
  let r = applyRules(e.rules, text); if(r!==null) return r;
  if(fx && fx.rule){ r = applyRules(fx.rule, text); if(r!==null) return r; }
  return text;
}

/* ---- animation maths (core.animation) ------------------------------------------- */
const EASINGS = {"linear":[0,0,1,1],"ease":[0.25,0.1,0.25,1],"ease-in":[0.42,0,1,1],"ease-out":[0,0,0.58,1],
  "ease-in-out":[0.42,0,0.58,1],"broadcast":[0.2,0.8,0.2,1],"back-out":[0.34,1.56,0.64,1],"bounce-out":"bounce"};
function bezier(x1,y1,x2,y2,x){
  if(x<=0) return 0; if(x>=1) return 1;
  const bx=t=>3*(1-t)*(1-t)*t*x1+3*(1-t)*t*t*x2+t*t*t, by=t=>3*(1-t)*(1-t)*t*y1+3*(1-t)*t*t*y2+t*t*t;
  const dbx=t=>3*(1-t)*(1-t)*x1+6*(1-t)*t*(x2-x1)+3*t*t*(1-x2);
  let t=x;
  for(let i=0;i<8;i++){ const err=bx(t)-x; if(Math.abs(err)<1e-7) return by(t); const d=dbx(t); if(Math.abs(d)<1e-6) break; t-=err/d; }
  let lo=0, hi=1; t=x;
  for(let i=0;i<40;i++){ const v=bx(t); if(Math.abs(v-x)<1e-7) break; if(v<x) lo=t; else hi=t; t=(lo+hi)/2; }
  return by(t);
}
function bounce(x){ const n=7.5625,d=2.75;
  if(x<1/d) return n*x*x; if(x<2/d){x-=1.5/d; return n*x*x+0.75;}
  if(x<2.5/d){x-=2.25/d; return n*x*x+0.9375;} x-=2.625/d; return n*x*x+0.984375; }
function ease(name,x){ x=Math.max(0,Math.min(1,x)); const e=EASINGS[name]||EASINGS.broadcast; return e==="bounce"?bounce(x):bezier(e[0],e[1],e[2],e[3],x); }
const ID = {opacity:1,x:0,y:0,scale:1,clip:[0,0,1,1]};
function total(a){ return a.delay + a.duration*(a.kind==="emphasis"?a.repeat:1); }
function sample(a, elapsed){
  const t = elapsed - a.delay;
  const lerp=(p,q,k)=>p+(q-p)*k;
  if(a.kind==="emphasis"){
    if(t<=0 || t>=a.duration*a.repeat) return Object.assign({},ID);
    const phase=(t%a.duration)/a.duration, tri= phase<0.5?phase*2:(1-phase)*2, p=ease(a.easing,tri);
    return {opacity:lerp(1,a.opacity,p),x:lerp(0,a.x,p),y:lerp(0,a.y,p),scale:lerp(1,a.scale,p),clip:[0,0,1,1]};
  }
  const raw = t<=0?0:Math.min(1,t/a.duration), p=ease(a.easing,raw);
  const k = a.kind==="in" ? 1-p : p;
  const shownPart = Math.max(0,Math.min(1, a.kind==="in" ? p : 1-p));
  let clip=[0,0,1,1];
  if(a.wipe==="left") clip=[0,0,shownPart,1]; else if(a.wipe==="right") clip=[1-shownPart,0,1,1];
  else if(a.wipe==="up") clip=[0,1-shownPart,1,1]; else if(a.wipe==="down") clip=[0,0,1,shownPart];
  return {opacity:Math.max(0,Math.min(1,lerp(1,a.opacity,k))),x:a.x*k,y:a.y*k,scale:lerp(1,a.scale,k),clip};
}
window.__ts = {ease, sample, applyRules, elementText, parseRules};

/* ---- building the board ----------------------------------------------------------- */
const D = {x:0,y:0,w:200,h:80,opacity:1,fill:"",stroke:"",stroke_width:0,radius:0,text:"",font:"Archivo",
  size:48,weight:700,italic:false,color:"#ffffff",align:"center",valign:"middle",uppercase:false,tracking:0,
  fit:true,tabular:true,padding:0,src:"",contain:true,show_when:"",visible:true,
  rules:"",anim_in:"",anim_out:"",anim_change:""};
const nodes = [];
function build(){
  stage.style.width = BOARD.width+"px"; stage.style.height = BOARD.height+"px";
  stage.style.background = color(BOARD.background) || "transparent";
  for(const raw of BOARD.elements){
    const e = Object.assign({}, D, raw);
    const n = document.createElement("div"); n.className="el"; n.dataset.id = e.id;
    Object.assign(n.style,{left:e.x+"px",top:e.y+"px",width:e.w+"px",height:e.h+"px",opacity:e.opacity,
      borderRadius:e.radius+"px",padding:e.padding+"px",transformOrigin:"50% 50%"});
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
    nodes.push({e,n,inner,last:{},st:{visible:null,content:null,anim:null,start:0,hideAfter:false,fxId:undefined}});
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
  const {e,inner} = o; const avail = e.w - 2*e.padding - 2*(e.stroke_width||0);
  let size = e.size; inner.style.fontSize = size+"px";
  if(!e.fit) return;
  const availH = e.h - 2*e.padding;
  let guard = 0;
  while(size > 6 && (inner.scrollWidth > avail + 0.5 || inner.offsetHeight > availH + 0.5) && guard++ < 40){
    size = Math.max(6, size * Math.min(0.97, avail / Math.max(1, inner.scrollWidth)));
    inner.style.fontSize = size+"px";
  }
}

/* ---- animation triggers (core.animation.Tracker) ----------------------------------- */
function startAnim(st, name, hideAfter){
  const a = ANIMS[name]; if(!a) return false;
  st.anim=a; st.start=performance.now(); st.hideAfter = !!hideAfter || a.kind==="out"; return true;
}
function targetVisible(e, fx){ if(e.visible===false) return false; if(fx && ("visible" in fx)) return !!fx.visible; return shown(e); }
function contentOf(e, fx){
  if(e.kind==="text") return elementText(e, fx);
  if(e.kind==="image") return (fx && fx.src) || tpl(e.src);
  return "";
}
function track(o){
  const {e,st} = o; const fx = fxAll[e.id] || {};
  let vis = targetVisible(e, fx); const cont = contentOf(e, fx);
  const first = st.visible===null;
  if(!first){
    if(vis && !st.visible){ if(!(e.anim_in && startAnim(st, e.anim_in))) st.anim=null; }
    else if(!vis && st.visible){ if(!(e.anim_out && startAnim(st, e.anim_out, true))) st.anim=null; }
    else if(vis && cont!==st.content && e.anim_change){ startAnim(st, e.anim_change); }
  }
  if(fx.anim && st.fxId!==fx.anim.id){
    st.fxId = fx.anim.id;
    if(!first){ const a = ANIMS[fx.anim.name]; if(a){ startAnim(st, a.name, a.kind==="out"); if(a.kind==="in") vis=true; } }
  }
  st.visible = vis; st.content = cont;
}
function look(o, now){
  const st=o.st;
  if(st.anim){
    const el = now - st.start;
    if(el >= total(st.anim)){ const hide=st.hideAfter; st.anim=null; if(hide) return null; }
    else {
      if(el < st.anim.delay && st.anim.kind==="in") return st.visible ? sample(st.anim, el) : null;
      return sample(st.anim, el);
    }
  }
  return st.visible ? ID : null;
}
let raf = 0;
function paint(){
  raf = 0; const now = performance.now(); let busy=false;
  for(const o of nodes){
    const {e,n,last} = o; const lk = look(o, now);
    const vis = !!lk;
    if(last.vis!==vis){ n.style.display = vis?"flex":"none"; last.vis=vis; }
    if(!vis) continue;
    if(o.st.anim) busy=true;
    const tr = (lk.x||lk.y||lk.scale!==1) ? `translate(${lk.x}px,${lk.y}px) scale(${lk.scale})` : "";
    if(last.tr!==tr){ n.style.transform = tr; last.tr=tr; }
    const op = String(Math.max(0,Math.min(1,e.opacity*lk.opacity)));
    if(last.op!==op){ n.style.opacity = op; last.op=op; }
    const c = lk.clip; const cp = (c[0]>0||c[1]>0||c[2]<1||c[3]<1) ? `inset(${c[1]*100}% ${(1-c[2])*100}% ${(1-c[3])*100}% ${c[0]*100}%)` : "";
    if(last.cp!==cp){ n.style.clipPath = cp; last.cp=cp; }
  }
  if(busy) raf = requestAnimationFrame(paint);
}
function schedule(){ if(!raf) raf = requestAnimationFrame(paint); }

function render(){
  for(const o of nodes){
    track(o);
    const {e,n,inner,last} = o; const fx = fxAll[e.id] || {};
    if(!o.st.visible && !o.st.anim) continue;
    const fill = color(fx.fill || (e.kind==="box" ? (fx.color||"") : "") || e.fill), stroke = color(e.stroke);
    if(last.fill!==fill){ n.style.background = fill||"transparent"; last.fill=fill; }
    const border = (stroke && e.stroke_width>0) ? `${e.stroke_width}px solid ${stroke}` : "none";
    if(last.border!==border){ n.style.border = border; last.border=border; }
    if(e.kind==="text"){
      const txt = elementText(e, fx), col = color(fx.color || e.color)||"#ffffff";
      const fam = `"${fx.font || e.font}", Archivo, "Helvetica Neue", Arial, sans-serif`;
      if(last.fam!==fam){ inner.style.fontFamily = fam; last.fam=fam; last.fitted=false; }
      if(last.txt!==txt){ inner.textContent = txt; last.txt=txt; last.fitted=false; }
      if(last.col!==col){ inner.style.color = col; last.col=col; }
      if(!last.fitted){ fitText(o); last.fitted=true; }
    } else if(e.kind==="image"){
      const p = ((fx.src) || tpl(e.src)).trim();
      const url = p ? (/^(https?:|data:)/.test(p) ? p : "/asset?path="+encodeURIComponent(p)) : "";
      if(last.src!==url){ if(url){ inner.src=url; inner.style.visibility="visible"; } else { inner.removeAttribute("src"); inner.style.visibility="hidden"; } last.src=url; }
    }
  }
  schedule();
}

/* ---- data ------------------------------------------------------------------------- */
function online(ok){ document.getElementById("offline").style.display = ok ? "none" : ""; }
let poller = null;
function poll(){
  if(poller) return;
  poller = setInterval(()=>fetch("/state.json",{cache:"no-store"}).then(r=>r.json())
    .then(s=>{values=s.values; fxAll=s.fx||{}; render(); online(true);}).catch(()=>online(false)), 250);
}
function connect(){
  if(!window.EventSource){ poll(); return; }
  const es = new EventSource("/events");
  es.addEventListener("full", ev=>{ values = JSON.parse(ev.data); render(); online(true); if(poller){clearInterval(poller);poller=null;} });
  es.addEventListener("diff", ev=>{ const d = JSON.parse(ev.data); for(const k in d){ if(d[k]===null) delete values[k]; else values[k]=d[k]; } render(); });
  es.addEventListener("fx", ev=>{ fxAll = JSON.parse(ev.data)||{}; render(); });
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
