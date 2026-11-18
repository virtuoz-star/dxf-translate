"""Find translated texts that run into drawing geometry.

For every text (also inside dimensions and SolidWorks note blocks) the real text box is
measured with the PDF font, shrunk a little (so a text resting on its own shelf/underline
is not reported), and tested against all lines/arcs/circles of the sheet.
A hit is reported only if the same spot was free in the source, i.e. the overlap
was caused by translation, not drawn that way in SolidWorks.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import bbox, disassemble  # noqa: F401
from ezdxf.fonts import fonts
from ezdxf.math import Vec2

from .fonts import FONT_NAME, setup

LETTER = re.compile(r"[A-Za-zА-Яа-яІіЇїЄє]")


def segments(entities):
    segs = []
    for e in entities:
        t = e.dxftype()
        try:
            if t == "LINE":
                segs.append((Vec2(e.dxf.start), Vec2(e.dxf.end)))
            elif t in ("ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE"):
                from ezdxf import path
                pts = [Vec2(p) for p in path.make_path(e).flattening(0.05)]
                segs += list(zip(pts, pts[1:]))
        except Exception:
            pass
    return [(a, b) for a, b in segs if (b - a).magnitude > 1e-6]


def text_boxes(entities, k, font_name: str = FONT_NAME, letter: re.Pattern = LETTER):
    """(text, frame) for every MTEXT with letters.
    frame = (origin, u, n, x0, y0, x1, y1): a rectangle in the text's own coordinates
    (u along the text, n up), measured with the real font, shrunk a little across the
    height so a text resting on its own shelf/underline is not reported."""
    out = []
    for e in entities:
        if e.dxftype() != "MTEXT":
            continue
        txt = e.plain_text().strip()
        if not letter.search(txt):
            continue
        h = e.dxf.char_height
        mh = re.search(r"\\H([\d.]+)x;", e.text)
        if mh:
            h *= float(mh.group(1))
        m = re.search(r"\\W([\d.]+);", e.text)
        wf = float(m.group(1)) if m else 1.0
        font = fonts.make_font(font_name, cap_height=h)
        lines = [l for l in e.plain_text().split("\n")]
        w = max(font.text_width(l) for l in lines) * wf
        line_h = 1.667 * h * e.dxf.get("line_spacing_factor", 1.0)
        tot_h = h + (len(lines) - 1) * line_h
        ang = math.radians(e.dxf.get("rotation", 0.0))
        if e.dxf.hasattr("text_direction"):
            td = Vec2(e.dxf.text_direction)
            ang = math.atan2(td.y, td.x)
        u = Vec2(math.cos(ang), math.sin(ang))
        n = u.orthogonal()
        ap = e.dxf.get("attachment_point", 1)
        col, row = (ap - 1) % 3, (ap - 1) // 3          # 0 left/top, 1 center/middle, 2 right/bottom
        x0 = -w * col / 2
        y1 = tot_h * row / 2                             # top edge relative to insert
        y0 = y1 - tot_h
        x1 = x0 + w
        x0, x1 = x0 + 0.02 * w, x1 - 0.02 * w
        y0, y1 = y0 + 0.2 * h, y1 - 0.2 * h
        out.append((txt, (Vec2(e.dxf.insert), u, n, x0, y0, x1, y1)))
    return out


def to_local(p, frame):
    o, u, n = frame[0], frame[1], frame[2]
    d = p - o
    return Vec2(d.dot(u), d.dot(n))


def seg_hits_box(a, b, box):
    x0, y0, x1, y1 = box
    # Liang-Barsky clipping
    dx, dy = b.x - a.x, b.y - a.y
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a.x - x0), (dx, x1 - a.x), (-dy, a.y - y0), (dy, y1 - a.y)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def analyse(path: Path, font_name: str | None = None):
    font_name = font_name or setup()
    doc = ezdxf.readfile(path)
    for st in doc.styles:
        st.dxf.font = font_name
    k = doc.header["$LIMMAX"][1] / 297.0
    ents = list(disassemble.recursive_decompose(doc.modelspace()))
    return k, text_boxes(ents, k, font_name), segments(ents)


def hits(boxes, segs):
    res = []
    for txt, fr in boxes:
        box = fr[3:]
        n = sum(1 for a, b in segs if seg_hits_box(to_local(a, fr), to_local(b, fr), box))
        if n:
            # world-space anchor for reporting / matching with the source
            res.append((txt, fr, n))
    return res


@dataclass
class Overlap:
    file: str
    text: str
    x_mm: float
    y_mm: float
    lines: int


def find_overlaps(out_dxf: Path, src_dxf: Path | None) -> list[Overlap]:
    """Overlaps in out_dxf; those already present at the same spot in src_dxf are dropped."""
    font = setup()
    k, boxes, segs = analyse(out_dxf, font)
    new = hits(boxes, segs)
    if src_dxf is not None and new:
        _, sboxes, ssegs = analyse(src_dxf, font)
        old = hits(sboxes, ssegs)
        # same anchor (insert point) overlapped already in the source -> not ours
        new = [h for h in new if not any((h[1][0] - o[1][0]).magnitude < 3 * k for o in old)]
    return [Overlap(out_dxf.name, txt, fr[0].x / k, fr[0].y / k, n) for txt, fr, n in new]
