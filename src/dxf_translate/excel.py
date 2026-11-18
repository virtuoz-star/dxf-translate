"""The order's translation file: one Excel production list with UA and EN columns side by side."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from dxf_translate.glossary import Glossary, GlossaryError

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
REQUIRED = ("Позначення", "Назва", "Name", "Матеріал", "Material")
# UA column -> EN column read from the same row
_PAIRS = (("Назва", "Name"), ("Матеріал", "Material"))


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
