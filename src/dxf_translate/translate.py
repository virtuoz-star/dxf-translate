"""Translate one SolidWorks DXF drawing UA -> EN, remove the GOST frame, render PDF.

Rules follow the manual example (AS029v2.010.002 EN.pdf):
  * whole GOST frame removed (border, side strip, title block, mirrored number box);
  * sheet size and view positions unchanged; roughness symbol kept;
  * technical requirements moved to bottom-right, followed by
    "Part No. / Name / Material" lines.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import ezdxf
from ezdxf import bbox as _bbox
from ezdxf.math import BoundingBox2d, Vec2

from dxf_translate import fonts
from dxf_translate.fonts import text_width
from dxf_translate.glossary import Glossary, norm

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
SHEETS = {420: "A3", 210: "A4"}


class UnsupportedSheet(Exception):
    """The drawing's sheet size is neither A3 nor A4."""


@dataclass
class Missing:
    text: str
    kind: Literal["phrase", "note", "part"]


@dataclass
class SheetResult:
    src: Path
    dxf: Path
    pdf: Path
    sheet: str
    frame_lines: int
    part_no: str | None
    name: str | None
    material: str | None
    missing: list[Missing] = field(default_factory=list)
    report: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)   # title-block info not found etc.


class _MissingSet:
    """Legacy `missing` set (keyed by the report string), remembering each entry's kind."""

    def __init__(self) -> None:
        self._d: dict[str, Missing] = {}

    def add(self, key: str, kind: str, text: str | None = None) -> None:
        self._d.setdefault(key, Missing(key if text is None else text, kind))

    def __bool__(self) -> bool:
        return bool(self._d)

    def keys_sorted(self) -> list[str]:
        return sorted(self._d)

    def items_sorted(self) -> list[Missing]:
        return [self._d[k] for k in sorted(self._d)]


def sheet_info(doc):
    W, H = doc.header["$LIMMAX"][:2]
    k = H / 297.0                      # DXF units per mm (SolidWorks sometimes exports x4)
    w_mm = round(W / k)
    if w_mm not in SHEETS:
        raise UnsupportedSheet(f"Unsupported sheet size {W}x{H}")
    return w_mm, k


def in_frame_zone(x, y, w_mm):
    """Title block / side strip / top-left box / bottom line zones, in sheet mm."""
    tb_x0 = 229.0 if w_mm == 420 else 17.0
    return (
        x < 20.5                          # left side strip
        or (x >= tb_x0 and y <= 61.0)     # title block
        or (x < 92.0 and y >= 277.0)      # mirrored designation box
        or y < 5.0                        # text under the frame
    )


def fix_sw_runs(text: str) -> str:
    toks = [t.strip() for t in text.split("^J")]
    if not any(re.fullmatch(r"\d+\.", t) for t in toks) and not any(t.endswith(":") for t in toks):
        return text
    lines, i = [], 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is not None and re.fullmatch(r"\d+\.", nxt):
            lines.append(f"{nxt}  {t}")
            i += 2
        elif t.endswith(":") and nxt is not None and not nxt.endswith(":"):
            lines.append(f"{t} {nxt}")
            i += 2
        else:
            lines.append(t)
            i += 1
    return "\\P".join(l for l in lines if l)


def wrap(line: str, max_w: float, h: float) -> list[str]:
    """Word-wrap one numbered note; continuation lines get a hanging indent."""
    if text_width(line, h) <= max_w:
        return [line]
    m = re.match(r"(\d+\.\s+)", line)
    indent = " " * (len(m.group(1)) + 1) if m else ""
    out, cur = [], ""
    for word in line.split(" "):
        cand = f"{cur} {word}" if cur else word
        if cur and text_width(cand, h) > max_w:
            out.append(cur)
            cur = indent + word
        else:
            cand = cand if cur else word
            cur = cand
    out.append(cur)
    return out


