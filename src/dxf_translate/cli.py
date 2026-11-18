"""Command line: dxf-translate PATH... [--translations FILE] [--out DIR] [--no-review] [--overlaps-only]
or dxf-translate --crop PDF X Y (render the area around a reported point of a sheet)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dxf_translate.glossary import GlossaryError
from dxf_translate.pipeline import JobResult, check_overlaps_only, run_job

_WARN = {"no_excel": "!! no translation file given (--translations): glossary comes from files only"}


def _print(res: JobResult) -> None:
    if res.translations:
        print(f"Translation file: {res.translations.pairs} UA->EN pairs from {res.translations.path.name}")
    for s in res.sheets:
        for line in s.report:
            print(line)
    _print_failed(res)
    for w in res.warnings:
        print(_WARN.get(w, w))
    for ua, col, pn in res.translations.missing if res.translations else ():
        print(f"!! TRANSLATION FILE: fill {col} for {pn}: {ua}")
    print_overlaps(res)


def _print_failed(res: JobResult) -> None:
    for name, msg in res.failed:
        print(f"{name}: !! FAILED: {msg}")


def print_overlaps(res: JobResult) -> None:
    for o in res.overlaps:
        print(f"{o.file}: '{o.text[:60]}' at ({o.x_mm:.0f}, {o.y_mm:.0f}) mm crosses {o.lines} line(s)")
    print(f"TOTAL new overlaps: {len(res.overlaps)}")


def _overlaps_only(paths: list[Path], out: Path | None) -> JobResult:
    res = check_overlaps_only(paths, out)
    _print_failed(res)
    total = res.checked + len(res.skipped) + sum(1 for n, _ in res.failed if n != "--overlaps-only")
    print(f"checked {res.checked} of {total} sheet(s)")
    for name in res.skipped:
        print(f"{name}: !! SKIPPED: no {Path(name).stem}_EN.dxf in {res.out_dir / 'dxf'}")
    print_overlaps(res)
    return res


def _crop(pdf: Path, x: float, y: float) -> int:
    from dxf_translate.review import crop_point, review_crops_at

    if not pdf.is_file():
        print(f"error: {pdf}: no such PDF", file=sys.stderr)
        return 1
    for p in review_crops_at(pdf, x, y):
        print(f"review crop: {p}")
    print(f"point crop: {crop_point(pdf, x, y)}")
    return 0


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dxf-translate", description="Translate SolidWorks DXF drawings UA -> EN")
    ap.add_argument("paths", nargs="*", type=Path, help="DXF files or folders")
    ap.add_argument("--translations", type=Path, metavar="FILE",
                    help="the order's translation file (.xlsx with Позначення, Назва, Name, "
                         "Матеріал, Material columns)")
    ap.add_argument("--out", type=Path, help="output folder (default: <input folder>/EN)")
    ap.add_argument("--no-review", action="store_true", help="skip the HTML review page")
    ap.add_argument("--overlaps-only", action="store_true", help="only check existing output")
    ap.add_argument("--crop", nargs=3, metavar=("PDF", "X", "Y"),
                    help="render the area around (X, Y) sheet mm of an EN PDF to a PNG and "
                         "list the review crops that contain that point")
    a = ap.parse_args(argv)
    # Windows consoles/pipes default to a legacy code page (cp1252/cp866) that cannot
    # encode Cyrillic report lines; always emit UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if a.crop:
        try:
            x, y = float(a.crop[1].replace(",", ".")), float(a.crop[2].replace(",", "."))
            code = _crop(Path(a.crop[0]), x, y)
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            code = 1
        sys.exit(code)
    if not a.paths:
        ap.error("the following arguments are required: paths")
    try:
        if a.overlaps_only:
            res = _overlaps_only(a.paths, a.out)
        else:
            res = run_job(a.paths, a.out, review=not a.no_review, translations=a.translations)
            _print(res)
            if res.review:
                print(f"Review: {res.review}")
    except (GlossaryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(res.exit_code)


if __name__ == "__main__":
    main()
