"""Compare two directories of DXF files by text/entity signature.

Usage: python scripts/compare_dxf.py <dir_a> <dir_b>
Prints per-file differences, last line `DIFF FILES: N`; exit 0 iff N == 0.
"""
import sys
from collections import Counter
from pathlib import Path

import ezdxf


def _text_of(e):
    return e.text if e.dxftype() == "MTEXT" else e.dxf.text


def _height(e):
    if e.dxftype() == "MTEXT":
        return e.dxf.get("char_height", 0.0)
    return e.dxf.get("height", 0.0)


def text_signature(path: Path) -> list[tuple]:
    doc = ezdxf.readfile(str(path))
    sig: list[tuple] = []
    for layout in [doc.modelspace(), *[b for b in doc.blocks]]:
        name = layout.name
        for e in layout:
            if e.dxftype() in ("MTEXT", "TEXT"):
                p = e.dxf.insert
                sig.append((name, e.dxftype(), _text_of(e), round(p.x, 3),
                            round(p.y, 3), round(_height(e), 3)))
    for t, n in Counter(e.dxftype() for e in doc.modelspace()).items():
        sig.append(("ENTITY_COUNT", t, n))
    return sorted(sig, key=repr)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    a, b = Path(argv[1]), Path(argv[2])
    names = sorted({p.name for p in a.glob("*.[dD][xX][fF]")} | {p.name for p in b.glob("*.[dD][xX][fF]")})
    diffs = 0
    for n in names:
        pa, pb = a / n, b / n
        if not pa.exists() or not pb.exists():
            print(f"{n}: missing in {'A' if not pa.exists() else 'B'}")
            diffs += 1
            continue
        sa, sb = text_signature(pa), text_signature(pb)
        if sa != sb:
            diffs += 1
            ca, cb = Counter(sa), Counter(sb)
            print(f"{n}: differs")
            for x in list((ca - cb).elements())[:5]:
                print(f"  only A: {x}")
            for x in list((cb - ca).elements())[:5]:
                print(f"  only B: {x}")
    print(f"DIFF FILES: {diffs}")
    return 0 if diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