def keep_right_end(e, old_plain: str) -> None:
    """SolidWorks leaves blanks at the end of a label for a symbol drawn right after it
    (e.g. "ВИД B   " + rotated-view arrow). If the English label is longer, grow it to the
    left only, so it does not run into that symbol."""
    h = e.dxf.char_height
    grow = text_width(e.plain_text(), h) - text_width(old_plain, h)
    flat = old_plain.replace("\n", " ")
    if re.search(r"М\s*$", flat) and grow < 0:
        # "** 2 отв. М" + separate "8": the thread size is its own text right after the M,
        # so a shorter English text must keep its right end, otherwise "M  8" drifts apart
        pass
    elif not re.search(r"\s{2,}$", flat) or grow <= 0:
        return
    col = (e.dxf.attachment_point - 1) % 3            # 0 left, 1 center, 2 right
    shift = grow * (1.0 - col / 2.0)                  # left: whole growth, center: half
    if shift == 0:
        return
    ang = math.radians(e.dxf.get("rotation", 0.0))
    u = Vec2(math.cos(ang), math.sin(ang))
    e.dxf.insert = (Vec2(e.dxf.insert) - u * shift).vec3


def pull_follower(block, e, old_plain: str) -> None:
    """A callout split in pieces ("** 2 отв. М" + "8"): when the translated piece got
    shorter, move the piece that followed it back, so "M" and "8" stay together."""
    if e.dxf.attachment_point not in (1, 4, 7):
        return
    h = e.dxf.char_height
    old_w, new_w = text_width(old_plain, h), text_width(e.plain_text(), h)
    if new_w >= old_w:
        return
    ang = math.radians(e.dxf.get("rotation", 0.0))
    u = Vec2(math.cos(ang), math.sin(ang))
    n = u.orthogonal()
    ins = Vec2(e.dxf.insert)
    old_end = ins + u * old_w
    for f in block.query("MTEXT"):
        if f is e:
            continue
        d = Vec2(f.dxf.insert) - old_end
        if abs(d.dot(n)) < 0.3 * h and -0.5 * h < d.dot(u) < 3 * h:
            f.dxf.insert = (Vec2(f.dxf.insert) - u * (old_w - new_w)).vec3


def fit_on_shelf(block, e, old_plain: str) -> None:
    """Dimension/leader text sits on a shelf line that starts at the text's left end.
    If the English text is longer than that shelf, slide the text back along the shelf
    and lengthen the shelf by the same amount, so it does not run into extension lines."""
    if e.dxf.attachment_point not in (1, 4, 7):
        return
    h = e.dxf.char_height
    need = 1.05 * text_width(e.plain_text(), h)
    ang = math.radians(e.dxf.get("rotation", 0.0))
    if e.dxf.hasattr("text_direction"):
        td = Vec2(e.dxf.text_direction)
        ang = math.atan2(td.y, td.x)
    u = Vec2(math.cos(ang), math.sin(ang))           # along the text
    n = u.orthogonal()                               # "up" for the text
    ins = Vec2(e.dxf.insert)
    best = None
    for ln in block.query("LINE"):
        a, b = Vec2(ln.dxf.start), Vec2(ln.dxf.end)
        if abs((b - a).normalize().dot(n)) > 0.02 if (b - a).magnitude > 1e-9 else True:
            continue                                 # not parallel to the text
        for p, q, attr in ((a, b, "start"), (b, a, "end")):
            d = p - ins
            if abs(d.dot(u)) < 0.6 and abs(d.dot(n)) < 1.5 * h and (q - p).dot(u) > 0:
                length = (q - p).dot(u)
                if best is None or length > best[0]:
                    best = (length, ln, attr)
    if best is None:
        return
    avail, ln, attr = best
    if need <= avail:
        return
    delta = need - avail + 0.5
    e.dxf.insert = (ins - u * delta).vec3
    end = Vec2(getattr(ln.dxf, attr)) - u * delta
    setattr(ln.dxf, attr, end.vec3)


def apply_substr(g: Glossary, s: str) -> str:
    for ua, en in g.substr:
        s = re.sub(ua, en, s)
    return s


def tr_phrase(g: Glossary, text: str, missing: _MissingSet) -> str:
    if not CYR.search(text):
        return text
    for table in ("phrases", "bom_material"):
        hit = g.lookup(table, text)
        if hit is not None:
            return hit
    out = apply_substr(g, text)
    if CYR.search(out):
        missing.add(norm(text), "phrase")
    return out


