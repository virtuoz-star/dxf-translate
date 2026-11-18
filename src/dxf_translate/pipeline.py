"""Batch job: collect inputs, build glossary, translate, check overlaps, build review."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from dxf_translate import glossary as glossary_mod
from dxf_translate.excel import TranslationFile, export_en, read_translations
from dxf_translate.overlaps import Overlap, find_overlaps
from dxf_translate.review import build_review
from dxf_translate.translate import SheetResult, translate_file

ProgressFn = Callable[[int, int, str], None]


class NoInputsError(ValueError):
    """No DXF files were found in the given paths."""


@dataclass
class MissingText:
    text: str
    kind: str
    files: list[str]
    hint: str = ""                 # kind "excel": "<column> · <part_no>"


@dataclass
class JobResult:
    out_dir: Path
    review: Path | None = None
    sheets: list[SheetResult] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    missing: list[MissingText] = field(default_factory=list)
    overlaps: list[Overlap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    translations: TranslationFile | None = None
    en_list: Path | None = None              # English production list written from the translation file
    order_dir: Path | None = None            # where the order glossary.yaml lives
    checked: int = 0                         # sheets the overlap check ran on
    skipped: list[str] = field(default_factory=list)   # --overlaps-only: no output to check

    @property
    def exit_code(self) -> int:
        if self.failed:
            return 1
        attention = (self.missing or self.overlaps or any(s.warnings for s in self.sheets)
                     or any(w.startswith(("en_list_failed:", "en_list_formula:")) for w in self.warnings))
        return 2 if attention else 0


@dataclass
class EnglishExport:
    """`export_english` result: the written file and what is still not English in it."""
    path: Path
    missing: list[tuple[str, str, str]]      # empty/Cyrillic Name or Material: (ua, column, part_no)
    untranslated: list[str]                  # other Cyrillic cells without a glossary translation
    problems: list[str]                      # formulas that referred to a dropped UA column

    @property
    def clean(self) -> bool:
        return not (self.missing or self.untranslated or self.problems)


def export_english(translations: Path, out_dir: Path | None = None,
                   order_dir: Path | None = None) -> EnglishExport:
    """English-only copy of the translation file for the customer, without any drawings:
    `<out_dir or file's folder>/<stem>_EN.xlsx`. Glossary = base + `<order_dir or file's
    folder>/glossary.yaml`. GlossaryError for an unreadable / non-translation file; any write
    error (file open in Excel) propagates."""
    translations = Path(translations)
    g = glossary_mod.load(order_dir if order_dir is not None else translations.parent)
    tf = read_translations(g, translations)
    path, untranslated, problems = export_en(tf, g, out_dir if out_dir is not None else translations.parent)
    return EnglishExport(path, tf.missing, untranslated, problems)


def collect_inputs(paths: list[Path]) -> list[Path]:
    """DXF inputs. Folders are scanned recursively, skipping sub-folders named EN
    (relative to the dropped folder), *_EN.dxf and ~$ files. Other files are ignored."""
    found: dict[Path, Path] = {}
    for raw in map(Path, paths):
        if raw.is_dir():
            cands = [p for p in sorted(raw.rglob("*")) if "EN" not in p.relative_to(raw).parts[:-1]]
        else:
            cands = [raw]
        for p in cands:
            if not p.is_file() or p.name.startswith("~$"):
                continue
            if p.suffix.lower() != ".dxf" or p.stem.endswith("_EN"):
                continue
            found.setdefault(p.resolve(), p)
    return sorted(found.values(), key=lambda p: p.name)


def default_out(paths: list[Path], dxfs: list[Path]) -> Path:
    """<first dropped folder>/EN, else <folder of first DXF>/EN."""
    for p in map(Path, paths):
        if p.is_dir():
            return p / "EN"
    return dxfs[0].parent / "EN"


def output_collisions(dxfs: list[Path], base: Path | None = None) -> dict[Path, str]:
    """Inputs whose `<stem>_EN` output name (case-insensitive, as on Windows) is shared with
    another input -> failure message naming the others. None of them is translated."""
    groups: dict[str, list[Path]] = {}
    for p in dxfs:
        groups.setdefault(f"{p.stem}_EN".casefold(), []).append(p)

    def show(p: Path) -> str:
        try:
            return p.relative_to(base).as_posix() if base else str(p)
        except ValueError:
            return str(p)

    out: dict[Path, str] = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        for p in group:
            others = ", ".join(show(o) for o in group if o is not p)
            out[p] = (f"output name collision: {show(p)} and {others} would both write "
                      f"{p.stem}_EN.dxf/.pdf; rename one or translate them separately")
    return out


def run_job(paths: list[Path], out_dir: Path | None = None,
            progress: ProgressFn | None = None, review: bool = True,
            translations: Path | None = None) -> JobResult:
    dxfs = collect_inputs(paths)
    if not dxfs:
        raise NoInputsError("no DXF files")
    order_dir = default_out(paths, dxfs).parent
    g = glossary_mod.load(order_dir)
    out = Path(out_dir) if out_dir else order_dir / "EN"
    res = JobResult(out_dir=out, order_dir=order_dir)
    if translations is None:
        res.warnings.append("no_excel")
    else:                                        # GlossaryError propagates before any work
        res.translations = read_translations(g, Path(translations))

    collide = output_collisions(dxfs, order_dir)
    miss: dict[tuple[str, str], MissingText] = {}
    for i, src in enumerate(dxfs, 1):
        if src in collide:
            res.failed.append((src.name, collide[src]))
            if progress:
                progress(i, len(dxfs), src.name)
            continue
        try:
            s = translate_file(src, out, g)
        except Exception as exc:
            res.failed.append((src.name, f"{type(exc).__name__}: {exc}"))
            if progress:
                progress(i, len(dxfs), src.name)
            continue
        res.sheets.append(s)
        res.warnings += [f"{src.name}: !! {w}" for w in s.warnings]
        for m in s.missing:
            e = miss.setdefault((m.text, m.kind), MissingText(m.text, m.kind, []))
            if src.name not in e.files:
                e.files.append(src.name)
        if progress:
            progress(i, len(dxfs), src.name)
    if res.translations:
        try:
            res.en_list, untranslated, problems = export_en(res.translations, g, out)
        except Exception as exc:                 # e.g. the old list is open in Excel
            res.warnings.append(f"en_list_failed: {type(exc).__name__}: {exc}")
        else:
            res.warnings += [f"en_list_formula: {p}" for p in problems]
            for text in untranslated:
                e = miss.setdefault((text, "phrase"), MissingText(text, "phrase", []))
                e.files.append(res.en_list.name)
    res.missing = [miss[k] for k in sorted(miss)]
    if res.translations and res.translations.missing:
        _merge_excel_missing(res)
    _check_overlaps(res, [(s.dxf, s.src) for s in res.sheets])
    if review and res.sheets:
        try:
            res.review = build_review(out, [s.dxf for s in res.sheets], warnings=res.warnings)
        except Exception as exc:
            res.review = None
            res.warnings.append(f"review failed: {type(exc).__name__}: {exc}")
    return res


_NO_TR = "   !! NO TRANSLATION: "


def _merge_excel_missing(res: JobResult) -> None:
    """Add the translation file's empty Name/Material cells as `excel` rows. A drawing text that
    is only missing because of such a cell is not reported again as a `phrase`: its files move to
    the `excel` row and it is removed from the sheets' missing lists and report lines, so the
    user fixes it in the translation file (one place) and not in the glossary."""
    excel = [MissingText(ua, "excel", [], f"{col} · {pn}") for ua, col, pn in res.translations.missing]
    by_text: dict[str, MissingText] = {}
    for e in excel:
        by_text.setdefault(e.text, e)
    kept = []
    for m in res.missing:
        e = by_text.get(m.text) if m.kind == "phrase" else None
        if e is None:
            kept.append(m)
        else:
            e.files += [f for f in m.files if f not in e.files]
    res.missing = kept + excel
    for s in res.sheets:
        s.missing = [m for m in s.missing if not (m.kind == "phrase" and m.text in by_text)]
        report = []
        for line in s.report:
            if line.startswith(_NO_TR):
                left = [k for k in line[len(_NO_TR):].split(" | ") if k not in by_text]
                if not left:
                    continue
                line = _NO_TR + " | ".join(left)
            report.append(line)
        s.report = report


def _check_overlaps(res: JobResult, pairs: list[tuple[Path, Path]]) -> None:
    for dxf, src in pairs:
        try:
            res.overlaps += find_overlaps(dxf, src)
            res.checked += 1
        except Exception as exc:
            res.failed.append((src.name, f"overlap check: {type(exc).__name__}: {exc}"))


def check_overlaps_only(paths: list[Path], out_dir: Path | None = None) -> JobResult:
    """Skip translation: check existing <out>/dxf/*_EN.dxf against their inputs."""
    dxfs = collect_inputs(paths)
    if not dxfs:
        raise NoInputsError("no DXF files")
    out = Path(out_dir) if out_dir else default_out(paths, dxfs)
    res = JobResult(out_dir=out)
    collide = output_collisions(dxfs, out.parent)
    pairs = []
    for s in dxfs:
        dxf = out / "dxf" / f"{s.stem}_EN.dxf"
        if s in collide:
            res.failed.append((s.name, collide[s]))
        elif dxf.is_file():
            pairs.append((dxf, s))
        else:
            res.skipped.append(s.name)
    _check_overlaps(res, pairs)
    if not res.checked and not res.failed:
        res.failed.append(("--overlaps-only", f"no translated sheet found in {out / 'dxf'}"))
    return res
