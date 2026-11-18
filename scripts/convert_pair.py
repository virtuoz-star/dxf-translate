"""Convert an old UA + EN production-list pair into one translation file (dev tool, run once).

Usage: uv run python scripts/convert_pair.py UA.xlsx EN.xlsx OUT.xlsx

Copies the UA list's first sheet (values, styles, merges, column widths, row heights) and
inserts a `Name` column right after `Назва` and a `Material` column right after `Матеріал`,
filled from the EN list's cells at the same row/column as `Назва` / `Матеріал`.
"""
from __future__ import annotations

import sys
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

INSERT = {"Назва": "Name", "Матеріал": "Material"}     # UA header -> inserted EN column


def _copy_style(src, dst) -> None:
    if src.has_style:
        dst.font, dst.fill, dst.border = copy(src.font), copy(src.fill), copy(src.border)
        dst.alignment, dst.protection = copy(src.alignment), copy(src.protection)
        dst.number_format = src.number_format


def convert(ua: Path, en: Path, out: Path) -> int:
    ws_ua = openpyxl.load_workbook(ua, data_only=True).worksheets[0]
    ws_en = openpyxl.load_workbook(en, data_only=True).worksheets[0]
    after: list[int] = []                                # UA columns followed by an inserted one
    for row in ws_ua.iter_rows():
        heads = {c.value.strip(): c.column for c in row if isinstance(c.value, str)}
        if all(h in heads for h in INSERT):
            after = sorted(heads[h] for h in INSERT)
            break
    if not after:
        raise SystemExit(f"{ua}: no header row with {', '.join(INSERT)}")

    def new_col(c: int) -> int:
        return c + sum(1 for a in after if a < c)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ws_ua.title
    for row in ws_ua.iter_rows():
        for c in row:
            if isinstance(c, MergedCell):
                continue
            d = ws.cell(row=c.row, column=new_col(c.column), value=c.value)
            _copy_style(c, d)
    filled = 0
    for a in after:
        for r in range(1, ws_ua.max_row + 1):
            src = ws_ua.cell(row=r, column=a)
            if isinstance(src, MergedCell):
                continue
            d = ws.cell(row=r, column=new_col(a) + 1)
            _copy_style(src, d)
            v = ws_en.cell(row=r, column=a).value
            if v not in (None, ""):
                d.value = v
                filled += 1
    for rng in ws_ua.merged_cells.ranges:
        c2 = new_col(rng.max_col) + (1 if rng.max_col in after else 0)
        ws.merge_cells(start_row=rng.min_row, start_column=new_col(rng.min_col),
                       end_row=rng.max_row, end_column=c2)
    for letter, dim in ws_ua.column_dimensions.items():
        if dim.width is None or dim.min is None:
            continue
        for c in range(dim.min, dim.max + 1):
            ws.column_dimensions[get_column_letter(new_col(c))].width = dim.width
            if c in after:
                ws.column_dimensions[get_column_letter(new_col(c) + 1)].width = dim.width
    for r, dim in ws_ua.row_dimensions.items():
        if dim.height is not None:
            ws.row_dimensions[r].height = dim.height
    ws.freeze_panes = ws_ua.freeze_panes
    wb.save(out)
    return filled


def main(argv: list[str]) -> None:
    if len(argv) != 3:
        raise SystemExit(__doc__)
    ua, en, out = map(Path, argv)
    n = convert(ua, en, out)
    print(f"wrote {out}: {n} cell(s) filled from {en.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
