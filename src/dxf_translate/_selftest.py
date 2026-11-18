"""Synthetic SolidWorks-like sheet (shared with tests) and the `--selftest` smoke run.

`--selftest` proves a build (e.g. the frozen Windows exe) can translate a drawing end to end:
bundled fonts, base glossary, DXF writing, PDF rendering and the review page.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import ezdxf

def make_sheet(
    path: Path,
    *,
    callout: str = "4 отв. Ø6",
    part_no: str = "AS1.001",
    name: str = "Балка",
    material: str = "Лист 3 алюм.",
    notes: tuple[str, str] = ("*Розмір для довідок.", "Гострі крайки притупити."),
    width: int = 420,
    extra_line: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> Path:
    doc = ezdxf.new("R2010")
    doc.header["$LIMMIN"] = (0, 0)
    doc.header["$LIMMAX"] = (width, 297)
    doc.layers.add("FRAME")
    msp = doc.modelspace()
    msp.dxf.limmin = (0, 0)              # ezdxf writes $LIMMIN/$LIMMAX from the layout
    msp.dxf.limmax = (width, 297)

    # 1. frame lines first: border + title block
    fa = {"layer": "FRAME"}
    x0, x1, y0, y1 = 20, width - 5, 5, 292
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                 ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        msp.add_line(a, b, dxfattribs=fa)
    tb_x0 = 229 if width == 420 else 17
    msp.add_line((tb_x0, 5), (tb_x0, 61), dxfattribs=fa)
    msp.add_line((tb_x0, 61), (x1, 61), dxfattribs=fa)
    msp.add_line((tb_x0, 30), (x1, 30), dxfattribs=fa)

    # 2. title-block texts right after the frame lines
    tx = width - 120
    msp.add_mtext(part_no, dxfattribs={"insert": (tx, 50), "char_height": 7})
    msp.add_mtext(name, dxfattribs={"insert": (tx, 40), "char_height": 7})
    msp.add_mtext(material, dxfattribs={"insert": (tx, 20), "char_height": 3.5})

    # 3. notes, part outline, callout with shelf
    msp.add_mtext(f"1.^J{notes[0]}^J2.^J{notes[1]}",
                  dxfattribs={"insert": (40, 120), "char_height": 3.5})
    for a, b in (((100, 100), (200, 100)), ((200, 100), (200, 200)),
                 ((200, 200), (100, 200)), ((100, 200), (100, 100))):
        msp.add_line(a, b, dxfattribs={"layer": "0"})
    msp.add_mtext(callout, dxfattribs={"insert": (120, 210), "char_height": 3.5,
                                       "attachment_point": 7})
    msp.add_line((120, 210), (140, 210), dxfattribs={"layer": "0"})

    if extra_line:
        msp.add_line(*extra_line, dxfattribs={"layer": "0"})

    doc.saveas(path)
    return path


def run() -> tuple[int, str]:
    """Translate one generated sheet in a temp dir; return (exit code, message)."""
    from dxf_translate.pipeline import run_job

    with tempfile.TemporaryDirectory(prefix="dxf-translate-selftest-",
                                     ignore_cleanup_errors=True) as tmp:
        order = Path(tmp) / "order"
        order.mkdir()
        make_sheet(order / "AS1.001.dxf")
        try:
            res = run_job([order])
        except Exception as exc:
            return 1, f"selftest FAILED: {type(exc).__name__}: {exc}"
        if res.failed:
            return 1, "selftest FAILED: " + "; ".join(f"{n}: {e}" for n, e in res.failed)
        if len(res.sheets) != 1:
            return 1, f"selftest FAILED: {len(res.sheets)} sheets translated, expected 1"
        s = res.sheets[0]
        if not (s.dxf.is_file() and s.pdf.is_file() and s.pdf.stat().st_size > 0):
            return 1, "selftest FAILED: output DXF/PDF missing"
        if res.review is None:
            return 1, "selftest FAILED: " + ("; ".join(res.warnings) or "no review page")
        return 0, f"selftest OK: 1 sheet translated ({s.pdf.name})"


def main() -> int:
    code, msg = run()
    if sys.stdout is not None:          # windowed exe without redirection: stdout is None
        print(msg, flush=True)
    return code
