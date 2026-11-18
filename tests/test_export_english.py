import re
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

from dxf_translate.cli import main
from dxf_translate.glossary import GlossaryError
from dxf_translate.pipeline import export_english
from make_template import OUT as TEMPLATE, build
from test_export_en import make

CYR = re.compile("[А-Яа-яІіЇїЄєҐґ]")


def cells(path):
    return [v for row in openpyxl.load_workbook(path).worksheets[0].iter_rows(values_only=True)
            for v in row if v is not None]


def test_export_next_to_file(tmp_path):
    src = make(tmp_path / "List.xlsx")
    res = export_english(src)
    assert res.path == tmp_path / "List_EN.xlsx" and res.clean
    assert not any(isinstance(v, str) and CYR.search(v) for v in cells(res.path))
    assert openpyxl.load_workbook(src).worksheets[0]["D1"].value == "Назва"   # source untouched


def test_order_glossary_next_to_file_used(tmp_path):
    src = make(tmp_path / "List.xlsx", section="Невідомий розділ")
    assert export_english(src).untranslated == ["Невідомий розділ"]
    (tmp_path / "glossary.yaml").write_text("phrases:\n  Невідомий розділ: Odd section\n",
                                            encoding="utf-8")
    res = export_english(src, out_dir=tmp_path / "out")
    assert res.clean and res.path == tmp_path / "out" / "List_EN.xlsx"
    assert "Odd section" in cells(res.path)


def test_empty_name_reported(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["Позначення", "Назва", "Name", "Матеріал", "Material"])
    wb.active.append(["AS1.001", "Балка", None, "Лист 3 алюм.", "Sheet 3 Al"])
    wb.save(tmp_path / "t.xlsx")
    res = export_english(tmp_path / "t.xlsx")
    assert res.missing == [("Балка", "Name", "AS1.001")] and not res.clean


def test_not_translation_file(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.append(["Позначення", "Назва", "Матеріал"])
    wb.save(tmp_path / "old.xlsx")
    with pytest.raises(GlossaryError, match="Material"):
        export_english(tmp_path / "old.xlsx")


def test_cli_export_en(tmp_path, capsys):
    src = make(tmp_path / "List.xlsx", section="Невідомий розділ")
    with pytest.raises(SystemExit) as e:
        main(["--export-en", str(src), "--out", str(tmp_path / "o")])
    out = capsys.readouterr().out
    assert e.value.code == 2
    assert f"EN production list: {tmp_path / 'o' / 'List_EN.xlsx'}" in out
    assert "!! NO TRANSLATION: Невідомий розділ" in out


def test_cli_export_en_clean_exit_0(tmp_path):
    with pytest.raises(SystemExit) as e:
        main(["--export-en", str(make(tmp_path / "List.xlsx"))])
    assert e.value.code == 0


def test_template_committed_and_current(tmp_path):
    assert TEMPLATE.is_file()
    fresh = build(tmp_path / "t.xlsx")
    assert cells(fresh) == cells(TEMPLATE)


def test_template_exports_fully_english(tmp_path):
    res = export_english(TEMPLATE, out_dir=tmp_path)
    assert res.clean, (res.missing, res.untranslated, res.problems)
    assert not any(isinstance(v, str) and CYR.search(v) for v in cells(res.path))
    assert res.path.name == "translation-template_EN.xlsx"


def test_template_tracked_by_git():
    root = TEMPLATE.parent.parent
    r = subprocess.run(["git", "check-ignore", "-q", str(TEMPLATE)], cwd=root)
    assert r.returncode == 1          # not ignored
