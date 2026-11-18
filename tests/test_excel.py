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
