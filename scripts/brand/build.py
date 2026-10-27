"""Build CORBELscore's brand assets: the wordmark, the lockup with its
tagline, and the app icon, as SVG paths (no font needed to show them) plus
PNG/ICO renders.

Chromium lays the text out (so kerning is the font's own); fontTools supplies
the outlines. Needs fontTools and Playwright with Chromium. Run from the repo:
    python3 scripts/brand/build.py
"""
import asyncio, base64, io, json, pathlib, subprocess, sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONTS = ROOT / "app/assets/fonts"
OUT = ROOT / "app/assets/brand"
OUT.mkdir(parents=True, exist_ok=True)

LIMESTONE, BASALT, PATINA = "#f5f5f1", "#0c0d0d", "#4cc9d6"
WEIGHT = 800
WORD = [("CORBEL", WEIGHT), ("score", WEIGHT)]           # one weight, case does the work
TAGLINE = ("LIVE BROADCAST SCORING SOLUTION", 500)
SIZE = 200                                         # wordmark font size in SVG units
TAG_TRACK = 0.06                                   # tagline letter-spacing, em
WORD_OPACITY = 0.91                                # the wordmark sits at 91%; the tagline at full strength

def instance(file, wght):
    f = TTFont(FONTS / file)
    return instancer.instantiateVariableFont(f, {"wght": wght}, inplace=False)

async def measure(page, family_file, text, size, track_em=0.0, wght=700):
    """x of each character's left edge and the total advance, as Chromium sets them."""
    data = base64.b64encode((FONTS / family_file).read_bytes()).decode()
    return await page.evaluate("""async ([data, text, size, track, wght]) => {
      const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
      const ff = new FontFace("M" + wght + Math.random().toString(36).slice(2), bytes, { weight: "100 900" });
      await ff.load(); document.fonts.add(ff);
      const s = document.createElement("span");
      Object.assign(s.style, { fontFamily: ff.family, fontWeight: wght, fontSize: size + "px", letterSpacing: track + "em",
        fontKerning: "normal", fontFeatureSettings: '"liga" 0, "kern" 1', whiteSpace: "pre", position: "absolute", left: "0", top: "0" });
      s.textContent = text; document.body.appendChild(s);
      const node = s.firstChild, base = s.getBoundingClientRect().left, xs = [];
      for (let i = 0; i < text.length; i++) { const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + 1); xs.push(r.getBoundingClientRect().left - base); }
      const w = s.getBoundingClientRect().width; s.remove(); return { xs, w };
    }""", [data, text, size, track_em, wght])

def outline(font, text, xs, size, x0, baseline):
    upm = font["head"].unitsPerEm
    k = size / upm
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    pen = SVGPathPen(gs)
    bp = BoundsPen(gs)
    for ch, x in zip(text, xs):
        if ch == " ":
            continue
        g = cmap[ord(ch)]
        t = (k, 0, 0, -k, x0 + x, baseline)
        gs[g].draw(TransformPen(pen, t))
        gs[g].draw(TransformPen(bp, t))
    return pen.getCommands(), bp.bounds

def cap_height(font, size):
    return font["OS/2"].sCapHeight * size / font["head"].unitsPerEm

