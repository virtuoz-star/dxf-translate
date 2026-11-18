import pytest

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


def test_order_glossary_used(tmp_path):
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    (tmp_path / "glossary.yaml").write_text(
        'phrases:\n  "Невідома деталь": "Mystery part"\n', encoding="utf-8")
    r = run_job([tmp_path])
    assert not r.missing
    assert r.order_dir == tmp_path
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
    dxfs = collect_inputs([tmp_path, tmp_path / "a.dxf"])
    assert [p.name for p in dxfs] == ["a.dxf"]


def test_order_root_recursive(tmp_path):
    (tmp_path / "dxf").mkdir()
    make_sheet(tmp_path / "dxf" / "a.dxf")
    _xlsx(tmp_path / "ua.xlsx", "Балка")               # ignored: not given explicitly
    r = run_job([tmp_path], review=False)
    assert r.out_dir == tmp_path / "EN" and len(r.sheets) == 1 and r.translations is None
    assert run_job([tmp_path], review=False).sheets.__len__() == 1   # rerun skips EN/


def test_order_under_EN_parent(tmp_path):
    root = tmp_path / "EN" / "order"
    (root / "dxf").mkdir(parents=True)
    make_sheet(root / "dxf" / "a.dxf")
    r = run_job([root], review=False)
    assert len(r.sheets) == 1 and r.out_dir == root / "EN"


def test_overlap_and_review_failures_do_not_abort(tmp_path, monkeypatch):
    import dxf_translate.pipeline as pl
    make_sheet(tmp_path / "a.dxf", name="Невідома деталь")
    monkeypatch.setattr(pl, "find_overlaps", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(pl, "build_review", lambda *a: (_ for _ in ()).throw(RuntimeError("bang")))
    r = pl.run_job([tmp_path])
    assert len(r.sheets) == 1 and r.missing and r.review is None
    assert any("overlap check: RuntimeError" in m for _, m in r.failed)
    assert any("review failed" in w for w in r.warnings)
    assert r.exit_code == 1


def test_output_name_collision_fails_whole_group(tmp_path):
    (tmp_path / "old").mkdir(); (tmp_path / "new").mkdir()
    make_sheet(tmp_path / "old" / "AS1.001.dxf")
    make_sheet(tmp_path / "new" / "as1.001.DXF")           # same output name on Windows
    make_sheet(tmp_path / "AS1.002.dxf")
    r = run_job([tmp_path], review=False)
    assert [s.src.name for s in r.sheets] == ["AS1.002.dxf"]
    assert len(r.failed) == 2 and r.exit_code == 1
    msgs = dict((m.split(" and ")[0], m) for _, m in r.failed)
    assert all("output name collision" in m for m in msgs.values())
    assert any("old/AS1.001.dxf" in m and "new/as1.001.DXF" in m for m in msgs.values())
    assert sorted(p.name for p in (r.out_dir / "dxf").iterdir()) == ["AS1.002_EN.dxf"]


def test_title_block_warning_reaches_job_and_exit_2(tmp_path):
    make_sheet(tmp_path / "x.dxf", part_no="BK1.001")
    r = run_job([tmp_path], review=False)
    assert not r.missing and not r.overlaps and not r.failed
    assert any(w.startswith("x.dxf: !! title block: Part No. not found") for w in r.warnings)
    assert r.exit_code == 2
    (tmp_path / "glossary.yaml").write_text('part_no_pattern: "^BK"\n', encoding="utf-8")
    r = run_job([tmp_path], review=False)
    assert r.sheets[0].part_no == "BK1.001" and r.exit_code == 0


def test_review_only_this_runs_sheets(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    out = tmp_path / "EN"
    (out / "dxf").mkdir(parents=True)
    make_sheet(out / "dxf" / "stale_EN.dxf")                 # old output without PDF
    r = run_job([tmp_path / "a.dxf"], out_dir=out)
    assert r.review is not None
    import json
    meta = json.loads((out / "review" / "meta.json").read_text(encoding="utf-8"))
    assert [m["sheet"] for m in meta] == ["a_EN"]


def test_check_overlaps_only_reports_skipped(tmp_path):
    from dxf_translate.pipeline import check_overlaps_only
    make_sheet(tmp_path / "a.dxf")
    make_sheet(tmp_path / "b.dxf")
    r = check_overlaps_only([tmp_path])
    assert r.checked == 0 and sorted(r.skipped) == ["a.dxf", "b.dxf"] and r.exit_code == 1
    run_job([tmp_path / "a.dxf"], out_dir=tmp_path / "EN", review=False)
    r = check_overlaps_only([tmp_path])
    assert r.checked == 1 and r.skipped == ["b.dxf"] and r.exit_code == 0
