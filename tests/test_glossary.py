import pytest
import yaml

from dxf_translate.glossary import GlossaryError, Glossary, load, load_base, load_file, save_terms


def test_base_sizes_frozen():
    # sizes recorded from the prototype glossary before it was removed
    g = load_base()
    assert (len(g.phrases), len(g.notes), len(g.substr)) == (39, 7, 12)


def test_order_file_wins(tmp_path):
    (tmp_path / "glossary.yaml").write_text('phrases:\n  "Балка": "Girder"\n', encoding="utf-8")
    g = load(tmp_path)
    assert g.lookup("phrases", "Балка") == "Girder"
    assert g.lookup("phrases", "Розгортка") == "Flat pattern"


def test_load_without_order_file(tmp_path):
    assert load(tmp_path).phrases == load_base().phrases
    assert load(None).phrases == load_base().phrases


def test_lookup_ignores_linebreaks():
    g = load_base()
    assert g.lookup("phrases", "Площини прилягання\\Pдо") == "Surfaces mating with"
    assert g.lookup("phrases", "Площини  прилягання^Jдо") == "Surfaces mating with"
    assert g.lookup("phrases", "nope") is None


def test_lookup_sees_later_mutation_and_later_key_wins():
    g = Glossary({"a b": "1", "a  b": "2"}, {}, {}, {}, [])
    assert g.lookup("phrases", "a b") == "2"
    g.phrases["c"] = "3"
    assert g.lookup("phrases", "c") == "3"
    g.phrases["c"] = "4"
    assert g.lookup("phrases", "c") == "4"


def test_merge():
    a = Glossary({"x": "1"}, {}, {}, {}, [("p", "q")])
    b = Glossary({"x": "2"}, {}, {}, {}, [("p", "z"), ("r", "s")], assembly_suffix="S")
    a.merge(b)
    assert a.phrases == {"x": "2"}
    assert a.substr == [("p", "q"), ("r", "s")]
    assert a.assembly_suffix == "S"


def test_malformed_yaml_raises(tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text("phrases: {a: [", encoding="utf-8")
    with pytest.raises(GlossaryError) as e:
        load_file(p)
    assert "glossary.yaml" in str(e.value) and "line" in str(e.value)


def test_unknown_section_raises(tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text("bogus: {a: b}\n", encoding="utf-8")
    with pytest.raises(GlossaryError) as e:
        load_file(p)
    assert "bogus" in str(e.value)


def test_save_terms_roundtrip(tmp_path):
    p = tmp_path / "glossary.yaml"
    p.write_text('phrases:\n  "Балка": "Beam"\n', encoding="utf-8")
    save_terms(p, {"phrases": {"Кришка": "Lid"}, "notes": {"Увага": "Caution"}})
    raw = p.read_text(encoding="utf-8")
    assert "Кришка" in raw and "\\u" not in raw
    data = yaml.safe_load(raw)
    assert data["phrases"] == {"Балка": "Beam", "Кришка": "Lid"}
    assert data["notes"] == {"Увага": "Caution"}


def test_save_terms_creates_file(tmp_path):
    p = tmp_path / "new.yaml"
    save_terms(p, {"phrases": {"а": "a"}})
    assert load_file(p).phrases == {"а": "a"}