async def main():
    disp = {WEIGHT: instance("RedHatDisplay.ttf", WEIGHT)}
    text = {500: instance("RedHatText.ttf", 500)}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        await page.set_content("<body style='margin:0'></body>")
        # Wordmark: CORBEL + score set as one word so the kerning between L and s is the font's.
        word = "".join(t for t, _ in WORD)
        m = await measure(page, "RedHatDisplay.ttf", word, SIZE, 0, WEIGHT)
        W = m["w"]
        cap = cap_height(disp[WEIGHT], SIZE)
        # Tagline: Red Hat Text, tracked, sized so it spans the wordmark exactly.
        tt, tw = TAGLINE
        probe = await measure(page, "RedHatText.ttf", tt, 100, TAG_TRACK, tw)
        natural = probe["w"] - TAG_TRACK * 100            # no trailing space after the last letter
        tsize = 100 * W / natural
        tm = await measure(page, "RedHatText.ttf", tt, tsize, TAG_TRACK, tw)
        await b.close()

    word_d, wb = outline(disp[WEIGHT], word, m["xs"], SIZE, 0, cap)       # wordmark baseline at its cap height
    gap = cap * 0.30
    tcap = cap_height(text[500], tsize)
    tag_base = cap + gap + tcap
    tag_d, tb = outline(text[500], tt, tm["xs"], tsize, 0, tag_base)
    x1 = min(wb[0], tb[0]); x2 = max(wb[2], tb[2])
    y1 = min(wb[1], 0); y2 = max(wb[3], tb[3])
    def svg(paths, box, fill, bg=None, pad=0.0, title="CORBELscore"):
        bx1, by1, bx2, by2 = box
        pw, ph = bx2 - bx1, by2 - by1
        px, py = pw * pad, pw * pad
        vb = f"{bx1 - px:.1f} {by1 - py:.1f} {pw + 2 * px:.1f} {ph + 2 * py:.1f}"
        rect = f'<rect x="{bx1 - px:.1f}" y="{by1 - py:.1f}" width="{pw + 2 * px:.1f}" height="{ph + 2 * py:.1f}" fill="{bg}"/>' if bg else ""
        # The first path is always the wordmark.
        body = "".join(f'<path d="{d}"{f' opacity="{WORD_OPACITY}"' if i == 0 else ""}/>' for i, d in enumerate(paths))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img" aria-label="{title}">'
                f"<title>{title}</title>{rect}<g fill=\"{fill}\">{body}</g></svg>\n")
    wbox = (wb[0], wb[1], wb[2], wb[3])
    lbox = (x1, y1, x2, y2)
    files = {
        "wordmark.svg": svg([word_d], wbox, LIMESTONE),
        "wordmark-basalt.svg": svg([word_d], wbox, BASALT),
        "lockup.svg": svg([word_d, tag_d], lbox, LIMESTONE, title="CORBELscore. Live broadcast scoring solution."),
        "lockup-basalt.svg": svg([word_d, tag_d], lbox, BASALT, title="CORBELscore. Live broadcast scoring solution."),
        "lockup-on-basalt.svg": svg([word_d, tag_d], lbox, LIMESTONE, bg=BASALT, pad=0.06, title="CORBELscore. Live broadcast scoring solution."),
    }
    # Icon: a corbel. Three courses of stone, each stepping further out from the
    # wall than the one below, the top one in Patina: the score the bracket
    # holds up. Basalt tile, 1024 units.
    icon = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="CORBELscore">'
            '<title>CORBELscore</title><rect width="1024" height="1024" rx="224" fill="#0c0d0d"/>'
            '<rect x="212" y="236" width="600" height="160" rx="20" fill="#4cc9d6"/>'
            '<rect x="212" y="432" width="430" height="160" rx="20" fill="#f5f5f1"/>'
            '<rect x="212" y="628" width="260" height="160" rx="20" fill="#f5f5f1"/>'
            '</svg>\n')
    files["icon.svg"] = icon
    for name, data in files.items():
        (OUT / name).write_text(data)
    json.dump({"wordmark_width": round(wb[2] - wb[0], 1), "tagline_size": round(tsize, 2), "cap": round(cap, 1)}, open(OUT / "metrics.json", "w"), indent=1)
    # PNGs for the icon and a preview of the lockup.
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for size in (16, 24, 32, 48, 64, 128, 256, 512):
            page = await b.new_page(viewport={"width": size, "height": size})
            await page.set_content(f"<style>html,body{{margin:0;background:transparent}}</style><img src='data:image/svg+xml;utf8,{icon.replace('#', '%23')}' width={size} height={size}>")
            await page.screenshot(path=str(OUT / f"icon-{size}.png"), omit_background=True)
            await page.close()
        page = await b.new_page(viewport={"width": 1640, "height": 400})
        lock = files["lockup-on-basalt.svg"]
        await page.set_content(f"<style>html,body{{margin:0;background:#0c0d0d}}</style><img src='data:image/svg+xml;utf8,{lock.replace('#', '%23')}' style='width:1640px'>")
        await page.screenshot(path=str(OUT / "lockup-preview.png"), full_page=True)
        await b.close()
    pngs = [str(OUT / f"icon-{s}.png") for s in (16, 24, 32, 48, 64, 128, 256)]
    subprocess.run(["convert", *pngs, str(ROOT / "app/assets/icon.ico")], check=True)
    for s in (16, 24, 32, 48, 64, 128):
        (OUT / f"icon-{s}.png").unlink()
    print("wrote", ", ".join(files), "icon.ico, icon-256.png, icon-512.png, lockup-preview.png")

asyncio.run(main())
