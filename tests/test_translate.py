import re

import ezdxf
import pytest
from fixtures import make_sheet

from dxf_translate.glossary import load_base
from dxf_translate.translate import Missing, UnsupportedSheet, translate_file

CYR = re.compile(r"[А-Яа-яІіЇїЄєҐґ]")


def run(tmp_path, **kw):
    src = make_sheet(tmp_path / "AS1.001.DXF", **kw)
    res = translate_file(src, tmp_path / "out", load_base())
    return res, ezdxf.readfile(res.dxf)


def texts(doc):
    msp = doc.modelspace()
    return [e.plain_text() for e in msp.query("MTEXT")] + [e.dxf.text for e in msp.query("TEXT")]


def test_frame_removed_and_info_block(tmp_path):
    res, doc = run(tmp_path)
    msp = doc.modelspace()
    assert not [e for e in msp.query("LINE") if e.dxf.layer == "FRAME"]
    ts = texts(doc)
    assert not [t for t in ts if CYR.search(t)]
    blob = "\n".join(ts)
    for s in ("Part No.: AS1.001", "Name: Beam",
              "Material: Sheet 3 Aluminum EN AW-6063 T5",
              "1.  *Reference dimension.", "2.  Break sharp edges."):
        assert s in blob
    assert res.sheet == "A3" and res.frame_lines == 7
    assert res.part_no == "AS1.001" and res.name == "Балка"
    assert res.missing == []
    assert res.pdf.is_file() and res.pdf.stat().st_size > 0


@pytest.mark.parametrize("ua,en", [("4 отв. Ø6", "4 X Ø6"), ("12 отв. М5", "12 X M5")])
def test_callout(tmp_path, ua, en):
    res, doc = run(tmp_path, callout=ua)
    assert en in texts(doc)


def test_missing_reported(tmp_path):
    res, _ = run(tmp_path, name="Невідома деталь",
                 notes=("*Розмір для довідок.", "Невідома вимога."))
    assert Missing("Невідома деталь", "phrase") in res.missing
    assert Missing("Невідома вимога.", "note") in res.missing
    assert res.report[-1] == "   !! NO TRANSLATION: Невідома вимога. | Невідома деталь"


def test_unsupported_sheet(tmp_path):
    src = make_sheet(tmp_path / "x.DXF", width=300)
    with pytest.raises(UnsupportedSheet):
        translate_file(src, tmp_path / "out", load_base())


def test_title_block_warnings_rules():
    from dxf_translate.translate import title_block_warnings as tbw
    assert tbw(0, None, None, None, False, False, []) == []           # hand-translated sheet
    assert tbw(44, "AS1", "Балка", "Лист", False, False, []) == []
    assert tbw(44, "AS1", "Збірка", None, True, False, []) == []      # assembly: no material
    assert tbw(52, "AS1", None, None, False, True, []) == []          # continuation sheet
    w = tbw(44, None, "Балка", "Лист", False, False, ["BK1.001"])
    assert len(w) == 1 and "Part No." in w[0] and "'BK1.001'" in w[0] and "part_no_pattern" in w[0]
    assert len(tbw(44, "AS1", None, None, False, False, [])) == 2


def test_part_no_outside_pattern_warns(tmp_path):
    res, doc = run(tmp_path, part_no="BK1.001")
    assert res.part_no is None
    assert any("Part No. not found" in w and "BK1.001" in w for w in res.warnings)
    assert res.report and not any("BK1.001" in l for l in res.report[1:])


def test_part_no_pattern_from_glossary(tmp_path):
    src = make_sheet(tmp_path / "BK1.001.DXF", part_no="BK1.001")
    g = load_base()
    g.part_no_pattern = r"^(AS|BK)"
    res = translate_file(src, tmp_path / "out", g)
    assert res.part_no == "BK1.001" and res.warnings == []
    assert "Part No.: BK1.001" in " ".join(texts(ezdxf.readfile(res.dxf)))


def test_clean_sheet_no_warnings(tmp_path):
    res, _ = run(tmp_path)
    assert res.warnings == []


def test_missing_note_with_double_dot_is_satisfiable(tmp_path):
    notes = ("*Розмір для довідок.", "Невідома вимога..")
    res, _ = run(tmp_path, notes=notes)
    keys = [m.text for m in res.missing if m.kind == "note"]
    assert keys == ["Невідома вимога."]
    g = load_base()
    g.notes[keys[0]] = "Unknown requirement."
    src = make_sheet(tmp_path / "AS1.002.DXF", notes=notes)
    res2 = translate_file(src, tmp_path / "out", g)
    assert not [m for m in res2.missing if m.kind == "note"]
    assert "Unknown requirement." in " ".join(texts(ezdxf.readfile(res2.dxf)))


def test_manual_sheet_unknown_part_reported(tmp_path):
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.dxf.limmin, msp.dxf.limmax = (0, 0), (420, 297)
    msp.add_mtext("1. Sharp edges blunt.^JPart No.: AS9.999^JName: Beam",
                  dxfattribs={"insert": (300, 50), "char_height": 3.5})
    doc.saveas(tmp_path / "m.dxf")
    res = translate_file(tmp_path / "m.dxf", tmp_path / "out", load_base())
    assert Missing("AS9.999", "part") in res.missing
    assert "(Part No. AS9.999 not in translation file)" in " ".join(res.report)
