"""Review page: every translated text with Latin letters, cropped from the EN PDFs."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from urllib.parse import quote

import ezdxf
import pymupdf

from . import overlaps as co
from .fonts import setup

LATIN = re.compile(r"[A-Za-z]")
NONSPACE = re.compile(r"\S")
MARGIN = 6.0
DPI = 300
MAXW, MAXH = 160.0, 110.0


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

def cluster(items, maxw=MAXW, maxh=MAXH):
    groups = [{"r": it["r"], "items": [it]} for it in items]
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i], groups[j]
                if inter(pad(a["r"], 10), pad(b["r"], 10)):
                    u = union(a["r"], b["r"])
                    if u[2]-u[0] <= maxw and u[3]-u[1] <= maxh:
                        a["r"] = u; a["items"] += b["items"]; del groups[j]; changed = True; break
            if changed: break
    return groups


def build_review(out_dir: Path, sheets: list[Path] | None = None,
                 warnings: list[str] | None = None) -> Path:
    """Read the EN DXFs (`sheets`, default: every out_dir/dxf/*_EN.dxf) and their PDFs in
    out_dir/pdf; write out_dir/review/index.html + crops/ + meta.json. A sheet without its
    PDF is skipped with a message in `warnings`."""
    out_dir = Path(out_dir)
    if sheets is None:
        sheets = sorted((out_dir / "dxf").glob("*_EN.dxf"))
    todo = []
    for p in sorted(map(Path, sheets)):
        if (out_dir / "pdf" / (p.stem + ".pdf")).is_file():
            todo.append(p)
        else:
            msg = f"review: {p.stem}.pdf not found, sheet skipped"
            if warnings is None:
                print(msg)
            else:
                warnings.append(msg)
    font = setup()
    review = out_dir / "review"
    crops_dir = review / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    for f in [*crops_dir.glob("*"), *(review / "points").glob("*.png")]:
        f.unlink()                                 # points/: --crop renders of the last run

    sheets = []
    total = 0
    for p in todo:
        k, boxes, segs = co.analyse(p, font)
        items = []
        others = [e for e in co.disassemble.recursive_decompose(ezdxf.readfile(p).modelspace())
                  if e.dxftype() == "MTEXT" and not LATIN.search(e.plain_text()) and e.plain_text().strip()]
        obox = []
        for e in others:   # measure non-letter texts (O12, 277,2 ...) like text_boxes does
            e2 = co.text_boxes([e], k, font, NONSPACE)
            if e2:
                obox.append(text_rect_mm(e2[0][1], k))
        for txt, fr in boxes:
            if not LATIN.search(txt):
                continue
            r = text_rect_mm(fr, k)
            for _ in range(2):
                for o in obox:
                    if inter(pad(r, 1.5), o) or same_line(r, o):
                        r = union(r, o)
            items.append({"t": txt, "r": r, "c": ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)})
        groups = cluster(items)
        groups.sort(key=lambda g: (-g["r"][3], g["r"][0]))
        total += len(groups)
        sheets.append((p, groups))

    meta = []
    for p, groups in sheets:
        doc = pymupdf.open(out_dir / "pdf" / (p.stem + ".pdf"))
        page = doc[0]
        H = page.rect.height * 25.4 / 72
        W = page.rect.width * 25.4 / 72
        crops = []
        for i, g in enumerate(groups, 1):
            x0, y0, x1, y1 = pad(g["r"])
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
            clip = pymupdf.Rect(x0 * 72 / 25.4, (H - y1) * 72 / 25.4, x1 * 72 / 25.4, (H - y0) * 72 / 25.4)
            pix = page.get_pixmap(dpi=DPI, clip=clip, alpha=False)
            name = f"{p.stem[:-3]}_{i:02d}.png"
            pix.save(crops_dir / name)
            g["items"].sort(key=lambda it: (-it["c"][1], it["c"][0]))
            crops.append({"file": name, "w": pix.width, "h": pix.height, "rect": [x0, y0, x1, y1],
                          "texts": [(it["t"], it["c"][0], it["c"][1]) for it in g["items"]]})
        doc.close()
        meta.append({"sheet": p.stem, "W": W, "crops": crops})
    (review / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

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
            u = e(quote(c["file"]))
            parts.append(f'<figure><div class="scroll"><a href="crops/{u}" target="_blank"><img src="crops/{u}" width="{c["w"]}" height="{c["h"]}" alt="" loading="lazy"></a></div>'
                         f'<figcaption><b>{e(c["file"])}</b> <span class="pos">x {x0:.0f}–{x1:.0f}, y {y0:.0f}–{y1:.0f} mm</span><ul>{lis}</ul></figcaption></figure>')
        parts.append("</div>")
    parts.append("</body></html>")
    (review / "index.html").write_text("".join(parts), encoding="utf-8")
    return review / "index.html"


def review_crops_at(pdf: Path, x_mm: float, y_mm: float) -> list[Path]:
    """Review crops of this sheet (from <out>/review/meta.json) whose rect contains (x, y)."""
    pdf = Path(pdf)
    review = pdf.parent.parent / "review"
    try:
        meta = json.loads((review / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for m in meta:
        if m.get("sheet") != pdf.stem:
            continue
        for c in m.get("crops", []):
            x0, y0, x1, y1 = c["rect"]
            if x0 <= x_mm <= x1 and y0 <= y_mm <= y1 and (review / "crops" / c["file"]).is_file():
                out.append(review / "crops" / c["file"])
    return out


def crop_point(pdf: Path, x_mm: float, y_mm: float, out_png: Path | None = None,
               w_mm: float = 80.0, h_mm: float = 50.0) -> Path:
    """Render a w x h mm area of page 1 of `pdf` centred on (x, y) sheet mm (origin bottom
    left, like the overlap report) at DPI. Default output: <out>/review/points/."""
    pdf = Path(pdf)
    if out_png is None:
        out_png = pdf.parent.parent / "review" / "points" / f"{pdf.stem}_{x_mm:.0f}_{y_mm:.0f}.png"
    out_png = Path(out_png)
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        W = page.rect.width * 25.4 / 72
        H = page.rect.height * 25.4 / 72
        x0, x1 = max(0.0, x_mm - w_mm / 2), min(W, x_mm + w_mm / 2)
        y0, y1 = max(0.0, y_mm - h_mm / 2), min(H, y_mm + h_mm / 2)
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"point ({x_mm:g}, {y_mm:g}) mm is outside the sheet ({W:.0f} x {H:.0f} mm)")
        clip = pymupdf.Rect(x0 * 72 / 25.4, (H - y1) * 72 / 25.4, x1 * 72 / 25.4, (H - y0) * 72 / 25.4)
        pix = page.get_pixmap(dpi=DPI, clip=clip, alpha=False)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        pix.save(out_png)
    return out_png