def title_block_warnings(frame_lines: int, part_no, name, material, is_assembly: bool,
                         continuation: bool, dropped_big: list[str]) -> list[str]:
    """What the title block should have given but did not (its texts are deleted anyway).

    Only sheets that had a GOST frame are checked (frame_lines == 0: translated by hand
    earlier). Part No. is expected on every framed sheet; name on the first sheet only
    (continuation sheets `_01`, `_02`... use the short title block); material only on
    part drawings (an assembly drawing "СБ" has no material cell)."""
    if not frame_lines:
        return []
    out = []
    if part_no is None:
        msg = "title block: Part No. not found"
        if dropped_big:
            msg += (f" (dropped {', '.join(repr(t) for t in dropped_big)}: "
                    f"set part_no_pattern in the order glossary.yaml)")
        out.append(msg)
    if name is None and not continuation:
        out.append("title block: name not found")
    if material is None and not continuation and not is_assembly:
        out.append("title block: material not found (a material missing from the glossary "
                   "is dropped: add it to full_material + bom_material)")
    return out


def process(src: Path, dst_dxf: Path, g: Glossary, report: list[str]):
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    w_mm, k = sheet_info(doc)
    missing = _MissingSet()

    # 1. frame lines: SolidWorks writes the sheet-format lines first, before anything else
    lead = []
    for e in msp:
        if e.dxftype() == "LINE" and e.dxf.layer != "0":
            lead.append(e)
        else:
            break
    for e in lead:
        msp.delete_entity(e)

    # 2. title-block texts: collect info, then delete
    part_no = name = material = None
    is_assembly = False
    dropped_big = []                # big non-Cyrillic title-block texts that are not a Part No.
    notes_ent = None
    # sheet-format texts are written right after the frame lines, as one run of MTEXT
    #     (the frame lines were already deleted, so model space now starts with that run)
    sheet_run = set()
    for e in msp:
        if e.dxftype() != "MTEXT":
            break
        sheet_run.add(e.dxf.handle)
    for e in list(msp.query("MTEXT")):
        t = e.plain_text().strip()
        if "Розмір для довідок" in t:
            notes_ent = e
            continue
        x, y = e.dxf.insert.x / k, e.dxf.insert.y / k
        if not lead or e.dxf.handle not in sheet_run or not in_frame_zone(x, y, w_mm):
            continue
        h = e.dxf.char_height / k
        if t == "СБ":
            is_assembly = True
        elif h > 5 and g.is_part_no(t):
            part_no = t.rstrip(".")
        elif h > 5 and CYR.search(t):
            name = t
        elif h > 5 and t:
            dropped_big.append(t)
        elif g.lookup("full_material", t) is not None:
            material = t
        msp.delete_entity(e)

    # 2b. SolidWorks exports note runs separated by ^J: rebuild real lines
    for e in msp.query("MTEXT"):
        if e is not notes_ent and "^J" in e.text:
            fixed = fix_sw_runs(e.text)
            if fixed != e.text:
                e.text = fixed

    # 3. translate remaining texts (model space + all blocks: notes, dimension blocks)
    translated_msp = []
    for layout in [msp, *doc.blocks]:
        for e in layout.query("MTEXT"):
            if e is notes_ent:
                continue
            if CYR.search(e.text):
                old_plain = e.plain_text()
                e.text = tr_phrase(g, e.text, missing)
                if layout is msp:
                    translated_msp.append(e)
                    keep_right_end(e, old_plain)
                elif layout.name.startswith("_D"):        # dimension geometry block
                    fit_on_shelf(layout, e, old_plain)
                    pull_follower(layout, e, old_plain)
        for e in layout.query("TEXT"):
            if CYR.search(e.dxf.text):
                e.dxf.text = tr_phrase(g, e.dxf.text, missing)
    for e in msp.query("DIMENSION"):
        t = e.dxf.get("text", "")
        if CYR.search(t):
            e.dxf.text = apply_substr(g, t)

    # 3b. table cells: squeeze text that would run into the next cell on the same row
    #     (cell border = nearest vertical line to the right that crosses the text row)
    vlines = [(l.dxf.start.x, min(l.dxf.start.y, l.dxf.end.y), max(l.dxf.start.y, l.dxf.end.y))
              for l in msp.query("LINE") if abs(l.dxf.start.x - l.dxf.end.x) < 1e-6]
    for e in translated_msp:
        x, y = e.dxf.insert.x, e.dxf.insert.y
        yc = y - e.dxf.char_height / 2
        right = [lx for lx, y0, y1 in vlines if lx > x + 0.5 * k and y0 <= yc <= y1
                 and lx - x < 80 * k]
        if not right:
            continue
        avail = min(right) - x - 1.0 * k
        need = 1.05 * text_width(e.plain_text(), e.dxf.char_height)
        if need > avail:
            r = avail / need
            if r >= 0.6:
                e.text = f"\\W{r:.2f};{e.text}"
            else:                                  # very narrow column: also lower the text a bit
                hf = max(r / 0.6, 0.6)
                e.text = f"\\H{hf:.2f}x;\\W{r / hf:.2f};{e.text}"

    # 4. notes + info block, bottom-right
    note_lines = []
    manual_info = None
    manual = None
    if not lead and notes_ent is None:
        manual = next((m for m in msp.query("MTEXT") if "Part No.:" in m.plain_text()), None)
    if manual is not None:
        # a sheet translated by hand earlier: keep its notes, take name/material from the translation file
        style = manual.dxf.style
        h_mm = manual.dxf.char_height / k
        lines = [l.strip() for l in manual.plain_text().split("\n") if l.strip()]
        notes = [re.sub(r"^\d+\.\s*", "", l) for l in lines if re.match(r"^\d+\.\s", l)]
        note_lines = [f"{i}.  {t}" for i, t in enumerate(notes, 1)]
        kv = {}
        extra = []
        for l in lines:
            m = re.match(r"^(Part No\.|Name|Material):\s*(.*)$", l)
            if m:
                kv[m.group(1)] = m.group(2)
            elif not re.match(r"^\d+\.\s", l):
                extra.append(l)
        pn = kv.get("Part No.", "").strip()
        xl_name, xl_mat = g.parts.get(pn, (None, None))
        manual_info = [f"Part No.: {pn}"]
        if "Name" in kv:
            manual_info.append(f"Name: {xl_name or kv['Name']}")
        if "Material" in kv:
            manual_info.append(f"Material: {xl_mat or kv['Material']}")
        manual_info += extra                     # e.g. "Sheet 1"
        if pn and pn not in g.parts:
            missing.add(f"(Part No. {pn} not in translation file)", "part", pn)
        msp.delete_entity(manual)
    elif notes_ent is not None:
        style = notes_ent.dxf.style
        h_mm = notes_ent.dxf.char_height / k
        raw = [s.strip() for s in notes_ent.plain_text().split("\n")]
        items = [s for s in raw if s and not re.fullmatch(r"\d+\.", s)]
        for i, s in enumerate(items, 1):
            key = re.sub(r"\.+$", ".", s)
            en = g.lookup("notes", key)
            if en is None:
                missing.add(key, "note")
                en = s
            note_lines.append(f"{i}.  {en}")
        msp.delete_entity(notes_ent)
    else:
        style, h_mm = "STANDARD", 3.5

    info = list(manual_info or [])
    if part_no and manual_info is None:
        info.append(f"Part No.: {part_no}")
    if name and manual_info is None:
        en_name = g.lookup("phrases", name)
        if en_name is None:
            missing.add(name, "phrase")
            en_name = name
        info.append(f"Name: {en_name}{g.assembly_suffix if is_assembly else ''}")
    if material and manual_info is None:
        info.append(f"Material: {g.lookup('full_material', material)}")

    sheet_no = re.search(r"_(\d\d)$", src.stem)        # multi-sheet export: name_00, name_01
    if sheet_no and info:
        info = [l for l in info if not re.fullmatch(r"Sheet \d+", l)]
        info.append(f"Sheet {int(sheet_no.group(1)) + 1}")
    right = w_mm - 10
    max_w = 115.0 if w_mm == 420 else 95.0          # wrap notes wider than this
    note_lines = [w for s in note_lines for w in wrap(s, max_w, h_mm)]
    box_w = max([min(text_width(s, h_mm), max_w) for s in note_lines]
                + [text_width(s, h_mm) for s in info] + [0.0])
    x0 = min(300.0 if w_mm == 420 else 110.0, right - box_w)
    line_h = 1.67 * h_mm
    gap = 6.0
    total_h = (len(note_lines) + len(info)) * line_h + (gap if note_lines and info else 0)
    y_top = max(52.0, 8.0 + total_h)              # never run off the bottom edge
    # ...but stay below anything already drawn in that corner (e.g. a BOM table)
    floor = None
    # (texts are skipped: their fast bbox is unreliable, and table texts sit inside table lines)
    geom = [e for e in msp if e.dxftype() not in ("MTEXT", "TEXT")]
    for b in _bbox.multi_flat(geom, fast=True):
        if not b.has_data:
            continue
        x_lo, x_hi = b.extmin.x / k, b.extmax.x / k
        y_lo, y_hi = b.extmin.y / k, b.extmax.y / k
        if x_hi > x0 and x_lo < right and 10.0 < y_lo < 120.0 and y_hi - y_lo < 250:
            floor = y_lo if floor is None else min(floor, y_lo)
    if floor is not None:
        y_top = min(y_top, floor - 3.0)
    if y_top - total_h < 4.0:                    # not enough room: shrink the block a little
        f = max(0.7, (y_top - 4.0) / total_h)
        h_mm, line_h, gap = h_mm * f, line_h * f, gap * f
    attribs = dict(style=style, char_height=h_mm * k, attachment_point=1, layer="0")
    if note_lines:
        msp.add_mtext("\\P".join(note_lines), dxfattribs={**attribs, "insert": (x0 * k, y_top * k)})
        y_top -= len(note_lines) * line_h + gap
    if info:
        msp.add_mtext("\\P".join(info), dxfattribs={**attribs, "insert": (x0 * k, y_top * k)})

    dst_dxf.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(dst_dxf)
    report.append(f"{src.name}: {SHEETS[w_mm]}, frame lines removed: {len(lead)}, "
                  f"Part No={part_no}, name={name}, material={material}")
    if missing:
        report.append("   !! NO TRANSLATION: " + " | ".join(missing.keys_sorted()))
    warnings = title_block_warnings(len(lead), part_no, name, material, is_assembly,
                                    sheet_no is not None and int(sheet_no.group(1)) > 0,
                                    dropped_big)
    info_out = dict(frame_lines=len(lead), part_no=part_no, name=name, material=material,
                    missing=missing.items_sorted(), warnings=warnings)
    return doc, w_mm, k, info_out


