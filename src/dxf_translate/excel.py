"""Excel production lists: UA/EN pairing and glossary extraction."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import openpyxl

from dxf_translate.glossary import Glossary, GlossaryError

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")
MATERIAL_COL = "Матеріал"


def _strings(path: Path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    for row in ws.iter_rows(values_only=True):
        for c in row:
            if isinstance(c, str) and c.strip():
                yield c


def classify(path: Path) -> Literal["ua", "en"]:
    cells = list(_strings(path))
    if not cells:
        return "en"
    cyr = sum(1 for c in cells if CYR.search(c))
    return "ua" if cyr / len(cells) > 0.2 else "en"


def pick_pair(paths: list[Path]) -> tuple[Path, Path] | None:
    xlsx = [Path(p) for p in paths if Path(p).suffix.lower() == ".xlsx"]
    if not xlsx:
        return None
    ua = [p for p in xlsx if classify(p) == "ua"]
    en = [p for p in xlsx if classify(p) == "en"]
    if len(ua) != 1 or len(en) != 1:
        raise GlossaryError(
            f"ambiguous Excel: need exactly one UA and one EN file, "
            f"found {len(ua)} UA ({', '.join(p.name for p in ua)}) "
            f"and {len(en)} EN ({', '.join(p.name for p in en)})"
        )
    return ua[0], en[0]


def add_excel_pairs(g: Glossary, ua: Path, en: Path) -> int:
    """Pair cells of the UA and EN production lists (same layout) into glossary entries."""
    ws_ua = openpyxl.load_workbook(ua, data_only=True).active
    ws_en = openpyxl.load_workbook(en, data_only=True).active
    mat_col = pn_col = name_col = None
    n = 0
    for r_ua, r_en in zip(ws_ua.iter_rows(values_only=True), ws_en.iter_rows(values_only=True)):
        if MATERIAL_COL in r_ua:
            mat_col = r_ua.index(MATERIAL_COL)
            pn_col, name_col = r_ua.index("Позначення"), r_ua.index("Назва")
        elif pn_col is not None and isinstance(r_en[pn_col], str) and r_en[pn_col].startswith("AS"):
            mat = r_en[mat_col] if mat_col < len(r_en) else None
            g.parts[r_en[pn_col].strip()] = (r_en[name_col], mat)
        for i, (u, e) in enumerate(zip(r_ua, r_en)):
            if not (isinstance(u, str) and isinstance(e, str) and CYR.search(u)):
                continue
            u, e = u.strip(), e.strip()
            if CYR.search(e):
                print(f"   !! Excel: not translated yet: {u!r}")
                continue
            if i == mat_col and u != MATERIAL_COL:
                g.full_material[u] = e
                g.bom_material[u] = e
            else:
                g.phrases[u] = e
            n += 1
    return n
