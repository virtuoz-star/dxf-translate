"""Synthetic SolidWorks-like sheets for tests (generated in tmp_path, never committed)."""
from __future__ import annotations

from pathlib import Path

import ezdxf


def make_sheet(
    path: Path,
    *,
    callout: str = "4 отв. Ø6",
    name: str = "Балка",
    material: str = "Лист 3 алюм.",
    notes: tuple[str, str] = ("*Розмір для довідок.", "Гострі крайки притупити."),
    width: int = 420,
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
    msp.add_mtext("AS1.001", dxfattribs={"insert": (tx, 50), "char_height": 7})
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

    doc.saveas(path)
    return path
