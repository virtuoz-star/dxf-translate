"""UA -> EN glossary: YAML loading, merging and lookup."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

TABLES = ("phrases", "full_material", "bom_material", "notes")
SECTIONS = (*TABLES, "substr", "assembly_suffix")


class GlossaryError(Exception):
    """Problem with a glossary or Excel file; message names the file."""


def norm(s: str) -> str:
    """Compare texts ignoring line breaks (^J, \\P) and repeated spaces."""
    return re.sub(r"(\^J|\\P|\s)+", " ", s).strip()


@dataclass
class Glossary:
    phrases: dict[str, str]
    full_material: dict[str, str]
    bom_material: dict[str, str]
    notes: dict[str, str]
    substr: list[tuple[str, str]]
    assembly_suffix: str = ""
    parts: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    _index: dict = field(default_factory=dict, repr=False, compare=False)

    def lookup(self, table: str, text: str) -> str | None:
        if table not in TABLES:
            raise ValueError(f"unknown glossary table: {table}")
        d = getattr(self, table)
        # Rebuild whenever the dict content differs from the snapshot the index was built from.
        cached = self._index.get(table)
        if cached is None or cached[0] != d:
            cached = (dict(d), {norm(k): v for k, v in d.items()})   # later key wins
            self._index[table] = cached
        return cached[1].get(norm(text))

    def merge(self, other: "Glossary") -> None:
        for t in TABLES:
            getattr(self, t).update(getattr(other, t))
        self.parts.update(other.parts)
        have = {p[0] for p in self.substr}
        for pat, rep in other.substr:
            if pat not in have:
                self.substr.append((pat, rep))
                have.add(pat)
        if other.assembly_suffix:
            self.assembly_suffix = other.assembly_suffix


def _parse(path: Path) -> Glossary:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f"{path}, line {mark.line + 1}" if mark else str(path)
        raise GlossaryError(f"{where}: invalid YAML: {e}") from e
    except OSError as e:
        raise GlossaryError(f"{path}: cannot read: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise GlossaryError(f"{path}: top level must be a mapping")
    unknown = sorted(set(data) - set(SECTIONS))
    if unknown:
        raise GlossaryError(f"{path}: unknown section(s): {', '.join(map(str, unknown))}")
    kw: dict = {}
    for t in TABLES:
        v = data.get(t) or {}
        if not isinstance(v, dict):
            raise GlossaryError(f"{path}: section '{t}' must be a mapping")
        kw[t] = {str(k): str(x) for k, x in v.items()}
    sub = data.get("substr") or []
    try:
        kw["substr"] = [(str(a), str(b)) for a, b in sub]
    except (TypeError, ValueError) as e:
        raise GlossaryError(f"{path}: 'substr' must be a list of [regex, replacement]") from e
    for pat, _ in kw["substr"]:
        try:
            re.compile(pat)
        except re.error as e:
            raise GlossaryError(f"{path}: bad regex in 'substr': {pat!r}: {e}") from e
    kw["assembly_suffix"] = str(data.get("assembly_suffix") or "")
    return Glossary(**kw)


def load_file(path: Path) -> Glossary:
    return _parse(Path(path))


def load_base() -> Glossary:
    ref = resources.files("dxf_translate").joinpath("data/glossary.yaml")
    with resources.as_file(ref) as p:
        return _parse(p)


def load(order_dir: Path | None) -> Glossary:
    g = load_base()
    if order_dir is not None:
        f = Path(order_dir) / "glossary.yaml"
        if f.is_file():
            g.merge(load_file(f))
    return g


def save_terms(path: Path, terms: dict[str, dict[str, str]]) -> None:
    path = Path(path)
    data: dict = {}
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise GlossaryError(f"{path}: invalid YAML: {e}") from e
        except OSError as e:
            raise GlossaryError(f"{path}: cannot read: {e}") from e
        if not isinstance(data, dict):
            raise GlossaryError(f"{path}: top level must be a mapping")
    for section, entries in terms.items():
        if section not in TABLES:
            raise GlossaryError(f"{path}: cannot save to section '{section}'")
        data.setdefault(section, {}).update(entries)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=10000),
        encoding="utf-8",
    )
