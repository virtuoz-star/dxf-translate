import pytest

from dxf_translate.glossary import GlossaryError
from dxf_translate.pipeline import collect_inputs, run_job
from fixtures import make_sheet


def test_cyrillic_and_spaces_in_names(tmp_path):
    make_sheet(tmp_path / "Деталь 1.DXF")
    r = run_job([tmp_path])
    assert (r.out_dir / "dxf" / "Деталь 1_EN.dxf").exists()
    assert (r.out_dir / "pdf" / "Деталь 1_EN.pdf").exists()


def test_rerun_skips_outputs(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    r1 = run_job([tmp_path])
    r2 = run_job([tmp_path])
    assert len(r1.sheets) == len(r2.sheets) == 1
    assert not list(tmp_path.rglob("*_EN_EN*"))


def test_bad_file_does_not_abort(tmp_path):
    make_sheet(tmp_path / "good.dxf")
    (tmp_path / "broken.dxf").write_bytes(b"\x00\xffgarbage")
    make_sheet(tmp_path / "wide.dxf", width=300)
    r = run_job([tmp_path])
    assert len(r.sheets) == 1 and len(r.failed) == 2
    assert r.exit_code == 1


def test_no_excel_warning(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    assert "no_excel" in run_job([tmp_path]).warnings


def _xlsx(path, text):
    import openpyxl
    wb = openpyxl.Workbook(); wb.active["A1"] = text; wb.save(path)


def test_ambiguous_excel(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    _xlsx(tmp_path / "one.xlsx", "Балка")
    _xlsx(tmp_path / "two.xlsx", "Деталь")
    with pytest.raises(GlossaryError, match="ambiguous"):
        run_job([tmp_path])
    assert not (tmp_path / "EN").exists()


def test_order_glossary_used(tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    (tmp_path / "glossary.yaml").write_text(
        'phrases:\n  "Невідома деталь": "Mystery part"\n', encoding="utf-8")
    r = run_job([tmp_path])
    assert not r.missing
    import ezdxf
    texts = " ".join(e.plain_text() for e in ezdxf.readfile(r.sheets[0].dxf).modelspace()
                     if e.dxftype() == "MTEXT")
    assert "Mystery part" in texts


def test_missing_dedup(tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    make_sheet(tmp_path / "b.dxf", name="Невідома деталь")
    r = run_job([tmp_path])
    m = [x for x in r.missing if "Невідома" in x.text]
    assert len(m) == 1 and sorted(m[0].files) == ["a.dxf", "b.dxf"]
    assert r.exit_code == 2


def test_progress_called(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    make_sheet(tmp_path / "b.dxf")
    calls = []
    run_job([tmp_path], progress=lambda d, t, n: calls.append((d, t, n)))
    assert len(calls) == 2 and calls[-1][0] == calls[-1][1] == 2


def test_no_dxf(tmp_path):
    with pytest.raises(ValueError, match="no DXF"):
        run_job([tmp_path])


def test_collect_skips_en_and_dedups(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    (tmp_path / "a_EN.dxf").write_bytes(b"")
    (tmp_path / "EN").mkdir()
    (tmp_path / "EN" / "x.dxf").write_bytes(b"")
    dxfs, _ = collect_inputs([tmp_path, tmp_path / "a.dxf"])
    assert [p.name for p in dxfs] == ["a.dxf"]
