"""The order's translation file: one Excel production list with UA and EN columns side by side."""
from __future__ import annotations

import re
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter

from dxf_translate.glossary import Glossary, GlossaryError

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
REQUIRED = ("Позначення", "Назва", "Name", "Матеріал", "Material")
# UA column -> EN column read from the same row
_PAIRS = (("Назва", "Name"), ("Матеріал", "Material"))
# UA columns left out of the English production list
DROP = ("Назва", "Матеріал")


@dataclass
class TranslationFile:
    path: Path
    header_row: int                                   # 1-based
    cols: dict[str, int]                              # header text -> 1-based column
    pairs: int = 0                                    # glossary entries added
    missing: list[tuple[str, str, str]] = field(default_factory=list)  # (ua_text, "Name"|"Material", part_no)


def _text(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _header_cols(row) -> dict[str, int]:
    cols: dict[str, int] = {}
    for c in row:
        t = _text(c.value)
        if t:
            cols.setdefault(t, c.column)
    return cols


def read_translations(g: Glossary, path: Path) -> TranslationFile:
    """Add the file's UA->EN names and materials (and Part No. -> (Name, Material)) to `g`.

    Header row = first row of the first sheet holding all REQUIRED headers. Data rows are rows
    whose `Позначення` matches the glossary's Part No. pattern. A UA name/material whose EN cell
    is empty or still Cyrillic is reported in `missing` and not added."""
    path = Path(path)
    try:
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = list(ws.iter_rows())
    except Exception as exc:
        raise GlossaryError(f"{path}: cannot read translation file: {type(exc).__name__}: {exc}") from exc

    header_row, cols, best, start = 0, {}, set(), 0
    for i, row in enumerate(rows):
        found = _header_cols(row)
        have = {h for h in REQUIRED if h in found}
        if len(have) == len(REQUIRED):
            header_row, cols, start = row[0].row, found, i + 1
            break
        if len(have) > len(best):
            best = have
    if not header_row:
        need = ", ".join(h for h in REQUIRED if h not in best)
        raise GlossaryError(f"{path}: not a translation file: missing column header(s) {need} "
                            f"(need {', '.join(REQUIRED)} in one row)")

    tf = TranslationFile(path, header_row, cols)
    for row in rows[start:]:
        cell = {c.column: c.value for c in row}
        pn = _text(cell.get(cols["Позначення"]))
        if not pn or not g.is_part_no(pn):
            continue
        en_vals: dict[str, str | None] = {}
        found: list[tuple[int, str, str]] = []
        for ua_col, en_col in _PAIRS:
            ua, en = _text(cell.get(cols[ua_col])), _text(cell.get(cols[en_col]))
            ok = bool(en) and not CYR.search(en)
            en_vals[en_col] = en if ok else None
            if not ua:
                if en and not ok:                  # Cyrillic in the EN cell, UA cell empty
                    found.append((cols[en_col], en, en_col))
                continue
            if not ok:
                found.append((cols[en_col], ua, en_col))
                continue
            if not CYR.search(ua):
                continue
            if en_col == "Material":
                g.full_material[ua] = en
                g.bom_material[ua] = en
            else:
                g.phrases[ua] = en
            tf.pairs += 1
        tf.missing += [(ua, col, pn) for _, ua, col in sorted(found)]
        g.parts[pn] = (en_vals["Name"], en_vals["Material"])
    return tf


_CELL = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d+)$")
_COL = re.compile(r"^(\$?)([A-Za-z]{1,3})$")
_ROW = re.compile(r"^\$?\d+$")


class _DroppedRef(Exception):
    """A formula reference points into a dropped column (arg: 1-based source column)."""


def _shift_ref(ref: str, new_col: dict[int, int], sheet: str) -> str:
    """Rewrite one RANGE operand (`A1`, `$F$5`, `A1:B2`, `F:F`, `3:3`, `Sheet1!F5`) through the
    column mapping. Other sheets, names and anything unrecognised stay as they are."""
    prefix, sep, body = ref.rpartition("!")
    if sep and prefix.strip("'").replace("''", "'").casefold() != sheet.casefold():
        return ref
    parts = body.split(":")
    if len(parts) > 2:
        return ref
    out = []
    for part in parts:
        m = _CELL.match(part)
        if m is None and len(parts) == 2:
            m = _COL.match(part)
            if m is None and _ROW.match(part):
                out.append(part)
                continue
        if m is None:
            return ref                              # a defined name or similar
        c = column_index_from_string(m.group(2).upper())
        if c not in new_col:
            raise _DroppedRef(c)
        out.append(m.group(1) + get_column_letter(new_col[c]) + "".join(m.groups()[2:]))
    return prefix + sep + ":".join(out)


