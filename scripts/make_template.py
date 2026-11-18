"""Regenerate `templates/translation-template.xlsx`, the empty translation file for a new order.

    uv run python scripts/make_template.py [OUT]

Example rows use made-up parts; replace them with the order's production list.
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "templates" / "translation-template.xlsx"

HEAD = ["Ф", "Поз.", "Позначення", "Назва", "Name", "Кільк.", "Матеріал", "Material", "Довжина"]
WIDTHS = [5, 6, 24, 30, 30, 7, 30, 36, 10]
ROWS = [
    ["Деталі"],
    [None, 1, "AS00.001", "Кронштейн", "Bracket", 4, "Лист 3 алюм.", "Sheet 3 Aluminum", 120],
    [None, 2, "AS00.002", "Втулка різьбова", "Threaded bushing", 8, "Круг 12 алюм.",
     "Round bar 12 Aluminum", 15],
    ["Зварювальні роботи"],
    ["СК", 3, "AS00.100", "Рама", "Frame", 1, None, None, None],
]


def build(out: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Production"
    thin = Side(style="thin", color="999999")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    ua_fill = PatternFill("solid", fgColor="FFF2CC")       # UA columns: dropped in the EN copy
    en_fill = PatternFill("solid", fgColor="DDEBF7")       # EN columns: fill these in
    ws.append(HEAD)
    for r in ROWS:
        ws.append(r)
    ncol = len(HEAD)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ncol):
        for c in row:
            c.border = box
            c.alignment = Alignment(vertical="center", wrap_text=True)
            h = HEAD[c.column - 1]
            if c.row > 1 and h in ("Назва", "Матеріал"):
                c.fill = ua_fill
            elif c.row > 1 and h in ("Name", "Material"):
                c.fill = en_fill
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, r in enumerate(ROWS, 2):
        if len(r) == 1:                                     # section row
            ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=ncol)
            ws.cell(i, 1).font = Font(bold=True)
            ws.cell(i, 1).alignment = Alignment(horizontal="center")
    for i, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT))
