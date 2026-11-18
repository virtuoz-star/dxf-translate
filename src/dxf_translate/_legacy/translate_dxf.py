"""Translate SolidWorks DXF drawings UA -> EN, remove the GOST frame, render PDF.

Usage:
    python translate_dxf.py <input_dir> <output_dir> --font <ttf>

Rules follow the manual example (example/AS029v2.010.002 EN.pdf):
  * whole GOST frame removed (border, side strip, title block, mirrored number box);
  * sheet size and view positions unchanged; roughness symbol kept;
  * technical requirements moved to bottom-right, followed by
    "Part No. / Name / Material" lines.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import ezdxf
from ezdxf.fonts import fonts
from ezdxf.math import BoundingBox2d

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glossary import (  # noqa: E402
    ASSEMBLY_SUFFIX, BOM_MATERIAL, FULL_MATERIAL, NOTES, PHRASES, SUBSTR,
)

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
SHEETS = {420: "A3", 210: "A4"}


def sheet_info(doc):
    W, H = doc.header["$LIMMAX"][:2]
    k = H / 297.0                      # DXF units per mm (SolidWorks sometimes exports x4)
    w_mm = round(W / k)
    if w_mm not in SHEETS:
        raise SystemExit(f"Unsupported sheet size {W}x{H}")
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


MEASURE_FONT = "osifont.ttf"   # set from --font; widest of the fonts we expect


def text_width(text: str, height: float) -> float:
    return fonts.make_font(MEASURE_FONT, cap_height=height).text_width(text)


def norm(s: str) -> str:
    """Compare texts ignoring line breaks (^J, \\P) and repeated spaces."""
    return re.sub(r"(\^J|\\P|\s)+", " ", s).strip()


def lookup(table: dict, s: str):
    if not hasattr(lookup, "cache"):
        lookup.cache = {}
    idx = lookup.cache.get(id(table))
    if idx is None or len(idx) != len(table):
        idx = {norm(k): v for k, v in table.items()}
        lookup.cache[id(table)] = idx
    return idx.get(norm(s))


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
    import math
    from ezdxf.math import Vec2
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
    import math
    from ezdxf.math import Vec2
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
    from ezdxf.math import Vec2
    if e.dxf.attachment_point not in (1, 4, 7):
        return
    h = e.dxf.char_height
    need = 1.05 * text_width(e.plain_text(), h)
    import math
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


def apply_substr(s: str) -> str:
    for ua, en in SUBSTR:
        s = re.sub(ua, en, s)
    return s


def tr_phrase(text: str, missing: set) -> str:
    if not CYR.search(text):
        return text
    for table in (PHRASES, BOM_MATERIAL):
        hit = lookup(table, text)
        if hit is not None:
            return hit
    out = apply_substr(text)
    if CYR.search(out):
        missing.add(norm(text))
    return out


def process(src: Path, dst_dxf: Path, report: list[str]):
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    w_mm, k = sheet_info(doc)
    missing: set[str] = set()

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
        elif h > 5 and t.startswith("AS"):
            part_no = t.rstrip(".")
        elif h > 5 and CYR.search(t):
            name = t
        elif lookup(FULL_MATERIAL, t) is not None:
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
                e.text = tr_phrase(e.text, missing)
                if layout is msp:
                    translated_msp.append(e)
                    keep_right_end(e, old_plain)
                elif layout.name.startswith("_D"):        # dimension geometry block
                    fit_on_shelf(layout, e, old_plain)
                    pull_follower(layout, e, old_plain)
        for e in layout.query("TEXT"):
            if CYR.search(e.dxf.text):
                e.dxf.text = tr_phrase(e.dxf.text, missing)
    for e in msp.query("DIMENSION"):
        t = e.dxf.get("text", "")
        if CYR.search(t):
            e.dxf.text = apply_substr(t)

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
        # a sheet translated by hand earlier: keep its notes, take name/material from Excel
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
        xl_name, xl_mat = PARTS.get(pn, (None, None))
        manual_info = [f"Part No.: {pn}"]
        if "Name" in kv:
            manual_info.append(f"Name: {xl_name or kv['Name']}")
        if "Material" in kv:
            manual_info.append(f"Material: {xl_mat or kv['Material']}")
        manual_info += extra                     # e.g. "Sheet 1"
        if pn and pn not in PARTS:
            missing.add(f"(Part No. {pn} not in Excel)")
        msp.delete_entity(manual)
    elif notes_ent is not None:
        style = notes_ent.dxf.style
        h_mm = notes_ent.dxf.char_height / k
        raw = [s.strip() for s in notes_ent.plain_text().split("\n")]
        items = [s for s in raw if s and not re.fullmatch(r"\d+\.", s)]
        for i, s in enumerate(items, 1):
            en = lookup(NOTES, re.sub(r"\.+$", ".", s))
            if en is None:
                missing.add(s)
                en = s
            note_lines.append(f"{i}.  {en}")
        msp.delete_entity(notes_ent)
    else:
        style, h_mm = "STANDARD", 3.5

    info = list(manual_info or [])
    if part_no and manual_info is None:
        info.append(f"Part No.: {part_no}")
    if name and manual_info is None:
        en_name = lookup(PHRASES, name)
        if en_name is None:
            missing.add(name)
            en_name = name
        info.append(f"Name: {en_name}{ASSEMBLY_SUFFIX if is_assembly else ''}")
    if material and manual_info is None:
        info.append(f"Material: {lookup(FULL_MATERIAL, material)}")

    sheet_no = re.search(r"_(\d\d)$", src.stem)        # multi-sheet export: name_00, name_01
    if sheet_no and info:
        info = [l for l in info if not re.fullmatch(r"Sheet \d+", l)]
        info.append(f"Sheet {int(sheet_no.group(1)) + 1}")
    longest = max((text_width(s, h_mm) for s in note_lines + info), default=0.0)
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
    from ezdxf import bbox as _bbox
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
        report.append("   !! NO TRANSLATION: " + " | ".join(sorted(missing)))
    return doc, w_mm, k


def render(doc, w_mm, k, out: Path, font_file: str, png_dpi: int | None = None):
    from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
    from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend

    for st in doc.styles:                      # GOST type A is not on Linux -> osifont
        st.dxf.font = font_file
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


MATERIAL_COL = "Матеріал"
PARTS: dict[str, tuple] = {}   # Part No. -> (EN name, EN material) from the Excel list


def bom_short(material_en: str) -> str:
    """Compact material for the narrow BOM column: drop the word Aluminum, short shape names."""
    s = material_en.replace(" Aluminum", "")
    for long, short in (("Square tube", "Tube"), ("Rectangular tube", "Tube"), ("Round bar", "Round")):
        s = s.replace(long, short)
    return s


def load_excel_pairs(ua_path: Path, en_path: Path) -> int:
    """Pair cells of the UA and EN production lists (same layout) -> glossary entries."""
    import openpyxl
    ua = openpyxl.load_workbook(ua_path, data_only=True).active
    en = openpyxl.load_workbook(en_path, data_only=True).active
    mat_col = pn_col = name_col = None
    n = 0
    for r_ua, r_en in zip(ua.iter_rows(values_only=True), en.iter_rows(values_only=True)):
        if MATERIAL_COL in r_ua:
            mat_col = r_ua.index(MATERIAL_COL)
            pn_col, name_col = r_ua.index("Позначення"), r_ua.index("Назва")
        elif pn_col is not None and isinstance(r_en[pn_col], str) and r_en[pn_col].startswith("AS"):
            mat = r_en[mat_col] if mat_col < len(r_en) else None
            PARTS[r_en[pn_col].strip()] = (r_en[name_col], mat)
        for i, (u, e) in enumerate(zip(r_ua, r_en)):
            if not (isinstance(u, str) and isinstance(e, str) and CYR.search(u)):
                continue
            u, e = u.strip(), e.strip()
            if CYR.search(e):
                print(f"   !! Excel: not translated yet: {u!r}")
                continue
            if i == mat_col and u != MATERIAL_COL:
                FULL_MATERIAL[u] = e
                BOM_MATERIAL[u] = e          # drawing BOM = Excel, word for word
            else:
                PHRASES[u] = e
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--font", required=True, help="TTF used for PDF rendering")
    ap.add_argument("--preview", type=Path, help="also write PNG previews here")
    ap.add_argument("--xlsx-ua", type=Path, help="production list, Ukrainian")
    ap.add_argument("--xlsx-en", type=Path, help="same list translated (same layout); "
                    "its names/materials override tool/glossary.py")
    a = ap.parse_args()

    if a.xlsx_ua and a.xlsx_en:
        n = load_excel_pairs(a.xlsx_ua, a.xlsx_en)
        print(f"Excel glossary: {n} UA->EN pairs from {a.xlsx_en.name}")
    font = Path(a.font).resolve()
    fonts.font_manager.build([str(font.parent)])
    global MEASURE_FONT
    MEASURE_FONT = font.name
    report = []
    for src in sorted(a.input_dir.glob("*.[dD][xX][fF]")):
        stem = src.stem + "_EN"
        try:
            doc, w_mm, k = process(src, a.output_dir / "dxf" / f"{stem}.dxf", report)
            render(doc, w_mm, k, a.output_dir / "pdf" / f"{stem}.pdf", font.name)
            if a.preview:
                doc2 = ezdxf.readfile(a.output_dir / "dxf" / f"{stem}.dxf")
                render(doc2, w_mm, k, a.preview / f"{stem}.png", font.name, png_dpi=110)
        except Exception as exc:  # keep going, report at the end
            report.append(f"{src.name}: !! FAILED: {type(exc).__name__}: {exc}")
    print("\n".join(report))


if __name__ == "__main__":
    sys.exit(main())