def _shift_formula(f: str, new_col: dict[int, int], sheet: str) -> str:
    tok = Tokenizer(f)
    for t in tok.items:
        if t.type == "OPERAND" and t.subtype == "RANGE":
            t.value = _shift_ref(t.value, new_col, sheet)
    return "=" + "".join(t.value for t in tok.items)


def en_list_path(tf: TranslationFile, out_dir: Path) -> Path:
    return Path(out_dir) / f"{tf.path.stem}_EN.xlsx"


def export_en(tf: TranslationFile, g: Glossary,
              out_dir: Path) -> tuple[Path, list[str], list[str]]:
    """Write `<out_dir>/<stem>_EN.xlsx`: the first sheet of the translation file without the UA
    columns Назва/Матеріал, other Cyrillic cells translated via `g.lookup("phrases")`.
    Styles, column widths (shifted), row heights and merges (recomputed) are kept. A formula cell
    gets its cached value; without one (file saved by a program that doesn't compute) the
    formula is kept with its same-sheet references moved to the new columns.
    Returns (path, untranslated, problems): the Cyrillic cells left untranslated (UA text, first
    occurrence order; Name/Material cells of data rows are not repeated here, `read_translations`
    reports them), and formulas that refer to a dropped column (left empty)."""
    src_wb = openpyxl.load_workbook(tf.path)
    src = src_wb.worksheets[0]
    cached = openpyxl.load_workbook(tf.path, data_only=True).worksheets[0]
    drop = {tf.cols[h] for h in DROP}
    keep = [c for c in range(1, src.max_column + 1) if c not in drop]
    new_col = {c: i for i, c in enumerate(keep, 1)}
    en_cols = {tf.cols[h] for h in ("Name", "Material")}
    pn_col = tf.cols["Позначення"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = src.title
    missing: list[str] = []
    problems: list[str] = []
    for row in src.iter_rows():
        r = row[0].row
        pn = _text(src.cell(r, pn_col).value)
        data_row = r > tf.header_row and bool(pn) and g.is_part_no(pn)
        for c in row:
            if c.column in drop:
                continue
            dst = ws.cell(r, new_col[c.column])
            if c.has_style:
                dst.font, dst.fill, dst.border = copy(c.font), copy(c.fill), copy(c.border)
                dst.alignment, dst.protection = copy(c.alignment), copy(c.protection)
                dst.number_format = c.number_format
            if isinstance(c, MergedCell):
                continue
            v = c.value
            if c.data_type == "f":
                cv = cached.cell(r, c.column).value
                if cv is not None:
                    v = cv
                elif isinstance(v, str):
                    try:
                        v = _shift_formula(v, new_col, src.title)
                    except _DroppedRef as e:
                        name = next(h for h in DROP if tf.cols[h] == e.args[0])
                        problems.append(f"formula in {c.coordinate} ({c.value}) refers to "
                                        f"dropped column {name}")
                        v = None
            if isinstance(v, str) and CYR.search(v):
                en = g.lookup("phrases", v)
                if en is not None:
                    v = en
                elif not (data_row and c.column in en_cols) and v.strip() not in missing:
                    missing.append(v.strip())
            dst.value = v

    for letter, dim in src.column_dimensions.items():
        lo = dim.min or column_index_from_string(letter)
        for c in range(lo, (dim.max or lo) + 1):
            if c not in new_col:
                continue
            d = ws.column_dimensions[get_column_letter(new_col[c])]
            d.width, d.hidden = dim.width, dim.hidden
    for r, dim in src.row_dimensions.items():
        if dim.height is not None:
            ws.row_dimensions[r].height = dim.height
        if dim.hidden:
            ws.row_dimensions[r].hidden = True
    for m in src.merged_cells.ranges:
        cols = [new_col[c] for c in range(m.min_col, m.max_col + 1) if c in new_col]
        if not cols or (len(cols) == 1 and m.min_row == m.max_row):
            continue
        ws.merge_cells(start_row=m.min_row, start_column=min(cols),
                       end_row=m.max_row, end_column=max(cols))

    out = en_list_path(tf, out_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out, missing, problems
