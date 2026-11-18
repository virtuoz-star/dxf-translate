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
    for n, v in (("1", "Балка"), ("2", "Деталь")):
        wb = openpyxl.Workbook(); wb.active["A1"] = v; wb.save(amb / f"{n}.xlsx")
    p = run(amb)
    assert p.returncode == 1
    assert "ambiguous" in p.stderr


def test_overlaps_only(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    run(tmp_path, "--no-review")
    p = run(tmp_path, "--overlaps-only")
    assert p.returncode == 0 and "TOTAL new overlaps: 0" in p.stdout


def test_cli_malformed_order_glossary(tmp_path):
    make_sheet(tmp_path / "a.dxf")
    (tmp_path / "glossary.yaml").write_text("phrases: [unclosed\n", encoding="utf-8")
    p = run(tmp_path, "--no-review")
    assert p.returncode == 1
    assert "glossary.yaml" in p.stderr and "Traceback" not in p.stderr
