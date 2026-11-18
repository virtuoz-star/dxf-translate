"""Command line: dxf-translate PATH... [--out DIR] [--no-review] [--overlaps-only]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dxf_translate.glossary import GlossaryError
from dxf_translate.pipeline import JobResult, check_overlaps_only, run_job

_WARN = {"no_excel": "!! no Excel production lists found: glossary comes from files only"}


def _print(res: JobResult) -> None:
    if res.excel:
        print(f"Excel glossary: {res.excel_pairs} UA->EN pairs from {res.excel[1].name}")
    for s in res.sheets:
        for line in s.report:
            print(line)
    for name, msg in res.failed:
        print(f"{name}: !! FAILED: {msg}")
    for w in res.warnings:
        print(_WARN.get(w, w))
    print_overlaps(res)


def print_overlaps(res: JobResult) -> None:
    for o in res.overlaps:
        print(f"{o.file}: '{o.text[:60]}' at ({o.x_mm:.0f}, {o.y_mm:.0f}) mm crosses {o.lines} line(s)")
    print(f"TOTAL new overlaps: {len(res.overlaps)}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dxf-translate", description="Translate SolidWorks DXF drawings UA -> EN")
    ap.add_argument("paths", nargs="+", type=Path, help="DXF/XLSX files or folders")
    ap.add_argument("--out", type=Path, help="output folder (default: <input folder>/EN)")
    ap.add_argument("--no-review", action="store_true", help="skip the HTML review page")
    ap.add_argument("--overlaps-only", action="store_true", help="only check existing output")
    a = ap.parse_args(argv)
    try:
        if a.overlaps_only:
            res = check_overlaps_only(a.paths, a.out)
            print_overlaps(res)
        else:
            res = run_job(a.paths, a.out, review=not a.no_review)
            _print(res)
            if res.review:
                print(f"Review: {res.review}")
    except (GlossaryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(res.exit_code)


if __name__ == "__main__":
    main()
