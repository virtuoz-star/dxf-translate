import openpyxl
import pytest

from dxf_translate.excel import add_excel_pairs, classify, pick_pair
from dxf_translate.glossary import Glossary, GlossaryError


def make(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


UA_ROWS = [["Поз.", "Позначення", "Назва", "Матеріал"], [1, "AS1.001", "Балка", "Лист 3 алюм."]]
EN_ROWS = [["Item", "Part No.", "Name", "Material"], [1, "AS1.001", "Beam-EN", "Sheet 3 Al-EN"]]


def test_classify(tmp_path):
    ua = make(tmp_path / "ua.xlsx", UA_ROWS)
    en = make(tmp_path / "en.xlsx", EN_ROWS)
    assert classify(ua) == "ua"
    assert classify(en) == "en"


def test_pick_pair(tmp_path):
    ua = make(tmp_path / "ua.xlsx", UA_ROWS)
    en = make(tmp_path / "en.xlsx", EN_ROWS)
    ua2 = make(tmp_path / "ua2.xlsx", UA_ROWS)
    assert pick_pair([en, ua]) == (ua, en)
    assert pick_pair([]) is None
    assert pick_pair([tmp_path / "x.txt"]) is None
    with pytest.raises(GlossaryError, match="ambiguous"):
        pick_pair([ua, ua2, en])
    with pytest.raises(GlossaryError, match="ambiguous"):
        pick_pair([ua])


def test_excel_pairs(tmp_path):
    ua = make(tmp_path / "ua.xlsx", UA_ROWS)
    en = make(tmp_path / "en.xlsx", EN_ROWS)
    g = Glossary({}, {}, {}, {}, [])
    n = add_excel_pairs(g, ua, en)
    assert n >= 2
    assert g.phrases["Балка"] == "Beam-EN"
    assert g.full_material["Лист 3 алюм."] == "Sheet 3 Al-EN"
    assert g.bom_material["Лист 3 алюм."] == "Sheet 3 Al-EN"
    assert g.parts["AS1.001"] == ("Beam-EN", "Sheet 3 Al-EN")


def test_add_excel_pairs_warnings_collected(tmp_path, capsys):
    import openpyxl
    from dxf_translate.excel import add_excel_pairs
    from dxf_translate.glossary import load_base
    for n, v in (("ua", "Балка"), ("en", "Балка")):   # EN left untranslated
        wb = openpyxl.Workbook(); wb.active["A1"] = v; wb.save(tmp_path / f"{n}.xlsx")
    w: list[str] = []
    add_excel_pairs(load_base(), tmp_path / "ua.xlsx", tmp_path / "en.xlsx", warnings=w)
    assert len(w) == 1 and "Балка" in w[0]
    assert capsys.readouterr().out == ""
