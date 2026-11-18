import openpyxl
from openpyxl.styles import Font

from dxf_translate import glossary
from dxf_translate.excel import export_en, read_translations
from dxf_translate.pipeline import run_job
from fixtures import make_sheet

HEAD = ["Ф", "Поз.", "Позначення", "Назва", "Name", "Кільк.", "Матеріал", "Material", "Довжина"]
ROW = [" ", 1, "AS1.001", "Балка", "Beam-EN", 4, "Лист 3 алюм.", "Sheet 3 Al", 15]
WIDTHS = dict(zip("ABCDEFGHI", [4.5, 6.0, 35.5, 28.3, 28.4, 7.7, 39.1, 39.2, 14.3]))


def make(path, section="Деталі"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEAD)
    ws.append([section])
    ws.append(ROW)
    ws.merge_cells("A2:I2")
    ws["A2"].font = Font(bold=True)
    ws.row_dimensions[3].height = 33.0
    for col, w in WIDTHS.items():
        ws.column_dimensions[col].width = w
    wb.save(path)
    return path


def export(tmp_path, section="Деталі"):
    g = glossary.load_base()
    tf = read_translations(g, make(tmp_path / "List.xlsx", section))
    out, missing = export_en(tf, g, tmp_path / "out")
    return out, missing, openpyxl.load_workbook(out).worksheets[0]


def test_columns_dropped_and_headers_translated(tmp_path):
    out, missing, ws = export(tmp_path)
    assert out == tmp_path / "out" / "List_EN.xlsx" and missing == []
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("F", "Item", "Part No.", "Name", "Qty", "Material", "Length")
    assert rows[2] == (" ", 1, "AS1.001", "Beam-EN", 4, "Sheet 3 Al", 15)
    widths = {c: ws.column_dimensions[c].width for c in "ABCDEFG"}
    assert widths == dict(zip("ABCDEFG", [4.5, 6.0, 35.5, 28.4, 7.7, 39.2, 14.3]))
    assert ws.row_dimensions[3].height == 33.0


def test_merged_section_row(tmp_path):
    _, _, ws = export(tmp_path)
    assert [str(r) for r in ws.merged_cells.ranges] == ["A2:G2"]
    assert ws["A2"].value == "Parts" and ws["A2"].font.bold


def test_untranslated_cell_reported(tmp_path):
    _, missing, ws = export(tmp_path, "Невідомий розділ")
    assert missing == ["Невідомий розділ"]
    assert ws["A2"].value == "Невідомий розділ"


def test_merge_inside_dropped_columns_removed_and_spanning_shrinks(tmp_path):
    g = glossary.load_base()
    p = make(tmp_path / "List.xlsx")
    wb = openpyxl.load_workbook(p)
    ws = wb.active
    ws.append([None] * 9)
    ws.merge_cells("D4:D5")             # inside dropped Назва
    ws.merge_cells("C4:E4")             # spans Назва -> C4:D4
    wb.save(p)
    out, _ = export_en(read_translations(g, p), g, tmp_path / "out")
    ranges = sorted(str(r) for r in openpyxl.load_workbook(out).active.merged_cells.ranges)
    assert ranges == ["A2:G2", "C4:D4"]


def test_existing_output_overwritten(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "List_EN.xlsx").write_bytes(b"old junk")
    _, _, ws = export(tmp_path)
    assert ws["A1"].value == "F"


def test_job_writes_en_list(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    t = make(tmp_path / "List.xlsx", "Невідомий розділ")
    r = run_job([tmp_path], review=False, translations=t)
    assert r.en_list == tmp_path / "EN" / "List_EN.xlsx" and r.en_list.is_file()
    m = [x for x in r.missing if x.text == "Невідомий розділ"]
    assert len(m) == 1 and m[0].kind == "phrase" and m[0].files == ["List_EN.xlsx"]


def test_locked_file_warning(tmp_path, monkeypatch):
    make_sheet(tmp_path / "a.dxf")
    t = make(tmp_path / "List.xlsx")

    def locked(self, path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(openpyxl.Workbook, "save", locked)
    r = run_job([tmp_path], review=False, translations=t)
    assert r.en_list is None
    assert [w for w in r.warnings if w.startswith("en_list_failed: PermissionError: ")]
    assert len(r.sheets) == 1 and r.sheets[0].dxf.is_file() and not r.failed
    assert r.exit_code == 2


def test_cli_prints_en_list(tmp_path):
    from test_cli import run
    make_sheet(tmp_path / "a.dxf")
    t = make(tmp_path / "List.xlsx")
    p = run(tmp_path, "--no-review", "--translations", t)
    assert f"EN production list: {tmp_path / 'EN' / 'List_EN.xlsx'}" in p.stdout, p.stdout + p.stderr
