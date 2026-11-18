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
