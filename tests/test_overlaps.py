from fixtures import make_sheet

from dxf_translate.glossary import load_base
from dxf_translate.overlaps import find_overlaps
from dxf_translate.translate import translate_file

CROSS = ((121.0, 204.0), (123.0, 216.0))   # slanted (not a table border) through the callout text


def build(tmp_path, **kw):
    src = make_sheet(tmp_path / "AS1.001.DXF", **kw)
    res = translate_file(src, tmp_path / "out", load_base())
    return src, res.dxf


def test_fixture_clean(tmp_path):
    src, out = build(tmp_path)
    assert find_overlaps(out, None) == []
    assert find_overlaps(out, src) == []


def test_overlap_found(tmp_path):
    src, out = build(tmp_path, extra_line=CROSS)
    res = find_overlaps(out, None)
    assert res and any("Ø6" in o.text for o in res)
    assert all(o.lines >= 1 and o.file == out.name for o in res)


def test_overlap_already_in_source_filtered(tmp_path):
    src, out = build(tmp_path, extra_line=CROSS)
    assert find_overlaps(out, src) == []
