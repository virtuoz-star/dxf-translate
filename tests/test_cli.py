import subprocess
import sys

from fixtures import make_sheet


def run(*args):
    return subprocess.run([sys.executable, "-m", "dxf_translate.cli", *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_exit_codes(tmp_path):
    clean = tmp_path / "clean"; clean.mkdir()
    make_sheet(clean / "a.dxf")
    p = run(clean, "--no-review")
    assert p.returncode == 0, p.stderr
    assert "TOTAL new overlaps: 0" in p.stdout

    unk = tmp_path / "unk"; unk.mkdir()
    make_sheet(unk / "a.dxf", name="Невідома деталь")
    p = run(unk, "--no-review")
    assert p.returncode == 2
    assert "!! NO TRANSLATION" in p.stdout

    import openpyxl
    amb = tmp_path / "amb"; amb.mkdir()
    make_sheet(amb / "a.dxf")
    for n, v in (("1", "Балка"), ("2", "Деталь")):      # xlsx in the folder are ignored
        wb = openpyxl.Workbook(); wb.active["A1"] = v; wb.save(amb / f"{n}.xlsx")
    p = run(amb, "--no-review")
    assert p.returncode == 0, p.stderr
    assert "no translation file given" in p.stdout


def test_overlaps_only(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    first = run(tmp_path, "--no-review")
    assert first.returncode == 0, first.stdout + first.stderr
    p = run(tmp_path, "--overlaps-only")
    assert p.returncode == 0 and "TOTAL new overlaps: 0" in p.stdout
    assert "checked 1 of 1 sheet(s)" in p.stdout


def test_overlaps_only_nothing_checked(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    make_sheet(tmp_path / "b.dxf")
    p = run(tmp_path, "--overlaps-only")
    assert p.returncode == 1
    assert "checked 0 of 2 sheet(s)" in p.stdout and "a.dxf: !! SKIPPED" in p.stdout
    run(tmp_path / "a.dxf", "--out", tmp_path / "EN", "--no-review")
    p = run(tmp_path, "--overlaps-only")
    assert p.returncode == 0, p.stdout
    assert "checked 1 of 2 sheet(s)" in p.stdout and "b.dxf: !! SKIPPED" in p.stdout


def test_crop_flag(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    assert run(tmp_path).returncode == 0
    pdf = tmp_path / "EN" / "pdf" / "a_EN.pdf"
    p = run("--crop", pdf, "130", "211,5")
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    point = [l for l in lines if l.startswith("point crop: ")]
    assert len(point) == 1 and (tmp_path / "EN" / "review" / "points").is_dir()
    from pathlib import Path
    assert Path(point[0].split(": ", 1)[1]).is_file()
    assert any(l.startswith("review crop: ") for l in lines)
    assert run("--crop", tmp_path / "nope.pdf", "1", "1").returncode == 1
    assert run("--crop", pdf, "x", "1").returncode == 1
    assert run().returncode == 2                        # argparse: paths required


def test_cli_malformed_order_glossary(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    (tmp_path / "glossary.yaml").write_text("phrases: [unclosed\n", encoding="utf-8")
    p = run(tmp_path, "--no-review")
    assert p.returncode == 1
    assert "glossary.yaml" in p.stderr and "Traceback" not in p.stderr


def test_cli_empty_name_only_translation_file_line(tmp_path):
    import openpyxl
    make_sheet(tmp_path / "a.dxf", part_no="AS1.009", name="Кришка")
    wb = openpyxl.Workbook()
    for r in (["Позначення", "Назва", "Name", "Матеріал", "Material"],
              ["AS1.009", "Кришка", None, "Лист 3 алюм.", "Sheet 3 Al"]):
        wb.active.append(r)
    wb.save(tmp_path / "t.xlsx")
    p = run(tmp_path, "--no-review", "--translations", tmp_path / "t.xlsx")
    assert p.returncode == 2, p.stdout + p.stderr
    assert "!! TRANSLATION FILE: fill Name for AS1.009: Кришка" in p.stdout
    assert "!! NO TRANSLATION" not in p.stdout, p.stdout
