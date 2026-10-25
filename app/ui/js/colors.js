// CORBELscore colours: Basalt black, Limestone cream (Pantone P 179-1 U) and
// Patina cyan, with Brass for "editing / careful" and Terracotta for errors.
// Nine colours per scheme; everything else is derived and contrast-checked,
// then applied as CSS variables. See docs/design-system.md.

export const PALETTE = {
  basalt: "#0c0d0d", slate: "#151717", slate2: "#1e2121", joint: "#2e3232",
  limestone: "#f5f5f1",            // Pantone P 179-1 U
  patina: "#4cc9d6", patinaDeep: "#0b7380",
  brass: "#e4b363", brassDeep: "#9a6512",
  terracotta: "#ef6a5e", terracottaDeep: "#b3261e",
};
const P = PALETTE;

export const SCHEMES = {
  Basalt: { bg: P.basalt, panel: P.slate, head: "#080909", ink: P.limestone, accent: P.patina, hi: P.patina, user: P.brass, alert: P.terracotta, mark: P.limestone },
  Limestone: { bg: P.limestone, panel: "#fbfbf8", head: P.basalt, ink: P.basalt, accent: P.patinaDeep, hi: P.patinaDeep, user: P.brassDeep, alert: P.terracottaDeep, mark: P.basalt },
};
export const DEFAULT_SCHEME = "Basalt";
export const schemeName = (name) => (SCHEMES[name] ? name : DEFAULT_SCHEME);

const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const hex = (c) => "#" + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
// t of colour a into colour b
export const mix = (a, b, t) => { const A = rgb(a), B = rgb(b); return hex(A.map((x, i) => x * t + B[i] * (1 - t))); };
export function luminance(h) {
  const ch = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const [r, g, b] = rgb(h);
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b);
}
export function contrast(a, b) { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
// Text on a fill: Basalt or Limestone, whichever reads better (never pure black or white).
export const inkOn = (fill) => (contrast(PALETTE.basalt, fill) >= contrast(PALETTE.limestone, fill) ? PALETTE.basalt : PALETTE.limestone);
function mixUntil(a, b, start, against, target) {
  for (let t = start; t <= 1.0001; t += 0.01) { const c = mix(a, b, t); if (against.every((g) => contrast(c, g) >= target)) return c; }
  return a;
}

export function derive(name) {
  const s = SCHEMES[name] ?? SCHEMES[DEFAULT_SCHEME];
  const c = { ...s };
  c["accent-ink"] = inkOn(s.accent);
  c["hi-ink"] = inkOn(s.hi);
  c["user-ink"] = inkOn(s.user);
  c["alert-ink"] = inkOn(s.alert);
  c["head-ink"] = contrast(s.ink, s.head) >= 4.5 ? s.ink : inkOn(s.head);
  c.muted = mix(s.ink, s.panel, 0.72);
  c.rule = mix(s.ink, s.panel, 0.17);
  c.field = mix(s.panel, s.bg, 0.72);
  c["rule-strong"] = mixUntil(s.ink, s.panel, 0.32, [s.panel, c.field], 3.0);
  c["accent-soft"] = mix(s.accent, s.panel, 0.14);
  c.sel = mix(s.accent, s.panel, 0.18);
  c["accent-text"] = mix(s.accent, s.ink, 0.78);
  c["alert-soft"] = mix(s.alert, s.panel, 0.12);
  c["alert-text"] = mix(s.alert, s.ink, 0.82);
  c["user-soft"] = mix(s.user, s.panel, 0.16);
  c["user-text"] = mixUntil(s.ink, s.user, 0.15, [s.panel, s.bg], 4.5);
  c["hi-soft"] = mix(s.hi, s.panel, 0.16);
  c["row-alt"] = mix(s.bg, s.panel, 0.45);
  c.hover = mix(s.ink, s.panel, 0.06);
  c["menu-fill"] = mix(c["head-ink"], s.head, 0.12);
  c["menu-border"] = mix(c["head-ink"], s.head, 0.38);
  c.grid = mix(s.ink, s.bg, 0.09);
  return c;
}

export function applyScheme(name) {
  const c = derive(name);
  const root = document.documentElement;
  for (const [k, v] of Object.entries(c)) root.style.setProperty(`--${k}`, v);
  root.dataset.scheme = name;
  root.style.colorScheme = luminance(c.bg) < 0.2 ? "dark" : "light";
}
