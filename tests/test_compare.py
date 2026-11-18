import ezdxf
from compare_dxf import text_signature


def _make(path, y):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_mtext("Hello", dxfattribs={"insert": (1, y), "char_height": 2.5})
    doc.saveas(path)


def test_signature_detects_moved_text(tmp_path):
    a, b, c = tmp_path / "a.dxf", tmp_path / "b.dxf", tmp_path / "c.dxf"
    _make(a, 5.0)
    _make(b, 6.0)
    _make(c, 5.0)
    assert text_signature(a) != text_signature(b)
    assert text_signature(a) == text_signature(c)
