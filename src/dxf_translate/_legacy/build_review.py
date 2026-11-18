import sys, re, json, html, math
sys.path.insert(0, "/home/king/Projects/translate/tool")
from pathlib import Path
import pymupdf
from ezdxf.fonts import fonts
fonts.font_manager.build(["/home/king/Projects/translate/tool/fonts"])
import check_overlaps as co
FONT = "OpenGostTypeA-Regular.ttf"
co.FONT = FONT
ROOT = Path("/home/king/Projects/translate")
OUT = ROOT / "EN/review"; CROPS = OUT / "crops"; CROPS.mkdir(parents=True, exist_ok=True)
LATIN = re.compile(r"[A-Za-z]")
MARGIN = 6.0; DPI = 300
MAXW, MAXH = float(sys.argv[1]) if len(sys.argv) > 1 else 160, float(sys.argv[2]) if len(sys.argv) > 2 else 110
DRY = "--dry" in sys.argv

def text_rect_mm(fr, k):
    o, u, n, x0, y0, x1, y1 = fr
    w = (x1 - x0) / 0.96; cx = (x0 + x1) / 2
    x0, x1 = cx - w / 2, cx + w / 2
    # undo 0.2h shrink approx: h unknown -> grow by 25% of the shrunk height on each side, at least small
    hh = y1 - y0; y0 -= 0.25 * hh; y1 += 0.25 * hh
    pts = [o + u * x + n * y for x in (x0, x1) for y in (y0, y1)]
    xs = [p.x / k for p in pts]; ys = [p.y / k for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]

def union(a, b): return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
def inter(a, b): return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
def same_line(a, b, gap=8.0):
    vo = min(a[3], b[3]) - max(a[1], b[1])
    hg = max(a[0], b[0]) - min(a[2], b[2])
    return vo > 0.5 * min(a[3]-a[1], b[3]-b[1]) and hg < gap
def pad(r, m=MARGIN): return [r[0]-m, r[1]-m, r[2]+m, r[3]+m]

def cluster(items):
    groups = [{"r": it["r"], "items": [it]} for it in items]
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if inter(pad(a["r"], 10), pad(b["r"], 10)):
                    u = union(a["r"], b["r"])
                    if u[2]-u[0] <= MAXW and u[3]-u[1] <= MAXH:
                        a["r"] = u; a["items"] += b["items"]; del groups[j]; changed = True; break
            if changed: break
    return groups

sheets = []; total = 0
for p in sorted((ROOT / "EN/dxf").glob("*_EN.dxf")):
    k, boxes, segs = co.analyse(p, FONT)
    sw = 420 if p.stem and k and True else 420
    items = []
    others = []
    for e in co.disassemble.recursive_decompose(__import__("ezdxf").readfile(p).modelspace()):
        if e.dxftype() == "MTEXT" and not LATIN.search(e.plain_text()) and e.plain_text().strip():
            others.append(e)
    obox = []
    for e in others:   # measure non-letter texts (Ø12, 277,2 ...) like text_boxes does
        L = co.LETTER; co.LETTER = re.compile(r"\S"); e2 = co.text_boxes([e], k); co.LETTER = L
        if e2:
            r0 = text_rect_mm(e2[0][1], k); obox.append(r0)
    for txt, fr in boxes:
        if not LATIN.search(txt): continue
        r = text_rect_mm(fr, k)
        for _ in range(2):
            for o in obox:
                if inter(pad(r, 1.5), o) or same_line(r, o): r = union(r, o)
        items.append({"t": txt, "r": r, "c": ((r[0]+r[2])/2, (r[1]+r[3])/2)})
    groups = cluster(items)
    groups.sort(key=lambda g: (-g["r"][3], g["r"][0]))
    total += len(groups)
    sheets.append((p, groups))
    print(p.name, len(items), len(groups))
print("TOTAL", total)
if DRY: sys.exit()

for f in CROPS.glob("*"): f.unlink()
meta = []
for p, groups in sheets:
    doc = pymupdf.open(ROOT / "EN/pdf" / (p.stem + ".pdf")); page = doc[0]
    H = page.rect.height * 25.4 / 72; W = page.rect.width * 25.4 / 72
    crops = []
    for i, g in enumerate(groups, 1):
        x0, y0, x1, y1 = pad(g["r"])
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        clip = pymupdf.Rect(x0*72/25.4, (H-y1)*72/25.4, x1*72/25.4, (H-y0)*72/25.4)
        pix = page.get_pixmap(dpi=DPI, clip=clip, alpha=False)
        name = f"{p.stem[:-3]}_{i:02d}.png"
        pix.save(CROPS / name)
        g["items"].sort(key=lambda it: (-it["c"][1], it["c"][0]))
        crops.append({"file": name, "w": pix.width, "h": pix.height, "rect": [x0, y0, x1, y1],
                      "texts": [(it["t"], it["c"][0], it["c"][1]) for it in g["items"]]})
    meta.append({"sheet": p.stem, "W": W, "crops": crops})
(Path(sys.argv[0]).parent / "meta.json").write_text(json.dumps(meta))

e = html.escape
parts = ["""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EN translation review</title><style>
body{font:14px/1.4 system-ui,sans-serif;margin:16px;background:#fff;color:#222}
h1{font-size:20px}h2{font-size:17px;margin:28px 0 8px;border-bottom:1px solid #ccc;padding-bottom:4px}
nav a{margin-right:10px;white-space:nowrap}
.grid{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-start}
figure{margin:0;border:1px solid #ddd;padding:6px;background:#fafafa;max-width:100%%}
figure img{display:block;border:1px solid #eee}
.scroll{overflow:auto;max-width:calc(100vw - 50px)}
figcaption{font-size:12px;margin-top:4px;max-width:900px}
figcaption ul{margin:2px 0 0 16px;padding:0}.pos{color:#777}
code{background:#eef;padding:0 2px}
</style></head><body><h1>Translated texts review</h1>
<p>Every text containing Latin letters on the %d EN sheets, cropped from the EN PDFs at %d dpi with a %g mm margin (%d crops). Images are shown at natural pixel size; click to open full size. Positions are sheet mm from the bottom-left corner (x, y) of each text's centre.</p><nav>""" % (len(meta), DPI, MARGIN, total)]
for m in meta: parts.append(f'<a href="#{e(m["sheet"])}">{e(m["sheet"][:-3])}</a> ')
parts.append("</nav>")
for m in meta:
    parts.append(f'<h2 id="{e(m["sheet"])}">{e(m["sheet"])} <small>({len(m["crops"])} crops)</small></h2><div class="grid">')
    for c in m["crops"]:
        x0, y0, x1, y1 = c["rect"]
        lis = "".join(f'<li><code>{e(t[:120]).replace(chr(10), " ⏎ ")}</code> <span class="pos">({x:.0f}, {y:.0f})</span></li>' for t, x, y in c["texts"])
        parts.append(f'<figure><div class="scroll"><a href="crops/{c["file"]}" target="_blank"><img src="crops/{c["file"]}" width="{c["w"]}" height="{c["h"]}" alt="" loading="lazy"></a></div>'
                     f'<figcaption><b>{c["file"]}</b> <span class="pos">x {x0:.0f}–{x1:.0f}, y {y0:.0f}–{y1:.0f} mm</span><ul>{lis}</ul></figcaption></figure>')
    parts.append("</div>")
parts.append("</body></html>")
(OUT / "index.html").write_text("".join(parts))
