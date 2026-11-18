"""Batch job: collect inputs, build glossary, translate, check overlaps, build review."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dxf_translate import glossary as glossary_mod
from dxf_translate.excel import add_excel_pairs, pick_pair
from dxf_translate.overlaps import Overlap, find_overlaps
from dxf_translate.review import build_review
from dxf_translate.translate import SheetResult, translate_file

ProgressFn = Callable[[int, int, str], None]


@dataclass
class MissingText:
    text: str
    kind: str
    files: list[str]


@dataclass
class JobResult:
    out_dir: Path
    review: Path | None = None
    sheets: list[SheetResult] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    missing: list[MissingText] = field(default_factory=list)
    overlaps: list[Overlap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    excel: tuple[Path, Path] | None = None
    excel_pairs: int = 0

    @property
    def exit_code(self) -> int:
        if self.failed:
            return 1
        return 2 if self.missing or self.overlaps else 0


def _skip(p: Path) -> bool:
    return p.stem.endswith("_EN") or "EN" in p.parent.parts


def collect_inputs(paths: list[Path]) -> tuple[list[Path], list[Path]]:
    """Split inputs into (dxfs, xlsxs); folders are not scanned recursively."""
    found: dict[Path, Path] = {}
    for raw in map(Path, paths):
        cands = sorted(raw.iterdir()) if raw.is_dir() else [raw]
        for p in cands:
            if not p.is_file() or p.name.startswith("~$"):
                continue
            ext = p.suffix.lower()
            if ext not in (".dxf", ".xlsx"):
                continue
            if ext == ".dxf" and _skip(p.resolve()):
                continue
            found.setdefault(p.resolve(), p)
    dxfs = sorted((p for p in found.values() if p.suffix.lower() == ".dxf"), key=lambda p: p.name)
    xlsx = sorted((p for p in found.values() if p.suffix.lower() == ".xlsx"), key=lambda p: p.name)
    return dxfs, xlsx


def run_job(paths: list[Path], out_dir: Path | None = None,
            progress: ProgressFn | None = None, review: bool = True) -> JobResult:
    dxfs, xlsx = collect_inputs(paths)
    if not dxfs:
        raise ValueError("no DXF files")
    pair = pick_pair(xlsx)                       # GlossaryError propagates before any work
    order_dir = dxfs[0].parent
    g = glossary_mod.load(order_dir)
    out = Path(out_dir) if out_dir else order_dir / "EN"
    res = JobResult(out_dir=out, excel=pair)
    if pair is None:
        res.warnings.append("no_excel")
    else:
        res.excel_pairs = add_excel_pairs(g, *pair, warnings=res.warnings)

    miss: dict[tuple[str, str], MissingText] = {}
    for i, src in enumerate(dxfs, 1):
        try:
            s = translate_file(src, out, g)
        except Exception as exc:
            res.failed.append((src.name, f"{type(exc).__name__}: {exc}"))
            if progress:
                progress(i, len(dxfs), src.name)
            continue
        res.sheets.append(s)
        for m in s.missing:
            e = miss.setdefault((m.text, m.kind), MissingText(m.text, m.kind, []))
            if src.name not in e.files:
                e.files.append(src.name)
        if progress:
            progress(i, len(dxfs), src.name)
    res.missing = [miss[k] for k in sorted(miss)]
    for s in res.sheets:
        res.overlaps += find_overlaps(s.dxf, s.src)
    if review and res.sheets:
        res.review = build_review(out)
    return res


def check_overlaps_only(paths: list[Path], out_dir: Path | None = None) -> JobResult:
    """Skip translation: check existing <out>/dxf/*_EN.dxf against their inputs."""
    dxfs, _ = collect_inputs(paths)
    if not dxfs:
        raise ValueError("no DXF files")
    out = Path(out_dir) if out_dir else dxfs[0].parent / "EN"
    res = JobResult(out_dir=out)
    for src in dxfs:
        d = out / "dxf" / f"{src.stem}_EN.dxf"
        if d.is_file():
            res.overlaps += find_overlaps(d, src)
    return res
