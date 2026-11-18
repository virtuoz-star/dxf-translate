import openpyxl
import pytest

from dxf_translate.excel import read_translations
from dxf_translate.glossary import Glossary, GlossaryError
from dxf_translate.pipeline import run_job
from fixtures import make_sheet

HEAD = ["Позначення", "Назва", "Name", "Матеріал", "Material"]
ROW = ["AS1.001", "Балка", "Beam-EN", "Лист 3 алюм.", "Sheet 3 Al"]


def make(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def empty():
    return Glossary({}, {}, {}, {}, [])


def _check(g, tf):
    assert tf.pairs >= 2
    assert g.phrases["Балка"] == "Beam-EN"
    assert g.full_material["Лист 3 алюм."] == "Sheet 3 Al"
    assert g.bom_material["Лист 3 алюм."] == "Sheet 3 Al"
    assert g.parts["AS1.001"] == ("Beam-EN", "Sheet 3 Al")
    assert tf.missing == []


def test_reads_pairs_and_parts(tmp_path):
    g = empty()
    tf = read_translations(g, make(tmp_path / "t.xlsx", [HEAD, ROW]))
    _check(g, tf)
    assert tf.header_row == 1 and tf.cols["Позначення"] == 1 and tf.cols["Material"] == 5
    assert tf.path == tmp_path / "t.xlsx"


def test_header_not_first_row_and_reordered(tmp_path):
    order = [4, 0, 2, 3, 1]                      # shuffled columns
    head = ["Extra"] + [HEAD[i] for i in order]
    row = ["x"] + [ROW[i] for i in order]
    g = empty()
    tf = read_translations(g, make(tmp_path / "t.xlsx", [["Title"], ["Виробництво"], head, row]))
    _check(g, tf)
    assert tf.header_row == 3 and tf.cols["Extra"] == 1 and tf.cols["Позначення"] == 3


def test_missing_name_reported(tmp_path):
    g = empty()
    row = ["AS1.001", "Балка", None, "Лист 3 алюм.", "Лист 3 алюм."]
    tf = read_translations(g, make(tmp_path / "t.xlsx", [HEAD, row]))
    assert tf.missing == [("Балка", "Name", "AS1.001"), ("Лист 3 алюм.", "Material", "AS1.001")]
    assert tf.pairs == 0
    assert "Балка" not in g.phrases and "Лист 3 алюм." not in g.full_material
    assert "Лист 3 алюм." not in g.bom_material


def test_non_data_rows_ignored(tmp_path):
    g = empty()
    tf = read_translations(g, make(tmp_path / "t.xlsx", [HEAD, ["Деталі"], ["BK1", "Кришка", None]]))
    assert tf.pairs == 0 and tf.missing == [] and not g.phrases and not g.parts


def test_missing_headers_error(tmp_path):
    old = make(tmp_path / "old.xlsx", [["Поз.", "Позначення", "Назва", "Матеріал"], [1] + ROW[:2] + ROW[3:4]])
    with pytest.raises(GlossaryError) as e:
        read_translations(empty(), old)
    assert "old.xlsx" in str(e.value) and "Name" in str(e.value) and "Material" in str(e.value)
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(GlossaryError, match="bad.xlsx"):
        read_translations(empty(), bad)
    with pytest.raises(GlossaryError, match="nope.xlsx"):
        read_translations(empty(), tmp_path / "nope.xlsx")


# --- pipeline -----------------------------------------------------------------

def test_folder_xlsx_ignored(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    (tmp_path / "bad.xlsx").write_bytes(b"not a zip")
    make(tmp_path / "t.xlsx", [HEAD, ROW])
    r = run_job([tmp_path], review=False)
    assert "no_excel" in r.warnings and r.translations is None and not r.failed


def test_translations_used(tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    t = make(tmp_path / "t.xlsx", [HEAD, ["AS1.001", "Невідома деталь", "Mystery part",
                                         "Лист 3 алюм.", "Sheet 3 Aluminum"]])
    r = run_job([tmp_path], review=False, translations=t)
    assert "no_excel" not in r.warnings and r.translations.pairs == 2
    assert not r.missing and r.exit_code == 0
    import ezdxf
    texts = " ".join(e.plain_text() for e in ezdxf.readfile(r.sheets[0].dxf).modelspace()
                     if e.dxftype() == "MTEXT")
    assert "Mystery part" in texts


def test_excel_missing_exit_2(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    t = make(tmp_path / "t.xlsx", [HEAD, ["AS1.009", "Кришка", "", "Лист 3 алюм.", "Sheet 3 Al"]])
    r = run_job([tmp_path], review=False, translations=t)
    m = [x for x in r.missing if x.kind == "excel"]
    assert len(m) == 1 and m[0].text == "Кришка" and m[0].files == []
    assert m[0].hint == "Name · AS1.009"
    assert r.exit_code == 2


def test_bad_translations_aborts_before_work(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    old = make(tmp_path / "old.xlsx", [["Позначення", "Назва", "Матеріал"]])
    with pytest.raises(GlossaryError, match="Name"):
        run_job([tmp_path], translations=old)
    assert not (tmp_path / "EN").exists()


# --- CLI ----------------------------------------------------------------------

def test_cli_translations(tmp_path):
    from test_cli import run
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    t = make(tmp_path / "t.xlsx", [HEAD, ["AS1.001", "Невідома деталь", "Mystery part",
                                         "Лист 3 алюм.", "Sheet 3 Aluminum"]])
    p = run(tmp_path, "--no-review", "--translations", t)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Translation file: 2 UA->EN pairs from t.xlsx" in p.stdout

    t2 = make(tmp_path / "t2.xlsx", [HEAD, ["AS1.009", "Кришка", None, "Лист 3 алюм.", "Sheet 3 Al"]])
    p = run(tmp_path / "a.dxf", "--out", tmp_path / "EN2", "--no-review", "--translations", t2)
    assert p.returncode == 2
    assert "!! TRANSLATION FILE: fill Name for AS1.009: Кришка" in p.stdout

    old = make(tmp_path / "old.xlsx", [["Позначення", "Назва", "Матеріал"]])
    p = run(tmp_path, "--translations", old)
    assert p.returncode == 1
    assert "Name" in p.stderr and "Material" in p.stderr and "Traceback" not in p.stderr
