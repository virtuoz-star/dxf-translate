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


NOTES_CROSS = ((45.0, 110.0), (47.0, 125.0))   # slanted line through the notes text (source only)


def test_overlap_caused_by_translation_survives_filter(tmp_path):
    (tmp_path / "a").mkdir()
    _, out = build(tmp_path / "a", extra_line=CROSS)
    clean_src = make_sheet(tmp_path / "clean.DXF")        # source without the line: spot was free
    res = find_overlaps(out, clean_src)
    assert res and any("Ø6" in o.text for o in res)


def test_source_hit_elsewhere_does_not_filter(tmp_path):
    (tmp_path / "a").mkdir()
    _, out = build(tmp_path / "a", extra_line=CROSS)
    other = make_sheet(tmp_path / "other.DXF", extra_line=NOTES_CROSS)
    assert find_overlaps(other, None)                      # the source does overlap, but elsewhere
    res = find_overlaps(out, other)
    assert res and any("Ø6" in o.text for o in res)
