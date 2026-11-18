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