def render(doc, w_mm, k, out: Path, png_dpi: int | None = None) -> None:
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
    from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend

    font_name = fonts.setup()
    for st in doc.styles:                      # GOST type A is not on every system: bundled
        st.dxf.font = font_name
    be = PyMuPdfBackend()
    cfg = config.Configuration(
        background_policy=config.BackgroundPolicy.WHITE,
        color_policy=config.ColorPolicy.BLACK,
    )
    Frontend(RenderContext(doc), be, config=cfg).draw_layout(doc.modelspace())
    page = layout.Page(w_mm, 297, layout.Units.mm, margins=layout.Margins.all(0))
    settings = layout.Settings(scale=1 / k, fit_page=False)
    box = BoundingBox2d([(0, 0), (w_mm * k, 297 * k)])
    if png_dpi:
        data = be.get_pixmap_bytes(page, fmt="png", dpi=png_dpi, settings=settings, render_box=box)
    else:
        data = be.get_pdf_bytes(page, settings=settings, render_box=box)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)


def translate_file(src: Path, out_dir: Path, g: Glossary) -> SheetResult:
    """Translate one drawing into out_dir/dxf/<stem>_EN.dxf and out_dir/pdf/<stem>_EN.pdf."""
    fonts.setup()
    src, out_dir = Path(src), Path(out_dir)
    stem = src.stem + "_EN"
    dxf = out_dir / "dxf" / f"{stem}.dxf"
    pdf = out_dir / "pdf" / f"{stem}.pdf"
    report: list[str] = []
    doc, w_mm, k, info = process(src, dxf, g, report)
    render(doc, w_mm, k, pdf)
    return SheetResult(src=src, dxf=dxf, pdf=pdf, sheet=SHEETS[w_mm], report=report, **info)
