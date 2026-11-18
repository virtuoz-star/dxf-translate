from fixtures import make_sheet

from dxf_translate.glossary import load_base
from dxf_translate.review import build_review
from dxf_translate.translate import translate_file


def test_review_builds(tmp_path):
    src = make_sheet(tmp_path / "AS1.001.DXF")
    translate_file(src, tmp_path, load_base())
    idx = build_review(tmp_path)
    assert idx == tmp_path / "review" / "index.html"
    html = idx.read_text(encoding="utf-8")
    assert "Translated texts review" in html and "AS1.001" in html
    crops = sorted((tmp_path / "review" / "crops").glob("*.png"))
    assert crops
    assert (tmp_path / "review" / "meta.json").exists()
    stale = tmp_path / "review" / "crops" / "stale.png"
    stale.write_bytes(b"x")
    build_review(tmp_path)
    assert not stale.exists()
    assert sorted((tmp_path / "review" / "crops").glob("*.png")) == crops


def test_review_skips_sheet_without_pdf(tmp_path):
    a = translate_file(make_sheet(tmp_path / "AS1.001.DXF"), tmp_path, load_base())
    b = translate_file(make_sheet(tmp_path / "AS1.002.DXF"), tmp_path, load_base())
    b.pdf.unlink()
    w: list[str] = []
    idx = build_review(tmp_path, [a.dxf, b.dxf], warnings=w)
    assert idx.is_file() and len(w) == 1 and "AS1.002_EN.pdf" in w[0]
    assert "AS1.002" not in idx.read_text(encoding="utf-8")


def test_review_escapes_crop_names(tmp_path):
    translate_file(make_sheet(tmp_path / "A&B'1.DXF"), tmp_path, load_base())
    html = build_review(tmp_path).read_text(encoding="utf-8")
    assert "crops/A&B" not in html and "A'B" not in html
    assert 'src="crops/A%26B%271_01.png"' in html


def test_crop_point_and_review_crops_at(tmp_path):
    import json
    from dxf_translate.review import crop_point, review_crops_at
    s = translate_file(make_sheet(tmp_path / "AS1.001.DXF"), tmp_path, load_base())
    build_review(tmp_path)
    meta = json.loads((tmp_path / "review" / "meta.json").read_text(encoding="utf-8"))
    c = meta[0]["crops"][0]
    x, y = (c["rect"][0] + c["rect"][2]) / 2, (c["rect"][1] + c["rect"][3]) / 2
    assert tmp_path / "review" / "crops" / c["file"] in review_crops_at(s.pdf, x, y)
    assert review_crops_at(s.pdf, -50, -50) == []
    png = crop_point(s.pdf, x, y)
    assert png.parent == tmp_path / "review" / "points" and png.stat().st_size > 0
